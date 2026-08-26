#!/usr/bin/env python3
"""Capture for KANTEN_LEDGER_v1 acceptance screening (ARCH_BINDEND).

κ=0 · ledger updates only on delivered (sender, receiver) interactions.
Does not modify sealed edge_signal / KOPPLUNG_EIJ_v1 paths.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from partner_select import StickySelector, permute_sticky_map
from kanten_ledger import (  # noqa: E402
    COMPONENT_NAMES,
    LedgerBook,
    screen_ledger_component,
)


def _setup_swarm(run_seed: int, dpc, orch):
    from coupling import init_timing
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


def capture_ledger(
    *,
    cycles: int = 512,
    warmup_ticks: int = 32,
    run_seed: int = 20261201,
) -> Dict[str, Any]:
    """Run swarm with ledger; return sticky maps + per-component edge histories."""
    from agents_b2g.protocol import PayloadType
    from agents_b2g.finale.finale_orchestrator import FinaleOrchestrator
    from agents_b2g.finale.subagents.audit_trail import AuditTrailAgent

    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import demo_producer_cluster as dpc

    tmp_root = Path(
        os.environ.get(
            "EMERGENCE_FINALE_ROOT",
            str(Path(os.environ.get("TMPDIR", "/tmp")) / "emergence_finale_ledger"),
        )
    )
    orch = FinaleOrchestrator(
        user_id="emergence-ledger",
        data_root=str(tmp_root / "finale"),
    )
    orch.audit = AuditTrailAgent(
        user_id="emergence-ledger",
        data_root=str(tmp_root / "audit"),
    )

    tc, agents, providers, evaluators, economics = _setup_swarm(run_seed, dpc, orch)
    recv_load = {a.id: 0 for a in agents}
    sticky = StickySelector(threshold=8)
    ledger = LedgerBook(gamma=0.05, latency_mode="ewma", trust_settlement_only=False)  # Vorher-Zustand (pre-M7/M9)
    pending_eval: Dict[str, list] = {a.id: [] for a in evaluators}
    pending_econ: Dict[str, list] = {a.id: [] for a in economics}
    rule_default = dpc.rule_default
    EVALUATOR_RULES = dpc.EVALUATOR_RULES
    frozen_map = None
    map_c = None
    # per-component histories in measure window
    hist: Dict[str, List[Dict[Tuple[str, str], float]]] = {
        name: [] for name in COMPONENT_NAMES
    }

    def _load(a):
        return recv_load.get(a.id, 0) + len(a.inbox)

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

    def deliver(msg):
        if msg.receiver == "evaluator":
            if not evaluators:
                return
            partner = sticky.select(msg.sender, "evaluator", evaluators, _load)
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            pending_eval[partner.id].append((msg.sender, msg.content, int(tc.cycle)))
        elif msg.receiver == "economic":
            if not economics:
                return
            partner = sticky.select(
                f"{msg.sender}:{msg.content.get('contract_id', '')}",
                "economic",
                economics,
                _load,
            )
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            if msg.payload_type == PayloadType.BHO_PROOF:
                pending_econ[partner.id].append(
                    (msg.sender, msg.content, int(tc.cycle))
                )
        elif msg.receiver == "broadcast":
            if not providers:
                return
            partner = sticky.select(
                msg.sender, "broadcast→provider", providers, _load,
            )
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            # broadcast delivery is an interaction (announce)
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
            for sender, content, _t0 in batch:
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
                    sender,
                    ev.id,
                    tick,
                    success=holds,
                    signed_net=_signed_net(content),
                    latency=1.0,
                )
        for ec in economics:
            batch = pending_econ[ec.id]
            pending_econ[ec.id] = []
            for sender, content, _t0 in batch:
                ledger.update(
                    sender,
                    ec.id,
                    tick,
                    success=True,
                    signed_net=_signed_net(content),
                    latency=1.0,
                )

    warmup = max(0, int(warmup_ticks))
    total = warmup + int(cycles)

    for _ in range(total):
        tc.cycle += 1
        tick = int(tc.cycle)
        ledger.decay_all(tick)
        env = {"cycle": tick, "agent_count": len(agents), "kappa": 0.0, "arm": "B"}
        for ag in agents:
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
            ledger.reset_window_flags()

        if tick > warmup:
            for idx, name in enumerate(COMPONENT_NAMES):
                hist[name].append(ledger.snapshot_component(idx))

    if frozen_map is None:
        frozen_map = sticky.freeze()
        map_c = permute_sticky_map(frozen_map, seed=int(run_seed))

    screens = []
    for name in COMPONENT_NAMES:
        screens.append(
            screen_ledger_component(
                sticky_map_b=frozen_map,
                sticky_map_c=map_c or {},
                edge_hist=hist[name],
                component=name,
            )
        )

    candidates = [s["component"] for s in screens if s.get("pass")]
    near = [
        s["component"]
        for s in screens
        if s.get("flags", {}).get("near_miss") and not s.get("pass")
    ]

    return {
        "run_seed": int(run_seed),
        "warmup": warmup,
        "cycles": int(cycles),
        "kappa": 0.0,
        "n_edges": len(ledger._edges),
        "n_sticky": len(frozen_map or {}),
        "components": screens,
        "candidates": candidates,
        "near_miss": near,
        "seed_pass": bool(candidates),
    }
