"""S3: DePINWalletAgent — Micro-payout wallet management for sensor operators.

Chain: DEPIN_APPCHAIN | Wallet aggregation | Payout batching
Manages per-sensor balances and aggregates micro-payouts.
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DePINWalletAgent")


@dataclass
class DePINWalletState:
    """Per-sensor wallet state."""
    balance: float = 0.0
    total_deposits: float = 0.0
    total_withdrawals: float = 0.0
    pending_payouts: int = 0
    last_updated: str = ""


class DePINWalletAgent:
    """Manages micro-payout wallets for DePIN sensor operators."""

    def __init__(
        self,
        chain: str = "DEPIN_APPCHAIN",
        user_id: Optional[str] = None,
        payout_threshold: Optional[float] = None,
    ):
        self.chain = chain
        self.user_id = user_id or os.getenv("SIMCHAIN_USER_ID", "default")
        self.payout_threshold = payout_threshold or float(
            os.getenv("SIMCHAIN_PAYOUT_THRESHOLD", "1.0")
        )
        self.wallets: Dict[str, DePINWalletState] = {}
        self._total_payouts_processed = 0.0

    async def process_batch(self, txs: List[Dict]) -> Dict[str, Any]:
        """Process micro-payouts for a batch of sensor transactions."""
        job_id = str(uuid.uuid4())
        start_time = time.time()
        logs: List[str] = []

        try:
            logger.info(
                "DePINWallet processing payouts",
                extra={"job_id": job_id, "tx_count": len(txs), "user_id": self.user_id},
            )
            logs.append(f"[INFO] processing {len(txs)} micro-payouts")

            total_payout = 0.0
            wallets_created = 0
            payouts_triggered = 0

            for tx in txs:
                sensor_id = tx.get("sensor_id", "UNKNOWN")
                amount = tx.get("amount", 0.0)

                if sensor_id not in self.wallets:
                    self.wallets[sensor_id] = DePINWalletState()
                    wallets_created += 1

                wallet = self.wallets[sensor_id]
                wallet.balance += amount
                wallet.total_deposits += amount
                wallet.pending_payouts += 1
                wallet.last_updated = datetime.now(timezone.utc).isoformat()
                total_payout += amount

                # Auto-payout if threshold reached
                if wallet.balance >= self.payout_threshold:
                    wallet.total_withdrawals += wallet.balance
                    wallet.balance = 0.0
                    wallet.pending_payouts = 0
                    payouts_triggered += 1

            self._total_payouts_processed += total_payout
            elapsed_ms = round((time.time() - start_time) * 1000, 2)

            logs.append(
                f"[INFO] total_payout={total_payout:.4f}€, "
                f"wallets={len(self.wallets)} ({wallets_created} new), "
                f"payouts_triggered={payouts_triggered}, "
                f"elapsed={elapsed_ms}ms"
            )

            return {
                "status": "completed",
                "job_id": job_id,
                "artifacts": [
                    {
                        "type": "depin_wallet_batch",
                        "chain": self.chain,
                        "total_payout": round(total_payout, 6),
                        "wallets_updated": len(self.wallets),
                        "wallets_created": wallets_created,
                        "payouts_triggered": payouts_triggered,
                        "payout_threshold": self.payout_threshold,
                        "wallet_summary": {
                            sid: {
                                "balance": round(w.balance, 6),
                                "total_deposits": round(w.total_deposits, 6),
                            }
                            for sid, w in list(self.wallets.items())[:10]
                        },
                    }
                ],
                "error": None,
                "logs": logs,
                "metadata": {
                    "total_payouts_all_time": round(self._total_payouts_processed, 6),
                    "active_wallets": len(self.wallets),
                    "elapsed_ms": elapsed_ms,
                    "user_id": self.user_id,
                },
            }

        except Exception as e:
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(
                "DePINWallet failed",
                extra={"job_id": job_id, "error": str(e)},
            )
            logs.append(f"[ERROR] {e}")

            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": {"code": "DEPIN_WALLET_FAILED", "message": str(e)},
                "logs": logs,
                "metadata": {"elapsed_ms": elapsed_ms, "user_id": self.user_id},
            }

    def get_stats(self) -> Dict[str, Any]:
        """Return wallet statistics."""
        return {
            "active_wallets": len(self.wallets),
            "total_payouts_processed": round(self._total_payouts_processed, 6),
            "payout_threshold": self.payout_threshold,
            "chain": self.chain,
        }
