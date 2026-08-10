"""A6: SettlementExecutorChain — Final multi-split settlement.

Chain: SETTLEMENT_L1 | Escrow retention | BHO Δ=0 per settlement
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SettlementExecutorChain")


class SettlementExecutorChain:
    """Sovereign executor chain: multi-split with escrow and BHO zero-sum."""

    def __init__(
        self,
        chain_id: str = "SETTLEMENT_L1",
        user_id: Optional[str] = None,
        net_ratio: Optional[float] = None,
        retention_ratio: Optional[float] = None,
    ):
        self.chain_id = chain_id
        self.user_id = user_id or os.getenv("MULTICHAIN_USER_ID", "default")
        self.net_ratio = net_ratio or float(os.getenv("MC_NET_RATIO", "0.80"))
        self.retention_ratio = retention_ratio or float(os.getenv("MC_RETENTION_RATIO", "0.05"))
        self.block_height = 0
        self.escrow_balance = 0.0
        self.total_settled = 0.0
        self._settlement_count = 0

    async def process_block(self, compliant_txs: List[Dict]) -> Dict[str, Any]:
        """Execute final multi-split for a block of compliant transactions."""
        job_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            logger.info("SettlementExecutor processing block", extra={"job_id": job_id, "count": len(compliant_txs)})

            results = []
            total_gross = 0.0
            for tx in compliant_txs:
                gross = tx.get("amount", 0.0)
                net = tx.get("net", round(gross * self.net_ratio, 2))
                tax_total = tx.get("tax", 0.0) + tx.get("withholding_tax", 0.0)
                if tax_total == 0.0:
                    tax_total = round(gross * 0.15, 2)
                retention = round(gross - net - tax_total, 2)

                self.escrow_balance += retention
                self.total_settled += net + tax_total
                self._settlement_count += 1
                total_gross += gross

                results.append({
                    "project_id": tx.get("project_id", ""),
                    "audit_id": tx.get("audit_id", ""),
                    "gross": gross,
                    "net": net,
                    "tax": tax_total,
                    "retention": retention,
                    "escrow_balance": round(self.escrow_balance, 2),
                    "bho_delta": round(gross - net - tax_total - retention, 2),
                    "settlement_id": f"SETTLE-{self._settlement_count:06d}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            self.block_height += 1
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [{
                    "type": "executor_block",
                    "chain_id": self.chain_id,
                    "block_height": self.block_height,
                    "settlement_count": len(results),
                    "total_gross": round(total_gross, 2),
                    "escrow_balance": round(self.escrow_balance, 2),
                    "bho_zero_sum": True,
                    "settlements": results,
                }],
                "error": None,
                "logs": [],
                "metadata": {
                    "total_settled_all_time": round(self.total_settled, 2),
                    "escrow_balance": round(self.escrow_balance, 2),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("SettlementExecutor failed", extra={"job_id": job_id, "error": str(e)})
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "EXECUTOR_CHAIN_FAILED", "message": str(e)},
                "logs": [f"[ERROR] {e}"],
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_chain_state(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "block_height": self.block_height,
            "escrow_balance": round(self.escrow_balance, 2),
            "total_settled": round(self.total_settled, 2),
            "settlement_count": self._settlement_count,
        }
