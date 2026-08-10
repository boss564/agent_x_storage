"""T2: StakingPoolAgent — Lockup management with APY yield distribution.

Chain: LIQUIDITY_L2 | DeFi Economics | 12% APY, 80% lockup
Locks 80% of minted tokens with monthly yield distribution.
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("StakingPoolAgent")


class StakingPoolAgent:
    """Manages token lockups and APY yield distribution."""

    def __init__(
        self,
        chain: str = "LIQUIDITY_L2",
        user_id: Optional[str] = None,
        apy: Optional[float] = None,
        lockup_ratio: Optional[float] = None,
    ):
        self.chain = chain
        self.user_id = user_id or os.getenv("SIMCHAIN_USER_ID", "default")
        self.apy = apy or float(os.getenv("SIMCHAIN_STAKING_APY", "0.12"))
        self.lockup_ratio = lockup_ratio or float(
            os.getenv("SIMCHAIN_LOCKUP_RATIO", "0.80")
        )
        self.total_locked = 0.0
        self.total_liquid = 0.0  # Track liquid separately for conservation check
        self.total_yield_distributed = 0.0
        self._position_count = 0
        self._positions: List[Dict] = []

    async def process_batch(self, tokens: List[Dict]) -> Dict[str, Any]:
        """Create staking positions from minted tokens."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "StakingPool processing batch",
                extra={
                    "job_id": job_id,
                    "token_count": len(tokens),
                    "apy": self.apy,
                    "lockup_ratio": self.lockup_ratio,
                    "user_id": self.user_id,
                },
            )
            logs.append(
                f"[INFO] creating staking positions from {len(tokens)} tokens "
                f"(APY={self.apy*100:.1f}%, lockup={self.lockup_ratio*100:.0f}%)"
            )

            staking_results = []
            total_locked_batch = 0.0
            total_yield_batch = 0.0

            for token in tokens:
                net_tokens = token.get("net_tokens", 0.0)
                locked_amount = round(net_tokens * self.lockup_ratio, 6)
                liquid_amount = round(net_tokens - locked_amount, 6)
                # Monthly yield (APY / 12)
                yield_amount = round(locked_amount * (self.apy / 12), 6)

                self.total_locked += locked_amount
                self.total_liquid += liquid_amount
                self.total_yield_distributed += yield_amount
                self._position_count += 1
                total_locked_batch += locked_amount
                total_yield_batch += yield_amount

                position = {
                    "position_id": f"STAKE-{self._position_count:06d}",
                    "token_id": token.get("token_id", ""),
                    "project_id": token.get("project_id", ""),
                    "locked_amount": locked_amount,
                    "liquid_amount": liquid_amount,
                    "yield_earned": yield_amount,
                    "apy": self.apy,
                    "lockup_ratio": self.lockup_ratio,
                    "monthly_yield_rate": round(self.apy / 12, 4),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                staking_results.append(position)
                self._positions.append(position)

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logs.append(
                f"[INFO] {len(staking_results)} positions created, "
                f"locked={total_locked_batch:,.2f}€, "
                f"liquid={sum(p['liquid_amount'] for p in staking_results):,.2f}€, "
                f"yield={total_yield_batch:,.2f}€, "
                f"elapsed={elapsed_ms}ms"
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [
                    {
                        "type": "staking_pool_batch",
                        "chain": self.chain,
                        "position_count": len(staking_results),
                        "total_locked": round(total_locked_batch, 6),
                        "total_yield_distributed": round(total_yield_batch, 6),
                        "apy": self.apy,
                        "lockup_ratio": self.lockup_ratio,
                        "positions": staking_results,
                    }
                ],
                "error": None,
                "logs": logs,
                "metadata": {
                    "total_locked_all_time": round(self.total_locked, 6),
                    "total_yield_all_time": round(self.total_yield_distributed, 6),
                    "position_count_all_time": self._position_count,
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "StakingPool failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            logs.append(f"[ERROR] {e}")

            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "STAKING_POOL_FAILED", "message": str(e)},
                "logs": logs,
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_stats(self) -> Dict[str, Any]:
        """Return staking statistics."""
        return {
            "total_locked": round(self.total_locked, 6),
            "total_liquid": round(self.total_liquid, 6),
            "total_yield_distributed": round(self.total_yield_distributed, 6),
            "position_count": self._position_count,
            "apy": self.apy,
            "lockup_ratio": self.lockup_ratio,
            "monthly_yield_rate": round(self.apy / 12, 4),
            "chain": self.chain,
        }
