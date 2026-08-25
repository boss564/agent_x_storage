"""Hard gate for Chainlink candidate verification before resolver/capture.

Stage 1 is manual and declared in the candidate file:
- docs_verified: bool
- docs_verified_at: ISO date
- docs_source: authoritative URL/reference

Feed states (see Pre-Reg §3.0.1):
- verified: proxy + docs_verified=true → testable, not a blocker
- excluded: documented waiver with adaptation_reason + Pre-Reg ref → V3_UNTESTBAR, not a blocker
- missing_candidate: no address yet → blocker
- substituted: replaced feed; substitute must be verified

This script enforces:
- missing_candidate / incomplete excluded blocks resolver release
- verified feeds need docs_verified=true and non-null proxy_candidate
- output gate file with all_verified flag
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

PREREG_MARKERS = ("Pre-Reg", "pre-reg", "BRIDGE_STUFE_A_V3_PREREG")


def _feed_state(feed: dict) -> str:
    status = feed.get("status")
    vc = feed.get("verification_status")
    if status in ("verified", "excluded", "missing_candidate", "substituted"):
        return status
    if vc in ("verified", "excluded", "missing_candidate", "substituted"):
        return vc
    if feed.get("proxy_candidate") in (None, ""):
        return "missing_candidate"
    return "unverified"


def _excluded_has_prereg_ref(adaptation_reason: str, docs_source: str) -> bool:
    text = f"{adaptation_reason} {docs_source}"
    return any(marker in text for marker in PREREG_MARKERS)


def _evaluate_feed(feed: dict, chain: str) -> dict:
    state = _feed_state(feed)
    proxy = feed.get("proxy_candidate")
    docs_verified = bool(feed.get("docs_verified", False))
    docs_verified_at = feed.get("docs_verified_at")
    docs_source = feed.get("docs_source")
    adaptation_reason = feed.get("adaptation_reason")

    if state == "excluded":
        if not adaptation_reason or not docs_source or not docs_verified_at:
            return {
                "feed": feed["name"],
                "chain": chain,
                "proxy_candidate": proxy,
                "feed_state": "excluded",
                "docs_verified": docs_verified,
                "docs_verified_at": docs_verified_at,
                "docs_source": docs_source,
                "adaptation_reason": adaptation_reason,
                "status": "EXCLUDED_INCOMPLETE",
                "reason": "excluded_missing_required_fields",
                "candidate_status": "V3_UNTESTBAR",
                "blocks_release": True,
            }
        if not _excluded_has_prereg_ref(str(adaptation_reason), str(docs_source)):
            return {
                "feed": feed["name"],
                "chain": chain,
                "proxy_candidate": proxy,
                "feed_state": "excluded",
                "docs_verified": docs_verified,
                "docs_verified_at": docs_verified_at,
                "docs_source": docs_source,
                "adaptation_reason": adaptation_reason,
                "status": "EXCLUDED_NO_PREREG_REF",
                "reason": "excluded_missing_prereg_reference",
                "candidate_status": "V3_UNTESTBAR",
                "blocks_release": True,
            }
        return {
            "feed": feed["name"],
            "chain": chain,
            "proxy_candidate": proxy,
            "feed_state": "excluded",
            "docs_verified": docs_verified,
            "docs_verified_at": docs_verified_at,
            "docs_source": docs_source,
            "adaptation_reason": adaptation_reason,
            "status": "EXCLUDED",
            "reason": "documented_exclusion",
            "candidate_status": "V3_UNTESTBAR",
            "blocks_release": False,
        }

    if state == "missing_candidate" or proxy in (None, ""):
        return {
            "feed": feed["name"],
            "chain": chain,
            "proxy_candidate": proxy,
            "feed_state": "missing_candidate",
            "docs_verified": docs_verified,
            "docs_verified_at": docs_verified_at,
            "docs_source": docs_source,
            "status": "MISSING_CANDIDATE",
            "reason": "missing_candidate",
            "candidate_status": "V3_UNTESTBAR",
            "blocks_release": True,
        }

    if state == "substituted":
        substitute_for = feed.get("substitute_for")
        if not substitute_for:
            return {
                "feed": feed["name"],
                "chain": chain,
                "proxy_candidate": proxy,
                "feed_state": "substituted",
                "docs_verified": docs_verified,
                "docs_verified_at": docs_verified_at,
                "docs_source": docs_source,
                "status": "SUBSTITUTED_INCOMPLETE",
                "reason": "substituted_missing_substitute_for",
                "candidate_status": "V3_UNTESTBAR",
                "blocks_release": True,
            }

    if not docs_verified:
        return {
            "feed": feed["name"],
            "chain": chain,
            "proxy_candidate": proxy,
            "feed_state": state,
            "docs_verified": docs_verified,
            "docs_verified_at": docs_verified_at,
            "docs_source": docs_source,
            "status": "DOCS_UNVERIFIED",
            "reason": "docs_verified_false",
            "candidate_status": "V3_UNTESTBAR",
            "blocks_release": True,
        }

    if not docs_verified_at or not docs_source:
        return {
            "feed": feed["name"],
            "chain": chain,
            "proxy_candidate": proxy,
            "feed_state": state,
            "docs_verified": docs_verified,
            "docs_verified_at": docs_verified_at,
            "docs_source": docs_source,
            "status": "DOCS_METADATA_MISSING",
            "reason": "docs_verified_at_or_source_missing",
            "candidate_status": "V3_UNTESTBAR",
            "blocks_release": True,
        }

    return {
        "feed": feed["name"],
        "chain": chain,
        "proxy_candidate": proxy,
        "feed_state": state if state != "unverified" else "verified",
        "docs_verified": docs_verified,
        "docs_verified_at": docs_verified_at,
        "docs_source": docs_source,
        "status": "VERIFIED",
        "reason": "ok",
        "candidate_status": "PENDING_ONCHAIN",
        "blocks_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Chainlink candidate declarations")
    parser.add_argument("--input", default="config/bridge_stufe_a_v3_chainlink_proxy_candidates.json")
    parser.add_argument("--output", default="bridge_stufe_a_v3_chainlink_verification_gate.json")
    args = parser.parse_args()

    body = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = []
    all_verified = True

    for chain, cfg in body.get("chains", {}).items():
        for feed in cfg.get("feeds", []):
            row = _evaluate_feed(feed, chain)
            rows.append(row)
            if row["blocks_release"]:
                all_verified = False

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": rows,
        "all_verified": all_verified,
        "resolver_release": "RELEASED" if all_verified else "BLOCKED",
        "chainlink_candidate_status": "PENDING_ONCHAIN" if all_verified else "V3_UNTESTBAR",
    }
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"all_verified={out['all_verified']} resolver_release={out['resolver_release']}")
    if not all_verified:
        blockers = [r for r in rows if r["blocks_release"]]
        for row in blockers:
            print(f"  BLOCKER {row['chain']} {row['feed']}: {row['status']} ({row['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
