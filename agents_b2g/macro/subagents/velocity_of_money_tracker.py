# agents_b2g/macro/subagents/velocity_of_money_tracker.py
"""
Agent 17.2 — VelocityOfMoneyTracker

Misst die Umlaufgeschwindigkeit des Geldes (Velocity of Money) im
Agent-X-Ökosystem. Fundamentale makroökonomische Metrik, die als Input
für InflationOracle, StimulusEngine und CapitalEfficiencyAnalyzer dient.

Theoretische Grundlage: Quantitätsgleichung MV = PY (Fisher)
  V = (P × Y) / M  →  V = Transaktionsvolumen / Geldmenge

Kennzahlen:
  - V_TX: Transaktions-Velocity (alle Zahlungen / durchschnittliche Geldmenge)
  - V_Income: Einkommens-Velocity (nur empfangene Zahlungen / Geldmenge)
  - V_Sector[n]: Sektor-spezifische Velocity
  - V_Regional[m]: Regional-spezifische Velocity
  - Dispersion: Standardabweichung der Sektor-Velocities (Frühwarnindikator)
  - Acceleration: dV/dt — Änderungsrate der Velocity (Konjunkturindikator)

Alarmierung bei:
  - Velocity < Historischer Mittelwert − 2σ (Liquiditätsstau / Deflationsdruck)
  - Velocity > Historischer Mittelwert + 2σ (Überhitzung / Inflationsdruck)
  - Sector-Dispersion > Schwellwert (sektorale Verwerfungen)
  - Acceleration > Schwellwert (abrupter Regime-Wechsel)
"""

import json
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Tuple, Optional
from decimal import Decimal, getcontext
from collections import defaultdict
from statistics import mean, stdev, median

# Set high precision for Decimal arithmetic
getcontext().prec = 30

logger = logging.getLogger("VelocityOfMoneyTracker")


class VelocityOfMoneyTrackerSubagent:
    """
    Subagent 17.2: Berechnet die Umlaufgeschwindigkeit des Geldes
    auf Transaktions-, Sektor- und Regionalebene.

    Formel: V = (Summe aller Transaktionen in Periode) / (Durchschnittliche Geldmenge in Periode)
    """

    # Sektor-Klassifikation (basierend auf GAEB-Gewerken / CPV-Codes)
    SECTOR_MAP = {
        "bau": ["bau", "beton", "stahl", "hochbau", "tiefbau", "bauwerk", "rohbau"],
        "ausbau": ["ausbau", "trockenbau", "putz", "maler", "fliesen", "boden"],
        "technik": ["elektro", "heizung", "lüftung", "sanitär", "hls", "elT", "msr"],
        "verkehr": ["straße", "brücke", "tunnel", "bahn", "verkehr", "asphalt"],
        "umwelt": ["kanal", "klär", "abwasser", "deponie", "umwelt", "wasser"],
        "planung": ["planung", "architekt", "ingenieur", "statik", "gutachten"],
        "sonstige": [],  # Fallback
    }

    # Regionale Klassifikation (basierend auf PLZ / Bundesland)
    REGION_MAP = {
        "nord": ["HB", "HH", "SH", "NI", "MV"],
        "ost": ["BE", "BB", "ST", "SN", "TH"],
        "sued": ["BW", "BY"],
        "west": ["NW", "RP", "SL", "HE"],
    }

    def __init__(
        self,
        period_days: int = 30,
        min_transactions_for_analysis: int = 10,
        velocity_spike_threshold: float = 2.0,  # σ-Multiplikator für Spike-Erkennung
        dispersion_alert_threshold: float = 0.5,  # CV > 0.5 => Sektor-Dispersion-Alert
        acceleration_alert_threshold: float = 0.3,  # 30% Änderung pro Periode
        history_window_periods: int = 12,  # 12 Perioden für historischen Vergleich
    ):
        """
        Args:
            period_days: Länge einer Analyse-Periode in Tagen (Default: 30)
            min_transactions_for_analysis: Mindestanzahl Transaktionen für valide Analyse
            velocity_spike_threshold: σ-Multiplikator für Spike-Erkennung
            dispersion_alert_threshold: Variationskoeffizient-Schwellwert für Sektor-Dispersion
            acceleration_alert_threshold: Prozentuale Änderung der Velocity für Beschleunigungs-Alert
            history_window_periods: Anzahl Perioden für historischen Mittelwert/StdDev
        """
        self.period_days = period_days
        self.min_transactions = min_transactions_for_analysis
        self.velocity_spike_threshold = velocity_spike_threshold
        self.dispersion_alert_threshold = dispersion_alert_threshold
        self.acceleration_alert_threshold = acceleration_alert_threshold
        self.history_window = history_window_periods

        # Cache für historische Velocity-Werte (period_index -> velocity)
        self._velocity_history: List[Dict[str, Any]] = []

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def analyze(
        self,
        transactions: List[Dict[str, Any]],
        money_supply_eur: float,
        tender_id: Optional[str] = None,
        period_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Hauptmethode: Berechnet die Umlaufgeschwindigkeit für die aktuelle Periode.

        Args:
            transactions: Liste von Transaktionen mit:
                - sender / receiver (oder from / to)
                - amount_eur (float)
                - timestamp (ISO 8601)
                - sector (optional)
                - region_code (optional, z.B. "NI" für Niedersachsen)
                - category (optional: "payment", "deposit", "retention", "refund")
            money_supply_eur: Durchschnittliche Geldmenge im System (EUR)
            tender_id: Optionaler Tender-Filter
            period_label: Label der aktuellen Periode (z.B. "2026-08")

        Returns:
            Standardisierter Velocity-Report mit:
            - status, job_id, artifacts, error, logs
            - velocity_metrics: V_TX, V_Income, sector_breakdown, regional_breakdown
            - alerts: Liste von Warnungen
            - trend: Historischer Vergleich
        """
        if period_label is None:
            period_label = datetime.now(timezone.utc).strftime("%Y-%m")

        logger.info(
            f"Velocity-Analyse für Periode {period_label}: "
            f"{len(transactions)} TX, Geldmenge={money_supply_eur:,.2f} EUR"
        )

        if len(transactions) < self.min_transactions:
            return {
                "status": "INSUFFICIENT_DATA",
                "job_id": f"vel_{period_label}",
                "artifacts": [],
                "error": None,
                "logs": [
                    {
                        "level": "WARN",
                        "message": (
                            f"Nur {len(transactions)} Transaktionen — "
                            f"mindestens {self.min_transactions} benötigt."
                        ),
                    }
                ],
            }

        if money_supply_eur <= 0:
            return {
                "status": "INVALID_INPUT",
                "job_id": f"vel_{period_label}",
                "artifacts": [],
                "error": "Geldmenge muss > 0 sein.",
                "logs": [],
            }

        try:
            # === 1. Gesamt-Velocity berechnen ===
            total_volume = sum(
                float(tx.get("amount_eur", 0.0)) for tx in transactions
            )
            velocity_tx = total_volume / money_supply_eur

            # Income-Velocity: Nur eingehende Zahlungen (empfangene Seite)
            income_volume = sum(
                float(tx.get("amount_eur", 0.0))
                for tx in transactions
                if tx.get("category", "payment") in ("payment", "deposit")
            )
            velocity_income = income_volume / money_supply_eur

            # === 2. Sektor-Velocity berechnen ===
            sector_breakdown = self._calculate_sector_velocity(
                transactions, money_supply_eur
            )

            # === 3. Regionale Velocity berechnen ===
            regional_breakdown = self._calculate_regional_velocity(
                transactions, money_supply_eur
            )

            # === 4. Velocity nach Transaktionstyp ===
            type_breakdown = self._calculate_type_velocity(
                transactions, money_supply_eur
            )

            # === 5. Velocity-Dispersion (Sektor) ===
            sector_velocities = [
                s["velocity"] for s in sector_breakdown if s["transaction_count"] > 0
            ]
            dispersion = stdev(sector_velocities) / mean(sector_velocities) if len(sector_velocities) >= 2 else 0.0

            # === 6. Historischen Trend berechnen ===
            trend = self._calculate_trend(velocity_tx, period_label)

            # === 7. Alerts generieren ===
            alerts = self._generate_alerts(
                velocity_tx=velocity_tx,
                velocity_income=velocity_income,
                sector_breakdown=sector_breakdown,
                dispersion=dispersion,
                total_volume=total_volume,
                money_supply_eur=money_supply_eur,
                transaction_count=len(transactions),
                trend=trend,
            )

            # === 8. Velocity-Historie aktualisieren ===
            self._update_history(
                {
                    "period": period_label,
                    "velocity_tx": velocity_tx,
                    "velocity_income": velocity_income,
                    "total_volume": total_volume,
                    "money_supply_eur": money_supply_eur,
                    "transaction_count": len(transactions),
                    "dispersion": dispersion,
                    "alerts_count": len(alerts),
                }
            )

            report = {
                "status": "ANALYSIS_COMPLETE",
                "job_id": f"vel_{period_label}",
                "tender_id": tender_id,
                "period_label": period_label,
                "period_days": self.period_days,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "artifacts": [
                    {
                        "type": "velocity_report",
                        "format": "json",
                        "metadata": {
                            "period": period_label,
                            "velocity_tx": round(velocity_tx, 4),
                            "is_anomaly": len(alerts) > 0,
                        },
                    }
                ],
                "error": None,
                "logs": [
                    {
                        "level": "INFO",
                        "message": (
                            f"Velocity TX={velocity_tx:.4f}, "
                            f"Income={velocity_income:.4f}, "
                            f"Volumen={total_volume:,.2f} EUR, "
                            f"TX-Count={len(transactions)}"
                        ),
                    }
                ],
                "velocity_metrics": {
                    "velocity_tx": round(velocity_tx, 6),
                    "velocity_income": round(velocity_income, 6),
                    "total_transaction_volume_eur": round(total_volume, 2),
                    "money_supply_eur": round(money_supply_eur, 2),
                    "transaction_count": len(transactions),
                    "sector_breakdown": sector_breakdown,
                    "regional_breakdown": regional_breakdown,
                    "type_breakdown": type_breakdown,
                    "sector_dispersion_cv": round(dispersion, 4),
                },
                "trend": trend,
                "alerts": alerts,
                "has_alerts": len(alerts) > 0,
            }

            logger.info(
                f"Velocity-Analyse abgeschlossen: V_TX={velocity_tx:.4f}, "
                f"Alerts={len(alerts)}"
            )
            return report

        except Exception as e:
            logger.error(f"Velocity-Analyse fehlgeschlagen: {e}", exc_info=True)
            return {
                "status": "failed",
                "job_id": f"vel_{period_label}",
                "artifacts": [],
                "error": str(e),
                "logs": [
                    {
                        "level": "ERROR",
                        "message": f"VelocityAnalyse abgestürzt: {e}",
                    }
                ],
            }

    def get_velocity_history(self) -> List[Dict[str, Any]]:
        """Gibt die Velocity-Historie zurück (für Dashboards & Trend-Analysen)."""
        return self._velocity_history

    def forecast_velocity(
        self, periods_ahead: int = 3
    ) -> Dict[str, Any]:
        """
        Einfache Velocity-Prognose basierend auf linearem Trend der Historie.

        Args:
            periods_ahead: Anzahl Perioden für Prognose

        Returns:
            Prognose mit Konfidenzintervall
        """
        if len(self._velocity_history) < 3:
            return {
                "status": "INSUFFICIENT_HISTORY",
                "message": f"Mindestens 3 historische Perioden benötigt, habe {len(self._velocity_history)}.",
            }

        velocities = [h["velocity_tx"] for h in self._velocity_history]
        n = len(velocities)

        # Einfache lineare Regression: velocity ~ period_index
        x_mean = (n - 1) / 2
        y_mean = mean(velocities)

        numerator = sum(
            (i - x_mean) * (v - y_mean) for i, v in enumerate(velocities)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        intercept = y_mean - slope * x_mean

        # Prognose
        forecast_values = []
        for i in range(1, periods_ahead + 1):
            forecast_idx = n + i - 1
            forecast_val = intercept + slope * forecast_idx
            forecast_values.append(
                {
                    "periods_ahead": i,
                    "forecast_velocity": round(forecast_val, 6),
                    "forecast_idx": forecast_idx,
                }
            )

        # Konfidenz: Standardfehler der Regression
        residuals = [
            v - (intercept + slope * i) for i, v in enumerate(velocities)
        ]
        std_error = (
            (sum(r**2 for r in residuals) / (n - 2)) ** 0.5
            if n > 2
            else 0.0
        )

        return {
            "status": "FORECAST_COMPLETE",
            "model": "linear_regression",
            "slope": round(slope, 6),
            "intercept": round(intercept, 6),
            "std_error": round(std_error, 6),
            "r_squared": round(
                1 - sum(r**2 for r in residuals) / sum((v - y_mean) ** 2 for v in velocities), 4
            ) if len(set(velocities)) > 1 else 1.0,
            "forecast": forecast_values,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    def _classify_sector(self, description: str) -> str:
        """Klassifiziert einen Transaktionsbeschreibungstext in einen Sektor."""
        desc_lower = description.lower() if description else ""
        for sector, keywords in self.SECTOR_MAP.items():
            if sector == "sonstige":
                continue
            for kw in keywords:
                if kw in desc_lower:
                    return sector
        return "sonstige"

    def _classify_region(self, region_code: str) -> str:
        """Klassifiziert einen Regionalcode (Bundesland-Kürzel) in eine Makro-Region."""
        if not region_code:
            return "unbekannt"
        code_upper = region_code.upper().strip()
        for region, codes in self.REGION_MAP.items():
            if code_upper in codes:
                return region
        return "unbekannt"

    def _calculate_sector_velocity(
        self,
        transactions: List[Dict[str, Any]],
        money_supply_eur: float,
    ) -> List[Dict[str, Any]]:
        """
        Berechnet die Velocity pro Sektor.

        Verwendet sector-Feld oder klassifiziert anhand der Beschreibung.
        """
        sector_volumes: Dict[str, float] = defaultdict(float)
        sector_counts: Dict[str, int] = defaultdict(int)
        sector_money: Dict[str, float] = defaultdict(float)

        for tx in transactions:
            sector = tx.get("sector")
            if not sector:
                sector = self._classify_sector(
                    tx.get("description", tx.get("purpose", ""))
                )

            amount = float(tx.get("amount_eur", 0.0))
            sector_volumes[sector] += amount
            sector_counts[sector] += 1

            # Geldmenge anteilig nach Transaktionsvolumen zuweisen
            # (Vereinfachung: in der Praxis bräuchte man Kontostände pro Sektor)
            sector_money[sector] += amount

        total_sector_volume = sum(sector_volumes.values())
        results = []

        for sector in sorted(sector_volumes.keys()):
            volume = sector_volumes[sector]
            count = sector_counts[sector]
            # Anteilige Geldmenge basierend auf Volumen-Anteil
            sector_share = volume / total_sector_volume if total_sector_volume > 0 else 0.0
            sector_ms = sector_share * money_supply_eur if money_supply_eur > 0 else 0.0
            velocity = volume / sector_ms if sector_ms > 0 else 0.0

            results.append(
                {
                    "sector": sector,
                    "transaction_volume_eur": round(volume, 2),
                    "transaction_count": count,
                    "volume_share_pct": round(sector_share * 100, 2),
                    "estimated_money_supply_eur": round(sector_ms, 2),
                    "velocity": round(velocity, 6),
                }
            )

        return results

    def _calculate_regional_velocity(
        self,
        transactions: List[Dict[str, Any]],
        money_supply_eur: float,
    ) -> List[Dict[str, Any]]:
        """Berechnet die Velocity pro Makro-Region."""
        regional_volumes: Dict[str, float] = defaultdict(float)
        regional_counts: Dict[str, int] = defaultdict(int)

        for tx in transactions:
            region_code = tx.get("region_code", tx.get("bundesland", ""))
            region = self._classify_region(region_code)
            amount = float(tx.get("amount_eur", 0.0))
            regional_volumes[region] += amount
            regional_counts[region] += 1

        total_regional_volume = sum(regional_volumes.values())
        results = []

        for region in sorted(regional_volumes.keys()):
            volume = regional_volumes[region]
            count = regional_counts[region]
            share = volume / total_regional_volume if total_regional_volume > 0 else 0.0
            regional_ms = share * money_supply_eur if money_supply_eur > 0 else 0.0
            velocity = volume / regional_ms if regional_ms > 0 else 0.0

            results.append(
                {
                    "region": region,
                    "transaction_volume_eur": round(volume, 2),
                    "transaction_count": count,
                    "volume_share_pct": round(share * 100, 2),
                    "velocity": round(velocity, 6),
                }
            )

        return results

    def _calculate_type_velocity(
        self,
        transactions: List[Dict[str, Any]],
        money_supply_eur: float,
    ) -> List[Dict[str, Any]]:
        """
        Berechnet Velocity aufgeschlüsselt nach Transaktionstyp:
        payment, deposit, retention, refund, fee
        """
        type_volumes: Dict[str, float] = defaultdict(float)
        type_counts: Dict[str, int] = defaultdict(int)

        for tx in transactions:
            tx_type = tx.get("category", tx.get("type", "payment"))
            amount = float(tx.get("amount_eur", 0.0))
            type_volumes[tx_type] += amount
            type_counts[tx_type] += 1

        total_type_volume = sum(type_volumes.values())
        results = []

        for tx_type in sorted(type_volumes.keys()):
            volume = type_volumes[tx_type]
            count = type_counts[tx_type]
            share = volume / total_type_volume if total_type_volume > 0 else 0.0
            type_ms = share * money_supply_eur if money_supply_eur > 0 else 0.0
            velocity = volume / type_ms if type_ms > 0 else 0.0

            results.append(
                {
                    "type": tx_type,
                    "transaction_volume_eur": round(volume, 2),
                    "transaction_count": count,
                    "volume_share_pct": round(share * 100, 2),
                    "velocity": round(velocity, 6),
                }
            )

        return results

    def _calculate_trend(
        self,
        current_velocity: float,
        period_label: str,
    ) -> Dict[str, Any]:
        """
        Berechnet den Velocity-Trend im Vergleich zur Historie.
        """
        if len(self._velocity_history) < 2:
            return {
                "status": "INSUFFICIENT_HISTORY",
                "historical_periods": len(self._velocity_history),
                "message": "Nicht genug historische Daten für Trendanalyse.",
            }

        historical_velocities = [h["velocity_tx"] for h in self._velocity_history]
        hist_mean = mean(historical_velocities)
        hist_std = stdev(historical_velocities) if len(historical_velocities) >= 2 else 0.0

        # Z-Score der aktuellen Velocity
        z_score = (
            (current_velocity - hist_mean) / hist_std if hist_std > 0 else 0.0
        )

        # Trendrichtung (einfache lineare Regression über Historie)
        n = len(historical_velocities)
        x_mean = (n - 1) / 2
        y_mean = hist_mean
        numerator = sum(
            (i - x_mean) * (v - y_mean)
            for i, v in enumerate(historical_velocities)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0.0

        # Acceleration: Aktuelle Velocity vs. vorherige Periode
        prev_velocity = (
            self._velocity_history[-1]["velocity_tx"]
            if self._velocity_history
            else current_velocity
        )
        acceleration_pct = (
            ((current_velocity - prev_velocity) / prev_velocity * 100)
            if prev_velocity > 0
            else 0.0
        )

        # Trend-Label
        if z_score > 2:
            trend_label = "ACCELERATING_STRONG"
        elif z_score > 1:
            trend_label = "ACCELERATING"
        elif z_score < -2:
            trend_label = "DECELERATING_STRONG"
        elif z_score < -1:
            trend_label = "DECELERATING"
        else:
            trend_label = "STABLE"

        return {
            "status": "TREND_AVAILABLE",
            "historical_periods": len(self._velocity_history),
            "historical_mean_velocity": round(hist_mean, 6),
            "historical_std_velocity": round(hist_std, 6),
            "current_z_score": round(z_score, 4),
            "trend_slope": round(slope, 6),
            "acceleration_pct": round(acceleration_pct, 2),
            "previous_period_velocity": round(prev_velocity, 6),
            "trend_label": trend_label,
        }

    def _generate_alerts(
        self,
        velocity_tx: float,
        velocity_income: float,
        sector_breakdown: List[Dict],
        dispersion: float,
        total_volume: float,
        money_supply_eur: float,
        transaction_count: int,
        trend: Dict,
    ) -> List[Dict[str, Any]]:
        """
        Generiert Alerts basierend auf Velocity-Anomalien.
        """
        alerts = []

        # --- 1. Velocity-Spike (Z-Score > threshold σ) ---
        if trend.get("status") == "TREND_AVAILABLE":
            z_score = abs(trend.get("current_z_score", 0.0))
            if z_score > self.velocity_spike_threshold:
                direction = "Anstieg" if trend["current_z_score"] > 0 else "Rückgang"
                alerts.append(
                    {
                        "alert_type": "VELOCITY_SPIKE",
                        "severity": "HIGH" if z_score > 3 else "MEDIUM",
                        "message": (
                            f"Velocity-Anomalie: Z-Score={z_score:.2f}σ "
                            f"({direction} auf {velocity_tx:.4f}, "
                            f"historischer Mittelwert={trend['historical_mean_velocity']:.4f})"
                        ),
                        "z_score": round(z_score, 2),
                        "current_velocity": round(velocity_tx, 4),
                        "historical_mean": trend["historical_mean_velocity"],
                    }
                )

        # --- 2. Sektor-Dispersion (CV > threshold) ---
        if dispersion > self.dispersion_alert_threshold:
            alerts.append(
                {
                    "alert_type": "SECTOR_DISPERSION",
                    "severity": "MEDIUM",
                    "message": (
                        f"Sektorale Velocity-Dispersion erhöht: "
                        f"CV={dispersion:.3f} > Schwellwert={self.dispersion_alert_threshold:.3f} "
                        f"— sektorale Verwerfungen möglich."
                    ),
                    "dispersion_cv": round(dispersion, 3),
                    "threshold": self.dispersion_alert_threshold,
                }
            )

        # --- 3. Acceleration (abrupter Regime-Wechsel) ---
        accel = abs(trend.get("acceleration_pct", 0.0))
        if accel > self.acceleration_alert_threshold * 100:
            direction = "Beschleunigung" if trend.get("acceleration_pct", 0) > 0 else "Abbremsung"
            alerts.append(
                {
                    "alert_type": "VELOCITY_ACCELERATION",
                    "severity": "HIGH" if accel > 50 else "MEDIUM",
                    "message": (
                        f"Abrupter Velocity-Wechsel: {direction} um {accel:.1f}% "
                        f"gegenüber Vorperiode."
                    ),
                    "acceleration_pct": round(trend.get("acceleration_pct", 0), 2),
                    "threshold_pct": self.acceleration_alert_threshold * 100,
                }
            )

        # --- 4. Velocity zu niedrig (Liquiditätsstau) ---
        if velocity_tx < 0.5 and transaction_count >= self.min_transactions:
            alerts.append(
                {
                    "alert_type": "LOW_VELOCITY",
                    "severity": "HIGH",
                    "message": (
                        f"Kritisch niedrige Velocity: V_TX={velocity_tx:.4f} — "
                        f"Geld zirkuliert kaum. Deflationsdruck oder Liquiditätsstau?"
                    ),
                    "velocity_tx": round(velocity_tx, 4),
                }
            )

        # --- 5. Velocity zu hoch (Überhitzung) ---
        if velocity_tx > 5.0 and transaction_count >= self.min_transactions:
            alerts.append(
                {
                    "alert_type": "HIGH_VELOCITY",
                    "severity": "HIGH",
                    "message": (
                        f"Extrem hohe Velocity: V_TX={velocity_tx:.4f} — "
                        f"mögliche Überhitzung oder spekulative Blase."
                    ),
                    "velocity_tx": round(velocity_tx, 4),
                }
            )

        # --- 6. Ungleichgewicht TX vs. Income ---
        if velocity_tx > 0 and velocity_income > 0:
            ratio = velocity_tx / velocity_income
            if ratio > 3.0:
                alerts.append(
                    {
                        "alert_type": "VELOCITY_IMBALANCE",
                        "severity": "MEDIUM",
                        "message": (
                            f"Velocity-Ungleichgewicht: V_TX/V_Income={ratio:.2f} — "
                            f"hoher Intermediär-Anteil (Durchlaufposten?)."
                        ),
                        "v_tx": round(velocity_tx, 4),
                        "v_income": round(velocity_income, 4),
                        "ratio": round(ratio, 2),
                    }
                )

        # --- 7. Sektor-Konzentration ---
        if sector_breakdown:
            top_sector = max(sector_breakdown, key=lambda s: s["volume_share_pct"])
            if top_sector["volume_share_pct"] > 60:
                alerts.append(
                    {
                        "alert_type": "SECTOR_CONCENTRATION",
                        "severity": "LOW",
                        "message": (
                            f"Sektor-Konzentration: '{top_sector['sector']}' "
                            f"vereint {top_sector['volume_share_pct']:.1f}% des Volumens."
                        ),
                        "dominant_sector": top_sector["sector"],
                        "share_pct": top_sector["volume_share_pct"],
                    }
                )

        return alerts

    def _update_history(self, period_data: Dict[str, Any]) -> None:
        """Aktualisiert die Velocity-Historie und begrenzt auf das History-Fenster."""
        self._velocity_history.append(period_data)
        # Auf History-Fenster begrenzen
        if len(self._velocity_history) > self.history_window:
            self._velocity_history = self._velocity_history[-self.history_window :]

    # ========================================================================
    # FAST-TRACK / SERIALIZATION
    # ========================================================================

    def export_history_to_jsonl(self, filepath: str) -> str:
        """
        Exportiert die Velocity-Historie als JSONL-Datei (GoBD-konform).
        """
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        with open(filepath, "a") as f:
            for entry in self._velocity_history:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info(f"Velocity-Historie nach {filepath} exportiert: {len(self._velocity_history)} Einträge.")
        return filepath

    def load_history_from_jsonl(self, filepath: str) -> int:
        """
        Lädt Velocity-Historie aus einer JSONL-Datei.
        """
        if not os.path.exists(filepath):
            logger.warning(f"History-Datei nicht gefunden: {filepath}")
            return 0

        loaded = 0
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        self._velocity_history.append(entry)
                        loaded += 1
                    except json.JSONDecodeError:
                        continue

        # Auf History-Fenster begrenzen
        if len(self._velocity_history) > self.history_window:
            self._velocity_history = self._velocity_history[-self.history_window :]

        logger.info(f"Velocity-Historie geladen: {loaded} Einträge aus {filepath}")
        return loaded


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    import random

    print("=" * 60)
    print("VelocityOfMoneyTracker — Smoke Test")
    print("=" * 60)

    tracker = VelocityOfMoneyTrackerSubagent(period_days=30)

    # Synthetische Transaktionen generieren
    rng = random.Random(42)
    sectors = ["bau", "technik", "ausbau", "planung", "umwelt"]
    regions = ["NI", "NW", "BY", "BE", "HH"]
    types = ["payment", "payment", "payment", "deposit", "retention", "refund"]

    transactions = []
    for i in range(200):
        sector = rng.choice(sectors)
        transactions.append(
            {
                "sender": f"Sender_{rng.randint(1, 20)}",
                "receiver": f"Receiver_{rng.randint(1, 20)}",
                "amount_eur": round(rng.lognormvariate(mu=10.0, sigma=1.5), 2),
                "timestamp": (datetime.now(timezone.utc) - timedelta(days=rng.randint(0, 30))).isoformat(),
                "sector": sector,
                "region_code": rng.choice(regions),
                "category": rng.choice(types),
                "description": f"Zahlung {sector} Projekt {rng.randint(1, 5)}",
            }
        )

    # Initiale Historie aufbauen (simulierte 6 Vormonate)
    for month_offset in range(6, 0, -1):
        hist_velocity = 1.2 + rng.gauss(0, 0.15)
        tracker._update_history(
            {
                "period": f"2026-{month_offset:02d}",
                "velocity_tx": round(hist_velocity, 4),
                "velocity_income": round(hist_velocity * 0.8, 4),
                "total_volume": round(rng.uniform(4000000, 6000000), 2),
                "money_supply_eur": round(rng.uniform(3000000, 5000000), 2),
                "transaction_count": rng.randint(150, 250),
                "dispersion": round(rng.uniform(0.2, 0.4), 3),
                "alerts_count": 0,
            }
        )

    # Analyse durchführen
    money_supply = 4_500_000.0  # 4.5 Mio EUR
    report = tracker.analyze(transactions, money_supply, period_label="2026-08")

    print(f"\nStatus: {report['status']}")
    print(f"V_TX: {report['velocity_metrics']['velocity_tx']}")
    print(f"V_Income: {report['velocity_metrics']['velocity_income']}")
    print(f"Volumen: {report['velocity_metrics']['total_transaction_volume_eur']:,.2f} EUR")
    print(f"Dispersion (CV): {report['velocity_metrics']['sector_dispersion_cv']}")
    print(f"Alerts: {len(report['alerts'])}")
    for a in report["alerts"]:
        print(f"  [{a['severity']}] {a['alert_type']}: {a['message'][:100]}...")

    # Prognose
    forecast = tracker.forecast_velocity(periods_ahead=3)
    print(f"\nPrognose-Status: {forecast.get('status')}")
    if forecast.get("forecast"):
        for f in forecast["forecast"]:
            print(f"  +{f['periods_ahead']} Perioden: V={f['forecast_velocity']}")

    # Export-Test
    tracker.export_history_to_jsonl("/tmp/velocity_history_test.jsonl")
    print("\n✅ Smoke Test abgeschlossen.")
