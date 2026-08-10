"""A7: TokenMinterChain — Token minting with burn mechanics.

Chain: LIQUIDITY_L2 | Event-driven | 5% burn at mint
"""

import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TokenMinterChain")


class TokenMinterChain:
    """Sovereign token chain: mints tokens from settlements, burns 5%."""

    def __init__(
        self,
        chain_id: str = "LIQUIDITY_L2",
        user_id: Optional[str] = None,
        burn_rate: Optional[float] = None,
    ):
        self.chain_id = chain_id
        self.user_id = user_id or os.getenv("MULTICHAIN_USER_ID", "default")
        self.burn_rate = burn_rate or float(os.getenv("MC_TOKEN_BURN_RATE", "0.05"))
        self.block_height = 0
        self.total_minted = 0.0
        self.total_burned = 0.0
        self._mint_count = 0

    async def process_block(self, settlements: List[Dict]) -> Dict[str, Any]:
        """Mint tokens from a block of settlements."""
        job_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            logger.info("TokenMinter processing block", extra={"job_id": job_id, "count": len(settlements)})

            tokens = []
            batch_minted = 0.0
            batch_burned = 0.0
            for s in settlements:
                net_amount = s.get("net", s.get("amount", 0.0) * 0.80)
                burn_amount = round(net_amount * self.burn_rate, 6)
                net_tokens = round(net_amount - burn_amount, 6)

                self.total_minted += net_amount
                self.total_burned += burn_amount
                self._mint_count += 1
                batch_minted += net_amount
                batch_burned += burn_amount

                tokens.append({
                    "project_id": s.get("project_id", ""),
                    "mint_amount": round(net_amount, 6),
                    "burn_amount": burn_amount,
                    "net_tokens": net_tokens,
                    "burn_rate": self.burn_rate,
                    "token_id": hashlib.sha256(
                        f"TOKEN_{s.get('project_id','')}_{self._mint_count}".encode()
                    ).hexdigest()[:16],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            self.block_height += 1
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [{
                    "type": "token_block",
                    "chain_id": self.chain_id,
                    "block_height": self.block_height,
                    "mint_count": len(tokens),
                    "total_minted": round(batch_minted, 6),
                    "total_burned": round(batch_burned, 6),
                    "tokens": tokens,
                }],
                "error": None,
                "logs": [],
                "metadata": {
                    "total_minted_all_time": round(self.total_minted, 6),
                    "total_burned_all_time": round(self.total_burned, 6),
                    "effective_supply": round(self.total_minted - self.total_burned, 6),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("TokenMinter failed", extra={"job_id": job_id, "error": str(e)})
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "TOKEN_CHAIN_FAILED", "message": str(e)},
                "logs": [f"[ERROR] {e}"],
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_chain_state(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "block_height": self.block_height,
            "total_minted": round(self.total_minted, 6),
            "total_burned": round(self.total_burned, 6),
            "effective_supply": round(self.total_minted - self.total_burned, 6),
        }
