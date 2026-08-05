"""
Subagent: ArchiveQuery — reads GoBD-compliant JSONL audit archives.

Supports full-text search, project/tender filtering, date range queries,
and aggregation across the complete B2G event history.

Usage:
    archive = ArchiveQuerySubagent()
    result = archive.search_awards(tender_id_filter="TED-2026-0815")
    result = archive.query_events(project_id="PROJ-...", event_types=["payment", "invoice"])
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict
from typing import Any

logger = logging.getLogger("ArchiveQuerySubagent")

DEFAULT_AUDIT_LOG = Path("logs/b2g_event_bus.jsonl")
ARCHIVE_DIR = Path("archive_b2g")


class ArchiveQuerySubagent:
    """Reads and queries the GoBD audit archive (JSONL + settlement JSON)."""

    def __init__(self, audit_log: Path | None = None):
        self.audit_log = audit_log or DEFAULT_AUDIT_LOG
        self._archive_dir = ARCHIVE_DIR

    # ============================================================
    # Event log queries
    # ============================================================

    def search_awards(self, tender_id_filter: str | None = None,
                      project_id_filter: str | None = None,
                      limit: int = 50) -> dict:
        """Full-text search across audit log for tender/project events."""
        awards = []
        if not self.audit_log.exists():
            return {"awards": [], "total": 0, "query": {"tender": tender_id_filter, "project": project_id_filter}}

        for line in _tail_file(self.audit_log, limit * 3):
            try:
                entry = json.loads(line.strip())
                payload = entry.get("payload", {})
                tid = payload.get("tender_id", "")
                pid = payload.get("project_id", "")

                if tender_id_filter and tender_id_filter not in tid:
                    continue
                if project_id_filter and project_id_filter not in pid:
                    continue

                awards.append({
                    "msg_id": entry.get("msg_id"),
                    "subject": entry.get("subject"),
                    "timestamp": entry.get("timestamp"),
                    "tender_id": tid,
                    "project_id": pid,
                    **payload,
                })
            except json.JSONDecodeError:
                continue
            if len(awards) >= limit:
                break

        return {"awards": awards, "total": len(awards),
                "query": {"tender": tender_id_filter, "project": project_id_filter}}

    def query_events(self, project_id: str = "", subject_filter: str = "",
                     date_from: str = "", date_to: str = "",
                     limit: int = 100) -> dict:
        """Query events with filters."""
        results = []
        if not self.audit_log.exists():
            return {"events": [], "total": 0}

        for line in _tail_file(self.audit_log, limit * 5):
            try:
                entry = json.loads(line.strip())
                ts = entry.get("timestamp", "")
                subj = entry.get("subject", "")
                payload = entry.get("payload", {})

                if subject_filter and subject_filter not in subj:
                    continue
                if project_id and project_id not in payload.get("project_id", ""):
                    continue
                if date_from and ts < date_from:
                    continue
                if date_to and ts > date_to:
                    continue

                results.append(entry)
            except json.JSONDecodeError:
                continue
            if len(results) >= limit:
                break

        return {"events": results, "total": len(results)}

    # ============================================================
    # Aggregate queries
    # ============================================================

    def aggregate_by_subject(self) -> dict:
        """Count events by subject type."""
        counts: dict[str, int] = defaultdict(int)
        if not self.audit_log.exists():
            return {"subject_counts": dict(counts)}

        for line in _tail_file(self.audit_log, 10000):
            try:
                entry = json.loads(line.strip())
                subj = entry.get("subject", "unknown")
                counts[subj] += 1
            except json.JSONDecodeError:
                continue

        return {"subject_counts": dict(sorted(counts.items(), key=lambda x: -x[1]))}

    def get_bho_ledger(self, tender_id: str) -> dict:
        """Reconstruct BHO ledger for a tender from audit events."""
        deposits = 0.0
        paid = 0.0
        retained = 0.0
        payment_count = 0

        if self.audit_log.exists():
            for line in _tail_file(self.audit_log, 20000):
                try:
                    entry = json.loads(line.strip())
                    payload = entry.get("payload", {})
                    if tender_id not in payload.get("tender_id", ""):
                        continue
                    subj = entry.get("subject", "")

                    if "deposit" in subj or "sepa.in" in subj:
                        deposits += float(payload.get("amount_eur", 0))
                    elif "disbursed" in subj or "payment.released" in subj:
                        paid += float(payload.get("amount_eur", 0))
                    elif "retention" in subj or "retained" in subj:
                        retained += float(payload.get("amount_eur", 0))
                        payment_count += 1
                except (json.JSONDecodeError, ValueError):
                    continue

        return {
            "tender_id": tender_id,
            "total_deposits_eur": round(deposits, 2),
            "total_paid_eur": round(paid, 2),
            "total_retained_eur": round(retained, 2),
            "vault_balance_eur": round(deposits - paid - retained, 2),
            "reconciliation_delta": round(deposits - paid - retained, 2),
            "payment_count": payment_count,
            "queried_at": datetime.now(timezone.utc).isoformat(),
        }

    def search_settlements(self, project_id_filter: str = "",
                           limit: int = 20) -> list[dict]:
        """Find settlement JSON files in the archive."""
        settlements = []
        settlement_dir = self._archive_dir
        for sf in settlement_dir.rglob("*settlement*.json"):
            try:
                data = json.loads(sf.read_text())
                if project_id_filter and project_id_filter not in str(sf):
                    continue
                settlements.append({"file": str(sf), "data": data})
            except (json.JSONDecodeError, OSError):
                continue
            if len(settlements) >= limit:
                break
        return settlements

    def stats(self) -> dict:
        """Return archive statistics."""
        log_size = self.audit_log.stat().st_size if self.audit_log.exists() else 0
        line_count = sum(1 for _ in _tail_file(self.audit_log, 0)) if self.audit_log.exists() else 0
        agg = self.aggregate_by_subject()
        return {
            "log_file": str(self.audit_log),
            "size_bytes": log_size,
            "event_count": line_count,
            "subject_distribution": agg.get("subject_counts", {}),
            "settlements_found": len(self.search_settlements()),
        }


def _tail_file(path: Path, max_lines: int = 0) -> list[str]:
    """Read file lines, optionally limited (tail-like)."""
    try:
        with open(path) as f:
            lines = f.readlines()
        if max_lines > 0 and len(lines) > max_lines:
            return lines[-max_lines:]
        return lines
    except OSError:
        return []
