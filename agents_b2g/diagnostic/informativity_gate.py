"""Informativitäts-Gate — Pre-Reg §4 (Wave 38).

Checks encoding properties (tertile dispersion, occupancy saturation).
No CTE, no permutation, no verdict.
"""

from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents_b2g.diagnostic.config import (
    CANDIDATE_IDS,
    OCC_SAT,
    PRE_REG_PATH,
    V3_ERGEBNIS_DEFAULT,
    V3_INTEGRITY_GATE_DEFAULT,
)

PROTOCOL_SENTENCE_V3_S8 = (
    "Ein Gate, das Kandidaten nicht trotz, sondern wegen Sättigung durchwinkt "
    "(coverage_ratio = 1.0 als Gütesiegel), belohnt genau die Eigenschaft, die "
    "sie als binäre Konditionierer wertlos macht — Bestehen und Unbrauchbarkeit "
    "korrelieren. Neben Abdeckung braucht jede binäre Belegungskodierung ein Gate "
    "auf Varianz oder Terzil-Dispersion."
)

# V3 capture paths (read-only); loaded only by gate runner, not orchestrator skeleton.
V3_CAPTURE_FILES: dict[str, str] = {
    "chainlink": "bridge_stufe_a_v3_chainlink.jsonl",
    "intent_relayers": "bridge_stufe_a_v3_intent_relayers.jsonl",
    "liquidations": "bridge_stufe_a_v3_liquidations.jsonl",
    "stablecoin_mint_burn": "bridge_stufe_a_v3_stablecoin_mint_burn.jsonl",
    "mev_cluster": "bridge_stufe_a_v3_mev_cluster.jsonl",
}


def _encode_z_neu_tertile(occ: list[int]) -> list[int]:
    """Same tertile scheme as V3 pipeline (no CTE import)."""
    import sys

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from bridge_stufe_a_stats import apply_tertiles, tertile_edges

    vals = [float(v) for v in occ]
    edges = tertile_edges(vals)
    return apply_tertiles(vals, edges)


def _load_occupancy(input_dir: Path, candidate_id: str) -> tuple[list[int], int]:
    import sys

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from bridge_stufe_a_v3_config import DEFAULT_INPUTS
    from bridge_stufe_a_v3_load import load_candidate_occupancy

    rel = DEFAULT_INPUTS.get(candidate_id) or V3_CAPTURE_FILES[candidate_id]
    path = input_dir / rel
    return load_candidate_occupancy(candidate_id, path)


def _load_events_per_minute(input_dir: Path, candidate_id: str) -> list[int]:
    """Event counts per minute bin (descriptive std, Pre-Reg §4)."""
    import sys

    scripts = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from bridge_stufe_a_v3_config import DEFAULT_INPUTS
    from bridge_stufe_a_v3_load import N_BINS, _minute_index, load_mev_occupancy

    rel = DEFAULT_INPUTS.get(candidate_id) or V3_CAPTURE_FILES[candidate_id]
    path = input_dir / rel
    counts = [0] * N_BINS

    if candidate_id == "mev_cluster":
        occ, _ = load_mev_occupancy(path)
        return [1 if x else 0 for x in occ]

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if candidate_id == "chainlink":
                excluded = {("ethereum", "USDT/USD")}
                feed = str(rec.get("feed") or "")
                chain = str(rec.get("chain") or "")
                if (chain, feed) in excluded:
                    continue
            ts = rec.get("timestamp", rec.get("blockTime"))
            if ts is None:
                continue
            idx = _minute_index(float(ts))
            if idx is None:
                continue
            counts[idx] += 1
    return counts


def _tertile_stats(occ: list[int]) -> dict[str, Any]:
    encoded = _encode_z_neu_tertile(occ)
    bin_counts: dict[str, int] = {"0": 0, "1": 0, "2": 0, "-1": 0}
    for b in encoded:
        key = str(b)
        bin_counts[key] = bin_counts.get(key, 0) + 1
    distinct = sum(1 for k in ("0", "1", "2") if bin_counts.get(k, 0) > 0)
    return {
        "n_distinct_tertile_bins": distinct,
        "tertile_bin_counts": {k: bin_counts[k] for k in ("0", "1", "2")},
        "n_dropped_bins": bin_counts.get("-1", 0),
    }


def _encoding_status(
    *,
    occupancy_rate: float,
    n_distinct_tertile_bins: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if occupancy_rate >= OCC_SAT:
        reasons.append("occupancy_saturated")
    if n_distinct_tertile_bins < 2:
        reasons.append("tertile_collapsed")
    if reasons:
        return "INERT_ENCODING", reasons
    return "OK", []


def run_informativity_gate(
    *,
    input_dir: Path,
    integrity_gate_path: Path,
    v3_ergebnis_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run Pre-Reg §4 gate; write JSON artifact if output_path set."""
    blockers: list[str] = []

    if not integrity_gate_path.exists():
        blockers.append(f"missing_integrity_gate:{integrity_gate_path}")
        integrity_body: dict[str, Any] = {}
    else:
        integrity_body = json.loads(integrity_gate_path.read_text(encoding="utf-8"))
        if integrity_body.get("status") != "PASS":
            blockers.append(f"integrity_gate_status:{integrity_body.get('status')}")

    if not v3_ergebnis_path.exists():
        blockers.append(f"missing_v3_ergebnis:{v3_ergebnis_path}")
        v3_verdict = None
    else:
        v3_body = json.loads(v3_ergebnis_path.read_text(encoding="utf-8"))
        v3_verdict = v3_body.get("verdict")
        if v3_verdict != "V3_PERSISTENZ":
            blockers.append(f"v3_verdict:{v3_verdict}")

    candidates: dict[str, Any] = {}
    for cid in CANDIDATE_IDS:
        rel = V3_CAPTURE_FILES[cid]
        cap_path = input_dir / rel
        if not cap_path.exists():
            blockers.append(f"missing_capture:{cid}:{rel}")
            continue

        occ, n_events_raw = _load_occupancy(input_dir, cid)
        n_occupied = sum(occ)
        occupancy_rate = round(n_occupied / len(occ), 6) if occ else 0.0
        tstats = _tertile_stats(occ)
        epm = _load_events_per_minute(input_dir, cid)
        epm_nonzero = [x for x in epm if x > 0]
        epm_std = (
            round(statistics.pstdev(epm), 6)
            if len(epm) > 1 and any(x != epm[0] for x in epm)
            else 0.0
        )
        enc_status, reasons = _encoding_status(
            occupancy_rate=occupancy_rate,
            n_distinct_tertile_bins=tstats["n_distinct_tertile_bins"],
        )
        candidates[cid] = {
            "capture_file": rel,
            "n_events_raw": n_events_raw,
            "n_bins": len(occ),
            "n_occupied": n_occupied,
            "occupancy_rate": occupancy_rate,
            **tstats,
            "events_per_minute_std": epm_std,
            "events_per_minute_max": max(epm) if epm else 0,
            "occupied_minute_event_std": (
                round(statistics.pstdev(epm_nonzero), 6) if len(epm_nonzero) > 1 else 0.0
            ),
            "encoding_status": enc_status,
            "inert_reasons": reasons,
            "perm_testable": occupancy_rate < OCC_SAT,
        }

    n_inert = sum(1 for c in candidates.values() if c["encoding_status"] == "INERT_ENCODING")
    n_ok = sum(1 for c in candidates.values() if c["encoding_status"] == "OK")
    perm_testable = [cid for cid, c in candidates.items() if c.get("perm_testable")]

    status = "BLOCKED" if blockers else "PASS"

    body: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pre_reg": PRE_REG_PATH,
        "protocol_sentence_v3_section8": PROTOCOL_SENTENCE_V3_S8,
        "status": status,
        "blockers": blockers,
        "integrity_gate_ref": str(integrity_gate_path),
        "v3_ergebnis_ref": str(v3_ergebnis_path),
        "v3_verdict_required": "V3_PERSISTENZ",
        "v3_verdict_observed": v3_verdict,
        "thresholds": {
            "OCC_SAT": OCC_SAT,
            "min_distinct_tertile_bins": 2,
        },
        "candidates": candidates,
        "summary": {
            "n_candidates": len(candidates),
            "n_inert_encoding": n_inert,
            "n_ok": n_ok,
            "perm_testable_candidates": perm_testable,
            "note": "Gate checks encoding only — not cleansing effect (no CTE).",
        },
    }

    if output_path is not None:
        output_path.write_text(json.dumps(body, indent=2), encoding="utf-8")

    return body
