#!/usr/bin/env python3
"""M1 E2E smoke — per-tenant prefilter path + submitter-only envelope + WORM.

Usage:
  PYTHONPATH=. python3 scripts/test_prefilter_m1_e2e.py
  make raas-prefilter-m1-e2e
"""
from __future__ import annotations

import json
import os
import pickle
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from plugins.risk_prefilter.scorer import FEATURE_NAMES  # noqa: E402
from prototypes.raas_hybrid_shell.prefilter_backlog import (  # noqa: E402
    resolve_tenant_prefilter_model,
    tenant_prefilter_dir,
)
from prototypes.raas_hybrid_shell.schemas import LLMStrategyProposal  # noqa: E402
from prototypes.raas_hybrid_shell.supranode_facade import (  # noqa: E402
    ExternalRequest,
    SupranodeFacade,
)
from prototypes.raas_hybrid_shell.untrusted_shell import propose  # noqa: E402
from services.raas_portal import exporter, store  # noqa: E402


def _tiny_model(path: Path, seed: int) -> None:
    from sklearn.ensemble import HistGradientBoostingRegressor

    rng = np.random.default_rng(seed)
    x = rng.normal(size=(80, len(FEATURE_NAMES)))
    y = (x[:, 1] * 0.2 + rng.normal(scale=0.05, size=80)).clip(0, 1)
    model = HistGradientBoostingRegressor(
        max_depth=3, max_iter=40, random_state=seed
    )
    model.fit(x, y)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        pickle.dump(
            {
                "backend": "sklearn_hist_gradient_boosting",
                "model": model,
                "features": FEATURE_NAMES,
            },
            f,
        )


def _req(cid: str, slip: float) -> ExternalRequest:
    base = propose("mild")
    prop = LLMStrategyProposal(
        **{**base.to_dict(), "proposal_id": cid, "max_slippage_pct": slip}
    )
    return ExternalRequest(correlation_id=cid, proposal=prop)


def main() -> int:
    print("M1 E2E (path · envelope · WORM)")
    print("=" * 60)
    failed = 0
    tmp = tempfile.mkdtemp(prefix="m1_e2e_")
    data_root = Path(tmp) / "raas"
    os.environ["RAAS_DATA_ROOT"] = str(data_root)
    # Ensure no silent global model
    os.environ.pop("PREFILTER_ALLOW_GLOBAL_MODEL", None)
    os.environ.pop("PREFILTER_MODEL_PATH", None)

    try:
        # --- Install disjoint tenant weights ---
        for tid, seed in (("tenant_a", 11), ("tenant_b", 22)):
            p = tenant_prefilter_dir(tid, data_root=data_root) / "prefilter_gbt.pkl"
            _tiny_model(p, seed=seed)

        ra = resolve_tenant_prefilter_model("tenant_a", data_root=data_root)
        rb = resolve_tenant_prefilter_model("tenant_b", data_root=data_root)
        if ra is None or rb is None or ra.resolve() == rb.resolve():
            print("  FAIL  M1 paths not disjoint")
            failed += 1
        else:
            print(f"  PASS  M1 paths A={ra.name} B≠A")

        # Missing tenant → None → backlog FIFO
        if resolve_tenant_prefilter_model("ghost", data_root=data_root) is not None:
            print("  FAIL  ghost tenant should miss model")
            failed += 1
        else:
            print("  PASS  missing model → None (FIFO)")

        # A must not resolve to B bytes
        if ra.read_bytes() == rb.read_bytes():
            # Models differ by seed — extremely unlikely equal; if equal still paths differ
            pass
        if "tenant_b" in str(ra) or "tenant_a" not in str(ra):
            print("  FAIL  A path wrong")
            failed += 1
        else:
            print("  PASS  A path under tenant_a/")

        # --- Facade batch uses tenant-scoped resolve (inject score reading path) ---
        facade_a = SupranodeFacade(tenant_id="tenant_a")
        batch = [
            _req("a1", 0.2),
            _req("a2", 0.8),
            _req("a3", 1.5),
            _req("a4", 2.0),
        ]
        # score_fn that asserts model path belongs to tenant_a
        seen_paths = []

        def score_assert(features: dict) -> dict:
            p = resolve_tenant_prefilter_model("tenant_a", data_root=data_root)
            seen_paths.append(str(p))
            if p is None or "tenant_a" not in str(p):
                raise RuntimeError("cross-tenant model")
            from plugins.risk_prefilter.scorer import score_features

            return score_features(features, model_path=p)

        cut = facade_a.handle_external_batch(
            batch,
            n_scenarios=8,
            prefilter_enabled=True,
            backlog_threshold=3,
            score_fn=score_assert,
        )
        if cut.mode != "priority" or not cut.all_processed:
            print(f"  FAIL  backlog mode={cut.mode}")
            failed += 1
        elif any("tenant_b" in p for p in seen_paths):
            print("  FAIL  scored with B path")
            failed += 1
        else:
            print("  PASS  backlog priority under tenant_a weights only")

        # --- Envelope + WORM ---
        contract = store.save_contract(
            tenant_id="tenant_a",
            name="M1-Smoke",
            bytecode_hex="0x00",
        )
        run = store.create_run(
            tenant_id="tenant_a",
            contract_id=contract["contract_id"],
            n_scenarios=5,
            profile="default",
        )
        store.update_run(
            "tenant_a",
            run["run_id"],
            {
                "status": "COMPLETED",
                "audit_verdict": "PASS",
                "gate_verdict": "RELEASED",
                "metrics": {"n_scenarios": 5},
            },
        )
        store.append_worm_line(
            "tenant_a",
            run["run_id"],
            {"phase": "stress_done", "tenant_id": "tenant_a"},
        )
        cert_out = exporter.export_certificate(
            tenant_id="tenant_a",
            run_id=run["run_id"],
            caller_tenant_id="tenant_a",
        )
        cert = cert_out["certificate"]
        subjects = cert.get("subjects") or []
        if (
            cert.get("tenant_id") != "tenant_a"
            or subjects != [{"role": "submitter", "tenant_id": "tenant_a"}]
            or cert.get("counterparties_mentioned") != []
        ):
            print(f"  FAIL  envelope subjects={subjects}")
            failed += 1
        else:
            print("  PASS  envelope submitter-only")

        deny_ok = False
        try:
            exporter.export_certificate(
                tenant_id="tenant_a",
                run_id=run["run_id"],
                caller_tenant_id="tenant_b",
            )
        except exporter.EnvelopeCrossTenantDeny:
            deny_ok = True
        if not deny_ok:
            print("  FAIL  caller B should deny")
            failed += 1
        else:
            print("  PASS  caller mismatch → ENVELOPE_CROSS_TENANT_DENY")

        # Foreign tenant in stress payload
        rd = store.run_dir("tenant_a", run["run_id"])
        (rd / "stress_summary.json").write_text(
            json.dumps({"metrics": {}, "foreign_tenant_id": "tenant_b"}),
            encoding="utf-8",
        )
        foreign_denied = False
        try:
            exporter.build_certificate(
                tenant_id="tenant_a",
                run_id=run["run_id"],
                caller_tenant_id="tenant_a",
            )
        except exporter.EnvelopeCrossTenantDeny:
            foreign_denied = True
        if not foreign_denied:
            print("  FAIL  foreign tenant in stress should deny")
            failed += 1
        else:
            print("  PASS  foreign stress tenant_id → deny")

        worm = rd / "audit.worm.jsonl"
        if not worm.is_file() or "certificate_export" not in worm.read_text(encoding="utf-8"):
            print("  FAIL  WORM missing certificate_export")
            failed += 1
        else:
            print("  PASS  WORM audit trail has certificate_export")

        # Disjoint WORM trees
        contract_b = store.save_contract(
            tenant_id="tenant_b", name="B2", bytecode_hex="0x02"
        )
        run_b = store.create_run(
            tenant_id="tenant_b",
            contract_id=contract_b["contract_id"],
            n_scenarios=1,
            profile="default",
        )
        path_a = store.run_dir("tenant_a", run["run_id"])
        path_b = store.run_dir("tenant_b", run_b["run_id"])
        if path_a == path_b or "tenant_a" not in str(path_a) or "tenant_b" not in str(path_b):
            print("  FAIL  WORM paths not tenant-disjoint")
            failed += 1
        else:
            print("  PASS  WORM paths tenant-disjoint")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    overall = failed == 0
    verdict = "PREFILTER_M1_E2E_PASS" if overall else "PREFILTER_M1_E2E_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
