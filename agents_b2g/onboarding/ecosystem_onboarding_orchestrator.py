# agents_b2g/onboarding/ecosystem_onboarding_orchestrator.py
"""
Agent 19.1 — EcosystemOnboardingOrchestrator
Root: Multi-Stakeholder Onboarding, alle 8 Subagenten integriert.
"""
import hashlib, json, logging, uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from enum import Enum

from agents_b2g.onboarding.subagents.craftsman_onboarding_agent import CraftsmanOnboardingAgent
from agents_b2g.onboarding.subagents.developer_onboarding_agent import DeveloperOnboardingAgent
from agents_b2g.onboarding.subagents.builder_onboarding_agent import BuilderOnboardingAgent
from agents_b2g.onboarding.subagents.iot_partner_onboarding_agent import IoTPartnerOnboardingAgent
from agents_b2g.onboarding.subagents.banking_partner_onboarding_agent import BankingPartnerOnboardingAgent
from agents_b2g.onboarding.subagents.compliance_enrollment_agent import ComplianceEnrollmentAgent
from agents_b2g.onboarding.subagents.ecosystem_health_monitor import EcosystemHealthMonitor
from agents_b2g.onboarding.subagents.partner_success_manager import PartnerSuccessManager

logger = logging.getLogger(__name__)

class StakeholderRole(Enum):
    CRAFTSMAN = "CRAFTSMAN"; DEVELOPER = "DEVELOPER"; BUILDER = "BUILDER"
    IOT_PARTNER = "IOT_PARTNER"; BANKING_PARTNER = "BANKING_PARTNER"

class EcosystemOnboardingOrchestrator:
    """Agent 19.1: 8 Subagenten, 5 Stakeholder-Rollen."""

    def __init__(self):
        self.compliance = ComplianceEnrollmentAgent()
        self.craftsman = CraftsmanOnboardingAgent()
        self.developer = DeveloperOnboardingAgent()
        self.builder = BuilderOnboardingAgent()
        self.iot = IoTPartnerOnboardingAgent()
        self.banking = BankingPartnerOnboardingAgent()
        self.health = EcosystemHealthMonitor()
        self.success = PartnerSuccessManager()
        self._ecosystem: Dict[str, int] = {"craftsmen": 0, "builders": 0, "developers": 0,
                                             "iot_partners": 0, "banking_partners": 0}
        self._history: List[Dict[str, Any]] = []

    def register(self, role: StakeholderRole, company_name: str, tax_id: str,
                 business_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Hauptmethode: Vollständiges Stakeholder-Onboarding."""
        job_id = hashlib.sha256(f"{company_name}{role.value}{uuid.uuid4()}".encode()).hexdigest()[:12]
        logger.info(f"Onboarding {job_id}: {company_name} as {role.value}")

        # Step 1: Compliance (Agent 7)
        comp = self.compliance.verify(tax_id, business_id)
        if comp["status"] != "APPROVED":
            return {"status": "REJECTED", "job_id": job_id, "company": company_name,
                    "compliance": comp, "artifacts": [], "error": comp.get("reason"),
                    "logs": [{"level": "WARN", "message": f"Compliance: {comp.get('reason')}"}]}

        # Step 2: Rollenspezifisches Provisioning
        role_map = {
            StakeholderRole.CRAFTSMAN: lambda: self.craftsman.onboard(
                company_name, payload.get("trade_license", ""), payload.get("iban", ""),
                tax_id, payload.get("email", ""), payload.get("bund_id", "")),
            StakeholderRole.DEVELOPER: lambda: self.developer.onboard(
                company_name, payload.get("use_case", "ERP")),
            StakeholderRole.BUILDER: lambda: self.builder.onboard(company_name, payload),
            StakeholderRole.IOT_PARTNER: lambda: self.iot.onboard(
                company_name, payload.get("device_dids", [])),
            StakeholderRole.BANKING_PARTNER: lambda: self.banking.onboard(company_name, payload),
        }
        provision = role_map.get(role, lambda: {"status": "UNKNOWN_ROLE"})()
        if provision.get("status") == "UNKNOWN_ROLE":
            return {"status": "FAILED", "job_id": job_id, "error": "Unknown role"}

        # Step 3: Health Monitor (Agent 8)
        record = {"company_name": company_name, "assigned_role": role.value,
                  "onboarding_timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                  "status": "ONBOARDING_SUCCESSFUL"}
        self.health.record_onboarding(record)

        # Step 4: Success Manager (Agent 9)
        welcome = self.success.welcome(company_name, role.value)

        # Step 5: Ecosystem-Tracking
        role_key = {"CRAFTSMAN": "craftsmen", "DEVELOPER": "developers", "BUILDER": "builders",
                     "IOT_PARTNER": "iot_partners", "BANKING_PARTNER": "banking_partners"}
        self._ecosystem[role_key.get(role.value, "craftsmen")] += 1
        self._history.append({"timestamp": record["onboarding_timestamp"], "role": role.value,
                              "company": company_name, "job_id": job_id})

        return {"status": "ONBOARDED", "job_id": job_id, "company_name": company_name,
                "role": role.value, "compliance": comp, "provisioning": provision,
                "welcome": welcome, "ecosystem": self.ecosystem_health(),
                "artifacts": [{"type": "onboarding_receipt", "format": "json"}],
                "error": None,
                "logs": [{"level": "INFO", "message": f"{company_name} onboarded as {role.value}"}]}

    def batch_onboard(self, stakeholders: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = []; success = 0
        for s in stakeholders:
            role = StakeholderRole[s["role"]]
            r = self.register(role, s["name"], s.get("tax_id", "DE000000000"),
                            s.get("business_id", "HRB00000"), s.get("payload", {}))
            results.append({"name": s["name"], "role": s["role"], "status": r["status"]})
            if r["status"] == "ONBOARDED": success += 1
        return {"status": "BATCH_COMPLETE", "total": len(stakeholders),
                "onboarded": success, "failed": len(stakeholders) - success,
                "conversion_pct": round(success / max(len(stakeholders), 1) * 100, 1),
                "details": results,
                "logs": [{"level": "INFO", "message": f"Batch: {success}/{len(stakeholders)}"}]}

    def ecosystem_health(self) -> Dict[str, Any]:
        h = self.health.get_health_report()
        return {"status": h["status"], "total_onboarded": self._ecosystem,
                "total_stakeholders": sum(self._ecosystem.values()),
                "success_rate_24h_pct": h["success_rate_24h_pct"],
                "role_distribution": h["role_distribution"],
                "recent": self._history[-5:]}

# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("EcosystemOnboardingOrchestrator — Full Test")
    print("=" * 60)
    orch = EcosystemOnboardingOrchestrator()

    # All 5 roles
    tests = [
        ("CRAFTSMAN", "Betonwerk Nord GmbH", "DE123456789", "HRB 12345",
         {"iban": "DE89370400440532013000", "trade_license": "HWK-0815",
          "email": "info@betonwerk.de", "bund_id": "valid_token_1234567890"}),
        ("DEVELOPER", "ERP-Systeme Schmidt AG", "DE987654321", "HRB 67890",
         {"use_case": "SAP Integration"}),
        ("BUILDER", "Wohnungsbau Nord eG", "DE456789123", "HRB 11111",
         {"project_name": "Kläranlage Nord", "budget_eur": 4_200_000,
          "milestones": [{"id": "M1"}, {"id": "M2"}, {"id": "M3"}], "gaeb_xml": "<GAEB>..."}),
        ("IOT_PARTNER", "SensorTech GmbH", "DE111222333", "HRB 22222",
         {"device_dids": ["did:peaq:waage_01", "did:peaq:bagger_03"]}),
        ("BANKING_PARTNER", "DekaBank", "DE999888777", "HRB 33333",
         {"partner_type": "BANK"}),
    ]
    for role, name, tax, biz, payload in tests:
        r = orch.register(StakeholderRole[role], name, tax, biz, payload)
        icon = "✅" if r["status"] == "ONBOARDED" else "❌"
        print(f"{icon} {role}: {name} — {r['status']}")

    health = orch.ecosystem_health()
    print(f"\nEcosystem: {health['status']} | {health['total_stakeholders']} stakeholders")
    print(f"Distribution: {health['total_onboarded']}")
    print("✅ Smoke Test complete.")
