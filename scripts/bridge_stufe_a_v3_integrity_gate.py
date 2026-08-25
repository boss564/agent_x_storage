"""Pre-CTE integrity gate: alignment, occupancy join, Z_alt missing gate (V3).

Must PASS before any CTE evaluation. Writes bridge_stufe_a_v3_integrity_gate.json.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from bridge_stufe_a_config import DRIVER_COVERAGE_MIN, WINDOW_END_UTC, WINDOW_START_UTC, n_minute_bins
from bridge_stufe_a_pipeline import load_driver_series, refuse_smoke_manifest
from bridge_stufe_a_stats import driver_coverage
from bridge_stufe_a_v3_config import CANDIDATE_IDS, DEFAULT_INPUTS
from bridge_stufe_a_v3_load import load_bridge_occupancy, load_candidate_occupancy, occupancy_stats


def _load_coverage_gate(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"missing coverage gate: {path}")
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("untestable_candidates", 1) > 0:
        raise SystemExit("coverage gate has untestable candidates")
    if body.get("testable_candidates", 0) != len(CANDIDATE_IDS):
        raise SystemExit(
            f"expected {len(CANDIDATE_IDS)} testable candidates, got {body.get('testable_candidates')}"
        )
    for cid in CANDIDATE_IDS:
        row = body.get("results", {}).get(cid, {})
        if row.get("status") != "TESTBAR":
            raise SystemExit(f"candidate {cid} not TESTBAR: {row}")
    return body


def run_gate(
    *,
    input_dir: Path,
    coverage_gate: str,
    bridge_eth: str,
    bridge_gnosis: str,
    drivers: str,
    allow_smoke: bool,
) -> dict:
    cov = _load_coverage_gate(input_dir / coverage_gate)
    n_bins = n_minute_bins()
    issues: list[str] = []

    for label, fname in (
        ("bridge_eth", bridge_eth),
        ("bridge_gnosis", bridge_gnosis),
        ("drivers", drivers),
    ):
        p = input_dir / fname
        if not p.exists():
            issues.append(f"missing {label}: {p}")
        else:
            refuse_smoke_manifest(str(p), allow_smoke)

    candidates: dict[str, dict] = {}
    for cid in CANDIDATE_IDS:
        fname = DEFAULT_INPUTS[cid]
        p = input_dir / fname
        if not p.exists():
            issues.append(f"missing candidate file: {p}")
            continue
        refuse_smoke_manifest(str(p), allow_smoke)
        occ, n_events = load_candidate_occupancy(cid, p)
        if len(occ) != n_bins:
            issues.append(f"{cid}: occupancy length {len(occ)} != {n_bins}")
        stats = occupancy_stats(occ)
        stats["n_events_raw"] = n_events
        candidates[cid] = stats

    treat_eth = treat_gno = None
    if not issues:
        occ_e, n_e = load_bridge_occupancy(input_dir / bridge_eth)
        occ_g, n_g = load_bridge_occupancy(input_dir / bridge_gnosis)
        treat_eth = {"n_events": n_e, **occupancy_stats(occ_e)}
        treat_gno = {"n_events": n_g, **occupancy_stats(occ_g)}
        if len(occ_e) != n_bins or len(occ_g) != n_bins:
            issues.append("treatment occupancy length mismatch")

    gas, btc, cex = load_driver_series(str(input_dir / drivers))
    if len(gas) != n_bins:
        issues.append(f"drivers length {len(gas)} != {n_bins}")
    z_cov = driver_coverage(gas, btc, cex)
    if z_cov < DRIVER_COVERAGE_MIN:
        issues.append(f"Z_alt coverage {z_cov:.4f} < {DRIVER_COVERAGE_MIN}")

    status = "PASS" if not issues else "FAIL"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pre_reg": "docs/BRIDGE_STUFE_A_V3_PREREG.md",
        "window_start": WINDOW_START_UTC.isoformat(),
        "window_end": WINDOW_END_UTC.isoformat(),
        "n_minute_bins": n_bins,
        "status": status,
        "issues": issues,
        "coverage_gate_ref": str(input_dir / coverage_gate),
        "coverage_gate": {
            "testable_candidates": cov.get("testable_candidates"),
            "results": {k: cov["results"][k]["status"] for k in CANDIDATE_IDS},
        },
        "treatment": {"eth": treat_eth, "gnosis": treat_gno},
        "z_alt": {
            "driver_coverage_joint": round(z_cov, 6),
            "min_required": DRIVER_COVERAGE_MIN,
        },
        "candidates": candidates,
        "join_rules": {
            "multi_event_per_minute": "OR → occupancy=1",
            "chainlink": "OR feeds except excluded USDT/USD ethereum",
            "mev_cluster": "sparse occupied minutes, no dedup needed",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stufe A V3 pre-CTE integrity gate")
    parser.add_argument("--input-dir", default=".")
    parser.add_argument("--coverage-gate", default=DEFAULT_INPUTS["coverage_gate"])
    parser.add_argument("--bridge-eth", default=DEFAULT_INPUTS["bridge_eth"])
    parser.add_argument("--bridge-gnosis", default=DEFAULT_INPUTS["bridge_gnosis"])
    parser.add_argument("--drivers", default=DEFAULT_INPUTS["drivers"])
    parser.add_argument("--output", default="bridge_stufe_a_v3_integrity_gate.json")
    parser.add_argument("--allow-smoke", action="store_true")
    args = parser.parse_args()

    root = Path(args.input_dir)
    result = run_gate(
        input_dir=root,
        coverage_gate=args.coverage_gate,
        bridge_eth=args.bridge_eth,
        bridge_gnosis=args.bridge_gnosis,
        drivers=args.drivers,
        allow_smoke=args.allow_smoke,
    )
    out = Path(args.output)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"status={result['status']}")
    if result["issues"]:
        for issue in result["issues"]:
            print(f"  issue: {issue}")
    print(f"Wrote {out}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
