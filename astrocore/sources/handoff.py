"""Handoff write lock — derived PhaseSignals, never the detector JSONL.

Layer 1 (this module): raise order_send_forbidden before any append.
Layer 2 (ops): optional read-only mount / chmod of gap_reports.jsonl and
news_scores.jsonl for the :06/:07 processes. Detector :00/:05 still appends.

A field `order_send: false` is not a check. This function is.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

DETECTOR_BASENAMES = frozenset({"gap_reports.jsonl", "news_scores.jsonl"})
DERIVED_DIR = "phase_signals"
WRITEBACK_MSG = "order_send_forbidden: handoff must not write back to detector JSONL"
DERIVED_MSG = "order_send_forbidden: derived PhaseSignals belong under .../phase_signals/"
DIAGNOSTIC_MSG = "order_send_forbidden: PhaseSignal JSONL is diagnostic_only"


def same_file(left: Path, right: Path) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return Path(left) == Path(right)


def assert_handoff_output(source: Path, dest: Path) -> None:
    """Reject write-back to the detector file. Destination must be derived."""
    dest = Path(dest)
    source = Path(source)
    if dest.name in DETECTOR_BASENAMES:
        raise RuntimeError(WRITEBACK_MSG)
    if same_file(source, dest):
        raise RuntimeError(WRITEBACK_MSG)
    if dest.parent.name != DERIVED_DIR:
        raise RuntimeError(DERIVED_MSG)


def assert_diagnostic_rows(rows: Sequence[Mapping]) -> None:
    for row in rows:
        if row.get("live_execution") is True or row.get("order_send") is True:
            raise RuntimeError(DIAGNOSTIC_MSG)
