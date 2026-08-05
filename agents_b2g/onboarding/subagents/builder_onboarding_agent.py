# agents_b2g/onboarding/subagents/builder_onboarding_agent.py
"""Agent 19.4 — BuilderOnboardingAgent: GAEB-Upload, Escrow, Shadow Contract Init."""
import hashlib, logging, uuid
from datetime import datetime, timezone
from typing import Dict, Any
logger = logging.getLogger(__name__)

class BuilderOnboardingAgent:
    def onboard(self, company_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        gaeb_hash = hashlib.sha256(payload.get("gaeb_xml", "").encode()).hexdigest()
        contract = "0x" + hashlib.sha256(f"builder:{company_name}:{uuid.uuid4()}".encode()).hexdigest()[:40]
        budget = float(payload.get("budget_eur", 0))
        milestones = len(payload.get("milestones", []))
        return {"account_type": "BUILDER", "company_name": company_name,
                "project_name": payload.get("project_name", "Unbenannt"),
                "gaeb_hash": gaeb_hash, "shadow_contract": contract,
                "escrow_balance_eur": budget, "milestones_count": milestones,
                "retention_pct": 5.0, "retention_eur": round(budget * 0.05, 2),
                "dashboard_url": f"https://app.agent-x.dev/builder/{contract}",
                "onboarded_at": datetime.now(timezone.utc).isoformat() + "Z"}
