"""Hard gate for liquidation pool candidates (Pre-Reg §3.0.2 Schicht A)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

PREREG_MARKERS = ("Pre-Reg", "pre-reg", "BRIDGE_STUFE_A_V3_PREREG", "§3.0.2")


def evaluate(pool: dict) -> dict:
    status = pool.get("status") or pool.get("verification_status")
    addr = pool.get("pool")
    docs_verified = bool(pool.get("docs_verified", False))
    docs_verified_at = pool.get("docs_verified_at")
    docs_source = pool.get("docs_source")
    reason_txt = pool.get("adaptation_reason") or ""

    if status == "excluded":
        ok_fields = bool(reason_txt and docs_source and docs_verified_at)
        ok_ref = any(m in f"{reason_txt} {docs_source}" for m in PREREG_MARKERS)
        if not ok_fields or not ok_ref:
            return {
                **_base(pool),
                "status": "EXCLUDED_INCOMPLETE",
                "blocks_release": True,
                "candidate_status": "V3_UNTESTBAR",
            }
        return {
            **_base(pool),
            "status": "EXCLUDED",
            "blocks_release": False,
            "candidate_status": "V3_UNTESTBAR",
        }

    if status == "missing_candidate" or addr in (None, ""):
        return {
            **_base(pool),
            "status": "MISSING_CANDIDATE",
            "blocks_release": True,
            "candidate_status": "V3_UNTESTBAR",
        }

    if not docs_verified or not docs_verified_at or not docs_source:
        return {
            **_base(pool),
            "status": "DOCS_UNVERIFIED",
            "blocks_release": True,
            "candidate_status": "V3_UNTESTBAR",
        }

    return {
        **_base(pool),
        "status": "VERIFIED",
        "blocks_release": False,
        "candidate_status": "PENDING_ONCHAIN",
    }


def _base(pool: dict) -> dict:
    return {
        "protocol": pool.get("protocol"),
        "chain": pool.get("chain"),
        "pool": pool.get("pool"),
        "docs_verified": bool(pool.get("docs_verified", False)),
        "docs_verified_at": pool.get("docs_verified_at"),
        "docs_source": pool.get("docs_source"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify liquidation pool declarations")
    parser.add_argument(
        "--input",
        default="config/bridge_stufe_a_v3_liquidation_pool_candidates.json",
    )
    parser.add_argument(
        "--output",
        default="bridge_stufe_a_v3_liquidation_verification_gate.json",
    )
    args = parser.parse_args()

    body = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = [evaluate(p) for p in body.get("pools", [])]
    all_verified = not any(r["blocks_release"] for r in rows)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": rows,
        "all_verified": all_verified,
        "resolver_release": "RELEASED" if all_verified else "BLOCKED",
    }
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"all_verified={all_verified} resolver_release={out['resolver_release']}")
    for row in rows:
        if row["blocks_release"]:
            print(f"  BLOCKER {row['chain']} {row['protocol']}: {row['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
