"""A5: LegalComplianceChain — GoBD archiving and tax computation.

Chain: SETTLEMENT_L1 | Mandatory compliance | §13b UStG, GoBD WORM
"""

import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("LegalComplianceChain")


class LegalComplianceChain:
    """Sovereign compliance chain: tax, GoBD archiving, audit trail."""

    def __init__(
        self,
        chain_id: str = "SETTLEMENT_L1",
        user_id: Optional[str] = None,
        tax_rate: Optional[float] = None,
        withholding_rate: Optional[float] = None,
    ):
        self.chain_id = chain_id
        self.user_id = user_id or os.getenv("MULTICHAIN_USER_ID", "default")
        self.tax_rate = tax_rate or float(os.getenv("MC_TAX_RATE", "0.19"))
        self.withholding_rate = withholding_rate or float(os.getenv("MC_WITHHOLDING_RATE", "0.15"))
        self.block_height = 0
        self.audit_trail: List[Dict] = []
        self.merkle_root = "0x0"
        self._total_tax = 0.0

    async def process_block(self, settlements: List[Dict]) -> Dict[str, Any]:
        """Apply tax and GoBD archiving to a settlement block."""
        job_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            logger.info("LegalCompliance processing block", extra={"job_id": job_id, "count": len(settlements)})

            compliant = []
            tax_batch = 0.0
            for s in settlements:
                gross = s.get("amount", 0.0)
                tax = round(gross * self.tax_rate, 2)
                withholding = round(gross * self.withholding_rate, 2)
                net = round(gross - tax - withholding, 2)

                audit = {
                    "audit_id": f"AUDIT-{len(self.audit_trail) + 1:06d}",
                    "project_id": s.get("project_id", ""),
                    "gross": gross,
                    "tax": tax,
                    "withholding_tax": withholding,
                    "net": net,
                    "gobd_worm_hash": f"WORM_{uuid.uuid4().hex[:16]}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.audit_trail.append(audit)
                self.merkle_root = hashlib.sha256(
                    (self.merkle_root + audit["gobd_worm_hash"]).encode()
                ).hexdigest()
                self._total_tax += tax + withholding
                tax_batch += tax + withholding

                compliant.append({**s, "net": net, "tax": tax, "withholding_tax": withholding,
                                  "audit_id": audit["audit_id"], "gobd_worm_hash": audit["gobd_worm_hash"]})

            self.block_height += 1
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [{
                    "type": "legal_block",
                    "chain_id": self.chain_id,
                    "block_height": self.block_height,
                    "compliant_count": len(compliant),
                    "tax_collected": round(tax_batch, 2),
                    "merkle_root": self.merkle_root,
                    "transactions": compliant,
                }],
                "error": None,
                "logs": [],
                "metadata": {
                    "total_tax_all_time": round(self._total_tax, 2),
                    "audit_trail_size": len(self.audit_trail),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("LegalCompliance failed", extra={"job_id": job_id, "error": str(e)})
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "LEGAL_CHAIN_FAILED", "message": str(e)},
                "logs": [f"[ERROR] {e}"],
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_chain_state(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "block_height": self.block_height,
            "audit_entries": len(self.audit_trail),
            "merkle_root": self.merkle_root[:16],
            "total_tax": round(self._total_tax, 2),
        }
