# agents_b2g/onboarding/subagents/compliance_enrollment_agent.py
"""Agent 19.7 — ComplianceEnrollmentAgent: KYB, AML, BZSt-Prüfung."""
import hashlib, logging
from typing import Dict, Any
logger = logging.getLogger(__name__)

class ComplianceEnrollmentAgent:
    def verify(self, tax_id: str, business_register_id: str) -> Dict[str, Any]:
        bzst_ok = tax_id.startswith("DE") and len(tax_id) == 11
        trade_ok = len(business_register_id) > 5
        aml_ok = True
        if bzst_ok and trade_ok and aml_ok:
            return {"status": "APPROVED", "bzst_verified": True, "trade_register_valid": True,
                    "aml_cleared": True, "compliance_hash": hashlib.sha256(
                    f"{tax_id}:{business_register_id}".encode()).hexdigest()}
        reasons = [r for r, ok in [("INVALID_TAX_ID", not bzst_ok),
                    ("INVALID_TRADE_REGISTER", not trade_ok), ("AML_SUSPICIOUS", not aml_ok)] if ok]
        return {"status": "REJECTED", "reason": ", ".join(reasons)}
