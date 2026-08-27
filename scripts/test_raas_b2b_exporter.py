#!/usr/bin/env python3
"""E2E smoke — B2B RaaS exporter (JSON/PDF/Merkle) against portal store.

Does not start gate/runner stress; synthesizes a completed run then exports.

Usage:
  PYTHONPATH=. python3 scripts/test_raas_b2b_exporter.py
  make raas-b2b-exporter-smoke
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services.exporter import merkle as merkle_mod  # noqa: E402
from services.exporter.agent_x_raas_exporter import (  # noqa: E402
    BASELINE_TAG,
    export_b2b_gutachten,
)
from services.raas_portal import exporter as portal_exporter  # noqa: E402
from services.raas_portal import store  # noqa: E402


def main() -> int:
    print("B2B RaaS exporter smoke")
    print("=" * 60)
    failed = 0
    tmp = tempfile.mkdtemp(prefix="b2b_export_")
    os.environ["RAAS_DATA_ROOT"] = str(Path(tmp) / "raas")

    try:
        contract = store.save_contract(
            tenant_id="b2b_demo",
            name="B2B-Smoke-Contract",
            bytecode_hex="0xabcd",
        )
        run = store.create_run(
            tenant_id="b2b_demo",
            contract_id=contract["contract_id"],
            n_scenarios=3,
            profile="default",
        )
        store.update_run(
            "b2b_demo",
            run["run_id"],
            {
                "status": "COMPLETED",
                "audit_verdict": "PASS",
                "gate_verdict": "RELEASED",
                "metrics": {"n_scenarios": 3, "risk_block_rate": 0.0},
            },
        )
        store.append_worm_line(
            "b2b_demo",
            run["run_id"],
            {"phase": "stress_done", "tenant_id": "b2b_demo"},
        )
        # Ensure portal cert path works first
        portal_exporter.export_certificate(
            tenant_id="b2b_demo",
            run_id=run["run_id"],
            caller_tenant_id="b2b_demo",
        )

        out = export_b2b_gutachten(
            tenant_id="b2b_demo",
            run_id=run["run_id"],
            caller_tenant_id="b2b_demo",
        )
        paths = out["paths"]
        for key in ("json", "markdown", "pdf", "merkle"):
            p = Path(paths[key])
            if not p.is_file() or p.stat().st_size < 20:
                print(f"  FAIL  missing/empty {key}: {p}")
                failed += 1
            else:
                print(f"  PASS  wrote {key} ({p.stat().st_size} B)")

        pkg = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
        if pkg.get("baseline_tag") != BASELINE_TAG:
            print("  FAIL  baseline_tag mismatch")
            failed += 1
        else:
            print(f"  PASS  baseline_tag={BASELINE_TAG}")

        if pkg.get("counterparties_mentioned") != []:
            print("  FAIL  counterparties not empty")
            failed += 1
        else:
            print("  PASS  submitter-only counterparties")

        root = pkg["merkle"]["root"]
        proofs = pkg["merkle"]["inclusion_proofs"]
        leaves = {s["id"]: s["hash"] for s in pkg["merkle"]["leaves"]}
        all_ok = True
        for lid, leaf in leaves.items():
            if not merkle_mod.verify_inclusion(leaf, proofs[lid], root):
                all_ok = False
                print(f"  FAIL  merkle verify {lid}")
                failed += 1
        if all_ok:
            print(f"  PASS  merkle inclusion ({len(leaves)} leaves)")

        # PDF magic
        pdf_head = Path(paths["pdf"]).read_bytes()[:5]
        if pdf_head != b"%PDF-":
            print(f"  FAIL  pdf magic {pdf_head!r}")
            failed += 1
        else:
            print("  PASS  pdf header")

        # Cross-tenant deny
        denied = False
        try:
            export_b2b_gutachten(
                tenant_id="b2b_demo",
                run_id=run["run_id"],
                caller_tenant_id="other",
            )
        except portal_exporter.EnvelopeCrossTenantDeny:
            denied = True
        if not denied:
            print("  FAIL  cross-tenant export should deny")
            failed += 1
        else:
            print("  PASS  cross-tenant deny")

        worm = store.run_dir("b2b_demo", run["run_id"]) / "audit.worm.jsonl"
        if "b2b_gutachten_export" not in worm.read_text(encoding="utf-8"):
            print("  FAIL  WORM missing b2b_gutachten_export")
            failed += 1
        else:
            print("  PASS  WORM phase b2b_gutachten_export")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    verdict = "RAAS_B2B_EXPORTER_PASS" if failed == 0 else "RAAS_B2B_EXPORTER_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
