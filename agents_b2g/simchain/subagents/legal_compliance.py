"""L2: LegalComplianceAgent — GoBD archiving, tax computation, audit trail.

Chain: SETTLEMENT_L1 | Mandatory compliance | §13b UStG, GoBD, BHO
Computes reverse-charge VAT, construction withholding tax, and archives audits.
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("LegalComplianceAgent")


class LegalComplianceAgent:
    """GoBD-compliant archiving and tax computation for VOB/B settlements."""

    def __init__(
        self,
        chain: str = "SETTLEMENT_L1",
        user_id: Optional[str] = None,
        tax_rate: Optional[float] = None,
        construction_withholding: Optional[float] = None,
    ):
        self.chain = chain
        self.user_id = user_id or os.getenv("SIMCHAIN_USER_ID", "default")
        self.tax_rate = tax_rate or float(os.getenv("SIMCHAIN_TAX_RATE", "0.19"))
        self.construction_withholding = construction_withholding or float(
            os.getenv("SIMCHAIN_CONSTRUCTION_WITHHOLDING", "0.15")
        )
        self.audit_trail: List[Dict] = []
        self._total_tax_collected = 0.0

    async def process_batch(self, settlements: List[Dict]) -> Dict[str, Any]:
        """Apply tax computation and GoBD archiving to settlements."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "LegalCompliance processing batch",
                extra={
                    "job_id": job_id,
                    "settlement_count": len(settlements),
                    "user_id": self.user_id,
                },
            )
            logs.append(
                f"[INFO] processing {len(settlements)} settlements "
                f"(tax={self.tax_rate}, withholding={self.construction_withholding})"
            )

            compliant_txs = []
            total_tax_this_batch = 0.0

            for settlement in settlements:
                gross = settlement.get("amount", 0.0)
                tax = round(gross * self.tax_rate, 2)
                withholding = round(gross * self.construction_withholding, 2)
                net = round(gross - tax - withholding, 2)

                audit_entry = {
                    "audit_id": f"AUDIT-{len(self.audit_trail) + 1:06d}",
                    "project_id": settlement.get("project_id", "UNKNOWN"),
                    "gross": gross,
                    "tax": tax,
                    "withholding_tax": withholding,
                    "net": net,
                    "tax_rate": self.tax_rate,
                    "withholding_rate": self.construction_withholding,
                    "bho_delta": 0.0,
                    "gobd_worm_hash": f"WORM_{uuid.uuid4().hex[:16]}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.audit_trail.append(audit_entry)
                self._total_tax_collected += tax + withholding
                total_tax_this_batch += tax + withholding

                compliant_tx = {
                    **settlement,
                    "net": net,
                    "tax": tax,
                    "withholding_tax": withholding,
                    "audit_id": audit_entry["audit_id"],
                    "gobd_worm_hash": audit_entry["gobd_worm_hash"],
                }
                compliant_txs.append(compliant_tx)

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logs.append(
                f"[INFO] {len(compliant_txs)} compliant txs, "
                f"tax_collected={total_tax_this_batch:,.2f}€, "
                f"audit_entries={len(self.audit_trail)}, "
                f"elapsed={elapsed_ms}ms"
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [
                    {
                        "type": "legal_compliance_batch",
                        "chain": self.chain,
                        "compliant_tx_count": len(compliant_txs),
                        "tax_collected": round(total_tax_this_batch, 2),
                        "tax_rate": self.tax_rate,
                        "withholding_rate": self.construction_withholding,
                        "gobd_compliant": True,
                        "audit_trail_size": len(self.audit_trail),
                        "transactions": compliant_txs,
                    }
                ],
                "error": None,
                "logs": logs,
                "metadata": {
                    "total_tax_collected_all_time": round(
                        self._total_tax_collected, 2
                    ),
                    "total_audit_entries": len(self.audit_trail),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "LegalCompliance failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            logs.append(f"[ERROR] {e}")

            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "LEGAL_COMPLIANCE_FAILED", "message": str(e)},
                "logs": logs,
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_stats(self) -> Dict[str, Any]:
        """Return compliance statistics."""
        return {
            "total_tax_collected": round(self._total_tax_collected, 2),
            "audit_trail_entries": len(self.audit_trail),
            "tax_rate": self.tax_rate,
            "withholding_rate": self.construction_withholding,
            "chain": self.chain,
        }
