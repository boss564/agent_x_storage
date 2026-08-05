# agents_b2g/onboarding/subagents/partner_success_manager.py
"""Agent 19.9 — PartnerSuccessManager: Kundenbindung, Upselling, Empfehlungen."""
import logging
from typing import Dict, Any, List
logger = logging.getLogger(__name__)

class PartnerSuccessManager:
    RECOMMENDATIONS = {
        "CRAFTSMAN": ["Automatische Rechnungsstellung (0,1% Gebühr)",
                      "Baustellen-Telemetrie-Dashboard", "Subunternehmer-Einladung (Netzwerk-Effekt)"],
        "DEVELOPER": ["Sandbox mit 100 Test-Transaktionen", "API-Dokumentation & Code-Beispiele",
                      "Co-Marketing-Partnerschaft"],
        "BUILDER": ["Shadow-Contract für alle Projekte aktivieren", "RPA-Dashboard freischalten",
                    "IoT-Partner einladen"],
        "IOT_PARTNER": ["peaq-DID-Batch-Registrierung", "ZK-Proof-Templates", "Datenmarktplatz-Zugang"],
        "BANKING_PARTNER": ["ISO-20022-Reconciliation", "Multi-Bank-Settlement", "EURe-Liquiditäts-Pool"],
    }

    def welcome(self, company_name: str, role: str) -> Dict[str, Any]:
        recs = self.RECOMMENDATIONS.get(role, ["Ecosystem-Health-Dashboard", "Benachrichtigungen aktivieren"])
        logger.info(f"Willkommen {company_name} ({role}): {len(recs)} Empfehlungen")
        return {"welcome_sent": True, "company": company_name, "role": role,
                "recommendations": recs, "next_best_action": recs[0] if recs else None}

    def upsell_opportunities(self, role: str, tx_volume_30d: float) -> List[Dict[str, Any]]:
        opportunities = []
        if role == "CRAFTSMAN" and tx_volume_30d > 500_000:
            opportunities.append({"from_plan": "FREEMIUM", "to_plan": "PRO",
                                  "reason": f"Volumen {tx_volume_30d:,.0f} EUR > 500k Limit"})
        if role == "BUILDER" and tx_volume_30d > 2_000_000:
            opportunities.append({"from_plan": "BUILDER", "to_plan": "ENTERPRISE",
                                  "reason": "Enterprise-SLA + Dedicated Node"})
        return opportunities
