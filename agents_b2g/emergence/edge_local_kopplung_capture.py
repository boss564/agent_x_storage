#!/usr/bin/env python3
"""Edge-local coupling capture — EDGE_LOCAL_KOPPLUNG_v0 (BINDEND).

φ_L + R_ij · h↔ = ½(h_ij+h_ji) · Arm B: true M · Arm C: delivery M, signal π(M).
F1 η=1.0 · F4 trimmed_m7 · F5 ACK/Receipt · reciprocity gate ≥0.3
docs/EDGE_LOCAL_KOPPLUNG_v0_PREREG.md
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from partner_select import StickySelector, permute_sticky_map
from coupling import init_timing, update_sender_interval, should_act_this_cycle
from measure import SwarmTrace
from kanten_ledger import (
    LedgerBook,
    screen_ledger_component,
    LATENCY_MODE_M7_TRIM,
)
from response_rij import AgentP, assign_p, signal_slope_probe

COMP_AVG_LATENCY = 3
EPS = 1e-9
ETA = 1.0  # F1 BINDEND
RECIP_MIN = 0.3
EdgeKey = Tuple[str, str]


def _setup_swarm(run_seed: int, dpc, orch):
    from agents_b2g.protocol import TickController

    agents = []
    for p in dpc.PROVIDER_PROFILES:
        agents.append(dpc.create_agent(p, "provider", orch))
    for p in dpc.EVALUATOR_PROFILES:
        agents.append(dpc.create_agent(p, "evaluator", orch))
    for p in dpc.ECONOMIC_PROFILES:
        agents.append(dpc.create_agent(p, "economic", orch))
    tc = TickController(seed=int(run_seed))
    for a in agents:
        tc.register(a)
        init_timing(a, base_interval=1.0, run_seed=int(run_seed))
    providers = [a for a in agents if isinstance(a, dpc.ProviderAgent)]
    evaluators = [a for a in agents if isinstance(a, dpc.EvaluatorAgent)]
    economics = [a for a in agents if isinstance(a, dpc.EconomicAgent)]
    return tc, agents, providers, evaluators, economics


def _signed_net(content) -> float:
    if not isinstance(content, dict):
        return 0.0
    for key in ("signed_net", "net_amount", "gross_amount", "amount", "volume"):
        if key in content:
            try:
                return float(content[key])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _r_ij(ell: float, gamma: float, p: AgentP, sigma: float) -> float:
    return float(p.a * (1.0 + float(gamma)) * (float(ell) - p.b(sigma)))


def _reciprocity_stats(frozen_map, ledger) -> Dict[str, Any]:
    sticky_pairs = []
    for (sk, _role), pid in (frozen_map or {}).items():
        sid = sk.split(":")[0]
        sticky_pairs.append((sid, pid))
    if not sticky_pairs:
        return {
            "n_sticky": 0,
            "frac_sticky_via_ledger": 0.0,
            "n_reciprocal_sticky_via_ledger": 0,
        }
    n_rec_l = 0
    for (i, j) in sticky_pairs:
        e = ledger.get(j, i)
        if e is not None and e.ever_updated:
            n_rec_l += 1
    return {
        "n_sticky": len(sticky_pairs),
        "n_reciprocal_sticky_via_ledger": n_rec_l,
        "frac_sticky_via_ledger": round(n_rec_l / len(sticky_pairs), 6),
    }


def capture_edge_local_coupling(
    *,
    cycles: int = 512,
    warmup_ticks: int = 32,
    run_seed: int = 20261801,
    kappa: float = 0.0,
    arm: str = "B",
) -> Dict[str, Any]:
    """Return {trace, precondition, battery, reciprocity, arm, kappa, eta}."""
    from agents_b2g.protocol import PayloadType
    from agents_b2g.finale.finale_orchestrator import FinaleOrchestrator
    from agents_b2g.finale.subagents.audit_trail import AuditTrailAgent

    arm = str(arm).upper()
    if arm not in {"A", "B", "C"}:
        raise ValueError(arm)
    kappa_run = 0.0 if arm == "A" else float(kappa)
    interval_on = kappa_run > 0.0

    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import demo_producer_cluster as dpc

    tmp_root = Path(
        os.environ.get(
            "EMERGENCE_FINALE_ROOT",
            str(Path(os.environ.get("TMPDIR", "/tmp")) / "emergence_finale_edge_local"),
        )
    )
    orch = FinaleOrchestrator(
        user_id="emergence-edge-local",
        data_root=str(tmp_root / "finale"),
    )
    orch.audit = AuditTrailAgent(
        user_id="emergence-edge-local",
        data_root=str(tmp_root / "audit"),
    )

    tc, agents, providers, evaluators, economics = _setup_swarm(run_seed, dpc, orch)
    by_id = {a.id: a for a in agents}
    p_of = assign_p([a.id for a in agents])
    recv_load = {a.id: 0 for a in agents}
    sticky = StickySelector(threshold=8)
    ledger = LedgerBook(gamma=0.05, latency_mode=LATENCY_MODE_M7_TRIM, trust_settlement_only=False)  # Vorher-M9
    coupling_edge: Dict[str, str] = {}
    signal_partner: Dict[str, str] = {}
    gamma_book: Dict[EdgeKey, float] = {}
    pending_eval: Dict[str, list] = {a.id: [] for a in evaluators}
    pending_econ: Dict[str, list] = {a.id: [] for a in economics}
    last_edge_tick: Dict[EdgeKey, int] = {}
    rule_default = dpc.rule_default
    EVALUATOR_RULES = dpc.EVALUATOR_RULES
    frozen_map = None
    map_c = None
    msg_log: List[Tuple[int, str, str]] = []
    sigma = 0.0
    eta = ETA
    ell_hist: List[Dict[EdgeKey, float]] = []
    r_hist: List[Dict[EdgeKey, float]] = []
    snapshots: List[List[Dict[str, float]]] = []

    def _load(a):
        return recv_load.get(a.id, 0) + len(a.inbox)

    def _latency(sender: str, receiver: str, tick: int) -> float:
        key = (sender, receiver)
        prev = last_edge_tick.get(key)
        last_edge_tick[key] = int(tick)
        if prev is None:
            return 1.0
        return float(max(1.0, int(tick) - int(prev)))

    def sync_signal_map(m_b, m_pi) -> None:
        signal_partner.clear()
        src = m_pi if (arm == "C" and m_pi is not None) else m_b
        if not src:
            return
        for (sk, _role), pid in src.items():
            signal_partner[sk.split(":")[0]] = pid

    def compute_r_snapshot() -> Dict[EdgeKey, float]:
        snap: Dict[EdgeKey, float] = {}
        for (i, j), e in ledger._edges.items():
            if not e.ever_updated:
                continue
            p = p_of.get(i)
            if p is None:
                continue
            ell = e.component(COMP_AVG_LATENCY)
            gij = gamma_book.get((i, j), 0.0)
            snap[(i, j)] = _r_ij(ell, gij, p, sigma if sigma > 0 else 1.0)
        return snap

    def update_gammas_from_r(r_snap: Dict[EdgeKey, float]) -> None:
        by_sender: Dict[str, List[float]] = {}
        for (i, _j), r in r_snap.items():
            by_sender.setdefault(i, []).append(r)
        means = {i: sum(vs) / len(vs) for i, vs in by_sender.items() if vs}
        for (i, j), r in r_snap.items():
            delta = r - means.get(i, r)
            g0 = gamma_book.get((i, j), 0.0)
            gamma_book[(i, j)] = math.tanh(g0 + eta * delta)

    def _h_from_r(r: float) -> float:
        return float(max(0.0, min(1.0, abs(r) / (abs(r) + 1.0))))

    def h_directed(i: str, j: str) -> float:
        p = p_of.get(i)
        if p is None:
            return 0.0
        ell = ledger.component(i, j, COMP_AVG_LATENCY)
        gij = gamma_book.get((i, j), 0.0)
        r = _r_ij(ell, gij, p, sigma if sigma > 0 else 1.0)
        return _h_from_r(r)

    def h_mutual(ag_id: str) -> float:
        """h↔ = ½(h_ij + h_ji); missing reverse → h_ij only (reciprocity_thin)."""
        pid = signal_partner.get(ag_id) or coupling_edge.get(ag_id)
        if pid is None:
            return 0.0
        hij = h_directed(ag_id, pid)
        ej = ledger.get(pid, ag_id)
        if ej is None or not ej.ever_updated:
            return hij
        hji = h_directed(pid, ag_id)
        return 0.5 * (hij + hji)

    def deliver(msg):
        if msg.receiver == "evaluator":
            if not evaluators:
                return
            partner = sticky.select(msg.sender, "evaluator", evaluators, _load)
            coupling_edge[msg.sender] = partner.id
            msg_log.append((tc.cycle, msg.sender, partner.id))
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            pending_eval[partner.id].append((msg.sender, msg.content))
        elif msg.receiver == "economic":
            if not economics:
                return
            partner = sticky.select(
                f"{msg.sender}:{msg.content.get('contract_id', '')}",
                "economic",
                economics,
                _load,
            )
            coupling_edge[msg.sender] = partner.id
            msg_log.append((tc.cycle, msg.sender, partner.id))
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            if msg.payload_type == PayloadType.BHO_PROOF:
                pending_econ[partner.id].append((msg.sender, msg.content))
        elif msg.receiver == "broadcast":
            if not providers:
                return
            partner = sticky.select(
                msg.sender, "broadcast→provider", providers, _load,
            )
            coupling_edge[msg.sender] = partner.id
            msg_log.append((tc.cycle, msg.sender, partner.id))
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            tick = int(tc.cycle)
            ledger.update(
                msg.sender, partner.id, tick,
                success=True, signed_net=_signed_net(msg.content),
                latency=_latency(msg.sender, partner.id, tick),
            )
        else:
            for ag in agents:
                if ag.id == msg.receiver:
                    if msg.payload_type == PayloadType.RECEIPT:
                        sticky.select(
                            msg.sender, f"receipt:{ag.id}", [ag], _load,
                        )
                    coupling_edge[msg.sender] = ag.id
                    msg_log.append((tc.cycle, msg.sender, ag.id))
                    ag.receive(msg)
                    recv_load[ag.id] = recv_load.get(ag.id, 0) + 1
                    tick = int(tc.cycle)
                    ledger.update(
                        msg.sender, ag.id, tick,
                        success=True, signed_net=_signed_net(msg.content),
                        latency=_latency(msg.sender, ag.id, tick),
                    )

    def flush_ledger(tick: int) -> None:
        for ev in evaluators:
            batch = pending_eval[ev.id]
            pending_eval[ev.id] = []
            rule = EVALUATOR_RULES.get(ev.id, rule_default)
            for sender, content in batch:
                holds = False
                if isinstance(content, dict):
                    holds = bool(
                        rule(
                            content.get("net_amount", 0),
                            content.get("tax_amount", 0),
                            content.get("retention_amount", 0),
                            content.get("gross_amount", 0),
                            bool(content.get("inflated", False)),
                            content.get("contract_id", ""),
                        )
                    )
                ledger.update(
                    sender, ev.id, tick, success=holds,
                    signed_net=_signed_net(content),
                    latency=_latency(sender, ev.id, tick),
                )
        for ec in economics:
            batch = pending_econ[ec.id]
            pending_econ[ec.id] = []
            for sender, content in batch:
                ledger.update(
                    sender, ec.id, tick, success=True,
                    signed_net=_signed_net(content),
                    latency=_latency(sender, ec.id, tick),
                )

    def freeze_sigma(m_b) -> float:
        vals = []
        for (sk, _role), pid in (m_b or {}).items():
            sid = sk.split(":")[0]
            vals.append(ledger.component(sid, pid, COMP_AVG_LATENCY))
        if len(vals) < 2:
            return 0.0
        mean = sum(vals) / len(vals)
        return math.sqrt(sum((x - mean) ** 2 for x in vals) / (len(vals) - 1))

    def numeric_state(a):
        out = {}
        skip = {
            "id", "cycle", "fee_rate", "base_interval", "effective_interval",
            "inbox_capacity", "last_transaction_time",
        }
        for k, v in vars(a).items():
            if k.startswith("_") or k in skip:
                continue
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                out[k] = float(v)
        out["inbox_len"] = float(len(getattr(a, "inbox", [])))
        out["phase"] = float(getattr(a, "phase", 0.0))
        out["h_mutual"] = float(h_mutual(a.id))
        if interval_on:
            out["effective_interval"] = float(getattr(a, "effective_interval", 1.0))
        return out

    warmup = max(0, int(warmup_ticks))
    total = warmup + int(cycles)

    for _ in range(total):
        tc.cycle += 1
        tick = int(tc.cycle)
        ledger.decay_all(tick)
        env = {
            "cycle": tick,
            "agent_count": len(agents),
            "kappa": kappa_run,
            "arm": arm,
        }
        for ag in agents:
            if interval_on:
                partner = by_id.get(coupling_edge.get(ag.id))
                update_sender_interval(
                    ag,
                    partner,
                    kappa_run,
                    t_now=float(tick),
                    partner_s_honor=h_mutual(ag.id),
                )
                if not should_act_this_cycle(ag):
                    continue
            ag.tick(env)
            if ag.outbox:
                ag.last_transaction_time = float(tick)

        out = []
        for ag in agents:
            out.extend(ag.outbox)
            ag.outbox.clear()
        for msg in out:
            deliver(msg)
        flush_ledger(tick)

        if warmup > 0 and tick == warmup:
            frozen_map = sticky.freeze()
            map_c = permute_sticky_map(frozen_map, seed=int(run_seed))
            sync_signal_map(frozen_map, map_c)
            sigma = freeze_sigma(frozen_map)
            gamma_book.clear()
            ledger.reset_window_flags()

        if tick > warmup:
            r_snap = compute_r_snapshot()
            update_gammas_from_r(r_snap)
            ell_hist.append(ledger.snapshot_component(COMP_AVG_LATENCY))
            r_hist.append(dict(r_snap))
            snapshots.append([numeric_state(a) for a in agents])

    if frozen_map is None:
        frozen_map = sticky.freeze()
        map_c = permute_sticky_map(frozen_map, seed=int(run_seed))
        sync_signal_map(frozen_map, map_c)
        sigma = freeze_sigma(frozen_map)

    keys = sorted({k for snap in snapshots for st in snap for k in st})
    if not keys:
        raise RuntimeError("no numeric state")
    T, N, D = len(snapshots), len(agents), len(keys)
    states = np.zeros((T, N, D))
    for t, snap in enumerate(snapshots):
        for i, st in enumerate(snap):
            for d, k in enumerate(keys):
                v = st.get(k, 0)
                states[t, i, d] = float(v) if isinstance(v, (int, float)) else 0.0

    msg_measure = [(t, s, r) for (t, s, r) in msg_log if t > warmup]
    tr = SwarmTrace([a.id for a in agents], states, msg_measure)
    tr.state_keys = keys
    tr.kappa = kappa_run
    tr.arm = arm
    tr.run_seed = int(run_seed)
    tr.warmup_ticks = warmup
    tr.frozen_map = frozen_map
    tr.shuffled_map = map_c

    layer_a_raw = screen_ledger_component(
        sticky_map_b=frozen_map or {},
        sticky_map_c=map_c or {},
        edge_hist=r_hist,
        component="R_ij",
        mae_min=0.05,
        rho_max=0.90,
    )
    mae_raw = float(layer_a_raw.get("mae") or 0.0)
    r_vals: List[float] = []
    if r_hist and frozen_map:
        last = r_hist[-1]
        for (sk, _role), pid in frozen_map.items():
            sid = sk.split(":")[0]
            r_vals.append(float(last.get((sid, pid), 0.0)))
    if len(r_vals) >= 2:
        mean_r = sum(r_vals) / len(r_vals)
        sigma_r = math.sqrt(
            sum((x - mean_r) ** 2 for x in r_vals) / (len(r_vals) - 1)
        )
    else:
        sigma_r = 1.0
    mae_norm = mae_raw / (sigma_r + EPS)
    n_corr = int(layer_a_raw.get("n_corr") or 0)
    med_rho = layer_a_raw.get("median_abs_rho")
    flag_a = bool(
        n_corr >= 14 and med_rho is not None and float(med_rho) <= 0.90
    )
    flag_b = bool(mae_norm >= 0.05)
    layer_c = signal_slope_probe(
        sticky_map_b=frozen_map or {},
        sticky_map_c=map_c or {},
        ell_hist=ell_hist,
        sigma=sigma if sigma > 0 else 1.0,
        p_of=p_of,
        formula="sensitivity_gamma_v02",
    )
    flag_c = bool(layer_c.get("pass"))
    recip = _reciprocity_stats(frozen_map or {}, ledger)
    frac_recip = float(recip.get("frac_sticky_via_ledger") or 0.0)
    flag_recip = bool(frac_recip >= RECIP_MIN)

    battery_ok = bool(flag_a and flag_b and flag_c)
    intact = bool(battery_ok and flag_recip)
    if not flag_recip and battery_ok:
        precon_label = "RECIPROCITY_LOST"
    elif not battery_ok:
        precon_label = "PRECONDITION_LOST"
    else:
        precon_label = "INTACT"

    battery = {
        "A": {
            "pass": flag_a,
            "median_abs_rho": med_rho,
            "n_corr": n_corr,
        },
        "B": {
            "pass": flag_b,
            "mae_raw": round(mae_raw, 6),
            "mae_norm": round(mae_norm, 6),
            "sigma_r": round(sigma_r, 6),
        },
        "C": {
            "pass": flag_c,
            "mean_abs_diff": layer_c.get("mean_abs_diff"),
        },
    }

    return {
        "trace": tr,
        "arm": arm,
        "kappa": float(kappa),
        "kappa_run": kappa_run,
        "run_seed": int(run_seed),
        "eta": eta,
        "sigma_ell": sigma,
        "latency_mode": LATENCY_MODE_M7_TRIM,
        "formula": "R=a(1+γ)(ℓ-b) · h↔=½(hij+hji)",
        "S_ij": "avg_latency/trimmed_m7",
        "reciprocity": recip,
        "precondition": {
            "label": precon_label,
            "intact": intact,
            "battery_ok": battery_ok,
            "reciprocity_ok": flag_recip,
            "battery": battery,
            "reciprocity": recip,
            "layer_c_detail": {
                k: layer_c[k]
                for k in ("mean_abs_diff", "S1", "S2", "pass", "n_agents")
                if k in layer_c
            },
        },
        "battery": battery,
    }
