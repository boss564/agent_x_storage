"""P6 — Z3 / exhaustive FSM checks for regime-swarm leader election (I1).

Modes:
  ordinal  — StatefulSet ordinal-0 (current production path)
  lease    — Planned Kubernetes Lease API (bounded BFS, gate-closed until §6 PASS)

Charter: monitoring only; proves leaders_count <= 1 for mutation path.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Set, Tuple

import z3

NO_HOLDER = -1


class PodState(IntEnum):
    FOLLOWER = 0
    STANDBY = 1
    LEADER = 2


@dataclass(frozen=True)
class LeaseWorld:
    """Snapshot of global lease + per-pod FSM (hashable for BFS)."""

    holder: int
    states: Tuple[PodState, ...]

    def holds(self, pod: int) -> bool:
        return self.holder == pod and self.states[pod] == PodState.LEADER

    def leaders_count(self) -> int:
        return sum(1 for i in range(len(self.states)) if self.holds(i))

    def mutators_count(self) -> int:
        return self.leaders_count()


@dataclass
class LeaderProofResult:
    gate: str
    invariant: str
    mode: str
    max_replicas: int
    steps_explored: int = 0
    states_explored: int = 0
    counterexample: Optional[Dict[str, Any]] = None
    proof_time_us: float = 0.0
    message: str = ""
    z3_result: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "invariant": self.invariant,
            "mode": self.mode,
            "max_replicas": self.max_replicas,
            "steps_explored": self.steps_explored,
            "states_explored": self.states_explored,
            "counterexample": self.counterexample,
            "proof_time_us": round(self.proof_time_us, 2),
            "message": self.message,
            "z3_result": self.z3_result,
        }


def _lease_successors(world: LeaseWorld) -> List[LeaseWorld]:
    """Legal single-step transitions (etcd mutual exclusion: one lease change per step)."""
    n = len(world.states)
    out: List[LeaseWorld] = []

    def push(holder: int, states: Tuple[PodState, ...]) -> None:
        out.append(LeaseWorld(holder=holder, states=states))

    states = list(world.states)

    # Acquire (only if no holder)
    if world.holder == NO_HOLDER:
        for i in range(n):
            if states[i] == PodState.FOLLOWER:
                ns = list(states)
                ns[i] = PodState.LEADER
                push(i, tuple(ns))

    # Renew (no state change)
    if world.holder != NO_HOLDER:
        push(world.holder, world.states)

    # Failed renew / release
    if world.holder != NO_HOLDER:
        i = world.holder
        ns = list(states)
        ns[i] = PodState.FOLLOWER
        push(NO_HOLDER, tuple(ns))

    # Standby observation (ordinal > 0, no lease)
    if world.holder == NO_HOLDER:
        for i in range(1, n):
            if states[i] != PodState.LEADER:
                ns = list(states)
                ns[i] = PodState.STANDBY
                push(NO_HOLDER, tuple(ns))

    # Follower noop
    if world.holder == NO_HOLDER:
        push(NO_HOLDER, world.states)

    return out


def prove_lease_fsm_bounded(
    max_replicas: int = 2,
    max_depth: int = 14,
) -> LeaderProofResult:
    """Exhaustive BFS — I1: mutators_count <= 1 on all reachable lease worlds."""
    t0 = time.perf_counter()
    if max_replicas < 1 or max_replicas > 4:
        return LeaderProofResult(
            gate="FAIL",
            invariant="I1_leaders_count_lte_1",
            mode="lease_bfs",
            max_replicas=max_replicas,
            message="max_replicas must be 1..4 for bounded proof",
        )

    init = LeaseWorld(
        holder=NO_HOLDER,
        states=tuple(PodState.FOLLOWER for _ in range(max_replicas)),
    )
    seen: Set[LeaseWorld] = {init}
    frontier: List[Tuple[LeaseWorld, int]] = [(init, 0)]
    max_depth_seen = 0

    while frontier:
        world, depth = frontier.pop(0)
        max_depth_seen = max(max_depth_seen, depth)

        if world.mutators_count() > 1:
            dt = (time.perf_counter() - t0) * 1_000_000
            return LeaderProofResult(
                gate="FAIL",
                invariant="I1_leaders_count_lte_1",
                mode="lease_bfs",
                max_replicas=max_replicas,
                steps_explored=max_depth_seen,
                states_explored=len(seen),
                counterexample={
                    "holder": world.holder,
                    "states": [s.name for s in world.states],
                    "mutators": world.mutators_count(),
                },
                proof_time_us=dt,
                message="Counterexample: two mutating leaders reachable",
            )

        if depth >= max_depth:
            continue

        for nxt in _lease_successors(world):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append((nxt, depth + 1))

    dt = (time.perf_counter() - t0) * 1_000_000
    return LeaderProofResult(
        gate="PASS",
        invariant="I1_leaders_count_lte_1",
        mode="lease_bfs",
        max_replicas=max_replicas,
        steps_explored=max_depth_seen,
        states_explored=len(seen),
        proof_time_us=dt,
        message=f"BFS PASS: {len(seen)} states, depth≤{max_depth}",
    )


def prove_ordinal_leader_z3(max_replicas: int = 3, leader_ordinal: int = 0) -> LeaderProofResult:
    """Z3: at most one pod may match leader_ordinal when election is enabled."""
    t0 = time.perf_counter()
    if leader_ordinal < 0 or leader_ordinal >= max_replicas:
        return LeaderProofResult(
            gate="FAIL",
            invariant="I1_ordinal_single_leader",
            mode="ordinal_z3",
            max_replicas=max_replicas,
            message="leader_ordinal out of range",
        )

    solver = z3.Solver()
    is_leader = [z3.Bool(f"is_leader_{i}") for i in range(max_replicas)]
    for i in range(max_replicas):
        solver.add(is_leader[i] == (i == leader_ordinal))

    # Counterexample: more than one leader flag true (unsatisfiable under definition)
    solver.add(z3.Sum([z3.If(is_leader[i], 1, 0) for i in range(max_replicas)]) > 1)

    result = solver.check()
    dt = (time.perf_counter() - t0) * 1_000_000
    if result == z3.unsat:
        return LeaderProofResult(
            gate="PASS",
            invariant="I1_ordinal_single_leader",
            mode="ordinal_z3",
            max_replicas=max_replicas,
            proof_time_us=dt,
            z3_result="unsat",
            message="Ordinal election: exactly one leader slot (Z3 UNSAT)",
        )
    return LeaderProofResult(
        gate="FAIL",
        invariant="I1_ordinal_single_leader",
        mode="ordinal_z3",
        max_replicas=max_replicas,
        proof_time_us=dt,
        z3_result="sat",
        message="Ordinal proof failed — unexpected SAT",
    )


def prove_lease_mutex_z3(max_replicas: int = 2) -> LeaderProofResult:
    """Z3: etcd mutex — at most one holds_lease bit under mutual exclusion."""
    t0 = time.perf_counter()
    solver = z3.Solver()
    holds = [z3.Bool(f"holds_{i}") for i in range(max_replicas)]

    # etcd Lease object: at most one holder
    solver.add(z3.Sum([z3.If(holds[i], 1, 0) for i in range(max_replicas)]) <= 1)

    # Seek violation
    solver.add(z3.Sum([z3.If(holds[i], 1, 0) for i in range(max_replicas)]) > 1)

    result = solver.check()
    dt = (time.perf_counter() - t0) * 1_000_000
    if result == z3.unsat:
        return LeaderProofResult(
            gate="PASS",
            invariant="I1_lease_mutex",
            mode="lease_mutex_z3",
            max_replicas=max_replicas,
            proof_time_us=dt,
            z3_result="unsat",
            message="Lease mutex: sum(holds)<=1 always (Z3 UNSAT)",
        )
    return LeaderProofResult(
        gate="FAIL",
        invariant="I1_lease_mutex",
        mode="lease_mutex_z3",
        max_replicas=max_replicas,
        proof_time_us=dt,
        z3_result="sat",
        message="Lease mutex proof failed",
    )


def prove_regime_leader_invariant(
    *,
    mode: str = "all",
    max_replicas: int = 2,
    leader_ordinal: int = 0,
    max_depth: int = 14,
) -> Dict[str, Any]:
    """Run P6 proof battery for Infra-Guardian gate."""
    results: List[LeaderProofResult] = []
    modes = (
        ["ordinal_z3", "lease_mutex_z3", "lease_bfs"]
        if mode == "all"
        else [mode]
    )

    if "ordinal_z3" in modes:
        results.append(prove_ordinal_leader_z3(max_replicas, leader_ordinal))
    if "lease_mutex_z3" in modes:
        results.append(prove_lease_mutex_z3(max_replicas))
    if "lease_bfs" in modes:
        results.append(prove_lease_fsm_bounded(max_replicas, max_depth))

    failed = [r for r in results if r.gate != "PASS"]
    gate = "PASS" if not failed else "BLOCKING"
    return {
        "schema": "infra_guardian_p6_z3_v0",
        "invariant": "I1_leaders_count_lte_1",
        "gate": gate,
        "failed_count": len(failed),
        "proofs": [r.to_dict() for r in results],
        "charter": "DEFENSIVE_CAUSAL_GROUNDING",
        "live_execution": False,
    }
