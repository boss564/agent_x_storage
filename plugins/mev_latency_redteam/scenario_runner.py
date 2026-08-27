"""Scenario interface — simulation only (no live MEV / no execute_*).

initialize_scenario → run_attack_scenario → report_scenario
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional
from zlib import crc32

from plugins.mev_latency_redteam.sandbox_io import write_sandbox_json

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
ALLOWED_KINDS = frozenset({"LATENCY_SPIKE", "SANDWICH_SIM", "JITTER_BURST"})


@dataclass
class ScenarioState:
    scenario_id: str
    kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    seed: int = 20260827
    started_mono: float = 0.0


def initialize_scenario(
    kind: str,
    *,
    scenario_id: str = "rt-default",
    params: Optional[Mapping[str, Any]] = None,
    seed: int = 20260827,
) -> ScenarioState:
    k = kind.upper()
    if k not in ALLOWED_KINDS:
        raise ValueError(f"unknown scenario kind: {kind}; allowed={sorted(ALLOWED_KINDS)}")
    return ScenarioState(
        scenario_id=scenario_id,
        kind=k,
        params=dict(params or {}),
        seed=int(seed),
        started_mono=time.perf_counter(),
    )


def run_attack_scenario(state: ScenarioState) -> Dict[str, Any]:
    """Simulate MEV/latency stress; returns candidates only — never gate fields."""
    dig = crc32(f"{state.seed}|{state.kind}|{state.scenario_id}".encode()) & 0xFFFFFFFF
    base_ms = float(state.params.get("base_latency_ms", 5.0))
    if state.kind == "LATENCY_SPIKE":
        spike_ms = base_ms * (1.0 + (dig % 50) / 10.0)  # 1×–6× synthetic
        result = {
            "scenario_kind": state.kind,
            "metric": "latency_ms",
            "observed_ms": round(spike_ms, 3),
            "baseline_ms": base_ms,
            "severity": "HIGH" if spike_ms > base_ms * 3 else "MODERATE",
        }
    elif state.kind == "SANDWICH_SIM":
        slip_bps = 5 + (dig % 40)
        result = {
            "scenario_kind": state.kind,
            "metric": "sandwich_slippage_bps",
            "observed_bps": slip_bps,
            "victim_leg": "synthetic",
            "severity": "HIGH" if slip_bps >= 30 else "MODERATE",
        }
    else:  # JITTER_BURST
        samples = [base_ms * (0.5 + ((dig >> i) & 0xF) / 16.0) for i in range(8)]
        result = {
            "scenario_kind": state.kind,
            "metric": "jitter_ms",
            "samples_ms": [round(x, 3) for x in samples],
            "p95_ms": round(sorted(samples)[int(0.95 * (len(samples) - 1))], 3),
            "severity": "MODERATE",
        }

    elapsed_ms = (time.perf_counter() - state.started_mono) * 1000.0
    out: Dict[str, Any] = {
        "type": "attack_result",
        "scenario_id": state.scenario_id,
        "role": "RED_TEAM",
        "status": "SIMULATED",
        "live_execution": False,
        "scope": SCOPE,
        "not_investment_advice": True,
        "elapsed_ms": round(elapsed_ms, 3),
        "artifact": result,
        "candidates": [
            f"CANDIDATE: review {state.kind} severity={result.get('severity')}"
        ],
    }
    # Explicitly never include decision fields
    assert "gate_verdict" not in out
    return out


def report_scenario(
    state: ScenarioState,
    attack_result: Mapping[str, Any],
    *,
    repo_root: Optional[Any] = None,
) -> Dict[str, Any]:
    """Persist report under sandbox only; strip any decision keys."""
    from pathlib import Path

    root = Path(repo_root) if repo_root else None
    material = dict(attack_result)
    for key in ("gate_verdict", "audit_verdict", "envelope_id", "egress_seal", "certificate_id"):
        material.pop(key, None)
    rel = f"{state.scenario_id}/report.json"
    path = write_sandbox_json(rel, material, repo_root=root)
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str).encode()
    ).hexdigest()
    return {
        "type": "scenario_report",
        "scenario_id": state.scenario_id,
        "sandbox_path": str(path),
        "report_sha256": digest,
        "live_execution": False,
        "scope": SCOPE,
        "role": "RED_TEAM",
    }
