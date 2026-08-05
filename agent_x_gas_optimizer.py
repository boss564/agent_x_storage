"""
Agent X — Live-Gas-Optimizer (Klasse B: Druckventile — Production Core).

Berechnet pro Block die optimale Priority-Fee und sagt Basefee voraus.
Integriert MEV-Schutz-Kosten/Nutzen-Analyse.

Kern-Formeln:
  - Basefee-Prediction: EMA(12-Blöcke) × Trend-Faktor × Block-Auslastung
  - Priority-Fee: Perzentil-basiert mit Mempool-Druck-Korrektur
  - MEV-Schutz-Break-Even: Bribe < (Trade_Value × MEV_Risk_Pct) → lohnt sich

Chains: ETH Mainnet, Arbitrum, Base, Optimism

Usage:
  opt = GasOptimizer()
  rec = opt.optimize(trade_value_usd=100_000, urgency="normal")
  # → {"basefee_gwei": 22.3, "priority_fee_gwei": 1.8, "total_gwei": 24.1,
  #    "use_mev_protect": False, "savings_vs_naive_usd": 8.40}
"""

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("gas_optimizer")

# ─── Konfiguration ───────────────────────────────────────────────────

ETH_PRICE_USD = float(os.getenv("ETH_PRICE_USD", "3200"))
DEFAULT_GAS_LIMIT_SWAP = 180_000
DEFAULT_GAS_LIMIT_ARBITRAGE = 350_000
DEFAULT_GAS_LIMIT_FLASH_LOAN = 500_000
DEFAULT_GAS_LIMIT_SIMPLE = 21_000

# Gas-Preise nach Chain (Gwei)
CHAIN_BASEFEE_DEFAULTS = {
    "ETHEREUM": 22.0, "ARBITRUM": 0.10, "BASE": 0.05, "OPTIMISM": 0.02,
}

# Priority-Fee-Defaults (P50/P95 gwei)
CHAIN_PRIORITY_DEFAULTS = {
    "ETHEREUM": (1.5, 4.5), "ARBITRUM": (0.01, 0.10),
    "BASE": (0.01, 0.05), "OPTIMISM": (0.005, 0.02),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return time.time()


# ═══════════════════════════════════════════════════════════════════════
# Rolling Gas History
# ═══════════════════════════════════════════════════════════════════════

class GasHistory:
    """Trackt Basefee-Historie pro Chain mit Rolling Windows."""

    def __init__(self, window_size: int = 100):
        self.basefees: dict[str, deque] = {}  # chain → deque of gwei values
        self.priority_fees: dict[str, deque] = {}
        self.blob_prices: deque = deque(maxlen=window_size)
        self.window = window_size

    def record_block(self, chain: str, basefee: float, pf_p50: float,
                     pf_p95: float, blob_price: float = 0, gas_used_pct: float = 70):
        self.basefees.setdefault(chain, deque(maxlen=self.window)).append(basefee)
        self.priority_fees.setdefault(chain, deque(maxlen=self.window)).append({
            "p50": pf_p50, "p95": pf_p95, "gas_used_pct": gas_used_pct,
        })
        if blob_price > 0:
            self.blob_prices.append(blob_price)

    def get_stats(self, chain: str) -> dict:
        bf = list(self.basefees.get(chain, deque([CHAIN_BASEFEE_DEFAULTS.get(chain, 20)])))
        pf = list(self.priority_fees.get(chain, deque([{"p50": 1.5, "p95": 4.5}])))

        if not bf:
            return {"basefee_mean": 20, "basefee_std": 0, "pf_p50": 1.5, "pf_p95": 4.5}

        mean_bf = sum(bf) / len(bf)
        std_bf = (sum((v - mean_bf) ** 2 for v in bf) / len(bf)) ** 0.5 if len(bf) > 1 else 0

        return {
            "basefee_mean": round(mean_bf, 2),
            "basefee_std": round(std_bf, 2),
            "basefee_min": round(min(bf), 2),
            "basefee_max": round(max(bf), 2),
            "basefee_current": round(bf[-1], 2) if bf else 0,
            "pf_p50_mean": round(sum(p["p50"] for p in pf) / len(pf), 2),
            "pf_p95_mean": round(sum(p["p95"] for p in pf) / len(pf), 2),
            "pf_p95_current": round(pf[-1]["p95"], 2) if pf else 4.5,
            "avg_gas_used_pct": round(sum(p.get("gas_used_pct", 70) for p in pf) / len(pf), 1),
            "samples": len(bf),
        }

    def predict_basefee(self, chain: str) -> float:
        """Sagt Basefee für den nächsten Block voraus.

        Formel: EMA(12-Blöcke) × (1 + Trend-Faktor) × Block-Auslastung
        """
        bf = list(self.basefees.get(chain, deque()))
        if len(bf) < 4:
            return CHAIN_BASEFEE_DEFAULTS.get(chain, 20.0)

        # EMA mit alpha=0.2 über die letzten 12 Blöcke
        recent = bf[-min(12, len(bf)):]
        ema = recent[0]
        for v in recent[1:]:
            ema = 0.2 * v + 0.8 * ema

        # Trend: Steigung der letzten 6 Blöcke
        recent6 = recent[-min(6, len(recent)):]
        if len(recent6) >= 2:
            trend = (recent6[-1] - recent6[0]) / recent6[0] if recent6[0] > 0 else 0
        else:
            trend = 0

        # Block-Auslastung >85% → Basefee steigt (max 12.5% pro Block)
        pf_list = list(self.priority_fees.get(chain, deque()))
        avg_fullness = sum(p.get("gas_used_pct", 70) for p in pf_list[-3:]) / 3 if pf_list else 70

        fullness_factor = 1.0 + max(0, (avg_fullness - 85) / 100 * 0.125)

        prediction = ema * (1 + trend) * fullness_factor
        # Basefee ändert sich max 12.5% pro Block (EIP-1559)
        current = bf[-1] if bf else 20
        max_change = current * 0.125
        prediction = max(current - max_change, min(current + max_change, prediction))

        return round(prediction, 2)


# ─── Globale Gas-History ─────────────────────────────────────────────

gas_history = GasHistory()

# Seed mit realistischen Werten (letzte 20 ETH-Blöcke)
SEED_BASEFEES = [21.5, 21.8, 22.1, 22.4, 22.1, 21.9, 21.7, 22.0, 22.3, 22.6,
                 22.4, 22.2, 22.0, 22.3, 22.7, 23.0, 22.8, 22.5, 22.3, 22.6]
SEED_PF = [(1.2, 3.5) for _ in range(20)]  # (p50, p95)
for bf in SEED_BASEFEES:
    gas_history.record_block("ETHEREUM", bf, 1.2, 3.5, blob_price=18.0, gas_used_pct=72)


# ═══════════════════════════════════════════════════════════════════════
# GasOptimizer
# ═══════════════════════════════════════════════════════════════════════

class GasOptimizer:
    """Live-Gas-Optimizer mit MEV-Schutz-Kosten/Nutzen-Analyse.

    Usage:
        opt = GasOptimizer()
        rec = opt.optimize(trade_value_usd=50000, urgency="high")
        print(f"Pay {rec['total_gwei']:.1f} gwei — save ${rec['savings_vs_naive_usd']:.2f}")
    """

    def __init__(self, history: GasHistory | None = None):
        self.history = history or gas_history

    def optimize(
        self,
        trade_value_usd: float = 50_000,
        urgency: str = "normal",  # low | normal | high | critical
        chain: str = "ETHEREUM",
        tx_type: str = "swap",  # swap | arbitrage | flash_loan | simple_transfer
        mev_bots_in_mempool: int = 0,
    ) -> dict:
        """Berechnet optimale Gas-Parameter für eine Transaktion.

        Args:
            trade_value_usd: Volumen der Transaktion in USD
            urgency: Dringlichkeit (beeinflusst Priority-Fee-Perzentil)
            chain: Chain
            tx_type: Typ der Transaktion
            mev_bots_in_mempool: Anzahl erkannter MEV-Bots

        Returns:
            Optimierungs-Empfehlung mit allen Gas-Parametern
        """
        try:
            # Schritt 1: Basefee-Prognose
            predicted_basefee = self._predict_basefee(chain, urgency)

            # Schritt 2: Optimale Priority-Fee
            optimal_pf = self._calculate_priority_fee(chain, urgency, mev_bots_in_mempool)

            # Schritt 3: Gas-Limit je nach TX-Typ
            gas_limit = self._gas_limit_for_tx(tx_type)

            # Schritt 4: MEV-Schutz-Break-Even-Analyse
            mev_analysis = self._analyze_mev_protection(
                trade_value_usd, gas_limit, predicted_basefee + optimal_pf,
                mev_bots_in_mempool, chain,
            )

            # Schritt 5: Kosten-Berechnung
            total_gwei = predicted_basefee + optimal_pf
            total_cost_eth = (total_gwei * gas_limit) / 1e9
            total_cost_usd = total_cost_eth * ETH_PRICE_USD

            # Vergleich: naive Strategie (immer P95 Priority + kein MEV-Schutz)
            stats = self.history.get_stats(chain)
            naive_pf = stats.get("pf_p95_current", 4.5)
            naive_total = predicted_basefee + naive_pf
            naive_cost_eth = (naive_total * gas_limit) / 1e9
            naive_cost_usd = naive_cost_eth * ETH_PRICE_USD
            savings_vs_naive = naive_cost_usd - total_cost_usd

            # Priority-Level (0-4)
            if urgency == "critical":
                pf_mult = 1.5
                level = 4
            elif urgency == "high":
                pf_mult = 1.2
                level = 3
            elif urgency == "normal":
                pf_mult = 1.0
                level = 2
            else:  # low
                pf_mult = 0.6
                level = 1

            # Wenn MEV-Bots aktiv: erhöhe Priority-Fee
            if mev_bots_in_mempool > 5:
                optimal_pf *= 1.5
            elif mev_bots_in_mempool > 2:
                optimal_pf *= 1.2

            total_gwei = predicted_basefee + optimal_pf

            return {
                "status": "ok",
                "chain": chain,
                "tx_type": tx_type,
                "urgency": urgency,
                "recommendation": {
                    "predicted_basefee_gwei": predicted_basefee,
                    "optimal_priority_fee_gwei": round(optimal_pf, 2),
                    "total_gas_price_gwei": round(total_gwei, 2),
                    "gas_limit": gas_limit,
                    "estimated_cost_eth": round(total_cost_eth, 8),
                    "estimated_cost_usd": round(total_cost_usd, 2),
                    "savings_vs_naive_usd": round(savings_vs_naive, 2),
                    "savings_vs_naive_pct": round(
                        (savings_vs_naive / naive_cost_usd * 100) if naive_cost_usd > 0 else 0, 1
                    ),
                    "use_mev_protection": mev_analysis["use_mev_protection"],
                    "mev_protection_cost_usd": round(mev_analysis["protection_cost_usd"], 2),
                    "mev_protection_roi": mev_analysis["protection_roi"],
                    "confirmation_estimate_s": self._estimate_confirmation(
                        optimal_pf, chain, mev_bots_in_mempool,
                    ),
                },
                "context": {
                    "chain_basefee_history": self.history.get_stats(chain),
                    "mev_bots_detected": mev_bots_in_mempool,
                    "block_fullness_pct": stats.get("avg_gas_used_pct", 70),
                },
                "timestamp": _now_iso(),
            }
        except Exception as e:
            logger.error("GasOptimizer Fehler: %s", e)
            return {"status": "failed", "error": str(e)}

    def _predict_basefee(self, chain: str, urgency: str) -> float:
        """Prognostiziert Basefee für nächsten Block."""
        predicted = self.history.predict_basefee(chain)

        # Bei critical: Sicherheitspuffer +10%
        if urgency == "critical":
            predicted *= 1.10

        return round(predicted, 2)

    def _calculate_priority_fee(self, chain: str, urgency: str, mev_bots: int) -> float:
        """Berechnet optimale Priority-Fee.

        Strategie:
          - low:     P25 (langsam, billig)
          - normal:  P50 (ausgewogen)
          - high:    P75 (schnell)
          - critical: P90 + MEV-Zuschlag (maximale Inklusions-Chance)
        """
        stats = self.history.get_stats(chain)
        pf_p50 = stats.get("pf_p50_mean", 1.5)
        pf_p95 = stats.get("pf_p95_current", 4.5)

        if urgency == "low":
            pf = pf_p50 * 0.6
        elif urgency == "normal":
            pf = pf_p50 * 0.9  # Leicht unter P50
        elif urgency == "high":
            pf = pf_p50 * 1.5  # P75-Näherung
        else:  # critical
            pf = pf_p95 * 0.8  # Nahe P95

        # MEV-Bot-Zuschlag
        if mev_bots > 5:
            pf *= 1.5
        elif mev_bots > 2:
            pf *= 1.2

        return round(pf, 2)

    def _gas_limit_for_tx(self, tx_type: str) -> int:
        return {
            "swap": DEFAULT_GAS_LIMIT_SWAP,
            "arbitrage": DEFAULT_GAS_LIMIT_ARBITRAGE,
            "flash_loan": DEFAULT_GAS_LIMIT_FLASH_LOAN,
            "simple_transfer": DEFAULT_GAS_LIMIT_SIMPLE,
        }.get(tx_type, DEFAULT_GAS_LIMIT_SWAP)

    def _analyze_mev_protection(
        self, trade_value: float, gas_limit: int, gas_price_gwei: float,
        mev_bots: int, chain: str,
    ) -> dict:
        """Kosten/Nutzen-Analyse: Lohnt sich Flashbots/MEV-Boost?

        Break-Even: Flashbots-Bribe < Trade_Value × MEV_Risk × Sandwich-Wahrscheinlichkeit

        MEV-Risk ist chain-abhängig:
          - ETH Mainnet: 0.5-2% Sandwich-Risk je nach Trade-Größe
          - Arbitrum: 0.1-0.5% (weniger MEV-Aktivität)
        """
        # MEV-Risiko: Wie wahrscheinlich ist ein Sandwich/Frontrun?
        mev_risk_base = {"ETHEREUM": 0.015, "ARBITRUM": 0.003, "BASE": 0.005, "OPTIMISM": 0.002}
        mev_risk = mev_risk_base.get(chain, 0.01)

        # Erhöhtes Risiko bei vielen MEV-Bots
        if mev_bots > 5:
            mev_risk *= 2.5
        elif mev_bots > 2:
            mev_risk *= 1.5

        # Erhöhtes Risiko bei großen Trades
        if trade_value > 1_000_000:
            mev_risk *= 2.0
        elif trade_value > 100_000:
            mev_risk *= 1.3

        expected_mev_loss = trade_value * mev_risk

        # Flashbots-Bribe (typisch: ETH mainnet ~0.01-0.05 ETH)
        protection_cost_eth = 0.02 if chain == "ETHEREUM" else 0.001
        protection_cost_usd = protection_cost_eth * ETH_PRICE_USD

        # ROI der MEV-Protection
        if protection_cost_usd > 0:
            protection_roi = (expected_mev_loss - protection_cost_usd) / protection_cost_usd
        else:
            protection_roi = 0

        use_protection = expected_mev_loss > protection_cost_usd * 1.5  # Mindestens 1.5x ROI

        return {
            "mev_risk_pct": round(mev_risk * 100, 2),
            "expected_mev_loss_usd": round(expected_mev_loss, 2),
            "protection_cost_usd": round(protection_cost_usd, 2),
            "protection_roi": f"{protection_roi:.1f}x",
            "use_mev_protection": use_protection,
            "recommendation": (
                "Flashbots/MEV-Boost empfohlen — MEV-Verlust > Schutzkosten"
                if use_protection
                else "Direkt-Sendung ausreichend — MEV-Risiko zu gering für Schutzkosten"
            ),
        }

    def _estimate_confirmation(self, pf: float, chain: str, mev_bots: int) -> int:
        """Schätzt Bestätigungszeit in Sekunden."""
        stats = self.history.get_stats(chain)
        pf_p95 = stats.get("pf_p95_current", 4.5)

        if pf >= pf_p95:
            base = 12  # Nächster Block (12s)
        elif pf >= pf_p95 * 0.7:
            base = 24  # 2 Blöcke
        elif pf >= pf_p95 * 0.4:
            base = 60  # ~5 Blöcke
        else:
            base = 120  # ~10 Blöcke

        if mev_bots > 5:
            base = int(base * 1.5)  # MEV-Konkurrenz verzögert

        return base

    # ─── Batch-Optimierung ───────────────────────────────────────────

    def optimize_batch(self, trades: list[dict]) -> list[dict]:
        """Optimiert mehrere Transaktionen gleichzeitig.

        Args:
            trades: [{"value_usd": 50000, "urgency": "normal", "tx_type": "swap"}, ...]

        Returns:
            Liste von Optimierungs-Empfehlungen, sortiert nach Dringlichkeit
        """
        results = []
        for t in trades:
            result = self.optimize(
                trade_value_usd=t.get("value_usd", 50000),
                urgency=t.get("urgency", "normal"),
                tx_type=t.get("tx_type", "swap"),
                mev_bots_in_mempool=t.get("mev_bots", 0),
            )
            results.append(result)

        # Sortiere: critical first, then by savings
        urgency_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        results.sort(key=lambda r: (
            urgency_order.get(r.get("urgency", "normal"), 2),
            -r.get("recommendation", {}).get("savings_vs_naive_usd", 0),
        ))
        return results

    # ─── Dashboard ───────────────────────────────────────────────────

    def dashboard(self) -> str:
        """Live-Gas-Dashboard."""
        stats = self.history.get_stats("ETHEREUM")
        prediction = self.history.predict_basefee("ETHEREUM")
        rec = self.optimize(trade_value_usd=100_000, urgency="normal")

        lines = [
            "=" * 60,
            "  AGENT X — LIVE GAS OPTIMIZER",
            f"  {_now_iso()}",
            "=" * 60,
            "",
            f"  Basefee:  current={stats['basefee_current']} gwei, "
            f"predicted={prediction} gwei",
            f"  History:  mean={stats['basefee_mean']}, "
            f"min={stats['basefee_min']}, max={stats['basefee_max']} "
            f"(n={stats['samples']})",
            f"  Priority: P50={stats['pf_p50_mean']} gwei, "
            f"P95={stats['pf_p95_current']} gwei",
            "",
            "  SAMPLE OPTIMIZATION ($100k Swap, normal urgency):",
            f"    Gas Price:   {rec['recommendation']['total_gas_price_gwei']:.1f} gwei",
            f"    Est. Cost:   ${rec['recommendation']['estimated_cost_usd']:.2f}",
            f"    vs. Naive:   SAVE ${rec['recommendation']['savings_vs_naive_usd']:.2f} "
            f"({rec['recommendation']['savings_vs_naive_pct']:.0f}%)",
            f"    MEV Protect: {'YES' if rec['recommendation']['use_mev_protection'] else 'NO'} "
            f"(ROI: {rec['recommendation']['mev_protection_roi']})",
            f"    Confirm:     ~{rec['recommendation']['confirmation_estimate_s']}s",
            "",
            "=" * 60,
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Convenience — Quick-Optimize für den Orchestrator
# ═══════════════════════════════════════════════════════════════════════

def quick_optimize(
    trade_value_usd: float = 50_000,
    urgency: str = "normal",
    mev_bots: int = 0,
    chain: str = "ETHEREUM",
) -> dict:
    """Einzeilige Optimierung für direkte Orchestrator-Integration."""
    opt = GasOptimizer()
    return opt.optimize(
        trade_value_usd=trade_value_usd,
        urgency=urgency,
        mev_bots_in_mempool=mev_bots,
        chain=chain,
    )


def feed_live_block(basefee: float, pf_p50: float, pf_p95: float,
                    blob_price: float = 0, gas_used_pct: float = 70):
    """Füttert Live-Block-Daten in die globale History."""
    gas_history.record_block("ETHEREUM", basefee, pf_p50, pf_p95,
                             blob_price=blob_price, gas_used_pct=gas_used_pct)


# ═══════════════════════════════════════════════════════════════════════
# PRODUCTION-GRADE: Dynamic Basefee Spread Optimizer (EVM)
# ═══════════════════════════════════════════════════════════════════════

class EVMDynamicOptimizer:
    """EVM-Optimizer mit dynamischem Volatilitätsfaktor (Alpha).

    Formel: priorityFee = baseFee × (1 + α) + δ

    α = std(priorityFees_10_blocks) / mean(priorityFees_10_blocks)
    δ = 0.05 Gwei (Sicherheitspuffer)

    Future-Block: maxBaseFee = baseFee × (1.125)^n
    """

    def __init__(self, lookback_blocks: int = 10, delta_gwei: float = 0.05):
        self.lookback = lookback_blocks
        self.delta = delta_gwei
        self._tip_history: deque = deque(maxlen=100)
        self._success_count = 0
        self._total_count = 0

    def compute_optimal_priority_fee(
        self, current_basefee_gwei: float,
        recent_priority_fees: list[float] | None = None,
        mev_pressure_index: float = 50.0,
        oracle_update_expected: bool = False,
    ) -> dict:
        """Berechnet optimale Priority-Fee mit dynamischem Alpha.

        Args:
            current_basefee_gwei: Aktuelle Basefee
            recent_priority_fees: P50/P95 Priority-Fees der letzten N Blöcke
            mev_pressure_index: Von Klasse B2 (0-100)
            oracle_update_expected: Von Klasse D3-1 (Update in <5s?)
        """
        tips = recent_priority_fees or [1.5, 1.6, 1.4, 1.8, 1.5, 1.7, 1.6, 1.9, 1.5, 1.8]

        # Alpha: Volatilität = std / mean
        import math
        mean_tip = sum(tips) / len(tips)
        variance = sum((t - mean_tip) ** 2 for t in tips) / len(tips)
        std_tip = math.sqrt(variance)
        alpha = (std_tip / mean_tip) if mean_tip > 0 else 0.1

        # Basis-Priority-Fee
        optimal_pf = current_basefee_gwei * (1 + alpha) + self.delta

        # MEV-Pressure-Korrektur (von Klasse B)
        if mev_pressure_index > 70:
            optimal_pf *= 1.25  # +25% bei hohem MEV-Druck
        elif mev_pressure_index > 50:
            optimal_pf *= 1.10

        # Oracle-Update-Boost (von Klasse D)
        if oracle_update_expected:
            optimal_pf *= 1.3  # +30% um im Oracle-Block zu landen

        optimal_pf = round(optimal_pf, 2)
        self._tip_history.append(optimal_pf)

        return {
            "optimal_priority_fee_gwei": optimal_pf,
            "alpha": round(alpha, 4),
            "delta": self.delta,
            "std_tips": round(std_tip, 4),
            "mean_tips": round(mean_tip, 2),
            "mev_adjustment": mev_pressure_index > 50,
            "oracle_boost": oracle_update_expected,
            "formula": f"{current_basefee_gwei:.1f} × (1 + {alpha:.4f}) + {self.delta} = {optimal_pf:.2f}",
        }

    def predict_max_fee_for_future_block(
        self, current_basefee_gwei: float, blocks_in_future: int,
    ) -> dict:
        """EIP-1559: maxBaseFee = baseFee × (1.125)^n."""
        max_basefee = current_basefee_gwei * (1.125 ** blocks_in_future)
        pf = self.compute_optimal_priority_fee(current_basefee_gwei)
        total = max_basefee + pf["optimal_priority_fee_gwei"]

        return {
            "current_basefee": current_basefee_gwei,
            "blocks_in_future": blocks_in_future,
            "max_possible_basefee": round(max_basefee, 2),
            "priority_fee": pf["optimal_priority_fee_gwei"],
            "total_max_fee_gwei": round(total, 2),
            "eip1559_rule": f"baseFee × (1.125)^{blocks_in_future}",
        }

    def record_transaction_result(self, landed_in_target_block: bool):
        """Feedback-Loop: Trackt Erfolgsrate zur Alpha-Kalibrierung."""
        self._total_count += 1
        if landed_in_target_block:
            self._success_count += 1

    @property
    def success_rate(self) -> float:
        return self._success_count / max(1, self._total_count)

    def should_adjust_alpha(self) -> dict:
        """Prüft ob Alpha erhöht werden muss (Erfolgsrate < 80%)."""
        rate = self.success_rate
        if rate < 0.5:
            action = "INCREASE_SIGNIFICANTLY"
            new_delta = self.delta * 1.5
        elif rate < 0.8:
            action = "INCREASE"
            new_delta = self.delta * 1.2
        elif rate > 0.95:
            action = "DECREASE"
            new_delta = self.delta * 0.9
        else:
            action = "MAINTAIN"
            new_delta = self.delta

        return {
            "success_rate": round(rate, 2),
            "action": action,
            "current_delta": self.delta,
            "suggested_delta": round(new_delta, 4),
            "total_tracked": self._total_count,
        }


# ═══════════════════════════════════════════════════════════════════════
# PRODUCTION-GRADE: Solana Priority-Fee + Jito-Tip Optimizer
# ═══════════════════════════════════════════════════════════════════════

class SolanaPriorityOptimizer:
    """Solana-Optimizer: CU-Preis + Jito-Tip.

    Priority-Fee-Formel:
      priority_fee_lamports = ceil(cu_price × cu_limit / 1_000_000)

    Jito-Tip-Formel:
      tip = max(landed_tips_50th_percentile, expected_profit × 0.05)

    Integration mit Klasse A (Leader Schedule):
      Niedrige Auslastung → senke cu_price + jito_tip
    """

    def __init__(self):
        self._cu_price_history: deque = deque(maxlen=100)
        self._tip_floor_history: deque = deque(maxlen=50)

    def compute_optimal_cu_price(
        self,
        recent_prioritization_fees: list[int] | None = None,
        leader_utilization_pct: float = 50.0,
    ) -> dict:
        """Berechnet optimalen CU-Preis (Mikro-Lamports) via Median.

        Args:
            recent_prioritization_fees: Liste letzter CU-Preise (Mikro-Lamports)
            leader_utilization_pct: Von Klasse A (Leader-Auslastung)
        """
        fees = recent_prioritization_fees or [5000, 8000, 12000, 6000, 9000, 7000, 11000, 5000, 8500, 9500]
        sorted_fees = sorted(fees)
        median = sorted_fees[len(sorted_fees) // 2]
        p75 = sorted_fees[int(len(sorted_fees) * 0.75)]

        cu_price = median

        # Leader-Auslastung (von Klasse A): niedrige Auslastung → niedrigere Fees
        if leader_utilization_pct < 30:
            cu_price = int(cu_price * 0.7)  # -30% bei niedriger Auslastung
        elif leader_utilization_pct > 80:
            cu_price = int(cu_price * 1.3)  # +30% bei hoher Auslastung

        self._cu_price_history.append(cu_price)

        return {
            "optimal_cu_price_microlamports": cu_price,
            "median_recent": median,
            "p75_recent": p75,
            "leader_utilization_pct": leader_utilization_pct,
            "leader_discount_applied": leader_utilization_pct < 30,
            "min_recent": min(fees),
            "max_recent": max(fees),
            "samples": len(fees),
        }

    def compute_priority_fee_lamports(
        self, cu_price: int, estimated_cu_limit: int = 200_000,
    ) -> int:
        """priority_fee = ceil(cu_price × cu_limit / 1_000_000)"""
        return (cu_price * estimated_cu_limit + 999_999) // 1_000_000

    def compute_optimal_jito_tip(
        self,
        expected_profit_lamports: int = 0,
        tip_floor_50th_lamports: int | None = None,
        oracle_update_expected: bool = False,
    ) -> dict:
        """Jito-Tip: max(tip_floor_50th, expected_profit × 0.05).

        Args:
            expected_profit_lamports: Erwarteter Profit in Lamports
            tip_floor_50th: 50. Perzentil der gelandeten Tips
            oracle_update_expected: Oracle-Update in <5s? → höherer Tip
        """
        floor = tip_floor_50th_lamports or 500_000  # Default: 0.0005 SOL
        profit_based = int(expected_profit_lamports * 0.05) if expected_profit_lamports > 0 else 0
        tip = max(floor, profit_based)

        # Oracle-Boost (von Klasse D)
        if oracle_update_expected:
            tip = int(tip * 1.5)

        self._tip_floor_history.append(tip)

        return {
            "optimal_jito_tip_lamports": tip,
            "optimal_jito_tip_sol": round(tip / 1e9, 9),
            "tip_floor_50th": floor,
            "profit_based_component": profit_based,
            "oracle_boost_applied": oracle_update_expected,
            "strategy": (
                "profit_based" if profit_based > floor
                else "floor_based" if floor > profit_based
                else "equal"
            ),
        }

    def full_optimization(
        self,
        expected_profit_lamports: int,
        estimated_cu_limit: int = 200_000,
        recent_cu_prices: list[int] | None = None,
        tip_floor_lamports: int | None = None,
        leader_utilization_pct: float = 50.0,
        oracle_update_expected: bool = False,
    ) -> dict:
        """Vollständige Solana-Fee-Optimierung in einem Aufruf."""
        cu_result = self.compute_optimal_cu_price(
            recent_prioritization_fees=recent_cu_prices,
            leader_utilization_pct=leader_utilization_pct,
        )
        cu_price = cu_result["optimal_cu_price_microlamports"]
        priority_fee = self.compute_priority_fee_lamports(cu_price, estimated_cu_limit)
        tip_result = self.compute_optimal_jito_tip(
            expected_profit_lamports=expected_profit_lamports,
            tip_floor_50th_lamports=tip_floor_lamports,
            oracle_update_expected=oracle_update_expected,
        )

        total_lamports = priority_fee + tip_result["optimal_jito_tip_lamports"]
        total_sol = total_lamports / 1e9
        profit_after_fees = expected_profit_lamports - total_lamports

        return {
            "cu_price_microlamports": cu_price,
            "cu_limit": estimated_cu_limit,
            "priority_fee_lamports": priority_fee,
            "jito_tip_lamports": tip_result["optimal_jito_tip_lamports"],
            "total_fee_lamports": total_lamports,
            "total_fee_sol": round(total_sol, 9),
            "expected_profit_lamports": expected_profit_lamports,
            "expected_profit_sol": round(expected_profit_lamports / 1e9, 9),
            "profit_after_fees_lamports": profit_after_fees,
            "profit_margin_pct": round(
                (profit_after_fees / expected_profit_lamports * 100)
                if expected_profit_lamports > 0 else 0, 2
            ),
            "cu_price_detail": cu_result,
            "jito_tip_detail": tip_result,
        }


# ═══════════════════════════════════════════════════════════════════════
# Circuit Breaker (Kill-Switch)
# ═══════════════════════════════════════════════════════════════════════

class FeeCircuitBreaker:
    """Verhindert Transaktionen wenn Fee > X% des erwarteten Profits.

    Default: Breche ab wenn Fee > 30% des Profits.
    """

    def __init__(self, max_fee_pct_of_profit: float = 30.0):
        self.max_pct = max_fee_pct_of_profit
        self._tripped_count = 0
        self._passed_count = 0

    def check(
        self, total_fee_usd: float, expected_profit_usd: float,
        chain: str = "ETHEREUM",
    ) -> dict:
        """Prüft ob die Transaktion unter der Kill-Schwelle bleibt.

        Returns:
            {"allowed": True/False, "reason": "..."}
        """
        if expected_profit_usd <= 0:
            # Kein Profit-Trade (z.B. einfacher Transfer) — immer erlauben
            self._passed_count += 1
            return {"allowed": True, "reason": "Non-profit transaction — allowed",
                    "fee_pct": 0}

        fee_pct = (total_fee_usd / expected_profit_usd) * 100

        if fee_pct > self.max_pct:
            self._tripped_count += 1
            return {
                "allowed": False,
                "reason": (
                    f"KILL-SWITCH: Fee (${total_fee_usd:.2f}) = {fee_pct:.1f}% "
                    f"of expected profit (${expected_profit_usd:.2f}) — "
                    f"exceeds {self.max_pct}% threshold"
                ),
                "fee_pct": round(fee_pct, 1),
                "chain": chain,
            }

        self._passed_count += 1
        return {"allowed": True, "fee_pct": round(fee_pct, 1),
                "reason": f"Fee {fee_pct:.1f}% under {self.max_pct}% — OK"}

    @property
    def stats(self) -> dict:
        total = self._tripped_count + self._passed_count
        return {
            "total_checked": total,
            "passed": self._passed_count,
            "tripped": self._tripped_count,
            "trip_rate_pct": round(
                self._tripped_count / max(1, total) * 100, 1
            ),
        }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dashboard"

    if cmd == "dashboard":
        opt = GasOptimizer()
        print(opt.dashboard())
    elif cmd == "optimize":
        value = float(sys.argv[2]) if len(sys.argv) > 2 else 100000
        urgency = sys.argv[3] if len(sys.argv) > 3 else "normal"
        opt = GasOptimizer()
        rec = opt.optimize(trade_value_usd=value, urgency=urgency)
        print(json.dumps(rec["recommendation"], indent=2))
    elif cmd == "batch":
        opt = GasOptimizer()
        trades = [
            {"value_usd": 50000, "urgency": "normal", "tx_type": "swap", "mev_bots": 1},
            {"value_usd": 500000, "urgency": "high", "tx_type": "arbitrage", "mev_bots": 3},
            {"value_usd": 10000, "urgency": "low", "tx_type": "simple_transfer", "mev_bots": 0},
            {"value_usd": 2000000, "urgency": "critical", "tx_type": "flash_loan", "mev_bots": 6},
        ]
        for r in opt.optimize_batch(trades):
            rec = r["recommendation"]
            print(f'{r["urgency"]:8s} ${r.get("tx_type","?"):15s}: '
                  f'{rec["total_gas_price_gwei"]:5.1f} gwei, '
                  f'${rec["estimated_cost_usd"]:6.2f}, '
                  f'save ${rec["savings_vs_naive_usd"]:5.2f}, '
                  f'MEV={"YES" if rec["use_mev_protection"] else "NO"}')
    elif cmd == "live":
        opt = GasOptimizer()
        print("Feeding live blocks...")
        for i in range(5):
            bf = 22.0 + i * 0.5
            feed_live_block(bf, 1.5 + i * 0.1, 3.5 + i * 0.3, gas_used_pct=70 + i * 5)
        print(f"Basefee prediction after 5 blocks: {gas_history.predict_basefee('ETHEREUM')} gwei")
        print(opt.dashboard())

    elif cmd == "evm_dynamic":
        # EVM Dynamic Alpha Optimizer Demo
        evm = EVMDynamicOptimizer()
        print("=== EVM Dynamic Basefee Spread Optimizer ===")
        print()
        # Normal
        r1 = evm.compute_optimal_priority_fee(22.0)
        print(f"Normal:  {r1['formula']}")
        print(f"         alpha={r1['alpha']:.4f}, std={r1['std_tips']:.4f}")
        # High MEV
        r2 = evm.compute_optimal_priority_fee(22.0, mev_pressure_index=75)
        print(f"MEV 75:  {r2['formula']} (MEV-Adjustment)")
        # Oracle expected
        r3 = evm.compute_optimal_priority_fee(22.0, oracle_update_expected=True)
        print(f"Oracle: {r3['formula']} (Oracle-Boost +30%)")
        # Future Block
        fb = evm.predict_max_fee_for_future_block(22.0, 3)
        print(f"Future (n=3): {fb['eip1559_rule']} → max {fb['total_max_fee_gwei']:.1f} gwei")
        # Feedback
        for _ in range(8):
            evm.record_transaction_result(True)
        evm.record_transaction_result(False)
        evm.record_transaction_result(False)
        print(f"Success Rate: {evm.success_rate:.0%} → {evm.should_adjust_alpha()['action']}")

    elif cmd == "solana":
        # Solana Priority + Jito Tip Optimizer
        sol = SolanaPriorityOptimizer()
        print("=== Solana Priority-Fee + Jito-Tip Optimizer ===")
        print()
        full = sol.full_optimization(
            expected_profit_lamports=10_000_000,  # 0.01 SOL Profit
            estimated_cu_limit=250_000,
            leader_utilization_pct=35.0,
            oracle_update_expected=False,
        )
        print(f"CU Price:  {full['cu_price_microlamports']:,} µLamports")
        print(f"Priority:  {full['priority_fee_lamports']:,} Lamports")
        print(f"Jito Tip:  {full['jito_tip_lamports']:,} Lamports")
        print(f"Total Fee: {full['total_fee_lamports']:,} Lamports = {full['total_fee_sol']:.9f} SOL")
        print(f"Profit:    {full['expected_profit_lamports']:,} Lamports → after fees: {full['profit_after_fees_lamports']:,} Lamports ({full['profit_margin_pct']:.1f}% margin)")
        print()
        # Mit Oracle-Boost
        full2 = sol.full_optimization(
            expected_profit_lamports=10_000_000,
            oracle_update_expected=True,
            leader_utilization_pct=75.0,
        )
        print(f"With Oracle-Boost + High-Leader-Util (75%):")
        print(f"  CU Price: {full2['cu_price_microlamports']:,} µLamports (+30% high util)")
        print(f"  Jito Tip: {full2['jito_tip_lamports']:,} Lamports (+50% oracle boost)")

    elif cmd == "circuit_breaker":
        cb = FeeCircuitBreaker(max_fee_pct_of_profit=30.0)
        print("=== Circuit Breaker (Kill-Switch) ===")
        print()
        checks = [
            (15.0, 100.0, "Normal trade"),
            (45.0, 100.0, "Expensive trade"),
            (5.0, 10.0, "Thin margin"),
            (8.0, 0, "Non-profit transfer"),
        ]
        for fee, profit, label in checks:
            r = cb.check(fee, profit)
            icon = "ALLOW" if r["allowed"] else "KILL"
            print(f"  {label}: Fee=${fee}, Profit=${profit} → {icon} ({r['reason'][:70]})")
        print(f"\nStats: {json.dumps(cb.stats, indent=2)}")

    else:
        print(f"Verwendung: {sys.argv[0]} [dashboard|optimize VALUE URGENCY|batch|live|evm_dynamic|solana|circuit_breaker]")
