#!/usr/bin/env python3
"""Adapter: schneidet einen Lauf des 27-Agenten-ABM als SwarmTrace mit.

TIER 0: crc32-Reproduzierbarkeit
TIER 1: StickySelector-Partnerwahl (Topologie)
TIER 2a: Rueckstau / Exzitation auf effective_interval
TIER 2b: Puls-gekoppelter Relaxations-Oszillator (Mirollo–Strogatz)
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, REPO)

from typing import Any, Optional
from pathlib import Path

import numpy as np
from measure import SwarmTrace
from partner_select import StickySelector, permute_sticky_map
from coupling import (
    init_timing,
    update_sender_interval,
    should_act_this_cycle,
    oscillator_from_gas,
)
from corridor import FireCorridor, corridor_step
from honor_signal import SwarmHonorBook, s_honor


def capture(
    cycles: int = 128,
    full: bool = True,
    kappa: float = 0.0,
    epsilon: float = 0.0,
    *,
    seed: int = 1,
    run_seed: int | None = None,
    relax: bool = False,
    corridor_width: Optional[int] = None,
    corridor_gap: Optional[int] = None,
    warmup_ticks: int = 0,
    arm: str = "B",
    honor_track: bool = False,
    honor_coupling: bool = False,
    collect_i1: bool = False,
) -> SwarmTrace | dict[str, Any]:
    """Capture a SwarmTrace.

    Pre-Reg Kopplung (§2):
      warmup_ticks — sticky map forms, then freeze(); measure window = ``cycles``.
      arm A — force kappa=0 (baseline).
      arm B — real sticky partners after freeze.
      arm C — degree-preserving shuffle of frozen map (seed=run_seed).

    KOPPLUNG_REPUTATION_v1:
      honor_track — accumulate H_i via HonorCalculator events.
      honor_coupling — interval = base × (1 + κ · s(H_partner)).
      collect_i1 — κ forced 0; return I1 payload (same H-table, B vs C maps).
    """
    from agents_b2g.protocol import TickController
    from agents_b2g.finale.finale_orchestrator import FinaleOrchestrator
    from agents_b2g.gas.gas_profiles import GasProfile
    import zlib
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import demo_producer_cluster as dpc
    globals()["dpc"] = dpc

    arm = str(arm).upper()
    if arm not in {"A", "B", "C"}:
        raise ValueError(f"arm must be A|B|C, got {arm!r}")

    # Pre-Reg §5.1: run_seed is the sole replicate knob.
    effective_seed = int(seed if run_seed is None else run_seed)
    if collect_i1:
        honor_track = True
        kappa_run = 0.0
        arm = "B"  # delivery on real map; C evaluated on same H-table (§7)
    else:
        kappa_run = 0.0 if arm == "A" else float(kappa)

    tmp_root = Path(
        os.environ.get(
            "EMERGENCE_FINALE_ROOT",
            str(Path(os.environ.get("TMPDIR", "/tmp")) / "emergence_finale"),
        )
    )
    orch = FinaleOrchestrator(
        user_id="emergence-probe",
        data_root=str(tmp_root / "finale"),
    )
    # AuditTrailAgent defaults to archive_b2g/audit — redirect for sandbox/isolation
    from agents_b2g.finale.subagents.audit_trail import AuditTrailAgent
    orch.audit = AuditTrailAgent(
        user_id="emergence-probe",
        data_root=str(tmp_root / "audit"),
    )
    agents = []
    if full:
        for p in dpc.PROVIDER_PROFILES:
            agents.append(dpc.create_agent(p, "provider", orch))
        for p in dpc.EVALUATOR_PROFILES:
            agents.append(dpc.create_agent(p, "evaluator", orch))
        for p in dpc.ECONOMIC_PROFILES:
            agents.append(dpc.create_agent(p, "economic", orch))
    else:
        agents = [dpc.ProviderAgent("provider"),
                  dpc.EvaluatorAgent("evaluator", orch),
                  dpc.EconomicAgent("economic", orch)]

    tc = TickController(seed=effective_seed)
    gases = {}
    oscillators = {}
    use_corridor = corridor_width is not None
    use_osc = relax or use_corridor
    for a in agents:
        tc.register(a)
        init_timing(a, base_interval=1.0, run_seed=effective_seed)
        fee = 0.4 + (zlib.crc32(a.id.encode()) % 17) * 0.05
        gases[a.id] = GasProfile.create(a.id, initial=200.0, fee=fee)
        if use_osc:
            oscillators[a.id] = oscillator_from_gas(
                gases[a.id], agent_id=a.id, run_seed=effective_seed,
            )

    corridor = None
    if use_corridor:
        from agents_b2g.crew.did_registry import DIDRegistry
        corridor = FireCorridor(
            width=int(corridor_width),
            gap=corridor_gap,
            registry=DIDRegistry(demo_mode=True),
        )

    msg_log = []
    interval_on = (not use_osc) and ((kappa_run > 0.0) or (epsilon > 0.0))
    relax_gate = relax and (not use_corridor) and (kappa_run > 0.0)

    providers  = [a for a in agents if isinstance(a, dpc.ProviderAgent)]
    evaluators = [a for a in agents if isinstance(a, dpc.EvaluatorAgent)]
    economics  = [a for a in agents if isinstance(a, dpc.EconomicAgent)]
    by_id = {a.id: a for a in agents}
    role_of = {}
    for a in providers:
        role_of[a.id] = "provider"
    for a in evaluators:
        role_of[a.id] = "evaluator"
    for a in economics:
        role_of[a.id] = "economic"
    recv_load = {a.id: 0 for a in agents}
    sticky = StickySelector(threshold=8)
    coupling_edge = {}
    fired_prev: set[str] = set()
    firing_times: dict[str, list[int]] = {a.id: [] for a in agents}
    frozen_map = None
    shuffled_map = None
    honor_book = SwarmHonorBook([a.id for a in agents]) if honor_track else None
    honor_hist: list[list[float]] = []  # measure-window rows
    i1_map_c = None

    def _load(a):
        return recv_load.get(a.id, 0) + len(a.inbox)

    def sync_coupling_from_sticky() -> None:
        for (sender_key, _role), pid in sticky.snapshot().items():
            agent_id = sender_key.split(":")[0]
            if agent_id in by_id and pid in by_id:
                coupling_edge[agent_id] = pid

    def deliver(msg):
        if msg.receiver == "broadcast":
            if not providers:
                return
            partner = sticky.select(
                msg.sender, "broadcast→provider", providers, _load,
            )
            coupling_edge[msg.sender] = partner.id
            msg_log.append((tc.cycle, msg.sender, partner.id))
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
        elif msg.receiver == "evaluator":
            if not evaluators:
                return
            partner = sticky.select(msg.sender, "evaluator", evaluators, _load)
            coupling_edge[msg.sender] = partner.id
            msg_log.append((tc.cycle, msg.sender, partner.id))
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
        elif msg.receiver == "economic":
            if not economics:
                return
            partner = sticky.select(
                f"{msg.sender}:{msg.content.get('contract_id', '')}",
                "economic", economics, _load,
            )
            coupling_edge[msg.sender] = partner.id
            msg_log.append((tc.cycle, msg.sender, partner.id))
            partner.receive(msg)
            recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
        else:
            for ag in agents:
                if ag.id == msg.receiver:
                    coupling_edge[msg.sender] = ag.id
                    msg_log.append((tc.cycle, msg.sender, ag.id)); ag.receive(msg)
                    recv_load[ag.id] = recv_load.get(ag.id, 0) + 1

    def partner_of(ag):
        return by_id.get(coupling_edge.get(ag.id))

    SKIP = {
        "id", "cycle", "fee_rate", "base_interval", "effective_interval",
        "inbox_capacity", "last_transaction_time",
    }

    def numeric_state(a):
        out = {}
        for k, v in vars(a).items():
            if k.startswith("_") or k in SKIP:
                continue
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                out[k] = float(v)
        for k, v in getattr(a, "state", {}).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[f"state.{k}"] = float(v)
        out["inbox_len"] = float(len(getattr(a, "inbox", [])))
        out["phase"] = float(getattr(a, "phase", 0.0))
        if honor_book is not None:
            out["honor"] = float(honor_book.get(a.id))
            out["s_honor"] = float(honor_book.s(a.id))
        if interval_on:
            out["effective_interval"] = float(getattr(a, "effective_interval", 1.0))
        if a.id in oscillators:
            osc = oscillators[a.id]
            out["osc_charge"] = float(osc.charge)
            out["osc_base_rate"] = float(osc.base_rate)
        return out

    if oscillators:
        rates = sorted(o.base_rate for o in oscillators.values())
        med = rates[len(rates) // 2]
    else:
        med = None

    warmup = max(0, int(warmup_ticks))
    total_ticks = warmup + int(cycles)
    snapshots = []
    for _ in range(total_ticks):
        tc.cycle += 1

        env = {
            "cycle": tc.cycle, "agent_count": len(agents),
            "kappa": kappa_run, "epsilon": epsilon, "relax": relax,
            "arm": arm,
        }
        fired_now: set[str] = set()

        for ag in agents:
            if use_corridor and corridor is not None and ag.id in oscillators:
                fired = corridor_step(
                    oscillators[ag.id], corridor, ag.id, int(tc.cycle),
                )
                if fired:
                    firing_times[ag.id].append(int(tc.cycle))
                    fired_now.add(ag.id)
                before = honor_book.snapshot_counters(ag) if honor_book else None
                ag.tick(env)
                if honor_book is not None and before is not None:
                    honor_book.update_after_tick(ag, before, role_of[ag.id])
                if ag.outbox:
                    ag.last_transaction_time = float(tc.cycle)
            elif relax and ag.id in oscillators:
                partner = partner_of(ag)
                pulses = (
                    1.0
                    if (relax_gate and partner is not None and partner.id in fired_prev)
                    else 0.0
                )
                fired = oscillators[ag.id].step(pulses, kappa_run if relax_gate else 0.0)
                if fired:
                    firing_times[ag.id].append(int(tc.cycle))
                    fired_now.add(ag.id)
                if relax_gate:
                    if fired:
                        before = honor_book.snapshot_counters(ag) if honor_book else None
                        ag.tick(env)
                        if honor_book is not None and before is not None:
                            honor_book.update_after_tick(ag, before, role_of[ag.id])
                        if ag.outbox:
                            ag.last_transaction_time = float(tc.cycle)
                else:
                    before = honor_book.snapshot_counters(ag) if honor_book else None
                    ag.tick(env)
                    if honor_book is not None and before is not None:
                        honor_book.update_after_tick(ag, before, role_of[ag.id])
                    if ag.outbox:
                        ag.last_transaction_time = float(tc.cycle)
            elif interval_on:
                partner = partner_of(ag)
                s_h = None
                if honor_coupling:
                    pid = partner.id if partner is not None else None
                    s_h = float(honor_book.s(pid)) if honor_book is not None else 0.0
                update_sender_interval(
                    ag, partner, kappa_run,
                    epsilon=epsilon, t_now=float(tc.cycle),
                    gas=gases[ag.id] if kappa_run > 0.0 else None,
                    partner_s_honor=s_h,
                )
                if not should_act_this_cycle(ag):
                    continue
                before = honor_book.snapshot_counters(ag) if honor_book else None
                ag.tick(env)
                if honor_book is not None and before is not None:
                    honor_book.update_after_tick(ag, before, role_of[ag.id])
                if ag.outbox:
                    ag.last_transaction_time = float(tc.cycle)
            else:
                before = honor_book.snapshot_counters(ag) if honor_book else None
                ag.tick(env)
                if honor_book is not None and before is not None:
                    honor_book.update_after_tick(ag, before, role_of[ag.id])
                if ag.outbox:
                    ag.last_transaction_time = float(tc.cycle)

        fired_prev = fired_now
        if corridor is not None:
            corridor.note_tick(int(tc.cycle))

        out = []
        for ag in agents:
            out.extend(ag.outbox); ag.outbox.clear()
        for msg in out:
            deliver(msg)

        # Topology freeze AFTER warm-up tick completes (Pre-Reg §2.2 / §2.3)
        if warmup > 0 and tc.cycle == warmup:
            frozen_map = sticky.freeze()
            if arm == "C":
                shuffled_map = permute_sticky_map(frozen_map, seed=effective_seed)
                sticky.load_map(shuffled_map, freeze=True)
            if collect_i1 and frozen_map is not None:
                i1_map_c = permute_sticky_map(frozen_map, seed=effective_seed)
            sync_coupling_from_sticky()
            if honor_book is not None:
                honor_book.reset_change_flags()  # I1-U: changes in measure window only

        # Measure window only (cycles after warm-up)
        if tc.cycle > warmup:
            snapshots.append([numeric_state(a) for a in agents])
            if honor_book is not None:
                honor_hist.append([honor_book.get(a.id) for a in agents])

    keys = sorted({k for snap in snapshots for st in snap for k in st})
    if not keys:
        raise RuntimeError("Agenten haben keinen numerischen Zustand")

    T, N, D = len(snapshots), len(agents), len(keys)
    states = np.zeros((T, N, D))
    for t, snap in enumerate(snapshots):
        for i, st in enumerate(snap):
            for d, k in enumerate(keys):
                v = st.get(k, 0)
                states[t, i, d] = float(v) if isinstance(v, (int, float)) else 0.0

    if corridor is not None:
        corridor.finalize(tc.cycle)

    # Graph/messages: post-warmup edges only
    msg_measure = [(t, s, r) for (t, s, r) in msg_log if t > warmup]

    if collect_i1:
        from honor_signal import evaluate_i1

        return evaluate_i1(
            agent_ids=[a.id for a in agents],
            honor_hist=honor_hist,
            map_b=frozen_map or {},
            map_c=i1_map_c or {},
            changed={a.id: honor_book.any_change(a.id) for a in agents}
            if honor_book
            else {},
            run_seed=effective_seed,
            warmup=warmup,
            cycles=int(cycles),
        )

    trace = SwarmTrace([a.id for a in agents], states, msg_measure)
    trace.state_keys = keys
    trace.economic_ids = [a.id for a in economics]
    trace.kappa = kappa_run
    trace.epsilon = epsilon
    trace.relax = relax
    trace.median_base_rate = med
    trace.corridor_width = corridor_width
    trace.arm = arm
    trace.run_seed = effective_seed
    trace.warmup_ticks = warmup
    trace.frozen_map = frozen_map
    trace.shuffled_map = shuffled_map
    if honor_book is not None:
        trace.honor = honor_book.as_dict()
    if use_osc:
        trace.firing_times = firing_times
    if corridor is not None:
        trace.corridor_stats = corridor.summary(len(agents))
    return trace


if __name__ == "__main__":
    import argparse
    import json
    from collections import Counter
    from measure import assess, summary_line

    ap = argparse.ArgumentParser()
    ap.add_argument("cycles", nargs="?", type=int, default=128)
    ap.add_argument("--kappa", type=float, default=float(os.environ.get("KAPPA", "0")))
    ap.add_argument("--epsilon", type=float,
                    default=float(os.environ.get("EPSILON", "0")))
    ap.add_argument("--relax", action="store_true",
                    help="TIER 2b: pulse-coupled relaxation oscillator")
    ap.add_argument("--corridor", type=int, default=None,
                    help="TIER 2c: fire corridor width in ticks (0=free IF control)")
    ap.add_argument("--gap", type=int, default=None,
                    help="TIER 2c: cooldown ticks after corridor (default=width)")
    args = ap.parse_args()

    tr = capture(
        cycles=args.cycles, full=True,
        kappa=args.kappa, epsilon=args.epsilon, relax=args.relax,
        corridor_width=args.corridor, corridor_gap=args.gap,
    )
    tx_rate = len(tr.messages) / max(tr.states.shape[0], 1)
    med = getattr(tr, "median_base_rate", None)
    print(f"kappa={args.kappa}  epsilon={args.epsilon}  relax={args.relax}  "
          f"corridor={args.corridor}")
    if med is not None:
        ratio = (args.kappa / med) if med > 0 else float("nan")
        print(f"median_base_rate={med:.4f}  kappa/median_rate={ratio:.2f}")
    if getattr(tr, "corridor_stats", None):
        print(f"corridor_stats: {tr.corridor_stats}")
    print(f"Agenten: {len(tr.agents)}  Ticks: {tr.states.shape[0]}  "
          f"Zustandsdimensionen: {tr.states.shape[2]} {getattr(tr,'state_keys',[])}")
    print(f"Nachrichten: {len(tr.messages)}  TX-Rate: {tx_rate:.4f} msg/tick")
    if getattr(tr, "firing_times", None):
        fc = [len(tr.firing_times.get(a, [])) for a in tr.agents]
        print(f"Feuer/Agent: min={min(fc)} median={sorted(fc)[len(fc)//2]} max={max(fc)} "
              f"total={sum(fc)}")
    eco = getattr(tr, "economic_ids", [])
    cnt = Counter(r for _, _, r in tr.messages if r in eco)
    print(f"Arbeitsverteilung: {[cnt[eid] for eid in eco]}")
    res = assess(tr, n_surrogates=200, seed=7)
    print()
    g = res.get("graph", {})
    print(f"Dichte: {g.get('density')}  null_model_informative: {g.get('null_model_informative')}  "
          f"hub_share: {g.get('hub_share')}")
    zs = g.get("z_scores") or {}
    print(f"Graph-z-Scores: {zs}")
    kur = res.get("kuramoto", {})
    div = res.get("divergence", {})
    print(f"D_dyn: {div.get('divergence_dynamic')}  r: {kur.get('r_observed')}  "
          f"p: {kur.get('p_value')}  method: {kur.get('method')}  verdict: {res.get('verdict')}")
    if kur.get("coincidence"):
        c = kur["coincidence"]
        print(f"Koinzidenz: peak={c.get('peak_coincidence')}  "
              f"cycles≥2={c.get('cycles_with_ge2')}  "
              f"frac_multi={c.get('fraction_multi')}  "
              f"peaks={c.get('has_coincidence_peaks')}  "
              f"hist={c.get('hist_n_firers')}")
    if kur.get("error"):
        print(f"Kuramoto-Fehler: {kur['error']}")
    print(json.dumps({k: v for k, v in res.items() if k != "divergence"},
                     indent=1, ensure_ascii=False, default=str)[:1600])
    d = res["divergence"]
    print(f"\nDivergenz: {d['divergence']}  identisch={d['identical_agents']}")
    print(f"Streuung je Dimension: {dict(zip(getattr(tr,'state_keys',[]), d['per_dimension_spread']))}")
    print(f"\n>>> {summary_line(res)}")
    print(f">>> {res['reason']}")
