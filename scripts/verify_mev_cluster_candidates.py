"""Hard gate for MEV-cluster candidate (Pre-Reg §3.0.5 Schicht A)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

PREREG_MARKERS = ("Pre-Reg", "pre-reg", "BRIDGE_STUFE_A_V3_PREREG", "§3.0.5")


def evaluate_chain(item: dict) -> dict:
    status = item.get("status") or item.get("verification_status")
    docs_verified = bool(item.get("docs_verified", False))
    docs_verified_at = item.get("docs_verified_at")
    docs_source = item.get("docs_source")
    reason_txt = item.get("adaptation_reason") or ""

    base = {
        "chain": item.get("chain"),
        "role": item.get("role"),
        "docs_verified": docs_verified,
        "docs_verified_at": docs_verified_at,
        "docs_source": docs_source,
    }

    if status == "excluded":
        ok_fields = bool(reason_txt and docs_source and docs_verified_at)
        ok_ref = any(m in f"{reason_txt} {docs_source}" for m in PREREG_MARKERS)
        if not ok_fields or not ok_ref:
            return {**base, "status": "EXCLUDED_INCOMPLETE", "blocks_release": True}
        return {**base, "status": "EXCLUDED", "blocks_release": False}

    if not docs_verified or not docs_verified_at or not docs_source:
        return {**base, "status": "DOCS_UNVERIFIED", "blocks_release": True}

    return {**base, "status": "VERIFIED", "blocks_release": False}


def evaluate_exclusion_list(path: Path) -> dict:
    if not path.exists():
        return {
            "status": "MISSING_EXCLUSION_LIST",
            "blocks_release": True,
            "n_entries": 0,
            "path": str(path),
        }
    body = json.loads(path.read_text(encoding="utf-8"))
    entries = body.get("entries") or []
    addrs = []
    for e in entries:
        a = (e.get("address") or "").lower()
        if not (a.startswith("0x") and len(a) == 42):
            return {
                "status": "INVALID_EXCLUSION_ENTRY",
                "blocks_release": True,
                "n_entries": len(entries),
                "path": str(path),
                "bad": e,
            }
        addrs.append(a)
    if len(addrs) < 10:
        return {
            "status": "EXCLUSION_LIST_TOO_SHORT",
            "blocks_release": True,
            "n_entries": len(addrs),
            "path": str(path),
        }
    if len(set(addrs)) != len(addrs):
        return {
            "status": "EXCLUSION_LIST_DUPLICATES",
            "blocks_release": True,
            "n_entries": len(addrs),
            "path": str(path),
        }
    return {
        "status": "EXCLUSION_LIST_OK",
        "blocks_release": False,
        "n_entries": len(addrs),
        "path": str(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify MEV-cluster declarations")
    parser.add_argument(
        "--input",
        default="config/bridge_stufe_a_v3_mev_cluster_candidates.json",
    )
    parser.add_argument(
        "--output",
        default="bridge_stufe_a_v3_mev_cluster_verification_gate.json",
    )
    args = parser.parse_args()

    body = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = [evaluate_chain(c) for c in body.get("chains", [])]
    excl_path = Path(body.get("exclusion_list") or "config/bridge_stufe_a_v3_mev_cluster_exclusion_list.json")
    excl = evaluate_exclusion_list(excl_path)
    all_verified = (not any(r["blocks_release"] for r in rows)) and (not excl["blocks_release"])
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": rows,
        "exclusion_list": excl,
        "all_verified": all_verified,
        "resolver_release": "RELEASED" if all_verified else "BLOCKED",
    }
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"all_verified={all_verified} resolver_release={out['resolver_release']}")
    print(f"exclusion_list={excl['status']} n={excl.get('n_entries')}")
    for row in rows:
        flag = "BLOCKER" if row["blocks_release"] else row["status"]
        print(f"  {flag} {row['chain']} {row.get('role')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
