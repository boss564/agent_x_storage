# agents_b2g/shadow/subagents/retention_vault_manager.py
"""
Agent 18.6 — RetentionVaultManager

Treuhand-Management für den 5% Sicherheitseinbehalt nach VOB/B §17.
Sperrt Einbehalte, überwacht die 4-jährige Gewährleistungsfrist,
ermöglicht Aval-Bürgschaft und gibt nach Fristablauf automatisch frei.

9-stufige Retention-Pipeline:
  1. RetentionRateCalculator       — 5% auf jede Abschlagsrechnung
  2. VaultLockExecutor             — Sperrt Betrag im Escrow Vault
  3. WarrantyPeriodTracker         — 4-Jahres-Frist ab Abnahme
  4. DefectNoticeMonitor           — Mängelrügen (§13), Fristhemmung
  5. BankGuaranteeBridge           — Aval-Bürgschaft statt Bareinbehalt
  6. WarrantyExpirationNotifier    — T-60/T-30 Warnung vor Ablauf
  7. ReleaseConditionEvaluator     — Freigabeprüfung (Frist + Mängelfrei)
  8. RetentionReleaseTxSigner      — releaseRetentionVault() TX
  9. RetentionAuditLogger          — GoBD-WORM-Einbehaltsprotokoll (jsonl)
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger("RetentionVaultManager")


# ============================================================================
# SUB-SUBAGENT 18.6.1: RetentionRateCalculator
# ============================================================================
class RetentionRateCalculator:
    """Berechnet 5% Sicherheitseinbehalt gemäß VOB/B §17."""

    RETENTION_RATE = 0.05
    LEGAL_BASIS = "VOB/B §17"

    def calculate(self, gross_amount_eur: float) -> Dict[str, Any]:
        retention = round(gross_amount_eur * self.RETENTION_RATE, 2)
        return {
            "gross_amount_eur": gross_amount_eur,
            "retention_rate_pct": self.RETENTION_RATE * 100,
            "retention_amount_eur": retention,
            "legal_basis": self.LEGAL_BASIS,
        }


# ============================================================================
# SUB-SUBAGENT 18.6.2: VaultLockExecutor
# ============================================================================
class VaultLockExecutor:
    """Sperrt den Einbehalt im Escrow Vault (Mock-TX)."""

    def lock(self, amount_eur: float, contract_address: str) -> Dict[str, Any]:
        lock_tx = "0x" + hashlib.sha256(
            f"lock{contract_address}{amount_eur}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()
        return {
            "locked_amount_eur": amount_eur,
            "contract_address": contract_address,
            "lock_tx_hash": lock_tx,
            "locked_at": datetime.now(timezone.utc).isoformat() + "Z",
        }


# ============================================================================
# SUB-SUBAGENT 18.6.3: WarrantyPeriodTracker
# ============================================================================
class WarrantyPeriodTracker:
    """4-jährige Gewährleistungsfrist ab Abnahme (§13 VOB/B)."""

    WARRANTY_YEARS = 4

    def calculate(self, acceptance_date_iso: str) -> Dict[str, Any]:
        try:
            acc_dt = datetime.fromisoformat(acceptance_date_iso.replace("Z", "+00:00")[:10])
            acc_dt = acc_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            acc_dt = datetime.now(timezone.utc)
        exp_dt = acc_dt.replace(year=acc_dt.year + self.WARRANTY_YEARS)
        now = datetime.now(timezone.utc)
        days_remaining = max(0, (exp_dt - now).days)
        is_expired = days_remaining == 0

        return {
            "acceptance_date": acc_dt.strftime("%Y-%m-%d"),
            "expiration_date": exp_dt.strftime("%Y-%m-%d"),
            "warranty_years": self.WARRANTY_YEARS,
            "days_remaining": days_remaining,
            "is_warranty_expired": is_expired,
            "status": "EXPIRED" if is_expired else f"ACTIVE ({days_remaining}d remaining)",
        }


# ============================================================================
# SUB-SUBAGENT 18.6.4: DefectNoticeMonitor
# ============================================================================
class DefectNoticeMonitor:
    """Überwacht Mängelrügen und hemmt die Gewährleistungsfrist (§13)."""

    def check(self, open_defect_ids: List[str], warranty_status: Dict[str, Any]) -> Dict[str, Any]:
        has_defects = len(open_defect_ids) > 0
        return {
            "open_defect_count": len(open_defect_ids),
            "defect_ids": open_defect_ids[:10],
            "is_suspended": has_defects,
            "warranty": "SUSPENDED" if has_defects else warranty_status.get("status", "RUNNING"),
            "legal_basis": "VOB/B §13 Abs. 5 (Fristhemmung)",
        }


# ============================================================================
# SUB-SUBAGENT 18.6.5: BankGuaranteeBridge
# ============================================================================
class BankGuaranteeBridge:
    """Ermöglicht Aval-Bürgschaft statt Bareinbehalt (§17 Abs. 4)."""

    def process_guarantee(self, aval_hash: str, aval_amount_eur: float) -> Dict[str, Any]:
        valid = aval_hash.startswith("0x") and len(aval_hash) >= 64
        return {
            "aval_hash": aval_hash,
            "aval_amount_eur": aval_amount_eur,
            "is_valid": valid,
            "legal_basis": "VOB/B §17 Abs. 4",
            "effect": "Bareinbehalt kann durch Aval ersetzt werden" if valid else "Aval ungültig",
        }


# ============================================================================
# SUB-SUBAGENT 18.6.7: ReleaseConditionEvaluator
# ============================================================================
class ReleaseConditionEvaluator:
    """Prüft Freigabereife: Frist abgelaufen + mängelfrei ODER Aval."""

    def evaluate(
        self,
        is_warranty_expired: bool,
        open_defect_count: int,
        has_bank_guarantee: bool,
    ) -> Dict[str, Any]:
        # Freigabe: Frist abgelaufen + mängelfrei ODER Aval vorhanden
        can_release = (is_warranty_expired and open_defect_count == 0) or has_bank_guarantee

        if has_bank_guarantee:
            reason = "RELEASED_VIA_BANK_GUARANTEE_AVAL"
        elif is_warranty_expired and open_defect_count == 0:
            reason = "RELEASED_WARRANTY_EXPIRED_NO_DEFECTS"
        elif open_defect_count > 0:
            reason = "HELD_DUE_TO_OPEN_DEFECTS"
        else:
            reason = "LOCKED_IN_WARRANTY_PERIOD"

        return {"can_release": can_release, "release_reason": reason}


# ============================================================================
# SUB-SUBAGENT 18.6.6: WarrantyExpirationNotifier
# ============================================================================
class WarrantyExpirationNotifier:
    """Automatische Warnung T-60/T-30 vor Fristablauf."""

    def check_notifications(self, days_remaining: int) -> List[Dict[str, Any]]:
        notifications = []
        if 0 < days_remaining <= 30:
            notifications.append({"level": "URGENT", "days_remaining": days_remaining,
                                  "message": f"Nur noch {days_remaining} Tage bis Fristablauf!"})
        elif days_remaining <= 60:
            notifications.append({"level": "WARNING", "days_remaining": days_remaining,
                                  "message": f"Noch {days_remaining} Tage bis Fristablauf."})
        return notifications


# ============================================================================
# SUB-SUBAGENT 18.6.9: RetentionAuditLogger
# ============================================================================
class RetentionAuditLogger:
    """GoBD-WORM-Einbehaltsprotokoll."""

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []
        self._prev_hash: Optional[str] = None

    def log(self, event: str, data: Dict[str, Any]) -> str:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                 "event": event, "data": data, "prev_hash": self._prev_hash}
        entry["hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()
        self._prev_hash = entry["hash"]
        self._entries.append(entry)
        return entry["hash"]

    def export_jsonl(self) -> str:
        return "\n".join(json.dumps(e, ensure_ascii=False) for e in self._entries)


# ============================================================================
# AGENT 18.6: RetentionVaultManager (Root)
# ============================================================================
class RetentionVaultManager:
    """
    Subagent 18.6: VOB/B §17 Sicherheitseinbehalt — Sperren, Überwachen, Freigeben.
    """

    def __init__(self):
        self.calculator = RetentionRateCalculator()
        self.lock_executor = VaultLockExecutor()
        self.warranty_tracker = WarrantyPeriodTracker()
        self.defect_monitor = DefectNoticeMonitor()
        self.guarantee_bridge = BankGuaranteeBridge()
        self.notifier = WarrantyExpirationNotifier()
        self.condition_evaluator = ReleaseConditionEvaluator()
        self.audit_logger = RetentionAuditLogger()

    def evaluate_retention_state(
        self,
        tender_id: str,
        total_gross_eur: float,
        acceptance_date_iso: str,
        contract_address: str = "",
        open_defect_ids: Optional[List[str]] = None,
        bank_guarantee_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Vollständige Einbehalts-Analyse mit 9 Sub-Subagenten.

        Returns:
            Retention-Report mit Vault-Status, Fristen und ggf. Release-TX.
        """
        job_id = hashlib.sha256(
            f"ret{tender_id}{total_gross_eur}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]

        logger.info(f"Retention {job_id}: {total_gross_eur:,.2f} EUR, Tender={tender_id}")

        try:
            open_defects = open_defect_ids or []

            # === Step 1: 5% berechnen ===
            calc = self.calculator.calculate(total_gross_eur)
            self.audit_logger.log("RETENTION_CALCULATED", calc)

            # === Step 2: Vault Lock ===
            lock = self.lock_executor.lock(calc["retention_amount_eur"], contract_address)
            self.audit_logger.log("VAULT_LOCKED", lock)

            # === Step 3: Frist berechnen ===
            warranty = self.warranty_tracker.calculate(acceptance_date_iso)
            self.audit_logger.log("WARRANTY_TRACKING", warranty)

            # === Step 4: Mängel prüfen ===
            defects = self.defect_monitor.check(open_defects, warranty)
            self.audit_logger.log("DEFECT_CHECK", defects)

            # === Step 5: Aval prüfen ===
            has_aval = bool(bank_guarantee_hash and len(bank_guarantee_hash) > 10)
            if has_aval:
                aval = self.guarantee_bridge.process_guarantee(
                    bank_guarantee_hash, calc["retention_amount_eur"]
                )
                self.audit_logger.log("BANK_GUARANTEE", aval)

            # === Step 6: Notifications ===
            notifications = self.notifier.check_notifications(warranty["days_remaining"])
            for n in notifications:
                self.audit_logger.log("WARRANTY_NOTIFICATION", n)

            # === Step 7: Freigabe evaluieren ===
            evaluation = self.condition_evaluator.evaluate(
                is_warranty_expired=warranty["is_warranty_expired"],
                open_defect_count=len(open_defects),
                has_bank_guarantee=has_aval,
            )
            self.audit_logger.log("RELEASE_EVALUATION", evaluation)

            # === Step 8: Release TX (Mock) ===
            release_tx = None
            if evaluation["can_release"]:
                release_tx = "0x" + hashlib.sha256(
                    f"release{tender_id}{calc['retention_amount_eur']}".encode()
                ).hexdigest()
                self.audit_logger.log("RETENTION_RELEASED", {
                    "amount": calc["retention_amount_eur"], "tx": release_tx,
                })

            # === Step 9: GoBD ===
            gobd_hash = self.audit_logger.log("RETENTION_REPORT_COMPLETE", {
                "tender_id": tender_id, "amount": calc["retention_amount_eur"],
                "can_release": evaluation["can_release"],
            })

            report = {
                "status": "RELEASED" if evaluation["can_release"] else "LOCKED",
                "job_id": job_id,
                "tender_id": tender_id,
                "vob_section": calc["legal_basis"],
                "vault_summary": {
                    "total_retention_locked_eur": calc["retention_amount_eur"],
                    "retention_rate_pct": calc["retention_rate_pct"],
                    "lock_tx": lock["lock_tx_hash"],
                    "vault_state": "RELEASED" if evaluation["can_release"] else "LOCKED",
                    "release_reason": evaluation["release_reason"],
                },
                "warranty_tracking": warranty,
                "defect_monitoring": {
                    "open_defects": len(open_defects),
                    "defect_ids": open_defects[:5],
                    "is_suspended": defects["is_suspended"],
                },
                "bank_guarantee": {
                    "has_aval": has_aval,
                    "guarantee_hash": bank_guarantee_hash,
                },
                "notifications": notifications,
                "on_chain_release_tx": release_tx,
                "gobd_audit_hash": gobd_hash,
                "artifacts": [
                    {"type": "retention_report", "format": "json"},
                    {"type": "retention_audit_log", "format": "jsonl",
                     "content": self.audit_logger.export_jsonl()},
                ],
                "error": None,
                "logs": [{"level": "INFO",
                          "message": f"Retention: {calc['retention_amount_eur']:,.2f} EUR {'FREIGEGEBEN' if evaluation['can_release'] else 'GESPERRT'} "
                                     f"(Frist: {warranty['expiration_date']}, Mängel: {len(open_defects)}, "
                                     f"Aval: {has_aval})"}],
            }
            return report

        except Exception as e:
            logger.error(f"Retention failed: {e}")
            return {"status": "FAILED", "job_id": job_id, "error": str(e),
                    "artifacts": [], "logs": [{"level": "ERROR", "message": str(e)}]}


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("RetentionVaultManager — Smoke Test")
    print("=" * 60)

    mgr = RetentionVaultManager()

    # Test 1: Während Gewährleistung — LOCKED
    r1 = mgr.evaluate_retention_state(
        tender_id="TED-2026-SHADOW-001",
        total_gross_eur=4_200_000.00,
        acceptance_date_iso="2026-08-05",
        contract_address="0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
    )
    print(f"\nTest 1 (LOCKED): {r1['status']} — {r1['vault_summary']['release_reason']}")
    print(f"  Retention: {r1['vault_summary']['total_retention_locked_eur']:,.2f} EUR")
    print(f"  Frist: {r1['warranty_tracking']['expiration_date']} ({r1['warranty_tracking']['days_remaining']}d)")
    print(f"  Notifications: {len(r1['notifications'])}")
    assert r1["status"] == "LOCKED"

    # Test 2: Mit Aval — RELEASED
    r2 = mgr.evaluate_retention_state(
        tender_id="TED-2026-SHADOW-002",
        total_gross_eur=1_500_000.00,
        acceptance_date_iso="2026-06-01",
        bank_guarantee_hash="0x8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e2d1c0b9a8f7e",
    )
    print(f"\nTest 2 (Aval): {r2['status']} — {r2['vault_summary']['release_reason']}")
    print(f"  TX: {r2['on_chain_release_tx'][:42]}...")
    assert r2["status"] == "RELEASED"

    # Test 3: Abgelaufen + mängelfrei — RELEASED
    r3 = mgr.evaluate_retention_state(
        tender_id="TED-2022-SHADOW-003",
        total_gross_eur=800_000.00,
        acceptance_date_iso="2022-01-15",  # >4 Jahre her
    )
    print(f"\nTest 3 (Expired): {r3['status']} — {r3['vault_summary']['release_reason']}")
    assert r3["status"] == "RELEASED"

    # Test 4: Abgelaufen aber Mängel offen — LOCKED
    r4 = mgr.evaluate_retention_state(
        tender_id="TED-2022-SHADOW-004",
        total_gross_eur=600_000.00,
        acceptance_date_iso="2022-01-15",
        open_defect_ids=["DEF-001", "DEF-002"],
    )
    print(f"\nTest 4 (Defects): {r4['status']} — {r4['vault_summary']['release_reason']}")
    assert r4["status"] == "LOCKED"

    print("\n✅ Smoke Test abgeschlossen.")
