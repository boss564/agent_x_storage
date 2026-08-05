# agents_b2g/onboarding/ecosystem_onboarding_orchestrator.py
"""
Agent 19.1 — EcosystemOnboardingOrchestrator

Root-Agent der Welle 19. Steuert das Multi-Stakeholder-Onboarding,
verwaltet Subagenten und erstellt den Ecosystem-Health-Report.

5 Zielgruppen: Handwerker → Bauherren → Software-Partner → IoT → Banken
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from agents_b2g.onboarding.subagents.craftsman_onboarding_agent import (
    CraftsmanOnboardingAgent,
)

logger = logging.getLogger("EcosystemOnboardingOrchestrator")


class EcosystemOnboardingOrchestrator:
    """
    Agent 19.1: Multi-Stakeholder Onboarding & Ecosystem Health.
    """

    def __init__(self):
        self.craftsman = CraftsmanOnboardingAgent()
        # Weitere Subagenten folgen in späteren Sprints

        # Ecosystem-Tracking
        self._ecosystem: Dict[str, int] = {
            "craftsmen": 0, "builders": 0, "developers": 0,
            "iot_partners": 0, "banking_partners": 0,
        }
        self._onboarding_history: List[Dict[str, Any]] = []

    def onboard_craftsman(
        self,
        company_name: str,
        trade_license: str,
        iban: str,
        tax_id: str,
        email: str,
        bund_id_token: str = "",
    ) -> Dict[str, Any]:
        """Handwerker-Onboarding via CraftsmanOnboardingAgent."""
        result = self.craftsman.onboard(
            company_name, trade_license, iban, tax_id, email, bund_id_token
        )
        if result["status"] == "ONBOARDED":
            self._ecosystem["craftsmen"] += 1
            self._onboarding_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "type": "craftsman",
                "company": company_name,
                "wallet": result["wallet_address"],
            })
        return result

    def ecosystem_health(self) -> Dict[str, Any]:
        """
        Ecosystem Health Dashboard.
        Aggregiert alle Stakeholder-Metriken.
        """
        total = sum(self._ecosystem.values())
        return {
            "status": "GROWING" if total > 10 else ("LAUNCHING" if total > 0 else "PRE_LAUNCH"),
            "total_onboarded": self._ecosystem,
            "total_stakeholders": total,
            "growth_strategy": {
                "current_focus": "Handwerker (höchster Time-to-Value)",
                "next_focus": "Bauherren & Projektentwickler",
                "flywheel": "Handwerker → Bauherren → Software-Partner → IoT → Banken",
            },
            "onboarding_history": self._onboarding_history[-10:],
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

    def batch_onboard_craftsmen(
        self, companies: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Batch-Onboarding für Pilotprogramm (z.B. 50 Handwerker)."""
        results = []
        success = 0
        for c in companies:
            r = self.onboard_craftsman(
                company_name=c.get("name", "Unbekannt"),
                trade_license=c.get("license", ""),
                iban=c.get("iban", ""),
                tax_id=c.get("tax_id", ""),
                email=c.get("email", ""),
                bund_id_token=c.get("bund_id", ""),
            )
            results.append({"name": c.get("name"), "status": r["status"]})
            if r["status"] == "ONBOARDED":
                success += 1

        return {
            "status": "BATCH_COMPLETE",
            "total": len(companies),
            "onboarded": success,
            "failed": len(companies) - success,
            "conversion_rate_pct": round(success / max(len(companies), 1) * 100, 1),
            "details": results,
            "artifacts": [],
            "error": None,
            "logs": [{"level": "INFO",
                      "message": f"Batch: {success}/{len(companies)} onboarded"}],
        }


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("EcosystemOnboardingOrchestrator — Smoke Test")
    print("=" * 60)

    orch = EcosystemOnboardingOrchestrator()

    # Einzel-Onboarding
    r1 = orch.onboard_craftsman(
        company_name="Betonwerk Nord GmbH",
        trade_license="HWK-2024-0815",
        iban="DE89370400440532013000",
        tax_id="DE123456789",
        email="info@betonwerk-nord.de",
        bund_id_token="valid_token_1234567890",
    )
    print(f"\nEinzel-Onboarding: {r1['status']} — {r1['wallet_address']}")

    # Batch-Onboarding (Pilot mit 5 Handwerkern)
    batch = [
        {"name": "Maurer Schmidt GmbH", "iban": "DE12345678901234567890", "tax_id": "DE111111111", "email": "ms@bau.de"},
        {"name": "Elektro Müller KG", "iban": "DE09876543210987654321", "tax_id": "DE222222222", "email": "em@bau.de"},
        {"name": "Dachdecker Schulz", "iban": "DE55555555555555555555", "tax_id": "DE333333333", "email": "ds@bau.de"},
        {"name": "Fliesen König GmbH", "iban": "DE44444444444444444444", "tax_id": "DE444444444", "email": "fk@bau.de"},
        {"name": "Tiefbau Nord AG", "iban": "INVALID_IBAN", "tax_id": "DE555555555", "email": "tn@bau.de"},
    ]
    batch_result = orch.batch_onboard_craftsmen(batch)
    print(f"\nBatch: {batch_result['onboarded']}/{batch_result['total']} onboarded "
          f"({batch_result['conversion_rate_pct']}%)")
    for d in batch_result["details"]:
        print(f"  {'✅' if d['status'] == 'ONBOARDED' else '❌'} {d['name']}")

    # Ecosystem Health
    health = orch.ecosystem_health()
    print(f"\nEcosystem: {health['status']}")
    print(f"Stakeholder: {health['total_onboarded']}")
    print(f"Total: {health['total_stakeholders']} onboarded")
    print(f"Strategie: {health['growth_strategy']['current_focus']}")

    print(f"\n✅ Smoke Test abgeschlossen.")
