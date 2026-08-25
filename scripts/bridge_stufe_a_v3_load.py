"""Load V3 candidate captures into 1-minute binary occupancy (Pre-Reg §4.3)."""

from __future__ import annotations

import json
from pathlib import Path

from bridge_stufe_a_config import WINDOW_END_UTC, WINDOW_START_UTC, n_minute_bins
from bridge_stufe_a_stats import WINDOW_END_TS, WINDOW_START_TS
from bridge_stufe_a_v3_config import CHAINLINK_EXCLUDED, CANDIDATE_IDS

N_BINS = n_minute_bins()
START_TS = int(WINDOW_START_TS)
END_TS = int(WINDOW_END_TS)


def _empty_occupancy() -> list[int]:
    return [0] * N_BINS


def _minute_index(ts: float) -> int | None:
    if ts < WINDOW_START_TS or ts > WINDOW_END_TS:
        return None
    idx = int((ts - WINDOW_START_TS) // 60)
    if 0 <= idx < N_BINS:
        return idx
    return None


def _or_timestamp(path: Path, *, skip_row=None) -> tuple[list[int], int]:
    occ = _empty_occupancy()
    n_events = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if skip_row and skip_row(rec):
                continue
            ts = rec.get("timestamp", rec.get("blockTime"))
            if ts is None:
                continue
            idx = _minute_index(float(ts))
            if idx is None:
                continue
            n_events += 1
            occ[idx] = 1
    return occ, n_events


def load_mev_occupancy(path: Path) -> tuple[list[int], int]:
    """Sparse occupied-minute series (already deduped)."""
    occ = _empty_occupancy()
    n_lines = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "minute" in rec:
                minute = int(rec["minute"])
                idx = minute - (START_TS // 60)
            elif "timestamp" in rec:
                idx = _minute_index(float(rec["timestamp"]))
            else:
                continue
            if idx is None or not 0 <= idx < N_BINS:
                continue
            occ[idx] = 1
            n_lines += 1
    return occ, n_lines


def load_chainlink_occupancy(path: Path) -> tuple[list[int], int]:
    excluded = set(CHAINLINK_EXCLUDED)

    def skip(rec: dict) -> bool:
        feed = str(rec.get("feed") or "")
        chain = str(rec.get("chain") or "")
        return (chain, feed) in excluded

    occ = _empty_occupancy()
    n_events = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if skip(rec):
                continue
            ts = rec.get("timestamp")
            if ts is None:
                continue
            idx = _minute_index(float(ts))
            if idx is None:
                continue
            n_events += 1
            occ[idx] = 1
    return occ, n_events


LOADERS = {
    "chainlink": load_chainlink_occupancy,
    "mev_cluster": load_mev_occupancy,
}


def load_candidate_occupancy(candidate_id: str, path: Path) -> tuple[list[int], int]:
    if candidate_id not in CANDIDATE_IDS:
        raise ValueError(f"unknown candidate {candidate_id}")
    loader = LOADERS.get(candidate_id)
    if loader:
        return loader(path)
    occ, n_events = _or_timestamp(path)
    return occ, n_events


def load_bridge_occupancy(path: Path) -> tuple[list[int], int]:
    occ = _empty_occupancy()
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            ts = rec.get("blockTime", rec.get("timestamp"))
            if ts is None:
                continue
            idx = _minute_index(float(ts))
            if idx is None:
                continue
            n += 1
            occ[idx] = 1
    return occ, n


def occupancy_stats(occ: list[int]) -> dict:
    occupied = sum(occ)
    return {
        "n_bins": len(occ),
        "n_occupied": occupied,
        "occupancy_rate": round(occupied / len(occ), 6) if occ else 0.0,
    }
