#!/usr/bin/env python3
"""CLI stress runner for RaaS (Podman-ready prototype).

Usage (repo root):
  PYTHONPATH=. python3 scripts/raas_stress_runner.py --tenant demo --run-id <uuid>
  PYTHONPATH=. python3 scripts/raas_stress_runner.py --tenant demo --create-from-contract <uuid> -n 100
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.raas_portal import exporter, runner, store  # noqa: E402


def _compose_health() -> dict:
    compose = _ROOT / "podman-compose.p9.yml"
    if not compose.exists():
        return {"compose": "missing", "services_up": None}
    try:
        out = subprocess.run(
            ["docker", "compose", "-f", str(compose), "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
        return {"compose": str(compose.name), "containers": len(lines)}
    except Exception as exc:
        return {"compose": str(compose.name), "error": str(exc)}


def main() -> int:
    p = argparse.ArgumentParser(description="RaaS stress runner (prototype)")
    p.add_argument("--tenant", default="demo")
    p.add_argument("--run-id", help="Existing run UUID")
    p.add_argument(
        "--create-from-contract",
        help="Create new run from contract_id then execute",
    )
    p.add_argument("-n", "--n-scenarios", type=int, default=100)
    p.add_argument("--profile", default="default")
    p.add_argument("--no-certificate", action="store_true")
    p.add_argument("--check-compose", action="store_true")
    args = p.parse_args()

    if args.check_compose:
        print(json.dumps(_compose_health(), indent=2))
        return 0

    run_id = args.run_id
    if args.create_from_contract:
        rec = store.create_run(
            tenant_id=args.tenant,
            contract_id=args.create_from_contract,
            n_scenarios=args.n_scenarios,
            profile=args.profile,
        )
        run_id = rec["run_id"]
        print(f"created run {run_id}")

    if not run_id:
        p.error("provide --run-id or --create-from-contract")

    result = runner.run_stress_job(
        tenant_id=args.tenant,
        run_id=run_id,
        n_scenarios=args.n_scenarios,
    )
    print(json.dumps({"run": result}, indent=2, default=str))

    if not args.no_certificate:
        cert = exporter.export_certificate(
            tenant_id=args.tenant, run_id=run_id, fmt="json"
        )
        print(json.dumps({"certificate_id": cert["certificate"]["certificate_id"]}, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
