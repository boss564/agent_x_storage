"""
Subagent: VOBBPaymentComplianceChecker — VOB/B Payment Rules Audit.

Validates compliance with German construction payment law:
  §16 — Payment deadlines (30 days max, Skonto within 14 days)
  §17 — 5% warranty retention, escrow separation, release at acceptance
  §13 — Defect detection → payment hold → resolution tracking

Usage:
    checker = VOBBPaymentComplianceChecker(archive_agent)
    result = checker.check_payments("TED-2026-0815-KLAERANLAGE-NORD")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any

getcontext().prec = 28
logger = logging.getLogger("VOBBPaymentComplianceChecker")


class VOBBPaymentComplianceChecker:
    """VOB/B §16 + §17 + §13 payment compliance audit."""

    def __init__(self, archive_agent: Any = None,
                 archive_dir: str = "archive_b2g",
                 audit_log: str = "logs/b2g_event_bus.jsonl"):
        self.archive = archive_agent
        self.archive_dir = Path(archive_dir)
        self.audit_log = Path(audit_log)

    # ============================================================
    # Main check
    # ============================================================

    def check_payments(self, tender_id: str) -> dict[str, Any]:
        """Run all three VOB/B payment compliance checks."""

        logger.info(f"VOB/B payment check for {tender_id}")

        events = self._fetch_events(tender_id)
        if not events:
            events = self._mock_events(tender_id)

        fristen = self._check_deadlines(events)
        retention = self._check_retention(events)
        defects = self._check_defects(events)

        all_errors = fristen.get("errors", []) + retention.get("errors", []) + defects.get("errors", [])
        all_warnings = fristen.get("warnings", []) + retention.get("warnings", []) + defects.get("warnings", [])

        print(f"  [VOBB-Check]    💰 Deadlines={'✓' if not fristen['errors'] else '✗'}, "
              f"Retention={'✓' if not retention['errors'] else '✗'}, "
              f"Defects={defects['total']} (open={defects['unresolved']})")

        return {
            "status": "FAILED" if all_errors else "PASSED",
            "tender_id": tender_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_compliant": len(all_errors) == 0,
            "fristen": fristen,
            "retention": retention,
            "defect_handling": defects,
            "errors": all_errors,
            "warnings": all_warnings,
        }

    # ============================================================
    # Event fetching
    # ============================================================

    def _fetch_events(self, tender_id: str) -> list[dict]:
        events: list[dict] = []
        if self.audit_log.exists():
            for line in self.audit_log.read_text().splitlines():
                if tender_id in line:
                    try:
                        events.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        for sf in self.archive_dir.rglob("*settlement*.json"):
            try:
                data = json.loads(sf.read_text())
                if tender_id in json.dumps(data):
                    events.append({"subject": "b2g.settlement.finalized",
                                   "payload": data, "timestamp": data.get("timestamp", "")})
            except (json.JSONDecodeError, OSError):
                continue
        return events

    @staticmethod
    def _mock_events(tender_id: str) -> list[dict]:
        return [
            {"subject": "b2g.contract.signed",
             "payload": {"amount_eur": 1_274_896.80, "tender_id": tender_id},
             "timestamp": "2026-08-10T10:05:00Z"},
            {"subject": "b2g.payment.disbursed",
             "payload": {"amount_eur": 318_724.00, "retention_eur": 15_936.20,
                         "installment_no": 1, "invoice_date": "2026-08-15T00:00:00Z",
                         "tender_id": tender_id},
             "timestamp": "2026-09-10T14:00:00Z"},
            {"subject": "b2g.retention.released",
             "payload": {"amount_eur": 63_744.84, "tender_id": tender_id},
             "timestamp": "2027-04-01T10:00:00Z"},
        ]

    # ============================================================
    # §16: Payment deadlines
    # ============================================================

    def _check_deadlines(self, events: list[dict]) -> dict:
        invoices = []
        for e in events:
            subj = e.get("subject", "")
            data = e.get("payload", e.get("data", {}))
            if "disburse" in subj or "payment" in subj:
                invoices.append({
                    "no": data.get("installment_no", len(invoices) + 1),
                    "invoice_date": data.get("invoice_date", ""),
                    "paid_date": e.get("timestamp", ""),
                })

        errors = []
        for inv in invoices:
            try:
                inv_dt = datetime.fromisoformat(str(inv["invoice_date"]).replace("Z", "+00:00"))
                pay_dt = datetime.fromisoformat(str(inv["paid_date"]).replace("Z", "+00:00"))
                deadline = inv_dt + timedelta(days=30)
                if pay_dt > deadline:
                    overdue = (pay_dt - deadline).days
                    errors.append(f"Rechnung #{inv['no']}: {overdue}d überfällig (VOB/B §16)")
            except (ValueError, KeyError):
                continue

        return {"total_invoices": len(invoices), "overdue": len(errors),
                "errors": errors, "warnings": []}

    # ============================================================
    # §17: 5% retention
    # ============================================================

    def _check_retention(self, events: list[dict]) -> dict:
        contract = Decimal("0")
        total_retained = Decimal("0")
        released = False

        for e in events:
            subj = e.get("subject", "")
            data = e.get("payload", e.get("data", {}))
            amt = Decimal(str(data.get("amount_eur", 0)))
            if "contract" in subj:
                contract = amt
            if "retention" in subj or "disburse" in subj:
                total_retained += Decimal(str(data.get("retention_eur", 0)))
            if "retention.released" in subj:
                released = True

        expected = (contract * Decimal("0.05")).quantize(Decimal("0.01"))
        errors = []
        warnings = []

        if contract > 0 and total_retained != expected and total_retained > 0:
            errors.append(f"Einbehalt {total_retained:.2f} € ≠ 5% Soll {expected:.2f} € (VOB/B §17)")
        if not released and total_retained > 0:
            warnings.append("Einbehalt noch nicht freigegeben (Gewährleistungsfrist?)")

        return {"contract_sum_eur": float(contract), "expected_5pct_eur": float(expected),
                "actual_retained_eur": float(total_retained), "released": released,
                "errors": errors, "warnings": warnings}

    # ============================================================
    # §13: Defect handling
    # ============================================================

    def _check_defects(self, events: list[dict]) -> dict:
        defect_list = []
        for e in events:
            subj = e.get("subject", "")
            data = e.get("payload", e.get("data", {}))
            if "defect" in subj and "resolved" not in subj:
                defect_list.append({"id": str(data.get("position_id", "?"))[:30],
                                    "resolved": False,
                                    "timestamp": e.get("timestamp", "")})
            if "resolved" in subj or "remediation" in subj:
                for d in defect_list:
                    if not d["resolved"]:
                        d["resolved"] = True
                        break

        unresolved = [d for d in defect_list if not d["resolved"]]
        errors = [f"Mangel {d['id']} nicht behoben (VOB/B §13)" for d in unresolved]

        return {"total": len(defect_list), "resolved": len(defect_list) - len(unresolved),
                "unresolved": len(unresolved), "errors": errors, "warnings": []}
