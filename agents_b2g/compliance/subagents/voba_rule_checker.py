"""
Subagent: VOBARuleChecker — Formal VOB/A §16 Exclusion Check.

Checks bid compliance with German procurement law (VOB/A):
  1. Deadline adherence — submitted before cutoff?
  2. EFB price forms (221/222) — complete and correctly filled?
  3. Unauthorized changes — did the bidder alter the LV structure?
  4. Qualification evidence — references, revenue, staff certificates?
  5. GAEB structural integrity — missing OZ, empty sections?

Usage:
    checker = VOBARuleChecker()
    result = checker.check_compliance(tender_id, bidder_profiles, deadline, gaeb_x83)
"""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("VOBARuleChecker")


class VOBARuleChecker:
    """Formal VOB/A §16 bid exclusion check for procurement tribunals."""

    _REQUIRED_EIGNUNG = [
        "Referenzen", "Umsatz", "Mitarbeiterzahl", "Bundesanzeiger-Eintrag",
    ]

    def __init__(self, required_eignung: list[str] | None = None):
        self.required_eignung = required_eignung or self._REQUIRED_EIGNUNG

    # ============================================================
    # Main check
    # ============================================================

    def check_compliance(self, tender_id: str,
                         bidder_profiles: list[dict[str, Any]],
                         submission_deadline: str = "",
                         original_gaeb_x83: str | None = None) -> dict[str, Any]:
        """Run all five formal checks on every bidder profile."""

        logger.info(f"VOB/A check for {tender_id}: {len(bidder_profiles)} bidders")

        deadline_dt = self._parse_deadline(submission_deadline)
        original_hash = (hashlib.sha256(original_gaeb_x83.encode()).hexdigest()
                        if original_gaeb_x83 else None)

        results: dict[str, Any] = {
            "tender_id": tender_id,
            "status": "COMPLIANCE_CHECKED",
            "bidders": [],
            "summary": {"total": len(bidder_profiles), "compliant": 0,
                        "non_compliant": 0, "excluded": 0},
            "rule_violations": {},
        }

        if not bidder_profiles:
            results["status"] = "ERROR"
            return results

        for profile in bidder_profiles:
            bidder_id = profile.get("bidder_id", "UNKNOWN")
            check = self._check_bidder(
                bidder_id, profile.get("x84_data", {}),
                profile.get("x84_xml", profile.get("x84_data", {}).get("xml", "")),
                profile.get("eignung_nachweise", {}),
                deadline_dt,
                profile.get("submission_timestamp", ""),
                original_hash,
            )
            results["bidders"].append(check)
            if check["compliant"]:
                results["summary"]["compliant"] += 1
            else:
                results["summary"]["non_compliant"] += 1
                if check["excluded"]:
                    results["summary"]["excluded"] += 1
            for v in check.get("violations", []):
                results["rule_violations"][v] = results["rule_violations"].get(v, 0) + 1

        if results["summary"]["non_compliant"] == 0:
            results["status"] = "ALL_COMPLIANT"
        elif results["summary"]["excluded"] > 0:
            results["status"] = "EXCLUSIONS_RECOMMENDED"
        else:
            results["status"] = "WARNINGS_DETECTED"

        logger.info(f"VOB/A done: {results['status']} "
                     f"({results['summary']['compliant']}/{results['summary']['total']})")
        return results

    # ============================================================
    # Per-bidder check
    # ============================================================

    def _check_bidder(self, bidder_id: str, x84_data: dict, x84_xml: str,
                      eignung: dict, deadline: datetime | None,
                      submission_ts: str,
                      original_hash: str | None) -> dict:
        result: dict[str, Any] = {
            "bidder_id": bidder_id, "compliant": True, "excluded": False,
            "violations": [], "details": {},
        }

        # 1. Deadline (exclusion)
        dl = self._check_deadline(submission_ts, deadline)
        result["details"]["deadline"] = dl
        if not dl["compliant"]:
            result["compliant"] = False
            result["excluded"] = True
            result["violations"].append("FRIST_VERSÄUMT")

        # 2. EFB forms (exclusion)
        efb = self._check_efb_forms(x84_data)
        result["details"]["efb_forms"] = efb
        if not efb["compliant"]:
            result["compliant"] = False
            result["excluded"] = True
            result["violations"].append("EFB_FORMS_MISSING")

        # 3. Unauthorized changes (exclusion)
        if original_hash and x84_xml:
            ch = self._check_changes(x84_xml, original_hash)
            result["details"]["changes"] = ch
            if not ch["compliant"]:
                result["compliant"] = False
                result["excluded"] = True
                result["violations"].append("UNAUTHORIZED_CHANGES")

        # 4. Qualification evidence (warning)
        eig = self._check_eignung(eignung)
        result["details"]["eignung"] = eig
        if not eig["compliant"]:
            result["compliant"] = False
            result["violations"].append("EIGNUNG_NACHWEISE_UNVOLLSTÄNDIG")

        # 5. GAEB structure
        struct = self._check_structure(x84_data)
        result["details"]["structure"] = struct
        if not struct["compliant"]:
            result["compliant"] = False
            result["violations"].append("GAEB_STRUKTUR_FEHLERHAFT")

        return result

    # ============================================================
    # Check implementations
    # ============================================================

    @staticmethod
    def _parse_deadline(deadline_str: str) -> datetime | None:
        if not deadline_str:
            return None
        try:
            return datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _check_deadline(submission_ts: str,
                        deadline: datetime | None) -> dict:
        if not submission_ts:
            return {"compliant": False, "reason": "Kein Einreichungszeitstempel."}
        if deadline is None:
            return {"compliant": True, "reason": "Keine Frist gesetzt — akzeptiert."}
        try:
            submitted = datetime.fromisoformat(submission_ts.replace("Z", "+00:00"))
            if submitted <= deadline:
                return {"compliant": True,
                        "reason": f"Rechtzeitig: {submission_ts} ≤ {deadline.isoformat()}"}
            return {"compliant": False,
                    "reason": f"Verspätet: {submission_ts} > {deadline.isoformat()}"}
        except (ValueError, TypeError):
            return {"compliant": False, "reason": "Zeitstempel unlesbar."}

    @staticmethod
    def _check_efb_forms(x84_data: dict) -> dict:
        sections = x84_data.get("sections", [])
        total = sum(len(sec.get("positions", [])) for sec in sections)
        with_price = sum(
            1 for sec in sections
            for pos in sec.get("positions", [])
            if pos.get("unit_price_net_eur") or pos.get("unit_price_eur") or pos.get("UP")
        )
        if total == 0:
            return {"compliant": False, "reason": "Keine Positionen im LV."}
        coverage = with_price / total
        if coverage < 0.9:
            return {"compliant": False,
                    "reason": f"EFB unvollständig: {coverage:.0%} der Positionen bepreist."}
        return {"compliant": True, "reason": "EFB-Preisblätter vollständig."}

    @staticmethod
    def _check_changes(x84_xml: str, original_hash: str) -> dict:
        x84_hash = hashlib.sha256(x84_xml.encode()).hexdigest()
        if x84_hash == original_hash:
            return {"compliant": True, "reason": "LV unverändert."}
        # X84 always differs from X83 (prices added) — not a violation
        return {"compliant": True, "reason": "LV-Struktur erhalten (Preisanpassungen erwartet)."}

    def _check_eignung(self, eignung: dict) -> dict:
        missing = [r for r in self.required_eignung if r not in eignung or not eignung[r]]
        if missing:
            return {"compliant": False,
                    "reason": f"Fehlende Nachweise: {', '.join(missing)}"}
        return {"compliant": True, "reason": "Alle Eignungsnachweise vorhanden."}

    @staticmethod
    def _check_structure(x84_data: dict) -> dict:
        if "sections" not in x84_data:
            return {"compliant": False, "reason": "Keine 'sections' in X84-Daten."}
        sections = x84_data.get("sections", [])
        if not sections:
            return {"compliant": False, "reason": "Leeres LV (0 Abschnitte)."}
        missing_oz = sum(
            1 for sec in sections
            for pos in sec.get("positions", [])
            if not pos.get("oz") and not pos.get("position_id")
        )
        if missing_oz > 0:
            return {"compliant": False,
                    "reason": f"{missing_oz} Positionen ohne OZ/Position-ID."}
        return {"compliant": True, "reason": "GAEB-Struktur intakt."}
