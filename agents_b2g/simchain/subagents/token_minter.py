"""T1: TokenMinterAgent — Token minting from settlement proceeds with burn mechanics.

Chain: LIQUIDITY_L2 | Event-Driven | Tokenomics
Mints tokens proportional to net settlement amounts, with automatic burn rate.
"""

import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TokenMinterAgent")


class TokenMinterAgent:
    """Mints tokens from settlement proceeds with built-in burn mechanics."""

    def __init__(
        self,
        chain: str = "LIQUIDITY_L2",
        user_id: Optional[str] = None,
        burn_rate: Optional[float] = None,
        token_name: Optional[str] = None,
        token_symbol: Optional[str] = None,
    ):
        self.chain = chain
        self.user_id = user_id or os.getenv("SIMCHAIN_USER_ID", "default")
        self.burn_rate = burn_rate or float(os.getenv("SIMCHAIN_TOKEN_BURN_RATE", "0.05"))
        self.token_name = token_name or os.getenv("SIMCHAIN_TOKEN_NAME", "AgentX Euro")
        self.token_symbol = token_symbol or os.getenv("SIMCHAIN_TOKEN_SYMBOL", "AGXEu")
        self.total_minted = 0.0
        self.total_burned = 0.0
        self._mint_count = 0

    async def process_batch(self, settlements: List[Dict]) -> Dict[str, Any]:
        """Mint tokens from settlement net amounts with burn."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "TokenMinter processing batch",
                extra={
                    "job_id": job_id,
                    "settlement_count": len(settlements),
                    "burn_rate": self.burn_rate,
                    "user_id": self.user_id,
                },
            )
            logs.append(
                f"[INFO] minting tokens from {len(settlements)} settlements "
                f"(burn_rate={self.burn_rate})"
            )

            tokens = []
            total_minted_batch = 0.0
            total_burned_batch = 0.0

            for settlement in settlements:
                net_amount = settlement.get("net", settlement.get("amount", 0.0) * 0.80)
                burn_amount = round(net_amount * self.burn_rate, 6)
                net_tokens = round(net_amount - burn_amount, 6)

                self.total_minted += net_amount
                self.total_burned += burn_amount
                self._mint_count += 1
                total_minted_batch += net_amount
                total_burned_batch += burn_amount

                token = {
                    "project_id": settlement.get("project_id", "UNKNOWN"),
                    "mint_amount": round(net_amount, 6),
                    "burn_amount": burn_amount,
                    "net_tokens": net_tokens,
                    "burn_rate": self.burn_rate,
                    "token_name": self.token_name,
                    "token_symbol": self.token_symbol,
                    "token_id": hashlib.sha256(
                        f"TOKEN_{settlement.get('project_id','')}_{self._mint_count}".encode()
                    ).hexdigest()[:16],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                tokens.append(token)

            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logs.append(
                f"[INFO] {len(tokens)} tokens minted, "
                f"minted={total_minted_batch:,.2f}€, "
                f"burned={total_burned_batch:,.2f}€ "
                f"({self.burn_rate*100:.1f}%), "
                f"elapsed={elapsed_ms}ms"
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [
                    {
                        "type": "token_mint_batch",
                        "chain": self.chain,
                        "token_name": self.token_name,
                        "token_symbol": self.token_symbol,
                        "mint_count": len(tokens),
                        "total_minted": round(total_minted_batch, 6),
                        "total_burned": round(total_burned_batch, 6),
                        "burn_rate": self.burn_rate,
                        "tokens": tokens,
                    }
                ],
                "error": None,
                "logs": logs,
                "metadata": {
                    "total_minted_all_time": round(self.total_minted, 6),
                    "total_burned_all_time": round(self.total_burned, 6),
                    "mint_count_all_time": self._mint_count,
                    "effective_supply": round(self.total_minted - self.total_burned, 6),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "TokenMinter failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            logs.append(f"[ERROR] {e}")

            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "TOKEN_MINT_FAILED", "message": str(e)},
                "logs": logs,
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_stats(self) -> Dict[str, Any]:
        """Return minting statistics."""
        return {
            "total_minted": round(self.total_minted, 6),
            "total_burned": round(self.total_burned, 6),
            "effective_supply": round(self.total_minted - self.total_burned, 6),
            "burn_rate": self.burn_rate,
            "mint_count": self._mint_count,
            "token_name": self.token_name,
            "token_symbol": self.token_symbol,
            "chain": self.chain,
        }
