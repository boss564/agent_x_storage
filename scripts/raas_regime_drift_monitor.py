#!/usr/bin/env python3
"""Baustein 2 — 9-Agent Regime Drift Schwarm (KS + Wasserstein, monitoring only).

Usage:
  PYTHONPATH=. python3 scripts/raas_regime_drift_monitor.py
  make raas-regime-drift-monitor
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from prototypes.raas_paper_trading.regime_drift import definition_hash, discover_worm_files  # noqa: E402
from prototypes.raas_paper_trading.regime_swarm import RegimeSwarmOrchestrator  # noqa: E402

DEFAULT_OUT = _ROOT / "exports" / "reports" / "regime_drift_latest.json"
DEFAULT_WORM_DIR = _ROOT / "logs" / "worm" / "paper_runs"
AUDIT = _ROOT / "logs" / "worm" / "regime_drift_audit.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="9-Agent regime drift swarm (Baustein 2)")
    parser.add_argument("--worm", action="append", default=[])
    parser.add_argument("--worm-dir", type=Path, default=DEFAULT_WORM_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-audit", action="store_true", help="Skip A9 audit append")
    args = parser.parse_args(argv)

    paths: List[Path] = []
    for raw in args.worm:
        paths.extend(discover_worm_files(Path(raw)))
    if args.worm_dir.is_dir():
        paths.extend(discover_worm_files(args.worm_dir))
    paths = sorted({str(p.resolve()): p for p in paths if p.is_file()}.values())

    orch = RegimeSwarmOrchestrator(
        audit_path=AUDIT,
        seed=args.seed,
    )

    print("RaaS Regime Drift Schwarm (A1–A9 · monitoring only)")
    print("=" * 60)
    print(f"definition_hash={definition_hash()[:16]}… worms={len(paths)}")

    if not paths:
        result = {
            "schema": "raas_regime_swarm_v2",
            "verdict": "RAAS_REGIME_DRIFT_EMPTY",
            "worm_count": 0,
            "definition_hash": definition_hash(),
            "ts": _now(),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"report: {args.out}")
        print("VERDICT: RAAS_REGIME_DRIFT_EMPTY")
        return 0

    reports: List[Dict[str, Any]] = []
    for path in paths:
        symbol = "UNKNOWN"
        for suffix in ("btcusdc", "ethusdc", "solusdc"):
            if suffix in path.as_posix().lower():
                symbol = suffix.upper()
                break
        reports.append(
            orch.run_cycle(
                worm_path=path,
                symbol=symbol,
                write_audit=not args.no_audit,
            )
        )

    critical = [r for r in reports if r.get("alert_level", "").startswith("CRITICAL")]
    warnings = [r for r in reports if r.get("alert_level") == "WARNING"]
    drift_any = [r for r in reports if (r.get("drift_summary") or {}).get("regime_flag", 0) > 0]

    for r in reports:
        sym = r.get("symbol", "?")
        ds = r.get("drift_summary") or {}
        print(
            f"  {sym} RSI={ds.get('regime_shift_index', '—')} "
            f"flag={ds.get('regime_flag', '—')} alert={r.get('alert_level', r.get('status'))}"
        )
        if ds.get("classified_regime"):
            print(f"    regime={ds['classified_regime']} features={ds.get('affected_features')}")

    verdict = "RAAS_REGIME_DRIFT_PASS"
    if critical:
        verdict = "RAAS_REGIME_DRIFT_CRITICAL"
    elif warnings or drift_any:
        verdict = "RAAS_REGIME_DRIFT_WARN"

    result = {
        "schema": "raas_regime_swarm_v0",
        "verdict": verdict,
        "worm_count": len(reports),
        "critical_count": len(critical),
        "warning_count": len(warnings),
        "definition_hash": definition_hash(),
        "audit_path": str(AUDIT),
        "reports": reports,
        "diagnostic_only": True,
        "not_investment_advice": True,
        "live_execution": False,
        "ts": _now(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"report: {args.out}")
    if critical or warnings:
        print(f"audit:  {AUDIT}")
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
