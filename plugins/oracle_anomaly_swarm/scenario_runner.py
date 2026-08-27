"""Oracle anomaly scenarios — simulation only (no live feed mutation).

initialize_scenario → run_oracle_attack_scenario → report_scenario
Kinds: STALE_PRICE · FAT_FINGER · FLASH_CRASH · DEPEG_SIM
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional
from zlib import crc32

from plugins.oracle_anomaly_swarm.sandbox_io import write_sandbox_json

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
ALLOWED_KINDS = frozenset({"STALE_PRICE", "FAT_FINGER", "FLASH_CRASH", "DEPEG_SIM"})


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
    scenario_id: str = "oa-default",
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


def run_oracle_attack_scenario(state: ScenarioState) -> Dict[str, Any]:
    """Inject synthetic oracle anomalies; candidates only — never gate fields."""
    dig = crc32(f"{state.seed}|{state.kind}|{state.scenario_id}".encode()) & 0xFFFFFFFF
    fair = float(state.params.get("fair_price", 100.0))
    feed = str(state.params.get("feed_id", "SYNTHETIC_ORACLE_A"))

    if state.kind == "STALE_PRICE":
        age_s = 30 + (dig % 300)  # 30s–329s stale
        quoted = fair * (1.0 + ((dig % 7) - 3) / 1000.0)  # tiny drift while stale
        result = {
            "scenario_kind": state.kind,
            "metric": "oracle_staleness_s",
            "feed_id": feed,
            "fair_price": fair,
            "quoted_price": round(quoted, 6),
            "staleness_s": age_s,
            "severity": "HIGH" if age_s >= 120 else "MODERATE",
        }
    elif state.kind == "FAT_FINGER":
        # Typo-scale outlier: 10×–100× or 0.01× synthetic
        mult = 10 + (dig % 91)
        if dig & 1:
            quoted = fair * mult
        else:
            quoted = fair / mult
        deviation_pct = abs(quoted - fair) / fair * 100.0
        result = {
            "scenario_kind": state.kind,
            "metric": "oracle_fat_finger_pct",
            "feed_id": feed,
            "fair_price": fair,
            "quoted_price": round(quoted, 6),
            "deviation_pct": round(deviation_pct, 3),
            "severity": "HIGH" if deviation_pct >= 50 else "MODERATE",
        }
    elif state.kind == "DEPEG_SIM":
        # Synthetic stable/peg break (e.g. 1.0 → 0.95…0.55)
        peg = float(state.params.get("peg_price", fair))
        break_pct = float(state.params.get("break_pct") or (5 + (dig % 45)))
        quoted = peg * (1.0 - break_pct / 100.0)
        result = {
            "scenario_kind": state.kind,
            "metric": "oracle_depeg_pct",
            "feed_id": feed,
            "fair_price": peg,
            "quoted_price": round(quoted, 6),
            "deviation_pct": round(break_pct, 3),
            "severity": "HIGH" if break_pct >= 10 else "MODERATE",
        }
    else:  # FLASH_CRASH
        drawdown_pct = 15 + (dig % 40)  # 15–54%
        trough = fair * (1.0 - drawdown_pct / 100.0)
        recovery_ticks = 3 + (dig % 8)
        result = {
            "scenario_kind": state.kind,
            "metric": "oracle_flash_crash",
            "feed_id": feed,
            "fair_price": fair,
            "trough_price": round(trough, 6),
            "drawdown_pct": drawdown_pct,
            "recovery_ticks": recovery_ticks,
            "severity": "HIGH" if drawdown_pct >= 30 else "MODERATE",
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
    assert "gate_verdict" not in out
    return out


def report_scenario(
    state: ScenarioState,
    attack_result: Mapping[str, Any],
    *,
    repo_root: Optional[Any] = None,
) -> Dict[str, Any]:
    from pathlib import Path

    root = Path(repo_root) if repo_root else None
    material = dict(attack_result)
    for key in (
        "gate_verdict",
        "audit_verdict",
        "envelope_id",
        "egress_seal",
        "certificate_id",
    ):
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
