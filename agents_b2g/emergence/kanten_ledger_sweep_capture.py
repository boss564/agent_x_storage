#!/usr/bin/env python3
"""Ledger coupling capture for KOPPLUNG_LEDGER_v1 (BINDEND).

Arm B: ℓ* from sticky M. Arm C: delivery on M, coupling reads ℓ under π(M).
σ-normalization at freeze. Per-cell precondition hist for S-S/S-G.
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
)

COMP_INDEX = {
    "interaction_count": 0,
    "avg_latency": 3,
}
EPS = 1e-9


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
    for key in ("net_amount", "gross_amount", "amount"):
        if key in content:
            try:
                return float(content[key])
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def capture_ledger_coupling(
    *,
    component: str,
    cycles: int = 512,
    warmup_ticks: int = 32,
    run_seed: int = 20261301,
    kappa: float = 0.0,
    arm: str = "B",
) -> Dict[str, Any]:
    """Return {trace, precondition, sigma, component, arm, kappa}."""
    from agents_b2g.protocol import PayloadType
    from agents_b2g.finale.finale_orchestrator import FinaleOrchestrator
    from agents_b2g.finale.subagents.audit_trail import AuditTrailAgent

    if component not in COMP_INDEX:
        raise ValueError(component)
    comp_idx = COMP_INDEX[component]
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
            str(Path(os.environ.get("TMPDIR", "/tmp")) / "emergence_finale_ledger_sweep"),
        )
    )
    orch = FinaleOrchestrator(
        user_id="emergence-ledger-sweep",
        data_root=str(tmp_root / "finale"),
    )
    orch.audit = AuditTrailAgent(
        user_id="emergence-ledger-sweep",
        data_root=str(tmp_root / "audit"),
    )

    tc, agents, providers, evaluators, economics = _setup_swarm(run_seed, dpc, orch)
    by_id = {a.id: a for a in agents}
    recv_load = {a.id: 0 for a in agents}
    sticky = StickySelector(threshold=8)
    ledger = LedgerBook(gamma=0.05, latency_mode="ewma", trust_settlement_only=False)  # Vorher-Zustand (pre-M7/M9)
    coupling_edge: Dict[str, str] = {}
    signal_partner: Dict[str, str] = {}
    pending_eval: Dict[str, list] = {a.id: [] for a in evaluators}
    pending_econ: Dict[str, list] = {a.id: [] for a in economics}
    rule_default = dpc.rule_default
    EVALUATOR_RULES = dpc.EVALUATOR_RULES
    frozen_map = None
    map_c = None
    msg_log: List[Tuple[int, str, str]] = []
    sigma_l = 0.0
    edge_hist: List[Dict[Tuple[str, str], float]] = []

    def _load(a):
        return recv_load.get(a.id, 0) + len(a.inbox)

    def sync_signal_map(m_b, m_pi) -> None:
        signal_partner.clear()
        src = m_pi if (arm == "C" and m_pi is not None) else m_b
        if not src:
            return
        for (sk, _role), pid in src.items():
            signal_partner[sk.split(":")[0]] = pid

    def ell_star(ag_id: str) -> float:
        pid = signal_partner.get(ag_id) or coupling_edge.get(ag_id)
        if pid is None:
            return 0.0
        raw = ledger.component(ag_id, pid, comp_idx)
        return float(max(0.0, min(1.0, raw / (sigma_l + EPS))))

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
            ledger.update(
                msg.sender,
                partner.id,
                int(tc.cycle),
                success=True,
                signed_net=_signed_net(msg.content),
                latency=1.0,
            )
        else:
            for ag in agents:
                if ag.id == msg.receiver:
                    coupling_edge[msg.sender] = ag.id
                    msg_log.append((tc.cycle, msg.sender, ag.id))
                    ag.receive(msg)
                    recv_load[ag.id] = recv_load.get(ag.id, 0) + 1
                    ledger.update(
                        msg.sender,
                        ag.id,
                        int(tc.cycle),
                        success=True,
                        signed_net=_signed_net(msg.content),
                        latency=1.0,
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
                    signed_net=_signed_net(content), latency=1.0,
                )
        for ec in economics:
            batch = pending_econ[ec.id]
            pending_econ[ec.id] = []
            for sender, content in batch:
                ledger.update(
                    sender, ec.id, tick, success=True,
                    signed_net=_signed_net(content), latency=1.0,
                )

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
        out["ell_star"] = float(ell_star(a.id))
        if interval_on:
            out["effective_interval"] = float(getattr(a, "effective_interval", 1.0))
        return out

    def freeze_sigma(m_b) -> float:
        vals = []
        for (sk, _role), pid in (m_b or {}).items():
            sid = sk.split(":")[0]
            vals.append(ledger.component(sid, pid, comp_idx))
        if len(vals) < 2:
            return 0.0
        mean = sum(vals) / len(vals)
        return math.sqrt(sum((x - mean) ** 2 for x in vals) / (len(vals) - 1))

    warmup = max(0, int(warmup_ticks))
    total = warmup + int(cycles)
    snapshots = []

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
                    partner_s_honor=ell_star(ag.id),
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
            sigma_l = freeze_sigma(frozen_map)
            ledger.reset_window_flags()

        if tick > warmup:
            snapshots.append([numeric_state(a) for a in agents])
            edge_hist.append(ledger.snapshot_component(comp_idx))

    if frozen_map is None:
        frozen_map = sticky.freeze()
        map_c = permute_sticky_map(frozen_map, seed=int(run_seed))
        sync_signal_map(frozen_map, map_c)
        sigma_l = freeze_sigma(frozen_map)

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

    # Precondition: S-S/S-G with σ-normalized MAE
    raw = screen_ledger_component(
        sticky_map_b=frozen_map or {},
        sticky_map_c=map_c or {},
        edge_hist=edge_hist,
        component=component,
        mae_min=0.05,
        rho_max=0.90,
    )
    mae_raw = float(raw.get("mae") or 0.0)
    mae_norm = mae_raw / (sigma_l + EPS)
    flag_s = bool(mae_norm >= 0.05)
    flag_g = bool(raw.get("flags", {}).get("S_G"))
    n_corr = int(raw.get("n_corr") or 0)
    if n_corr < 14:
        precon = "PRECONDITION_LOST"
        intact = False
        untestable = True
    elif flag_s and flag_g:
        precon = "INTACT"
        intact = True
        untestable = False
    else:
        precon = "PRECONDITION_LOST"
        intact = False
        untestable = False

    return {
        "trace": tr,
        "component": component,
        "arm": arm,
        "kappa": float(kappa),
        "kappa_run": kappa_run,
        "run_seed": int(run_seed),
        "sigma": sigma_l,
        "precondition": {
            "label": precon,
            "intact": intact,
            "untestable_sg": untestable,
            "mae_raw": round(mae_raw, 6),
            "mae_norm": round(mae_norm, 6),
            "median_abs_rho": raw.get("median_abs_rho"),
            "n_corr": n_corr,
            "flags": {"S_S_norm": flag_s, "S_G": flag_g},
            "screen_raw": raw,
        },
    }
