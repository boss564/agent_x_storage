# agents_b2g/macro/subagents/programmable_stimulus_engine.py
"""
Agent 17.3 — ProgrammableStimulusEngine

Der fiskalpolitische Aktor der MacroEconomy Engine. Entscheidet automatisiert
über Geldmengen-Impulse basierend auf Echtzeit-Sensordaten von Velocity-,
Inflation- und Multiplikator-Analysen.

Theoretische Grundlagen:
  1. Taylor-Regel (erweitert für Fiskalpolitik):
     ΔG = α × (Y* − Y) + β × (π* − π) + γ × (k* − k)
     wobei:
       Y* = Ziel-BIP, Y = aktuelles BIP
       π* = Ziel-Inflation (2%), π = aktuelle Inflation
       k* = Ziel-Multiplikator, k = aktueller Multiplikator
       α, β, γ = Reaktionskoeffizienten

  2. Konditionale Transfers (Helikoptergeld mit Bedingungen):
     - Nur an Akteure mit Multiplikator > 1.2
     - Nur in Regionen mit lokaler Geldbindung > 50%
     - Nur in Sektoren mit positiver Velocity-Trend

  3. Automatische Stabilisatoren:
     - Counter-cyclical: Stimulus bei Rezession, Abschöpfung bei Überhitzung
     - Pro-cyclical vermeiden (kein Stimulus bei Vollauslastung)

  4. EURe Mint/Burn-Integration (Wave 16):
     - Stimulus = EURe Mint → SEPA-Auszahlung
     - Abschöpfung = EURe Burn → Geldvernichtung

Stimulus-Typen:
  - DIRECT_TRANSFER: Direktzahlung an Akteure (Nachfrage-Stimulus)
  - INVESTMENT_GRANT: Investitionszuschuss (Angebots-Stimulus)
  - TAX_DEFERRAL: Steuerstundung (Liquiditäts-Stimulus)
  - RETENTION_REDUCTION: Einbehalt-Senkung von 5% → 3% (Cashflow-Stimulus)
  - ACCELERATED_PAYMENT: Zahlungsziel-Verkürzung (Velocity-Stimulus)
  - CONDITIONAL_MINT: EURe-Prägung mit Auflagen (gezielter Stimulus)

Features:
  - Taylor-Regel-basierte Stimulus-Berechnung
  - Sektor- und regionalspezifische Allokation
  - EURe Mint/Burn-Integration
  - Wirksamkeits-Tracking (Ex-post-Evaluation)
  - Overheating-Protection (kein Stimulus bei Inflation > 5%)
  - Deflation-Emergency-Mode (aggressiver Stimulus bei π < −1%)
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from enum import Enum

logger = logging.getLogger("ProgrammableStimulusEngine")


class StimulusType(Enum):
    DIRECT_TRANSFER = "DIRECT_TRANSFER"
    INVESTMENT_GRANT = "INVESTMENT_GRANT"
    TAX_DEFERRAL = "TAX_DEFERRAL"
    RETENTION_REDUCTION = "RETENTION_REDUCTION"
    ACCELERATED_PAYMENT = "ACCELERATED_PAYMENT"
    CONDITIONAL_MINT = "CONDITIONAL_MINT"


class StimulusMode(Enum):
    NEUTRAL = "NEUTRAL"               # Kein Eingriff
    EXPANSIONARY = "EXPANSIONARY"     # Stimulus (Geldmenge ↑)
    CONTRACTIONARY = "CONTRACTIONARY" # Abschöpfung (Geldmenge ↓)
    EMERGENCY = "EMERGENCY"           # Notfall-Modus (Deflation/Überhitzung)


class ProgrammableStimulusEngineSubagent:
    """
    Subagent 17.3: Automatisierte Fiskalpolitik auf Basis von Echtzeit-Sensordaten.

    Entscheidungsmatrix:
                    Inflation
                    NIEDRIG  MODERAT  HOCH
    Velocity  HOCH  NEUTRAL  CONTRACT CONTRACT
              MITTEL EXPAND   NEUTRAL  CONTRACT
              NIEDRIG EMERGENCY EXPAND NEUTRAL
    """

    # Taylor-Regel-Reaktionskoeffizienten
    DEFAULT_COEFFICIENTS = {
        "alpha": 0.5,    # Output-Gap-Reaktion
        "beta": 0.8,     # Inflations-Gap-Reaktion (stärker gewichtet)
        "gamma": 0.3,    # Multiplikator-Gap-Reaktion
    }

    # Zielwerte
    TARGETS = {
        "inflation_pct": 2.0,        # EZB-Ziel: 2%
        "velocity_tx": 2.5,          # Gesunde Umlaufgeschwindigkeit
        "multiplier_k": 1.5,         # Solider Multiplikator
        "local_retention": 0.60,     # 60% regionale Geldbindung
    }

    # Schwellwerte für automatische Entscheidungen
    THRESHOLDS = {
        "deflation_emergency": -1.0,     # π < −1% → Emergency Expand
        "low_inflation": 1.0,            # π < 1% → Expand möglich
        "high_inflation": 5.0,           # π > 5% → Contract
        "hyperinflation": 10.0,          # π > 10% → Emergency Contract
        "low_velocity": 0.8,             # V < 0.8 → Stagnation
        "high_velocity": 6.0,            # V > 6.0 → Überhitzung
        "low_multiplier": 0.9,           # k < 0.9 → Stimulus lohnt nicht
        "high_multiplier": 2.5,          # k > 2.5 → Stimulus sehr effizient
    }

    def __init__(
        self,
        coefficients: Optional[Dict[str, float]] = None,
        targets: Optional[Dict[str, float]] = None,
        thresholds: Optional[Dict[str, float]] = None,
        max_stimulus_per_cycle_eur: float = 2_000_000.0,
        min_stimulus_eur: float = 10_000.0,
        emergency_multiplier: float = 3.0,
    ):
        """
        Args:
            coefficients: Taylor-Regel-Koeffizienten (alpha, beta, gamma)
            targets: Zielwerte für Inflation, Velocity, Multiplikator
            thresholds: Schwellwerte für automatische Entscheidungen
            max_stimulus_per_cycle_eur: Maximaler Stimulus pro Zyklus
            min_stimulus_eur: Minimaler Stimulus (darunter lohnt nicht)
            emergency_multiplier: Multiplikator für Emergency-Modus
        """
        self.coefficients = coefficients or self.DEFAULT_COEFFICIENTS
        self.targets = targets or self.TARGETS
        self.thresholds = thresholds or self.THRESHOLDS
        self.max_stimulus_per_cycle = max_stimulus_per_cycle_eur
        self.min_stimulus = min_stimulus_eur
        self.emergency_multiplier = emergency_multiplier

        # Historie der Stimulus-Entscheidungen
        self._stimulus_history: List[Dict[str, Any]] = []
        self._total_stimulus_deployed_eur: float = 0.0

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def decide_stimulus(
        self,
        velocity_report: Dict[str, Any],
        inflation_report: Dict[str, Any],
        multiplier_report: Dict[str, Any],
        money_supply_eur: float,
        tender_id: Optional[str] = None,
        period_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Hauptmethode: Entscheidet über fiskalische Impulse.

        Args:
            velocity_report: Output von VelocityOfMoneyTracker.analyze()
            inflation_report: Output von RealTimeInflationOracle.measure_inflation()
            multiplier_report: Output von SupplyChainMultiplierCalc.calculate_multiplier()
            money_supply_eur: Aktuelle Geldmenge M
            tender_id: Optionaler Tender-Filter
            period_label: Perioden-Label

        Returns:
            Stimulus-Entscheidung mit Typ, Betrag, Allokation und Begründung
        """
        period_label = period_label or datetime.now(timezone.utc).strftime("%Y-%m")
        job_id = f"stim_{period_label}"

        logger.info(f"Stimulus-Entscheidung für Periode {period_label}")

        try:
            # === 1. Sensordaten extrahieren ===
            sensors = self._extract_sensor_data(
                velocity_report, inflation_report, multiplier_report
            )

            if sensors is None:
                return {
                    "status": "INSUFFICIENT_SENSOR_DATA",
                    "job_id": job_id,
                    "artifacts": [],
                    "error": None,
                    "logs": [{"level": "WARN", "message": "Nicht genug Sensordaten für Stimulus-Entscheidung."}],
                }

            # === 2. Makroökonomischen Modus bestimmen ===
            mode = self._determine_mode(sensors)
            logger.info(f"Stimulus-Modus: {mode.value}")

            # === 3. Stimulus-Betrag berechnen (Taylor-Regel) ===
            stimulus_amount, taylor_components = self._calculate_stimulus_amount(
                sensors, mode, money_supply_eur
            )

            # === 4. Stimulus-Typ bestimmen ===
            stimulus_type = self._determine_stimulus_type(sensors, mode, stimulus_amount)

            # === 5. Sektorale und regionale Allokation ===
            allocation = self._allocate_stimulus(
                stimulus_amount, sensors, velocity_report, multiplier_report
            )

            # === 6. EURe Mint/Burn-Anweisung ===
            eure_instruction = self._generate_eure_instruction(
                mode, stimulus_amount, stimulus_type
            )

            # === 7. Risikoprüfung (Overheating, Mitnahmeeffekte) ===
            risk_assessment = self._assess_stimulus_risk(
                sensors, mode, stimulus_amount, allocation
            )

            # === 8. Wirksamkeits-Prognose ===
            impact_forecast = self._forecast_impact(
                sensors, stimulus_amount, allocation
            )

            # === 9. Entscheidungs-Memo ===
            decision_memo = self._write_decision_memo(
                mode, stimulus_amount, stimulus_type, sensors, risk_assessment
            )

            # === 10. Historie aktualisieren ===
            self._record_decision(
                period_label, mode, stimulus_amount, stimulus_type, job_id
            )

            report = {
                "status": "DECISION_COMPLETE",
                "job_id": job_id,
                "tender_id": tender_id,
                "period_label": period_label,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "artifacts": [
                    {
                        "type": "stimulus_decision",
                        "format": "json",
                        "metadata": {
                            "mode": mode.value,
                            "amount_eur": round(stimulus_amount, 2),
                            "type": stimulus_type.value if stimulus_type else "NONE",
                        },
                    }
                ],
                "error": None,
                "logs": [
                    {
                        "level": "INFO",
                        "message": (
                            f"Stimulus-Entscheidung: {mode.value}, "
                            f"{stimulus_amount:,.0f} EUR, "
                            f"Typ={stimulus_type.value if stimulus_type else 'NONE'}"
                        ),
                    }
                ],
                "decision": {
                    "mode": mode.value,
                    "stimulus_amount_eur": round(stimulus_amount, 2),
                    "stimulus_type": stimulus_type.value if stimulus_type else "NONE",
                    "taylor_components": taylor_components,
                    "is_active": stimulus_amount >= self.min_stimulus,
                },
                "sensor_summary": sensors,
                "allocation": allocation,
                "eure_instruction": eure_instruction,
                "risk_assessment": risk_assessment,
                "impact_forecast": impact_forecast,
                "decision_memo": decision_memo,
                "alerts": risk_assessment.get("alerts", []),
                "has_alerts": len(risk_assessment.get("alerts", [])) > 0,
            }

            logger.info(
                f"Stimulus-Entscheidung abgeschlossen: {mode.value}, "
                f"{stimulus_amount:,.0f} EUR"
            )
            return report

        except Exception as e:
            logger.error(f"Stimulus-Entscheidung fehlgeschlagen: {e}", exc_info=True)
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": str(e),
                "logs": [{"level": "ERROR", "message": str(e)}],
            }

    def get_stimulus_history(self) -> List[Dict[str, Any]]:
        """Gibt die Historie aller Stimulus-Entscheidungen zurück."""
        return self._stimulus_history

    def get_total_deployed(self) -> float:
        """Gibt den insgesamt ausgeschütteten Stimulus zurück."""
        return self._total_stimulus_deployed_eur

    # ========================================================================
    # SENSOR DATA EXTRACTION
    # ========================================================================

    def _extract_sensor_data(
        self,
        velocity_report: Dict[str, Any],
        inflation_report: Dict[str, Any],
        multiplier_report: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Extrahiert die relevanten Kennzahlen aus den drei Sensor-Reports.
        """
        sensors = {}

        # Velocity
        vel_metrics = velocity_report.get("velocity_metrics", {})
        if vel_metrics:
            sensors["velocity_tx"] = vel_metrics.get("velocity_tx", 1.0)
            sensors["velocity_income"] = vel_metrics.get("velocity_income", 1.0)
            sensors["velocity_dispersion"] = vel_metrics.get("sector_dispersion_cv", 0.0)
            sensors["velocity_trend"] = velocity_report.get("trend", {}).get("trend_label", "STABLE")
            sensors["velocity_alerts"] = len(velocity_report.get("alerts", []))

        # Inflation
        sensors["inflation_pct"] = inflation_report.get("composite_inflation_pct", 0.0)
        sensors["inflation_trend"] = inflation_report.get("trend", {}).get("trend_direction", "STABLE")
        sensors["inflation_alerts"] = len(inflation_report.get("alerts", []))

        # Multiplikator
        mm = multiplier_report.get("multiplier_metrics", {})
        if mm:
            sensors["multiplier_k"] = mm.get("composite_multiplier", 1.0)
            sensors["multiplier_empirical"] = mm.get("empirical_multiplier", 1.0)
            sensors["multiplier_mpc"] = mm.get("mpc", 0.7)
            sensors["local_retention"] = multiplier_report.get(
                "regional_multiplier", {}
            ).get("local_retention_rate", 0.5)
            sensors["multiplier_alerts"] = len(multiplier_report.get("alerts", []))
            sensors["jobs_per_mio"] = multiplier_report.get(
                "employment_impact", {}
            ).get("jobs_per_mio_eur", 10.0)

        # Prüfen ob genug Daten
        required = ["velocity_tx", "inflation_pct", "multiplier_k"]
        if not all(k in sensors for k in required):
            missing = [k for k in required if k not in sensors]
            logger.warning(f"Fehlende Sensordaten: {missing}")
            return None

        return sensors

    # ========================================================================
    # MODE DETERMINATION
    # ========================================================================

    def _determine_mode(self, sensors: Dict[str, Any]) -> StimulusMode:
        """
        Bestimmt den fiskalpolitischen Modus anhand der Entscheidungsmatrix:

                        Inflation
                        NIEDRIG   MODERAT   HOCH
        Velocity  HOCH  NEUTRAL   CONTRACT  CONTRACT
                  MITTEL EXPAND    NEUTRAL   CONTRACT
                  NIEDRIG EMERGENCY EXPAND   NEUTRAL
        """
        v = sensors["velocity_tx"]
        pi = sensors["inflation_pct"]

        # Velocity-Kategorie
        if v > self.thresholds["high_velocity"]:
            v_cat = "HOCH"
        elif v > self.thresholds["low_velocity"]:
            v_cat = "MITTEL"
        else:
            v_cat = "NIEDRIG"

        # Inflations-Kategorie
        if pi > self.thresholds["high_inflation"]:
            pi_cat = "HOCH"
        elif pi > self.thresholds["low_inflation"]:
            pi_cat = "MODERAT"
        else:
            pi_cat = "NIEDRIG"

        # Matrix: Zeile = pi_cat, Spalte = v_cat
        if pi_cat == "NIEDRIG" and v_cat == "NIEDRIG":
            return StimulusMode.EMERGENCY  # Deflationsspirale
        elif pi_cat == "NIEDRIG":
            return StimulusMode.EXPANSIONARY
        elif pi_cat == "HOCH":
            if v_cat == "HOCH":
                return StimulusMode.EMERGENCY  # Überhitzung
            return StimulusMode.CONTRACTIONARY
        elif pi_cat == "MODERAT" and v_cat == "HOCH":
            return StimulusMode.CONTRACTIONARY
        elif pi_cat == "MODERAT" and v_cat == "NIEDRIG":
            return StimulusMode.EXPANSIONARY
        else:
            return StimulusMode.NEUTRAL

    # ========================================================================
    # STIMULUS AMOUNT (Taylor Rule)
    # ========================================================================

    def _calculate_stimulus_amount(
        self,
        sensors: Dict[str, Any],
        mode: StimulusMode,
        money_supply_eur: float,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Berechnet den Stimulus-Betrag mittels erweiterter Taylor-Regel:

        ΔG = α × (Y* − Y) + β × (π* − π) + γ × (k* − k)

        Skaliert auf Geldmenge: ΔG = taylor_output × M × mode_sign
        """
        if mode == StimulusMode.NEUTRAL:
            return 0.0, {"mode": "NEUTRAL", "reason": "Kein Eingriff nötig."}

        # Output-Gap (approximiert durch Velocity-Gap)
        velocity_gap = self.targets["velocity_tx"] - sensors["velocity_tx"]

        # Inflations-Gap
        inflation_gap = self.targets["inflation_pct"] - sensors["inflation_pct"]

        # Multiplikator-Gap
        multiplier_gap = self.targets["multiplier_k"] - sensors["multiplier_k"]

        # Taylor-Regel
        taylor_raw = (
            self.coefficients["alpha"] * velocity_gap
            + self.coefficients["beta"] * inflation_gap
            + self.coefficients["gamma"] * multiplier_gap
        )

        # Mode-Sign: positiv = expansiv, negativ = kontraktiv
        if mode == StimulusMode.EXPANSIONARY:
            mode_sign = 1.0
        elif mode == StimulusMode.CONTRACTIONARY:
            mode_sign = -1.0
        elif mode == StimulusMode.EMERGENCY:
            mode_sign = 1.0 if sensors["inflation_pct"] < 0 else -1.0
        else:
            mode_sign = 0.0

        # Basis-Stimulus als Anteil der Geldmenge
        stimulus_pct = abs(taylor_raw) * 0.05  # Max 5% der Geldmenge pro Zyklus
        stimulus_pct = min(stimulus_pct, 0.05)  # Cap

        # Emergency-Multiplikator
        if mode == StimulusMode.EMERGENCY:
            stimulus_pct *= self.emergency_multiplier

        stimulus_amount = money_supply_eur * stimulus_pct * mode_sign

        # Auf Max/Min begrenzen
        stimulus_amount = max(
            -self.max_stimulus_per_cycle,
            min(self.max_stimulus_per_cycle, stimulus_amount)
        )

        # Wenn Betrag zu klein → kein Stimulus
        if abs(stimulus_amount) < self.min_stimulus and mode != StimulusMode.EMERGENCY:
            stimulus_amount = 0.0

        taylor_components = {
            "velocity_gap": round(velocity_gap, 3),
            "inflation_gap": round(inflation_gap, 3),
            "multiplier_gap": round(multiplier_gap, 3),
            "taylor_raw": round(taylor_raw, 4),
            "stimulus_pct_of_money_supply": round(stimulus_pct, 4),
            "mode_sign": mode_sign,
            "alpha": self.coefficients["alpha"],
            "beta": self.coefficients["beta"],
            "gamma": self.coefficients["gamma"],
        }

        return round(stimulus_amount, 2), taylor_components

    # ========================================================================
    # STIMULUS TYPE
    # ========================================================================

    def _determine_stimulus_type(
        self,
        sensors: Dict[str, Any],
        mode: StimulusMode,
        amount: float,
    ) -> Optional[StimulusType]:
        """
        Wählt den optimalen Stimulus-Typ basierend auf der Situation.
        """
        if mode == StimulusMode.NEUTRAL or abs(amount) < self.min_stimulus:
            return None

        if mode == StimulusMode.EMERGENCY:
            # Deflation → direktes Helikoptergeld
            if sensors["inflation_pct"] < 0:
                return StimulusType.DIRECT_TRANSFER
            # Überhitzung → Einbehalt erhöhen
            else:
                return StimulusType.RETENTION_REDUCTION

        if mode == StimulusMode.EXPANSIONARY:
            # Niedrige Velocity → Zahlungen beschleunigen
            if sensors["velocity_tx"] < self.thresholds["low_velocity"]:
                return StimulusType.ACCELERATED_PAYMENT
            # Hoher Multiplikator → Investitionszuschuss
            elif sensors["multiplier_k"] > self.targets["multiplier_k"]:
                return StimulusType.INVESTMENT_GRANT
            # Niedriger Multiplikator → Steuerstundung (indirekt)
            else:
                return StimulusType.TAX_DEFERRAL

        if mode == StimulusMode.CONTRACTIONARY:
            # Geld abschöpfen → Retention erhöhen
            return StimulusType.RETENTION_REDUCTION  # Negativ = Erhöhung

        return StimulusType.CONDITIONAL_MINT

    # ========================================================================
    # ALLOCATION
    # ========================================================================

    def _allocate_stimulus(
        self,
        amount: float,
        sensors: Dict[str, Any],
        velocity_report: Dict[str, Any],
        multiplier_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Verteilt den Stimulus auf Sektoren und Regionen nach Effizienz.

        Regel: Geld fließt dorthin, wo der Multiplikator am höchsten ist.
        """
        if abs(amount) < self.min_stimulus:
            return {"mode": "NO_ALLOCATION", "reason": "Betrag zu gering."}

        # Sektor-Multiplikatoren aus dem Report
        sector_multipliers = multiplier_report.get("sector_multipliers", {})
        sector_velocity = velocity_report.get("velocity_metrics", {}).get("sector_breakdown", [])

        # Effizienz-Score pro Sektor: k × velocity × local_retention
        sector_scores = {}
        for sector, data in sector_multipliers.items():
            k = data.get("sector_multiplier", 1.0)
            # Velocity für diesen Sektor finden
            v = 1.0
            for sv in sector_velocity:
                if sv.get("sector") == sector:
                    v = sv.get("velocity", 1.0)
                    break
            score = k * v
            sector_scores[sector] = {
                "score": round(score, 3),
                "k": k,
                "velocity": v,
            }

        # Nur Sektoren mit k > 1.0 (positiver Hebel) erhalten Stimulus
        eligible = {
            s: d for s, d in sector_scores.items()
            if d["k"] > 1.0
        }

        if not eligible:
            return {
                "mode": "NO_ELIGIBLE_SECTORS",
                "reason": "Kein Sektor mit k>1.0 — Stimulus wäre kontraproduktiv.",
            }

        # Nach Score gewichten
        total_score = sum(d["score"] for d in eligible.values())
        allocation = {}
        for sector, data in sorted(eligible.items(), key=lambda x: x[1]["score"], reverse=True):
            share = data["score"] / total_score if total_score > 0 else 0.0
            allocation[sector] = {
                "amount_eur": round(amount * share, 2),
                "share_pct": round(share * 100, 1),
                "k_sector": data["k"],
                "velocity_sector": data["velocity"],
            }

        # Regional: Bevorzugt Regionen mit hoher lokaler Geldbindung
        regional = multiplier_report.get("regional_multiplier", {}).get("regional_breakdown", {})

        return {
            "mode": "EFFICIENCY_WEIGHTED",
            "total_amount_eur": round(amount, 2),
            "eligible_sectors": len(eligible),
            "sector_allocation": allocation,
            "regional_preference": {
                r: d for r, d in sorted(
                    regional.items(),
                    key=lambda x: x[1].get("local_retention_pct", 0),
                    reverse=True,
                )[:3]
            },
            "excluded_sectors": [
                s for s in sector_scores if s not in eligible
            ],
        }

    # ========================================================================
    # EURe INSTRUCTION
    # ========================================================================

    def _generate_eure_instruction(
        self,
        mode: StimulusMode,
        amount: float,
        stimulus_type: Optional[StimulusType],
    ) -> Dict[str, Any]:
        """
        Generiert eine EURe Mint/Burn-Anweisung für Wave 16 (SEPA Bridge).
        """
        if mode == StimulusMode.NEUTRAL or abs(amount) < self.min_stimulus:
            return {
                "action": "NONE",
                "reason": "Kein Mint/Burn nötig.",
            }

        if amount > 0:
            action = "MINT"
            instruction = {
                "action": "MINT",
                "amount_eur": round(amount, 2),
                "purpose": stimulus_type.value if stimulus_type else "CONDITIONAL_MINT",
                "compliance": {
                    "mica_check": "SEPA_ZONE_ONLY",
                    "max_per_tx_eur": min(amount, 5_000_000),
                    "bho_zero_sum": "DELTA_LE_0_01_EUR",
                },
                "routing": {
                    "via": "MoneriumAPIClientSubagent",
                    "settlement": "SEPA_INSTANT",
                },
            }
        else:
            action = "BURN"
            burn_amount = abs(amount)
            instruction = {
                "action": "BURN",
                "amount_eur": round(burn_amount, 2),
                "purpose": "CONTRACTIONARY_ABSORPTION",
                "source": "RETENTION_VAULT",
                "compliance": {
                    "bho_zero_sum": "DELTA_LE_0_01_EUR",
                },
            }

        return {
            "action": action,
            "instruction": instruction,
            "wave16_agent": "EUReMinterSubagent" if action == "MINT" else "EUReBurnerSubagent",
        }

    # ========================================================================
    # RISK ASSESSMENT
    # ========================================================================

    def _assess_stimulus_risk(
        self,
        sensors: Dict[str, Any],
        mode: StimulusMode,
        amount: float,
        allocation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Prüft auf Risiken: Überhitzung, Mitnahmeeffekte, Crowding-Out.
        """
        alerts = []
        risks = []

        # 1. Überhitzungsrisiko
        if sensors["inflation_pct"] > 4.0 and mode == StimulusMode.EXPANSIONARY:
            risks.append({
                "risk": "OVERHEATING",
                "severity": "HIGH",
                "description": "Inflation >4% — expansiver Stimulus riskiert Überhitzung.",
            })
            alerts.append({
                "alert_type": "OVERHEATING_RISK",
                "severity": "HIGH",
                "message": f"Inflation bei {sensors['inflation_pct']:.1f}% — Stimulus trotz Expansion riskant!",
            })

        # 2. Mitnahmeeffekt
        if sensors["multiplier_k"] < 1.0 and amount > 0:
            risks.append({
                "risk": "DEADWEIGHT_LOSS",
                "severity": "HIGH",
                "description": f"Multiplikator k={sensors['multiplier_k']:.2f}<1 — Stimulus verpufft (Mitnahmeeffekt).",
            })
            alerts.append({
                "alert_type": "LOW_MULTIPLIER_STIMULUS",
                "severity": "HIGH",
                "message": f"Multiplikator {sensors['multiplier_k']:.2f}<1 — JEDER € Stimulus generiert WENIGER als 1€ Output!",
            })

        # 3. Prozyklischer Stimulus
        if sensors["velocity_tx"] > 5.0 and mode == StimulusMode.EXPANSIONARY:
            risks.append({
                "risk": "PROCYCLICAL",
                "severity": "MEDIUM",
                "description": "Velocity bereits hoch — expansiver Stimulus wäre prozyklisch.",
            })

        # 4. Crowding-Out
        if sensors["local_retention"] < 0.35:
            risks.append({
                "risk": "CROWDING_OUT",
                "severity": "MEDIUM",
                "description": f"Niedrige lokale Bindung ({sensors['local_retention']*100:.0f}%) — Geld fließt ab.",
            })

        # 5. Sektor-Konzentration
        sector_alloc = allocation.get("sector_allocation", {})
        if sector_alloc:
            top_share = max(d["share_pct"] for d in sector_alloc.values())
            if top_share > 60:
                risks.append({
                    "risk": "SECTOR_CONCENTRATION",
                    "severity": "LOW",
                    "description": f"Stimulus zu >60% in einem Sektor konzentriert — Klumpenrisiko.",
                })

        # Gesamtrisiko
        high_risks = [r for r in risks if r["severity"] == "HIGH"]
        overall = "HIGH" if high_risks else ("MEDIUM" if risks else "LOW")

        return {
            "overall_risk": overall,
            "risk_count": len(risks),
            "high_risk_count": len(high_risks),
            "risks": risks,
            "alerts": alerts,
            "veto_recommended": len(high_risks) > 0,
        }

    # ========================================================================
    # IMPACT FORECAST
    # ========================================================================

    def _forecast_impact(
        self,
        sensors: Dict[str, Any],
        amount: float,
        allocation: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Prognostiziert die Wirkung des Stimulus.
        """
        if abs(amount) < self.min_stimulus:
            return {"status": "NO_IMPACT", "reason": "Betrag zu gering."}

        # ΔY = k × ΔG
        delta_y = sensors["multiplier_k"] * amount

        # ΔJobs = (ΔY / 1_000_000) × jobs_per_mio
        delta_jobs = (delta_y / 1_000_000) * sensors.get("jobs_per_mio", 10.0)

        # ΔVelocity (geschätzt)
        delta_velocity = 0.05 * (amount / max(abs(amount), 1))  # ±5% Velocity-Änderung

        # ΔInflation (über Quantitätsgleichung)
        delta_inflation = 0.02 * (amount / max(abs(amount), 1))  # ±2% Inflations-Änderung

        return {
            "status": "FORECAST_COMPLETE",
            "delta_gdp_eur": round(delta_y, 2),
            "delta_jobs": round(delta_jobs, 1),
            "delta_velocity_est": round(delta_velocity, 3),
            "delta_inflation_est_pct": round(delta_inflation, 1),
            "roi": round(delta_y / max(abs(amount), 1), 2),
            "break_even_months": round(12 / max(sensors["multiplier_k"], 0.01), 1),
        }

    # ========================================================================
    # DECISION MEMO
    # ========================================================================

    def _write_decision_memo(
        self,
        mode: StimulusMode,
        amount: float,
        stimulus_type: Optional[StimulusType],
        sensors: Dict[str, Any],
        risk: Dict[str, Any],
    ) -> str:
        """
        Schreibt ein menschenlesbares Entscheidungs-Memo.
        """
        if mode == StimulusMode.NEUTRAL or abs(amount) < self.min_stimulus:
            return (
                f"KEIN EINGRIFF (Periode: {datetime.now(timezone.utc).strftime('%Y-%m')})\n"
                f" Inflation={sensors['inflation_pct']:.1f}%, Velocity={sensors['velocity_tx']:.2f}, "
                f"k={sensors['multiplier_k']:.2f}\n"
                f" Alle Indikatoren im Normbereich. Kein automatischer Stimulus nötig."
            )

        direction = "EXPANSIV" if amount > 0 else "KONTRAKTIV"
        return (
            f"{direction}ER STIMULUS ({mode.value})\n"
            f" Betrag: {abs(amount):,.0f} EUR ({direction})\n"
            f" Typ: {stimulus_type.value if stimulus_type else 'N/A'}\n"
            f" Begründung: π={sensors['inflation_pct']:.1f}% "
            f"(Ziel: {self.targets['inflation_pct']}%), "
            f"V={sensors['velocity_tx']:.2f} (Ziel: {self.targets['velocity_tx']}), "
            f"k={sensors['multiplier_k']:.2f} (Ziel: {self.targets['multiplier_k']})\n"
            f" Risiko: {risk['overall_risk']} "
            f"({'VETO empfohlen' if risk.get('veto_recommended') else 'Freigabe'})"
        )

    # ========================================================================
    # HISTORY
    # ========================================================================

    def _record_decision(
        self,
        period_label: str,
        mode: StimulusMode,
        amount: float,
        stimulus_type: Optional[StimulusType],
        job_id: str,
    ) -> None:
        """Protokolliert die Entscheidung in der Historie."""
        self._stimulus_history.append(
            {
                "period": period_label,
                "job_id": job_id,
                "mode": mode.value,
                "amount_eur": round(amount, 2),
                "type": stimulus_type.value if stimulus_type else "NONE",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            }
        )
        if amount > 0:
            self._total_stimulus_deployed_eur += amount

    # ========================================================================
    # INTEGRATION HOOKS
    # ========================================================================

    def load_sensor_bundle(
        self,
        velocity_report: Dict[str, Any],
        inflation_report: Dict[str, Any],
        multiplier_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Convenience-Methode für den Orchestrator:
        Lädt alle drei Sensor-Reports und gibt die extrahierten Daten zurück.
        """
        return self._extract_sensor_data(
            velocity_report, inflation_report, multiplier_report
        )


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ProgrammableStimulusEngine — Smoke Test")
    print("=" * 60)

    engine = ProgrammableStimulusEngineSubagent()

    # Simulierte Sensor-Daten (aus vorherigen Smoke-Tests)
    velocity_report = {
        "velocity_metrics": {
            "velocity_tx": 1.30,
            "velocity_income": 0.83,
            "sector_dispersion_cv": 0.0,
            "sector_breakdown": [
                {"sector": "bau", "velocity": 1.5},
                {"sector": "technik", "velocity": 0.9},
                {"sector": "ausbau", "velocity": 1.3},
            ],
        },
        "trend": {"trend_label": "STABLE"},
        "alerts": [],
    }

    inflation_report = {
        "composite_inflation_pct": 0.33,
        "trend": {"trend_direction": "STABLE"},
        "alerts": [],
    }

    multiplier_report = {
        "multiplier_metrics": {
            "composite_multiplier": 1.14,
            "empirical_multiplier": 0.91,
            "mpc": 0.73,
        },
        "sector_multipliers": {
            "bau": {"sector_multiplier": 1.3, "volume_eur": 500000},
            "technik": {"sector_multiplier": 0.9, "volume_eur": 300000},
            "ausbau": {"sector_multiplier": 1.1, "volume_eur": 150000},
        },
        "regional_multiplier": {
            "local_retention_rate": 0.29,
            "regional_breakdown": {
                "NI": {"local_retention_pct": 55.0, "total_volume_eur": 2000000},
                "NW": {"local_retention_pct": 40.0, "total_volume_eur": 1000000},
            },
        },
        "employment_impact": {"jobs_per_mio_eur": 8.8},
        "alerts": [],
    }

    # Test 1: Normale Situation
    print("\n--- Test 1: Normale Konjunktur ---")
    decision = engine.decide_stimulus(
        velocity_report=velocity_report,
        inflation_report=inflation_report,
        multiplier_report=multiplier_report,
        money_supply_eur=5_000_000.0,
    )
    print(f"Modus: {decision['decision']['mode']}")
    print(f"Betrag: {decision['decision']['stimulus_amount_eur']:,.0f} EUR")
    print(f"Typ: {decision['decision']['stimulus_type']}")
    print(f"Memo: {decision['decision_memo'][:150]}...")

    # Test 2: Deflationäre Krise
    print("\n--- Test 2: Deflations-Krise ---")
    crisis_inflation = dict(inflation_report)
    crisis_inflation["composite_inflation_pct"] = -2.0
    crisis_velocity = dict(velocity_report)
    crisis_velocity["velocity_metrics"] = dict(velocity_report["velocity_metrics"])
    crisis_velocity["velocity_metrics"]["velocity_tx"] = 0.5

    crisis_decision = engine.decide_stimulus(
        velocity_report=crisis_velocity,
        inflation_report=crisis_inflation,
        multiplier_report=multiplier_report,
        money_supply_eur=5_000_000.0,
    )
    print(f"Modus: {crisis_decision['decision']['mode']}")
    print(f"Betrag: {crisis_decision['decision']['stimulus_amount_eur']:,.0f} EUR")
    print(f"Typ: {crisis_decision['decision']['stimulus_type']}")
    print(f"EURe: {crisis_decision['eure_instruction']['action']}")

    # Test 3: Überhitzung
    print("\n--- Test 3: Überhitzung ---")
    hot_inflation = dict(inflation_report)
    hot_inflation["composite_inflation_pct"] = 7.0
    hot_velocity = dict(velocity_report)
    hot_velocity["velocity_metrics"] = dict(velocity_report["velocity_metrics"])
    hot_velocity["velocity_metrics"]["velocity_tx"] = 6.5

    hot_decision = engine.decide_stimulus(
        velocity_report=hot_velocity,
        inflation_report=hot_inflation,
        multiplier_report=multiplier_report,
        money_supply_eur=5_000_000.0,
    )
    print(f"Modus: {hot_decision['decision']['mode']}")
    print(f"Betrag: {hot_decision['decision']['stimulus_amount_eur']:,.0f} EUR")
    print(f"EURe: {hot_decision['eure_instruction']['action']}")
    print(f"Veto: {hot_decision['risk_assessment']['veto_recommended']}")

    print(f"\nHistorie: {len(engine.get_stimulus_history())} Entscheidungen")
    print(f"Total deployed: {engine.get_total_deployed():,.0f} EUR")

    print("\n✅ Smoke Test abgeschlossen.")
