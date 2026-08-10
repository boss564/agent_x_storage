"""A3: DePINWalletChain — Micro-payout wallet management.

Chain: DEPIN_APPCHAIN | Per-sensor balance tracking | Auto-payout at threshold
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DePINWalletChain")


@dataclass
class WalletState:
    balance: float = 0.0
    total_earned: float = 0.0
    total_withdrawn: float = 0.0
    pending_payouts: int = 0


class DePINWalletChain:
    """Sovereign wallet chain: manages per-sensor micro-payout balances."""

    def __init__(
        self,
        chain_id: str = "DEPIN_APPCHAIN",
        user_id: Optional[str] = None,
        payout_threshold: Optional[float] = None,
    ):
        self.chain_id = chain_id
        self.user_id = user_id or os.getenv("MULTICHAIN_USER_ID", "default")
        self.payout_threshold = payout_threshold or float(
            os.getenv("MC_PAYOUT_THRESHOLD", "1.0")
        )
        self.block_height = 0
        self.wallets: Dict[str, WalletState] = {}
        self.state_root = "0x0"
        self._total_payouts = 0.0

    async def process_block(self, txs: List[Dict]) -> Dict[str, Any]:
        """Process micro-payouts for one block."""
        job_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            logger.info("DePINWallet processing block", extra={"job_id": job_id, "tx_count": len(txs)})

            total = 0.0
            payouts_triggered = 0
            for tx in txs:
                sid = tx.get("sensor_id", "UNKNOWN")
                amount = tx.get("amount", 0.0)
                if sid not in self.wallets:
                    self.wallets[sid] = WalletState()
                w = self.wallets[sid]
                w.balance += amount
                w.total_earned += amount
                w.pending_payouts += 1
                total += amount
                if w.balance >= self.payout_threshold:
                    w.total_withdrawn += w.balance
                    w.balance = 0.0
                    w.pending_payouts = 0
                    payouts_triggered += 1

            self._total_payouts += total
            self.block_height += 1
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [{
                    "type": "wallet_block",
                    "chain_id": self.chain_id,
                    "block_height": self.block_height,
                    "total_payout": round(total, 6),
                    "wallets_updated": len(self.wallets),
                    "payouts_triggered": payouts_triggered,
                }],
                "error": None,
                "logs": [],
                "metadata": {
                    "total_payouts_all_time": round(self._total_payouts, 6),
                    "active_wallets": len(self.wallets),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("DePINWallet failed", extra={"job_id": job_id, "error": str(e)})
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "WALLET_CHAIN_FAILED", "message": str(e)},
                "logs": [f"[ERROR] {e}"],
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_chain_state(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "block_height": self.block_height,
            "active_wallets": len(self.wallets),
            "total_payouts": round(self._total_payouts, 6),
            "payout_threshold": self.payout_threshold,
        }
