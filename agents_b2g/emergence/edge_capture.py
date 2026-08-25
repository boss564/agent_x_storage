#!/usr/bin/env python3
"""E_ij capture for KOPPLUNG_EIJ_v1 (BINDEND) — I1 and κ-Sweep.

Delivery always uses frozen sticky map M (Arm B topology).
Arm C: coupling reads e_ij* from π(M) on the same edge table (§2.4).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from partner_select import StickySelector, permute_sticky_map
from coupling import init_timing, update_sender_interval, should_act_this_cycle
from edge_signal import EdgeBook, evaluate_i1_edge
from measure import SwarmTrace


def _setup_swarm(run_seed: int, dpc, orch):
    agents = []
    for p in dpc.PROVIDER_PROFILES:
        agents.append(dpc.create_agent(p, "provider", orch))
    for p in dpc.EVALUATOR_PROFILES:
        agents.append(dpc.create_agent(p, "evaluator", orch))
    for p in dpc.ECONOMIC_PROFILES:
        agents.append(dpc.create_agent(p, "economic", orch))
    from agents_b2g.protocol import TickController

    tc = TickController(seed=int(run_seed))
    for a in agents:
        tc.register(a)
        init_timing(a, base_interval=1.0, run_seed=int(run_seed))
    providers = [a for a in agents if isinstance(a, dpc.ProviderAgent)]
    evaluators = [a for a in agents if isinstance(a, dpc.EvaluatorAgent)]
    economics = [a for a in agents if isinstance(a, dpc.EconomicAgent)]
    return tc, agents, providers, evaluators, economics


def capture_edge(
    *,
    cycles: int = 512,
    warmup_ticks: int = 32,
    run_seed: int = 20261001,
    kappa: float = 0.0,
    arm: str = "B",
) -> SwarmTrace:
    """Full capture returning SwarmTrace for Kuramoto/divergence."""
    from agents_b2g.protocol import PayloadType
    from agents_b2g.finale.finale_orchestrator import FinaleOrchestrator
    from agents_b2g.finale.subagents.audit_trail import AuditTrailAgent

    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import demo_producer_cluster as dpc

    arm = str(arm).upper()
    if arm not in {"A", "B", "C"}:
        raise ValueError(arm)
    kappa_run = 0.0 if arm == "A" else float(kappa)
    interval_on = kappa_run > 0.0

    tmp_root = Path(
        os.environ.get(
            "EMERGENCE_FINALE_ROOT",
            str(Path(os.environ.get("TMPDIR", "/tmp")) / "emergence_finale_eij"),
        )
    )
    orch = FinaleOrchestrator(
        user_id="emergence-eij",
        data_root=str(tmp_root / "finale"),
    )
    orch.audit = AuditTrailAgent(
        user_id="emergence-eij",
        data_root=str(tmp_root / "audit"),
    )

    tc, agents, providers, evaluators, economics = _setup_swarm(run_seed, dpc, orch)
    by_id = {a.id: a for a in agents}
    recv_load = {a.id: 0 for a in agents}
    sticky = StickySelector(threshold=8)
    edges = EdgeBook()
    coupling_edge: dict[str, str] = {}
    signal_partner: dict[str, str] = {}  # agent_id -> partner_id for e_ij*
    map_c = None
    frozen_map = None
    pending_eval: dict[str, list] = {a.id: [] for a in evaluators}
    pending_econ: dict[str, list] = {a.id: [] for a in economics}
    rule_default = dpc.rule_default
    EVALUATOR_RULES = dpc.EVALUATOR_RULES
    msg_log = []

    def _load(a):
        return recv_load.get(a.id, 0) + len(a.inbox)

    def sync_signal_map(m_b, m_pi) -> None:
        signal_partner.clear()
        src = m_pi if (arm == "C" and m_pi is not None) else m_b
        if not src:
            return
        for (sk, _role), pid in src.items():
            aid = sk.split(":")[0]
            signal_partner[aid] = pid

    def deliver(msg):
        if msg.receiver == "evaluator":
            partner = sticky.select(msg.sender, "evaluator", evaluators, _load)
            coupling_edge[msg.sender] = partner.id
            msg_log.append((tc.cycle, msg.sender, partner.id))
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            pending_eval[partner.id].append((msg.sender, msg.content))
        elif msg.receiver == "economic":
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
                pending_econ[partner.id].append(msg.sender)
        elif msg.receiver == "broadcast":
            partner = sticky.select(
                msg.sender, "broadcast→provider", providers, _load,
            )
            coupling_edge[msg.sender] = partner.id
            msg_log.append((tc.cycle, msg.sender, partner.id))
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1

    def flush_edge_events(tick: int) -> None:
        for ev in evaluators:
            batch = pending_eval[ev.id]
            pending_eval[ev.id] = []
            rule = EVALUATOR_RULES.get(ev.id, rule_default)
            for sender, content in batch:
                if not isinstance(content, dict):
                    continue
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
                edges.apply_tx_gate(sender, ev.id, tick, delta_ok=holds)
        for ec in economics:
            batch = pending_econ[ec.id]
            pending_econ[ec.id] = []
            for sender in batch:
                edges.apply_tx_gate(sender, ec.id, tick, delta_ok=True)

    def e_star_for(ag) -> float:
        pid = signal_partner.get(ag.id) or coupling_edge.get(ag.id)
        return edges.scalar(ag.id, pid)

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
        out["e_star"] = float(e_star_for(a))
        if interval_on:
            out["effective_interval"] = float(getattr(a, "effective_interval", 1.0))
        return out

    warmup = max(0, int(warmup_ticks))
    total = warmup + int(cycles)
    snapshots = []

    for _ in range(total):
        tc.cycle += 1
        tick = int(tc.cycle)
        edges.decay_all(tick)
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
                    partner_s_honor=e_star_for(ag),
                )
                if not should_act_this_cycle(ag):
                    continue
            ag.tick(env)
            if ag.outbox:
                ag.last_transaction_time = float(tick)

        flush_edge_events(tick)

        out = []
        for ag in agents:
            out.extend(ag.outbox)
            ag.outbox.clear()
        for msg in out:
            deliver(msg)

        if warmup > 0 and tick == warmup:
            frozen_map = sticky.freeze()
            map_c = permute_sticky_map(frozen_map, seed=int(run_seed))
            # Delivery stays on M; Arm C only remaps coupling signal (§2.4)
            sync_signal_map(frozen_map, map_c)

        if tick > warmup:
            snapshots.append([numeric_state(a) for a in agents])

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
    return tr


def capture_edge_i1(
    *,
    warmup_ticks: int = 32,
    cycles: int = 64,
    run_seed: int = 20261001,
) -> dict[str, Any]:
    """I1-Edge: κ=0, Arm B delivery, evaluate B vs π(M) on same edge table."""
    from agents_b2g.protocol import PayloadType
    from agents_b2g.finale.finale_orchestrator import FinaleOrchestrator
    from agents_b2g.finale.subagents.audit_trail import AuditTrailAgent

    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import demo_producer_cluster as dpc

    tmp_root = Path(
        os.environ.get(
            "EMERGENCE_FINALE_ROOT",
            str(Path(os.environ.get("TMPDIR", "/tmp")) / "emergence_finale_eij"),
        )
    )
    orch = FinaleOrchestrator(
        user_id="emergence-eij",
        data_root=str(tmp_root / "finale"),
    )
    orch.audit = AuditTrailAgent(
        user_id="emergence-eij",
        data_root=str(tmp_root / "audit"),
    )

    tc, agents, providers, evaluators, economics = _setup_swarm(run_seed, dpc, orch)
    recv_load = {a.id: 0 for a in agents}
    sticky = StickySelector(threshold=8)
    edges = EdgeBook()
    pending_eval: dict[str, list] = {a.id: [] for a in evaluators}
    pending_econ: dict[str, list] = {a.id: [] for a in economics}
    rule_default = dpc.rule_default
    EVALUATOR_RULES = dpc.EVALUATOR_RULES

    def _load(a):
        return recv_load.get(a.id, 0) + len(a.inbox)

    def deliver(msg):
        if msg.receiver == "evaluator":
            partner = sticky.select(msg.sender, "evaluator", evaluators, _load)
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            pending_eval[partner.id].append((msg.sender, msg.content))
        elif msg.receiver == "economic":
            partner = sticky.select(
                f"{msg.sender}:{msg.content.get('contract_id', '')}",
                "economic",
                economics,
                _load,
            )
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            if msg.payload_type == PayloadType.BHO_PROOF:
                pending_econ[partner.id].append(msg.sender)
        elif msg.receiver == "broadcast":
            partner = sticky.select(
                msg.sender, "broadcast→provider", providers, _load,
            )
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1

    def flush_edge_events(tick: int) -> None:
        for ev in evaluators:
            batch = pending_eval[ev.id]
            pending_eval[ev.id] = []
            rule = EVALUATOR_RULES.get(ev.id, rule_default)
            for sender, content in batch:
                if not isinstance(content, dict):
                    continue
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
                edges.apply_tx_gate(sender, ev.id, tick, delta_ok=holds)
        for ec in economics:
            batch = pending_econ[ec.id]
            pending_econ[ec.id] = []
            for sender in batch:
                edges.apply_tx_gate(sender, ec.id, tick, delta_ok=True)

    warmup = int(warmup_ticks)
    total = warmup + int(cycles)
    frozen_map = None
    map_c = None
    edge_hist: list[dict] = []

    for _ in range(total):
        tc.cycle += 1
        tick = int(tc.cycle)
        edges.decay_all(tick)
        env = {"cycle": tick, "agent_count": len(agents), "kappa": 0.0, "arm": "B"}
        for ag in agents:
            ag.tick(env)
        flush_edge_events(tick)
        out = []
        for ag in agents:
            out.extend(ag.outbox)
            ag.outbox.clear()
        for msg in out:
            deliver(msg)

        if warmup > 0 and tick == warmup:
            frozen_map = sticky.freeze()
            map_c = permute_sticky_map(frozen_map, seed=int(run_seed))
            edges.reset_window_flags()

        if tick > warmup:
            snap = {
                (i, j): (est.scalar() if est.ever_updated else 0.0)
                for (i, j), est in edges._edges.items()
            }
            edge_hist.append(snap)

    assert frozen_map is not None and map_c is not None
    updated = {}
    for (sk, role), pid in frozen_map.items():
        ek = (sk.split(":")[0], pid)
        updated[ek] = edges.window_updated(ek)

    result = evaluate_i1_edge(
        sticky_map_b=frozen_map,
        sticky_map_c=map_c,
        edge_hist=edge_hist,
        updated_flags=updated,
        run_seed=int(run_seed),
        warmup=warmup,
        cycles=int(cycles),
    )
    result["n_edges_total"] = len(edges._edges)
    result["n_edges_updated_ever"] = sum(
        1 for e in edges._edges.values() if e.ever_updated
    )
    return result
