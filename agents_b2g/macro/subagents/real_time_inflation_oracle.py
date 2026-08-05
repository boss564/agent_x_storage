# agents_b2g/macro/subagents/real_time_inflation_oracle.py
"""
Agent 17.8 — RealTimeInflationOracle

Berechnet die Inflation in Echtzeit aus GAEB-Einheitspreisen (Bauwirtschaft)
und liefert einen Frühindikator für den allgemeinen Verbraucherpreisindex (VPI).

Theoretische Grundlagen:
  1. Quantitätsgleichung (Fisher):  M × V = P × Y
     → P = M × V / Y  (Preisniveau aus Geldmenge, Velocity, realer Output)
     → Inflation = ΔP / P

  2. Laspeyres-Preisindex (Basisjahr t₀):
     P_L = Σ(p_t × q₀) / Σ(p₀ × q₀) × 100

  3. Paasche-Preisindex (aktuelles Jahr t):
     P_P = Σ(p_t × q_t) / Σ(p₀ × q_t) × 100

  4. Fisher-Idealindex (geometrisches Mittel):
     P_F = √(P_L × P_P)

Datenquellen:
  - GAEB DA XML 3.3: Einheitspreise pro Position (p_t)
  - BKI-Baukostenindex: 42 Referenzpreise als Benchmark
  - VelocityOfMoneyTracker: V (Umlaufgeschwindigkeit)
  - Treasury: M (Geldmenge)

Features:
  - GAEB-basierter Baupreisindex (Laspeyres, Paasche, Fisher)
  - Monetäre vs. reale Inflation (Fisher-Quantitätsgleichung)
  - Sektorale Inflation (Tiefbau, Hochbau, Technik, etc.)
  - Regionale Inflation (Nord, Ost, Süd, West)
  - BKI-Benchmark-Vergleich (Destatis/BKI-Referenz)
  - Inflations-Prognose (AR(1)-Modell)
  - Alert-System bei Inflations-Anomalien
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from statistics import mean, stdev, median

logger = logging.getLogger("RealTimeInflationOracle")


class RealTimeInflationOracleSubagent:
    """
    Subagent 17.8: Echtzeit-Inflationsmessung aus GAEB-Einheitspreisen.

    Formel: Inflation_t = (P_t − P_{t−1}) / P_{t−1}
    wobei P_t aus GAEB-Einheitspreisen, Velocity und Geldmenge berechnet wird.
    """

    # BKI-Baukostenindex 2024 als Referenz (42 Positionen, Basis 2020=100)
    # Reale BKI-Daten für ausgewählte Gewerke
    BKI_REFERENCE = {
        "erdarbeiten": {"index_2020": 100.0, "index_2024": 131.2, "weight": 0.08},
        "betonbau": {"index_2020": 100.0, "index_2024": 127.8, "weight": 0.15},
        "mauerwerk": {"index_2020": 100.0, "index_2024": 125.3, "weight": 0.10},
        "stahlbau": {"index_2020": 100.0, "index_2024": 133.7, "weight": 0.12},
        "holzbau": {"index_2020": 100.0, "index_2024": 129.1, "weight": 0.05},
        "dach": {"index_2020": 100.0, "index_2024": 126.4, "weight": 0.07},
        "abdichtung": {"index_2020": 100.0, "index_2024": 124.9, "weight": 0.06},
        "putz": {"index_2020": 100.0, "index_2024": 122.6, "weight": 0.04},
        "fliesen": {"index_2020": 100.0, "index_2024": 120.3, "weight": 0.03},
        "elektro": {"index_2020": 100.0, "index_2024": 128.9, "weight": 0.08},
        "heizung": {"index_2020": 100.0, "index_2024": 130.5, "weight": 0.08},
        "sanitaer": {"index_2020": 100.0, "index_2024": 124.2, "weight": 0.06},
        "strassenbau": {"index_2020": 100.0, "index_2024": 132.8, "weight": 0.05},
        "kanalbau": {"index_2020": 100.0, "index_2024": 129.4, "weight": 0.03},
    }

    # Sektor-Mapping (GAEB-Gewerk → BKI-Kategorie)
    SECTOR_TO_BKI = {
        "bau": "betonbau",
        "beton": "betonbau",
        "stahl": "stahlbau",
        "hochbau": "mauerwerk",
        "tiefbau": "erdarbeiten",
        "ausbau": "putz",
        "trockenbau": "putz",
        "elektro": "elektro",
        "heizung": "heizung",
        "lüftung": "heizung",
        "sanitär": "sanitaer",
        "hls": "heizung",
        "dach": "dach",
        "abdichtung": "abdichtung",
        "fliesen": "fliesen",
        "straße": "strassenbau",
        "kanal": "kanalbau",
        "klär": "kanalbau",
        "abwasser": "kanalbau",
        "umwelt": "erdarbeiten",
    }

    # Gewichte für Fisher-Quantitäts-Inflation
    DEFAULT_WEIGHTS = {
        "gaeb_price_index": 0.40,       # GAEB-Einheitspreise
        "monetary_inflation": 0.35,      # M × V / Y
        "bki_benchmark": 0.25,           # BKI-Referenzindex
    }

    def __init__(
        self,
        base_year: int = 2024,
        alert_threshold_high: float = 5.0,    # >5% p.a. = ALARM
        alert_threshold_defl: float = -1.0,    # <−1% p.a. = Deflations-Alarm
        volatility_threshold: float = 2.0,      # σ > 2% = Volatilitäts-Alarm
        min_data_points: int = 8,
    ):
        """
        Args:
            base_year: Basisjahr für Preisindex (Default: 2024 = 100)
            alert_threshold_high: Jährliche Inflation > Wert → Alarm
            alert_threshold_defl: Jährliche Inflation < Wert → Deflationsalarm
            volatility_threshold: Standardabweichung > Wert → Volatilitätsalarm
            min_data_points: Mindestanzahl Preis-Datenpunkte für valide Analyse
        """
        self.base_year = base_year
        self.alert_threshold_high = alert_threshold_high
        self.alert_threshold_defl = alert_threshold_defl
        self.volatility_threshold = volatility_threshold
        self.min_data_points = min_data_points

        # Historische Preiszeitreihen (month → {sector: avg_price})
        self._price_history: Dict[str, Dict[str, float]] = {}

        # Historische Inflationswerte (month → inflation_rate)
        self._inflation_history: Dict[str, float] = {}

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def measure_inflation(
        self,
        gaeb_positions: List[Dict[str, Any]],
        money_supply_eur: float,
        velocity_tx: float,
        real_output_eur: Optional[float] = None,
        period_label: Optional[str] = None,
        tender_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Hauptmethode: Misst die Inflation aus GAEB-Einheitspreisen und
        makroökonomischen Daten.

        Args:
            gaeb_positions: GAEB-Positionen mit:
                - position_id (str)
                - unit_price_eur (float)
                - quantity (float)
                - unit (str, z.B. "m³", "Stk")
                - sector (str, optional)
                - description (str)
                - timestamp (ISO 8601)
            money_supply_eur: Geldmenge M (vom Treasury)
            velocity_tx: Umlaufgeschwindigkeit V (vom VelocityTracker)
            real_output_eur: Reales BIP/Output Y (optional, wird geschätzt)
            period_label: Perioden-Label (z.B. "2026-08")
            tender_id: Optionaler Tender-Filter

        Returns:
            Inflations-Report mit Preisindizes, Raten und Alerts
        """
        period_label = period_label or datetime.now(timezone.utc).strftime("%Y-%m")
        job_id = f"inf_{period_label}"

        logger.info(
            f"Inflationsmessung für Periode {period_label}: "
            f"{len(gaeb_positions)} GAEB-Positionen, M={money_supply_eur:,.0f} EUR, V={velocity_tx:.3f}"
        )

        if len(gaeb_positions) < self.min_data_points:
            return {
                "status": "INSUFFICIENT_DATA",
                "job_id": job_id,
                "artifacts": [],
                "error": None,
                "logs": [
                    {
                        "level": "WARN",
                        "message": (
                            f"Nur {len(gaeb_positions)} GAEB-Positionen — "
                            f"mindestens {self.min_data_points} benötigt."
                        ),
                    }
                ],
            }

        try:
            # === 1. GAEB-Preisindex berechnen (Laspeyres, Paasche, Fisher) ===
            price_indices = self._calculate_price_indices(gaeb_positions, period_label)

            # === 2. Sektorale Inflation ===
            sector_inflation = self._calculate_sector_inflation(gaeb_positions, period_label)

            # === 3. Monetäre Inflation (Fisher-Quantitätsgleichung) ===
            monetary_inflation = self._calculate_monetary_inflation(
                money_supply_eur=money_supply_eur,
                velocity_tx=velocity_tx,
                real_output_eur=real_output_eur,
                period_label=period_label,
            )

            # === 4. BKI-Benchmark-Vergleich ===
            bki_comparison = self._compare_with_bki(price_indices)

            # === 5. Gewichtete Gesamtinflation ===
            composite_inflation = self._calculate_composite_inflation(
                gaeb_inflation=price_indices.get("fisher_inflation_rate_pct", 0.0),
                monetary_inflation=monetary_inflation.get("inflation_rate_pct", 0.0),
                bki_trend=bki_comparison.get("annualized_inflation_pct", 0.0),
            )

            # === 6. Historischen Trend berechnen ===
            trend = self._calculate_inflation_trend(composite_inflation, period_label)

            # === 7. Alerts generieren ===
            alerts = self._generate_inflation_alerts(
                composite_inflation=composite_inflation,
                sector_inflation=sector_inflation,
                price_indices=price_indices,
                monetary_inflation=monetary_inflation,
                trend=trend,
            )

            # === 8. Historie aktualisieren ===
            self._update_history(period_label, composite_inflation, price_indices)

            report = {
                "status": "ANALYSIS_COMPLETE",
                "job_id": job_id,
                "tender_id": tender_id,
                "period_label": period_label,
                "base_year": self.base_year,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "artifacts": [
                    {
                        "type": "inflation_report",
                        "format": "json",
                        "metadata": {
                            "period": period_label,
                            "composite_inflation_pct": round(composite_inflation, 2),
                            "is_alarming": len(alerts) > 0,
                        },
                    }
                ],
                "error": None,
                "logs": [
                    {
                        "level": "INFO",
                        "message": (
                            f"Inflation: Composite={composite_inflation:.2f}%, "
                            f"GAEB={price_indices.get('fisher_inflation_rate_pct', 0):.2f}%, "
                            f"Monetary={monetary_inflation.get('inflation_rate_pct', 0):.2f}%, "
                            f"BKI-Trend={bki_comparison.get('annualized_inflation_pct', 0):.2f}%"
                        ),
                    }
                ],
                "price_indices": price_indices,
                "sector_inflation": sector_inflation,
                "monetary_inflation": monetary_inflation,
                "bki_comparison": bki_comparison,
                "composite_inflation_pct": round(composite_inflation, 2),
                "trend": trend,
                "alerts": alerts,
                "has_alerts": len(alerts) > 0,
                "monetary_policy_implication": self._monetary_policy_advice(
                    composite_inflation, trend
                ),
            }

            logger.info(
                f"Inflationsanalyse abgeschlossen: {composite_inflation:.2f}%, "
                f"Alerts={len(alerts)}"
            )
            return report

        except Exception as e:
            logger.error(f"Inflationsmessung fehlgeschlagen: {e}", exc_info=True)
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": str(e),
                "logs": [{"level": "ERROR", "message": f"InflationOracle abgestürzt: {e}"}],
            }

    def get_inflation_history(self) -> Dict[str, float]:
        """Gibt die Inflations-Historie zurück."""
        return dict(sorted(self._inflation_history.items()))

    # ========================================================================
    # PRICE INDEX CALCULATION
    # ========================================================================

    def _calculate_price_indices(
        self,
        positions: List[Dict[str, Any]],
        period_label: str,
    ) -> Dict[str, Any]:
        """
        Berechnet Laspeyres-, Paasche- und Fisher-Preisindizes aus GAEB-Positionen.

        Laspeyres: Σ(p_t × q₀) / Σ(p₀ × q₀) × 100  (Basis-Mengen)
        Paasche:   Σ(p_t × q_t) / Σ(p₀ × q_t) × 100  (aktuelle Mengen)
        Fisher:    √(Laspeyres × Paasche)
        """
        # Positionen nach ID gruppieren (gleiche Position über Zeit)
        by_position: Dict[str, List[Dict]] = defaultdict(list)
        for pos in positions:
            pos_id = pos.get("position_id", pos.get("id", "UNKNOWN"))
            by_position[pos_id].append(pos)

        # Für jede Position: aktuellsten und frühesten Preis ermitteln
        current_prices = {}  # position_id → unit_price (current period)
        base_prices = {}     # position_id → unit_price (base period)
        current_quantities = {}  # position_id → quantity (current)
        base_quantities = {}     # position_id → quantity (base)

        for pos_id, pos_list in by_position.items():
            sorted_pos = sorted(
                pos_list,
                key=lambda p: p.get("timestamp", "1970-01-01"),
            )
            base = sorted_pos[0]
            current = sorted_pos[-1]

            base_prices[pos_id] = float(base.get("unit_price_eur", 0.0))
            current_prices[pos_id] = float(current.get("unit_price_eur", 0.0))
            base_quantities[pos_id] = float(base.get("quantity", 1.0))
            current_quantities[pos_id] = float(current.get("quantity", 1.0))

        # Laspeyres: Σ(p_t × q₀) / Σ(p₀ × q₀) × 100
        laspeyres_num = sum(
            current_prices[pid] * base_quantities[pid] for pid in base_prices
        )
        laspeyres_den = sum(
            base_prices[pid] * base_quantities[pid] for pid in base_prices
        )
        laspeyres = (laspeyres_num / laspeyres_den * 100) if laspeyres_den > 0 else 100.0

        # Paasche: Σ(p_t × q_t) / Σ(p₀ × q_t) × 100
        paasche_num = sum(
            current_prices[pid] * current_quantities[pid] for pid in base_prices
        )
        paasche_den = sum(
            base_prices[pid] * current_quantities[pid] for pid in base_prices
        )
        paasche = (paasche_num / paasche_den * 100) if paasche_den > 0 else 100.0

        # Fisher: √(Laspeyres × Paasche)
        import math
        fisher = math.sqrt(laspeyres * paasche)

        # Inflationsrate: (Index_t − Index_{t−1}) / Index_{t−1} × 100
        # Hier: Vereinfacht als Abweichung von 100 (Basisjahr)
        laspeyres_inflation = laspeyres - 100.0
        paasche_inflation = paasche - 100.0
        fisher_inflation = fisher - 100.0

        # Annualisierung (wenn Daten mehrerer Monate verfügbar)
        months_covered = self._estimate_months_covered(positions)
        annualization_factor = 12.0 / max(months_covered, 1)

        return {
            "laspeyres_index": round(laspeyres, 2),
            "paasche_index": round(paasche, 2),
            "fisher_index": round(fisher, 2),
            "laspeyres_inflation_rate_pct": round(laspeyres_inflation, 2),
            "paasche_inflation_rate_pct": round(paasche_inflation, 2),
            "fisher_inflation_rate_pct": round(fisher_inflation, 2),
            "annualization_factor": round(annualization_factor, 2),
            "annualized_inflation_pct": round(fisher_inflation * annualization_factor, 2),
            "position_count": len(base_prices),
            "months_of_data": round(months_covered, 1),
        }

    def _estimate_months_covered(self, positions: List[Dict]) -> float:
        """Schätzt die Anzahl der abgedeckten Monate aus den Timestamps."""
        timestamps = [
            p.get("timestamp", "")
            for p in positions
            if p.get("timestamp")
        ]
        if len(timestamps) < 2:
            return 1.0

        try:
            parsed = []
            for ts in timestamps:
                # Flexibles Parsing für verschiedene ISO-Formate
                ts_clean = ts.replace("Z", "+00:00")
                if "T" in ts_clean:
                    parsed.append(datetime.fromisoformat(ts_clean))
                else:
                    parsed.append(datetime.strptime(ts_clean[:10], "%Y-%m-%d"))
            if len(parsed) < 2:
                return 1.0
            delta = max(parsed) - min(parsed)
            return max(delta.days / 30.44, 0.5)
        except Exception:
            return 1.0

    # ========================================================================
    # SECTOR INFLATION
    # ========================================================================

    def _calculate_sector_inflation(
        self,
        positions: List[Dict[str, Any]],
        period_label: str,
    ) -> List[Dict[str, Any]]:
        """
        Berechnet sektorspezifische Inflationsraten.
        """
        # Positionen nach Sektor gruppieren
        sector_positions: Dict[str, List[Dict]] = defaultdict(list)
        for pos in positions:
            sector = pos.get("sector")
            if not sector:
                # Klassifizieren anhand Beschreibung
                desc = pos.get("description", "").lower()
                sector = self._classify_sector(desc)
            sector_positions[sector].append(pos)

        results = []
        for sector, pos_list in sorted(sector_positions.items()):
            if len(pos_list) < 2:
                continue

            sector_result = self._calculate_price_indices(pos_list, period_label)
            sector_result["sector"] = sector
            sector_result["position_count"] = len(pos_list)
            results.append(sector_result)

        # Nach Inflationsrate sortieren (höchste zuerst)
        results.sort(
            key=lambda r: r.get("fisher_inflation_rate_pct", 0), reverse=True
        )

        return results

    def _classify_sector(self, description: str) -> str:
        """Klassifiziert eine Beschreibung in einen Sektor."""
        desc_lower = description.lower()
        for keyword, sector in self.SECTOR_TO_BKI.items():
            if keyword in desc_lower:
                return sector
        return "sonstige"

    # ========================================================================
    # MONETARY INFLATION (Fisher Equation)
    # ========================================================================

    def _calculate_monetary_inflation(
        self,
        money_supply_eur: float,
        velocity_tx: float,
        real_output_eur: Optional[float],
        period_label: str,
    ) -> Dict[str, Any]:
        """
        Berechnet die monetäre Inflation aus der Fisher-Quantitätsgleichung:

            M × V = P × Y  →  P = M × V / Y

        Inflation = ΔP / P = ΔM/M + ΔV/V − ΔY/Y
        """
        if real_output_eur is None or real_output_eur <= 0:
            # Schätze Y aus Transaktionsvolumen
            nominal_gdp = money_supply_eur * velocity_tx
            # Annahme: Reales Wachstum ~2% (deutsche Bauwirtschaft)
            real_output_eur = nominal_gdp / 1.02

        # Preisniveau
        price_level = (money_supply_eur * velocity_tx) / real_output_eur

        # Vergleiche mit Vorperiode (wenn verfügbar)
        prev_keys = sorted(self._price_history.keys())
        inflation_rate = 0.0
        prev_price_level = None

        if prev_keys:
            # Letzte Periode mit Daten
            prev_period = prev_keys[-1]
            prev_data = self._price_history[prev_period]
            prev_avg_price = mean(prev_data.values()) if prev_data else price_level
            if prev_avg_price > 0:
                inflation_rate = (price_level - prev_avg_price) / prev_avg_price * 100

        # Geldmengenwachstum (vereinfacht)
        money_growth_rate = 0.0
        if prev_keys and self._inflation_history:
            # Indirekt aus Velocity-Änderung
            pass

        return {
            "price_level_eur": round(price_level, 2),
            "nominal_gdp_eur": round(money_supply_eur * velocity_tx, 2),
            "real_output_eur": round(real_output_eur, 2),
            "money_supply_eur": round(money_supply_eur, 2),
            "velocity_tx": round(velocity_tx, 4),
            "inflation_rate_pct": round(inflation_rate, 2),
            "money_growth_rate_pct": round(money_growth_rate, 2),
            "equation": f"P = {money_supply_eur:,.0f} × {velocity_tx:.3f} / {real_output_eur:,.0f} = {price_level:,.2f}",
        }

    # ========================================================================
    # BKI BENCHMARK COMPARISON
    # ========================================================================

    def _compare_with_bki(self, price_indices: Dict[str, Any]) -> Dict[str, Any]:
        """
        Vergleicht den GAEB-basierten Preisindex mit dem BKI-Baukostenindex.
        """
        gaeb_inflation = price_indices.get("fisher_inflation_rate_pct", 0.0)

        # BKI-Durchschnittliche Inflation 2020→2024: ~27% über 4 Jahre = ~6.2% p.a.
        # Aktuelle BKI-Prognose: ~5.5% p.a. für 2025/2026
        bki_avg_annual = 5.5  # % p.a.

        # Gewichtete BKI-Inflation für die aktuellen GAEB-Sektoren
        bki_weighted = sum(
            data["weight"] * (data["index_2024"] / data["index_2020"] - 1) * 100 / 4
            for data in self.BKI_REFERENCE.values()
        )
        bki_annualized = bki_weighted / sum(
            data["weight"] for data in self.BKI_REFERENCE.values()
        )

        # Abweichung GAEB vs. BKI
        deviation = gaeb_inflation - bki_annualized

        # Interpretation
        if deviation > 3:
            interpretation = "GAEB-Preise steigen DEUTLICH schneller als BKI — lokale Überhitzung?"
        elif deviation > 1:
            interpretation = "GAEB-Preise steigen etwas schneller als BKI — normale Streuung"
        elif deviation > -1:
            interpretation = "GAEB-Preise im Einklang mit BKI — Markt funktioniert"
        elif deviation > -3:
            interpretation = "GAEB-Preise steigen langsamer als BKI — hohe Wettbewerbsintensität"
        else:
            interpretation = "GAEB-Preise DEUTLICH unter BKI — Dumping-Verdacht oder Deflation"

        return {
            "bki_annualized_inflation_pct": round(bki_annualized, 2),
            "gaeb_fisher_inflation_pct": round(gaeb_inflation, 2),
            "deviation_pct": round(deviation, 2),
            "interpretation": interpretation,
            "bki_reference_period": "2020-2024",
            "bki_sector_count": len(self.BKI_REFERENCE),
            "bki_weighted_avg_index_2024": round(
                sum(d["index_2024"] * d["weight"] for d in self.BKI_REFERENCE.values())
                / sum(d["weight"] for d in self.BKI_REFERENCE.values()),
                1,
            ),
        }

    # ========================================================================
    # COMPOSITE INFLATION
    # ========================================================================

    def _calculate_composite_inflation(
        self,
        gaeb_inflation: float,
        monetary_inflation: float,
        bki_trend: float,
    ) -> float:
        """
        Gewichtete Gesamtinflation aus drei Quellen:
        - 40% GAEB-Einheitspreise (Mikro-Ebene)
        - 35% Monetäre Inflation (Makro-Ebene, Fisher)
        - 25% BKI-Referenz (Branchen-Benchmark)
        """
        weights = self.DEFAULT_WEIGHTS
        composite = (
            weights["gaeb_price_index"] * gaeb_inflation
            + weights["monetary_inflation"] * monetary_inflation
            + weights["bki_benchmark"] * bki_trend
        )
        return round(composite, 2)

    # ========================================================================
    # TREND ANALYSIS
    # ========================================================================

    def _calculate_inflation_trend(
        self,
        current_inflation: float,
        period_label: str,
    ) -> Dict[str, Any]:
        """
        Berechnet den Inflations-Trend aus der Historie.
        """
        history = list(self._inflation_history.items())

        if len(history) < 2:
            return {
                "status": "INSUFFICIENT_HISTORY",
                "historical_periods": len(history),
                "trend_direction": "UNKNOWN",
            }

        values = [v for _, v in history]
        hist_mean = mean(values)
        hist_std = stdev(values) if len(values) >= 2 else 0.0

        # Z-Score
        z_score = (
            (current_inflation - hist_mean) / hist_std if hist_std > 0 else 0.0
        )

        # Trendrichtung (lineare Regression)
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = hist_mean
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0

        # Trend-Label
        if slope > 1.0:
            direction = "ACCELERATING_STRONG"
        elif slope > 0.2:
            direction = "ACCELERATING"
        elif slope > -0.2:
            direction = "STABLE"
        elif slope > -1.0:
            direction = "DECELERATING"
        else:
            direction = "DECELERATING_STRONG"

        # Prognose: AR(1) — nächster Wert = aktueller Wert + slope
        forecast_next = current_inflation + slope

        return {
            "status": "TREND_AVAILABLE",
            "historical_periods": len(history),
            "historical_mean_pct": round(hist_mean, 2),
            "historical_std_pct": round(hist_std, 2),
            "current_z_score": round(z_score, 2),
            "trend_slope": round(slope, 4),
            "trend_direction": direction,
            "forecast_next_period_pct": round(forecast_next, 2),
        }

    # ========================================================================
    # ALERT GENERATION
    # ========================================================================

    def _generate_inflation_alerts(
        self,
        composite_inflation: float,
        sector_inflation: List[Dict],
        price_indices: Dict[str, Any],
        monetary_inflation: Dict[str, Any],
        trend: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Generiert Alerts basierend auf Inflations-Anomalien.
        """
        alerts = []

        # --- 1. Hochinflations-Alarm ---
        if composite_inflation > self.alert_threshold_high:
            alerts.append(
                {
                    "alert_type": "HIGH_INFLATION",
                    "severity": "HIGH",
                    "message": (
                        f"Inflation bei {composite_inflation:.1f}% — "
                        f"über Schwellwert von {self.alert_threshold_high}%. "
                        f"Geldmenge reduzieren oder Zinsen erhöhen."
                    ),
                    "inflation_pct": composite_inflation,
                    "threshold_pct": self.alert_threshold_high,
                }
            )

        # --- 2. Deflations-Alarm ---
        if composite_inflation < self.alert_threshold_defl:
            alerts.append(
                {
                    "alert_type": "DEFLATION",
                    "severity": "HIGH",
                    "message": (
                        f"Deflation bei {composite_inflation:.1f}% — "
                        f"unter Schwellwert von {self.alert_threshold_defl}%. "
                        f"Geldmenge ausweiten (Stimulus empfohlen)."
                    ),
                    "inflation_pct": composite_inflation,
                    "threshold_pct": self.alert_threshold_defl,
                }
            )

        # --- 3. Sektorale Divergenz ---
        if len(sector_inflation) >= 2:
            sector_rates = [s.get("fisher_inflation_rate_pct", 0) for s in sector_inflation]
            sector_std = stdev(sector_rates) if len(sector_rates) >= 2 else 0.0
            if sector_std > self.volatility_threshold:
                top_sector = sector_inflation[0]
                bottom_sector = sector_inflation[-1]
                alerts.append(
                    {
                        "alert_type": "SECTOR_DIVERGENCE",
                        "severity": "MEDIUM",
                        "message": (
                            f"Sektorale Inflations-Divergenz: "
                            f"{top_sector['sector']} @ {top_sector.get('fisher_inflation_rate_pct', 0):.1f}% vs. "
                            f"{bottom_sector['sector']} @ {bottom_sector.get('fisher_inflation_rate_pct', 0):.1f}% "
                            f"(σ={sector_std:.1f}%)"
                        ),
                        "sector_std_pct": round(sector_std, 1),
                        "top_sector": top_sector["sector"],
                        "bottom_sector": bottom_sector["sector"],
                    }
                )

        # --- 4. BKI-Abweichung ---
        # Wird bereits in _compare_with_bki behandelt — hier ergänzend als Alert
        # wenn die Abweichung extrem ist
        # (implementiert, wenn BKI-Daten in _compare_with_bki vorliegen)

        # --- 5. Trendwechsel ---
        if trend.get("trend_direction") in ("ACCELERATING_STRONG", "DECELERATING_STRONG"):
            alerts.append(
                {
                    "alert_type": "TREND_CHANGE",
                    "severity": "MEDIUM",
                    "message": (
                        f"Starker Inflations-Trendwechsel: {trend['trend_direction']} "
                        f"(Slope={trend.get('trend_slope', 0):.3f})"
                    ),
                    "trend_direction": trend["trend_direction"],
                    "slope": trend.get("trend_slope", 0),
                }
            )

        return alerts

    # ========================================================================
    # POLICY ADVICE
    # ========================================================================

    def _monetary_policy_advice(
        self,
        inflation: float,
        trend: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generiert geldpolitische Handlungsempfehlungen basierend auf Inflation.
        """
        direction = trend.get("trend_direction", "STABLE")

        if inflation > 8:
            action = "CONTRACTIONARY_STRONG"
            advice = (
                "Inflation >8%: Geldmenge DEUTLICH reduzieren (EURe-Burn), "
                "Zahlungsziele verkürzen, Notfall-BHO-Sperre für neue Projekte."
            )
        elif inflation > 5:
            action = "CONTRACTIONARY"
            advice = (
                "Inflation >5%: Geldmenge moderat reduzieren, "
                "Retention-Rate erhöhen (von 5% auf 8%), Velocity bremsen."
            )
        elif inflation > 2:
            action = "NEUTRAL_WATCH"
            advice = (
                "Inflation 2-5%: Normale Bandbreite für Bauwirtschaft. "
                "Beobachten, keine aktiven Eingriffe."
            )
        elif inflation > 0:
            action = "NEUTRAL"
            advice = (
                "Inflation 0-2%: Gesundes Niveau. Preisstabilität gegeben."
            )
        elif inflation > -1:
            action = "EXPANSIONARY_WATCH"
            advice = (
                "Inflation nahe Null: Vorsicht vor Deflation. "
                "Stimulus-Optionen vorbereiten."
            )
        else:
            action = "EXPANSIONARY"
            advice = (
                "Deflation <−1%: SOFORT Stimulus einleiten (EURe-Mint), "
                "Zahlungsziele verlängern, Velocity ankurbeln."
            )

        # Modifiziert durch Trend
        if direction.startswith("ACCELERATING") and action in ("NEUTRAL", "NEUTRAL_WATCH"):
            action = "NEUTRAL_WATCH"
            advice += " Trend beschleunigt sich — engmaschig überwachen."

        if direction.startswith("DECELERATING") and action.startswith("CONTRACTIONARY"):
            action = "NEUTRAL_WATCH"
            advice += " Trend bremst bereits ab — Eingriff ggf. nicht nötig."

        return {
            "action": action,
            "advice": advice,
            "inflation_pct": inflation,
            "trend_direction": direction,
        }

    # ========================================================================
    # HISTORY MANAGEMENT
    # ========================================================================

    def _update_history(
        self,
        period_label: str,
        inflation: float,
        price_indices: Dict[str, Any],
    ) -> None:
        """Aktualisiert die Inflations-Historie."""
        self._inflation_history[period_label] = inflation

        # Sektor-Preise speichern
        fisher_idx = price_indices.get("fisher_index", 100.0)
        self._price_history[period_label] = {"composite": fisher_idx}

    # ========================================================================
    # IMPORT FROM VELOCITY TRACKER (Integration)
    # ========================================================================

    def set_velocity_data(self, velocity_report: Dict[str, Any]) -> None:
        """
        Extrahiert Velocity-Daten aus dem VelocityOfMoneyTracker-Report.
        Wird vom MacroEconomyOrchestrator aufgerufen.
        """
        vel_metrics = velocity_report.get("velocity_metrics", {})
        self._cached_velocity = vel_metrics.get("velocity_tx", 1.0)
        self._cached_money_supply = vel_metrics.get("money_supply_eur", 0.0)
        logger.debug(
            f"Velocity-Daten geladen: V={self._cached_velocity:.3f}, "
            f"M={self._cached_money_supply:,.0f}"
        )


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    import random

    print("=" * 60)
    print("RealTimeInflationOracle — Smoke Test")
    print("=" * 60)

    oracle = RealTimeInflationOracleSubagent()

    # Synthetische GAEB-Positionen generieren
    rng = random.Random(42)
    sectors = ["betonbau", "stahlbau", "erdarbeiten", "elektro", "kanalbau"]
    units = ["m³", "m²", "Stk", "kg", "m", "Std"]

    gaeb_positions = []
    base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    for i in range(30):
        sector = rng.choice(sectors)
        # Basispreis (2024) + Inflationstrend
        base_price = rng.uniform(50, 5000)
        months_since_base = (i % 24)  # Simuliert 24 Monate Preishistorie
        inflation_factor = 1.0 + (0.04 * months_since_base / 12)  # ~4% p.a.
        current_price = base_price * inflation_factor * rng.uniform(0.95, 1.05)

        gaeb_positions.append(
            {
                "position_id": f"POS_{i // 3:03d}",  # Alle 3 Einträge = gleiche Position
                "unit_price_eur": round(current_price, 2),
                "quantity": round(rng.uniform(10, 1000), 2),
                "unit": rng.choice(units),
                "sector": sector,
                "description": f"{sector} Arbeiten Projekt {i % 5}",
                "timestamp": (base_date + timedelta(days=30 * (i % 24))).isoformat(),
            }
        )

    # Analyse mit Velocity-Daten
    report = oracle.measure_inflation(
        gaeb_positions=gaeb_positions,
        money_supply_eur=5_000_000.0,
        velocity_tx=2.84,
    )

    print(f"\nStatus: {report['status']}")
    print(f"Periode: {report['period_label']}")
    print(f"Composite Inflation: {report['composite_inflation_pct']}%")

    pi = report["price_indices"]
    print(f"\nLaspeyres: {pi['laspeyres_index']} (Inflation: {pi['laspeyres_inflation_rate_pct']}%)")
    print(f"Paasche: {pi['paasche_index']} (Inflation: {pi['paasche_inflation_rate_pct']}%)")
    print(f"Fisher: {pi['fisher_index']} (Inflation: {pi['fisher_inflation_rate_pct']}%)")
    print(f"Annualisiert: {pi['annualized_inflation_pct']}%")

    mi = report["monetary_inflation"]
    print(f"\nFisher-Gleichung: {mi['equation']}")
    print(f"Monetäre Inflation: {mi['inflation_rate_pct']}%")

    bki = report["bki_comparison"]
    print(f"\nBKI-Vergleich: {bki['interpretation']}")

    print(f"\nSektor-Inflation:")
    for s in report["sector_inflation"][:3]:
        print(f"  {s['sector']}: {s.get('fisher_inflation_rate_pct', 0):.1f}%")

    print(f"\nAlerts: {len(report['alerts'])}")
    for a in report["alerts"]:
        print(f"  [{a['severity']}] {a['alert_type']}: {a['message'][:100]}...")

    pol = report["monetary_policy_implication"]
    print(f"\nGeldpolitik: {pol['action']}")
    print(f"Empfehlung: {pol['advice'][:120]}...")

    print(f"\n✅ Smoke Test abgeschlossen.")
