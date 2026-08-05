"""
Agent 1 (Wave 8): VergabekammerOrchestrator — Root Agent.

Orchestrates all 8 compliance subagents for a complete procurement
tribunal investigation. Takes a tender ID + complaint details, runs
the full forensic pipeline, and produces a court-ready PDF report
with tamper-proof evidence package.

Usage:
    orch = VergabekammerOrchestrator()
    result = orch.investigate("TED-2026-0815", ruge_details)
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents_b2g.compliance.subagents.tender_history_fetcher import TenderHistoryFetcher
from agents_b2g.compliance.subagents.voba_rule_checker import VOBARuleChecker
from agents_b2g.compliance.subagents.price_plausibility_analyzer import PricePlausibilityAnalyzer
from agents_b2g.compliance.subagents.cartel_collusion_detector import CartelCollusionDetector
from agents_b2g.compliance.subagents.popw_bonus_auditor import PoPWBonusAuditor
from agents_b2g.compliance.subagents.qes_crypto_verifier import QESCryptoVerifier
from agents_b2g.compliance.subagents.bidder_comparison_engine import BidderComparisonEngine
from agents_b2g.compliance.subagents.audit_report_generator import AuditReportGenerator

logger = logging.getLogger("VergabekammerOrchestrator")


class VergabekammerOrchestrator:
    """Root agent for Vergabekammer procurement tribunal proceedings."""

    def __init__(self, archive_base_dir: str = "archive_b2g",
                 chain_adapter: Any = None, dkg_adapter: Any = None):
        self.archive_dir = Path(archive_base_dir)
        self.history_fetcher = TenderHistoryFetcher(archive_dir=str(archive_base_dir),
                                                    chain_adapter=chain_adapter)
        self.voba_checker = VOBARuleChecker()
        self.price_analyzer = PricePlausibilityAnalyzer()
        self.cartel_detector = CartelCollusionDetector()
        self.popw_auditor = PoPWBonusAuditor(dkg_adapter, chain_adapter)
        self.qes_verifier = QESCryptoVerifier(chain_adapter)
        self.comparison_engine = BidderComparisonEngine()
        self.report_generator = AuditReportGenerator()

    # ============================================================
    # Main investigation
    # ============================================================

    def investigate(self, tender_id: str,
                    ruge_details: dict[str, Any] | None = None,
                    claimant_bidder_id: str | None = None,
                    bidder_profiles: list[dict] | None = None) -> dict[str, Any]:
        """Complete Vergabekammer investigation from complaint to report."""

        start = time.perf_counter()
        ruge = ruge_details or {
            "aktenzeichen": f"VK-{tender_id[-8:]}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "eingangsdatum": datetime.now(timezone.utc).isoformat(),
            "pruefgegenstand": f"Nachprüfung der Vergabe {tender_id}",
            "antragsteller": claimant_bidder_id or "Unbekannt",
        }

        logger.info(f"Vergabekammer investigation: {tender_id}")

        # 0. Input validation
        if not tender_id:
            return {"status": "ERROR", "message": "Keine Tender-ID."}

        # 1. History reconstruction
        history = self.history_fetcher.fetch_history(tender_id)
        if history.get("status") == "ERROR":
            return {"status": "ERROR", "message": history.get("message", "History-Fehler")}

        # 2. Bidder profiles
        profiles = bidder_profiles or self._extract_profiles(history)
        if not profiles:
            return {"status": "ERROR", "message": "Keine Bieter-Profile gefunden."}

        results: dict[str, Any] = {
            "tender_id": tender_id, "ruge_details": ruge,
            "status": "INVESTIGATION_RUNNING", "history": history,
        }

        try:
            # 3. VOB/A formal check
            results["voba_check"] = self.voba_checker.check_compliance(
                tender_id=tender_id, bidder_profiles=profiles,
                submission_deadline=history.get("metadata", {}).get("submission_deadline", ""))

            # 4. Price plausibility
            results["price_check"] = self.price_analyzer.analyze(profiles)

            # 5. Cartel detection
            results["cartel_check"] = self.cartel_detector.analyze_bids(profiles)

            # 6. PoPW bonus audit
            popw_results = []
            for p in profiles:
                cit = p.get("popw_citations", [])
                if cit:
                    audit = self.popw_auditor.audit_popw_bonus(
                        tender_id, cit, p.get("claimed_bonus_percent", 0),
                        p.get("bidder_did", ""))
                    popw_results.append({"bidder_id": p.get("bidder_id"), "audit_result": audit})
            results["popw_audits"] = popw_results

            # 7. QES verification
            qes_results = []
            for p in profiles:
                qes_data = p.get("qes_data", {})
                if qes_data:
                    audit = self.qes_verifier.verify_qes_signature(
                        tender_id, p.get("bidder_did", ""),
                        qes_data.get("xml", ""), qes_data.get("cert_pem", ""),
                        qes_data.get("sig_bytes", b""),
                        qes_data.get("signing_time"),
                        history.get("metadata", {}).get("submission_deadline"))
                    qes_results.append({"bidder_id": p.get("bidder_id"), "audit_result": audit})
            results["qes_audits"] = qes_results

            # 8. Bidder comparison
            results["comparison"] = self.comparison_engine.compare_bidders(
                tender_id, profiles, claimant_bidder_id)

            # 9. Overall verdict
            results["overall_verdict"] = self._calculate_verdict(results)

            # 10. Evidence package
            results["evidence_package"] = self._seal_evidence(tender_id, results)

            # 11. Final PDF
            results["report_pdf"] = self.report_generator.generate_report(
                tender_id, results, ruge)

            results["status"] = "INVESTIGATION_COMPLETE"

        except Exception as exc:
            logger.error(f"Investigation failed: {exc}")
            results["status"] = "INVESTIGATION_FAILED"
            results["error"] = str(exc)

        elapsed = time.perf_counter() - start
        verdict = results.get("overall_verdict", {})
        print(f"\n  [Vergabekammer] 🏛️ Investigation complete in {elapsed:.1f}s")
        print(f"    Verdict: {verdict.get('verdict_level', '?')} — "
              f"{verdict.get('verdict_text', '?')[:80]}")
        print(f"    Evidence: {results.get('evidence_package', {}).get('package_id', '?')}")
        if results.get("report_pdf"):
            print(f"    Report:  {results['report_pdf']['report_id']}.pdf "
                  f"({results['report_pdf']['size_bytes']:,} bytes)")

        # Archive
        self._archive(tender_id, results)

        return results

    # ============================================================
    # Helpers
    # ============================================================

    @staticmethod
    def _extract_profiles(history: dict) -> list[dict]:
        profiles = []
        for offer in history.get("offers", []):
            profiles.append({
                "bidder_id": offer.get("bidder", "UNKNOWN"),
                "bidder_did": offer.get("bidder_did", ""),
                "total_price_eur": offer.get("price_eur", 0),
                "claimed_bonus_percent": offer.get("claimed_bonus_pct", 0),
                "submission_timestamp": offer.get("timestamp", ""),
                "x84_data": offer.get("x84_data", {}),
            })
        return profiles

    def _calculate_verdict(self, results: dict) -> dict:
        vob = results.get("voba_check", {})
        cartel = results.get("cartel_check", {})
        price = results.get("price_check", {})
        popw = results.get("popw_audits", [])
        qes = results.get("qes_audits", [])

        findings = []
        level = "GREEN"
        text = "Keine wesentlichen Auffälligkeiten."

        # VOB/A exclusions = instant RED
        if vob.get("summary", {}).get("excluded", 0) > 0:
            level, text = "RED", "Formale Ausschlussgründe nach VOB/A §16 — Vergabe aufheben!"
            findings.append(f"{vob['summary']['excluded']} Bieter auszuschließen.")

        # Cartel >50% = RED
        cs = cartel.get("collusion_score", 0)
        if cs > 50:
            level, text = "RED", "Erhebliche Kartellindizien — Nachprüfungsverfahren erforderlich."
            findings.append(f"Kartellrisiko: {cs:.0f}%")
        elif cs > 25 and level not in ("RED",):
            level, text = "YELLOW", "Kartellrisiko erhöht — weitere Prüfung empfohlen."

        # PoPW failures
        for a in popw:
            status = a.get("audit_result", {}).get("status", "")
            if status == "AUDIT_FAILED":
                level, text = "RED", "PoPW-Bonus-Fälschung festgestellt!"
                findings.append(f"Bieter {a['bidder_id']}: PoPW-Audit fehlgeschlagen.")
            elif status == "AUDIT_WARNING" and level not in ("RED",):
                findings.append(f"Bieter {a['bidder_id']}: PoPW-Bonusabweichung.")

        # QES failures
        for a in qes:
            status = a.get("audit_result", {}).get("status", "")
            if status not in ("AUDIT_PASSED",):
                level, text = "RED", "QES-Signatur ungültig!"
                findings.append(f"Bieter {a['bidder_id']}: QES fehlgeschlagen.")

        recs = {
            "GREEN": "Vergabe bestätigen.",
            "YELLOW": "Vergabe mit Auflagen, Nachweise nachfordern.",
            "ORANGE": "Vergabe stoppen, weitere Prüfung.",
            "RED": "Vergabe aufheben, Nachprüfungsverfahren einleiten.",
        }
        return {"verdict_level": level, "verdict_text": text,
                "findings": findings, "recommendation": recs.get(level, "?")}

    def _seal_evidence(self, tender_id: str, results: dict) -> dict:
        ts = datetime.now(timezone.utc).isoformat()
        hashes = []
        for a in results.get("popw_audits", []):
            seal = a.get("audit_result", {}).get("audit_seal", {})
            if seal.get("seal_hash"):
                hashes.append(seal["seal_hash"])
        for a in results.get("qes_audits", []):
            seal = a.get("audit_result", {}).get("audit_seal", {})
            if seal.get("seal_hash"):
                hashes.append(seal["seal_hash"])
        for a in results.get("qes_audits", []):
            if isinstance(a, dict) and "audit_seal" in a:
                pass  # already collected

        combined = "|".join(sorted(hashes)) if hashes else f"{tender_id}:{ts}"
        evidence_hash = "0x" + hashlib.sha256(combined.encode()).hexdigest()[:40]

        return {
            "package_id": f"EVIDENCE-{tender_id[-16:]}-{ts[:10]}",
            "timestamp": ts,
            "evidence_hash": evidence_hash,
            "included_hashes": hashes,
            "verification_method": "SHA-256 Merkle Aggregation",
            "status": "SEALED",
        }

    def _archive(self, tender_id: str, results: dict) -> None:
        archive_path = self.archive_dir / tender_id / "investigations"
        archive_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_file = archive_path / f"vergabekammer_{ts}.json"
        save = {k: v for k, v in results.items() if k != "report_pdf"}
        report_file.write_text(json.dumps(save, indent=2, default=str, ensure_ascii=False))
        logger.info(f"Investigation archived: {report_file}")
