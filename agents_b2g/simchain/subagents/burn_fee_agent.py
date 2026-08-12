"""T3: BurnFeeAgent — Fee collection and token burns (economic friction).

Chain: LIQUIDITY_L2 | Friction layer | Reduces circulating supply
2% protocol fee + 1% additional burn on liquid amounts → verifiable sink.
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("BurnFeeAgent")


class BurnFeeAgent:
    """Collects fees and burns tokens — the economic friction layer."""

    def __init__(
        self,
        chain: str = "LIQUIDITY_L2",
        user_id: Optional[str] = None,
        fee_rate: Optional[float] = None,
        additional_burn_rate: Optional[float] = None,
    ):
        self.chain = chain
        self.user_id = user_id or os.getenv("SIMCHAIN_USER_ID", "default")
        self.fee_rate = fee_rate or float(os.getenv("SIMCHAIN_FEE_RATE", "0.02"))
        self.additional_burn_rate = additional_burn_rate or float(
            os.getenv("SIMCHAIN_ADDITIONAL_BURN_RATE", "0.01")
        )
        self.total_fees_collected = 0.0
        self.total_burns_executed = 0.0
        self._operation_count = 0

    async def process_batch(self, staking_results: List[Dict]) -> Dict[str, Any]:
        """Apply fees and burns to staking results — the friction sink."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "BurnFeeAgent processing batch",
                extra={
                    "job_id": job_id,
                    "position_count": len(staking_results),
                    "fee_rate": self.fee_rate,
                    "burn_rate": self.additional_burn_rate,
                    "user_id": self.user_id,
                },
            )
            logs.append(
                f"[INFO] applying fees & burns to {len(staking_results)} positions "
                f"(fee={self.fee_rate*100:.1f}%, burn={self.additional_burn_rate*100:.1f}%)"
            )

            results = []
            total_fees_batch = 0.0
            total_burns_batch = 0.0

            for position in staking_results:
                liquid = position.get("liquid_amount", 0.0)
                fee = round(liquid * self.fee_rate, 6)
                burn = round(liquid * self.additional_burn_rate, 6)
                net_payout = round(liquid - fee - burn, 6)
                sicker_loss = round(fee + burn, 6)

                self.total_fees_collected += fee
                self.total_burns_executed += burn
                self._operation_count += 1
                total_fees_batch += fee
                total_burns_batch += burn

                final = {
                    "position_id": position.get("position_id", ""),
                    "token_id": position.get("token_id", ""),
                    "gross_payout": liquid,
                    "fee": fee,
                    "fee_rate": self.fee_rate,
                    "burn": burn,
                    "burn_rate": self.additional_burn_rate,
                    "net_payout": net_payout,
                    "sicker_loss": sicker_loss,
                    "fee_burn_pct": round(
                        (sicker_loss / liquid * 100) if liquid > 0 else 0, 2
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                results.append(final)

            total_sicker = total_fees_batch + total_burns_batch
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logs.append(
                f"[INFO] {len(results)} operations, "
                f"fees={total_fees_batch:,.2f}€, "
                f"burns={total_burns_batch:,.2f}€, "
                f"sicker_total={total_sicker:,.2f}€, "
                f"elapsed={elapsed_ms}ms"
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [
                    {
                        "type": "burn_fee_batch",
                        "chain": self.chain,
                        "operation_count": len(results),
                        "total_fees_collected": round(total_fees_batch, 6),
                        "total_burns_executed": round(total_burns_batch, 6),
                        "total_sicker_loss": round(total_sicker, 6),
                        "fee_rate": self.fee_rate,
                        "burn_rate": self.additional_burn_rate,
                        "operations": results,
                    }
                ],
                "error": None,
                "logs": logs,
                "metadata": {
                    "total_fees_all_time": round(self.total_fees_collected, 6),
                    "total_burns_all_time": round(self.total_burns_executed, 6),
                    "total_sicker_all_time": round(
                        self.total_fees_collected + self.total_burns_executed, 6
                    ),
                    "operation_count_all_time": self._operation_count,
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "BurnFeeAgent failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            logs.append(f"[ERROR] {e}")

            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "BURN_FEE_FAILED", "message": str(e)},
                "logs": logs,
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_stats(self) -> Dict[str, Any]:
        """Return fee and burn statistics."""
        return {
            "total_fees_collected": round(self.total_fees_collected, 6),
            "total_burns_executed": round(self.total_burns_executed, 6),
            "total_sicker_loss": round(
                self.total_fees_collected + self.total_burns_executed, 6
            ),
            "fee_rate": self.fee_rate,
            "burn_rate": self.additional_burn_rate,
            "operation_count": self._operation_count,
            "chain": self.chain,
        }
