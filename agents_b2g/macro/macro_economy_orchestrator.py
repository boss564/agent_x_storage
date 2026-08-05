# agents_b2g/macro/macro_economy_orchestrator.py
"""
Agent 17.1 — MacroEconomyOrchestrator

Root-Agent der Welle 17 (MacroEconomy Engine). Orchestriert alle 8
makroökonomischen Subagenten in einer 8-stufigen Analyse-Pipeline:

  Step 1: VelocityOfMoneyTracker     → Umlaufgeschwindigkeit
  Step 2: RealTimeTaxSplitter        → Steuerabfluss in Echtzeit
  Step 3: CapitalEfficiencyAnalyzer  → Kapitaleffizienz & ROIC
  Step 4: SupplyChainMultiplierCalc  → Lieferketten-Multiplikator
  Step 5: RealTimeInflationOracle    → Preisindex aus GAEB-Daten
  Step 6: SystemicRiskAndCartelMonitor → Kartell- & Monopolerkennung
  Step 7: ProgrammableStimulusEngine → Fiskalimpulse bewerten
  Step 8: CentralBankLedgerTwin      → Zentralbank-Bilanz spiegeln

Ergebnis: MacroEconomyReport — ein vollständiges makroökonomisches
Lagebild des Agent-X-Ökosystems, auditiert und GoBD-konform.

Standardisierte Output-Schnittstelle (JSON-Vertrag):
  {
    "status": "started|completed|failed",
    "job_id": "uuid",
    "period_label": "2026-08",
    "artifacts": [{"type": "macro_report", "format": "json", "metadata": {...}}],
    "error": null,
    "logs": [...]
  }
"""

import json
import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from decimal import Decimal

from agents_b2g.macro.subagents.velocity_of_money_tracker import (
    VelocityOfMoneyTrackerSubagent,
)
from agents_b2g.macro.subagents.real_time_inflation_oracle import (
    RealTimeInflationOracleSubagent,
)
from agents_b2g.macro.subagents.supply_chain_multiplier_calc import (
    SupplyChainMultiplierCalcSubagent,
)
from agents_b2g.macro.subagents.programmable_stimulus_engine import (
    ProgrammableStimulusEngineSubagent,
)
from agents_b2g.macro.subagents.real_time_tax_splitter import (
    RealTimeTaxSplitterSubagent,
)
from agents_b2g.macro.subagents.capital_efficiency_analyzer import (
    CapitalEfficiencyAnalyzerSubagent,
)
from agents_b2g.macro.subagents.systemic_risk_and_cartel_monitor import (
    SystemicRiskAndCartelMonitorSubagent,
)
from agents_b2g.macro.subagents.central_bank_ledger_twin import (
    CentralBankLedgerTwinSubagent,
)

logger = logging.getLogger("MacroEconomyOrchestrator")


class MacroEconomyOrchestrator:
    """
    Root-Agent der MacroEconomy-Engine (Welle 17).

    Sammelt Transaktionsdaten, orchestriert Subagenten,
    aggregiert Ergebnisse in einem MacroEconomyReport.
    """

    # 8-Stufen-Pipeline (wird schrittweise mit Subagenten befüllt)
    PIPELINE_STEPS = [
        {"id": "velocity", "name": "VelocityOfMoneyTracker", "agent_index": 2, "implemented": True},
        {"id": "tax_splitter", "name": "RealTimeTaxSplitter", "agent_index": 4, "implemented": True},
        {"id": "capital_efficiency", "name": "CapitalEfficiencyAnalyzer", "agent_index": 5, "implemented": True},
        {"id": "supply_chain", "name": "SupplyChainMultiplierCalc", "agent_index": 6, "implemented": True},
        {"id": "inflation", "name": "RealTimeInflationOracle", "agent_index": 8, "implemented": True},
        {"id": "cartel_monitor", "name": "SystemicRiskAndCartelMonitor", "agent_index": 7, "implemented": True},
        {"id": "stimulus", "name": "ProgrammableStimulusEngine", "agent_index": 3, "implemented": True},
        {"id": "cb_ledger", "name": "CentralBankLedgerTwin", "agent_index": 9, "implemented": True},
    ]

    def __init__(
        self,
        ledger_agent=None,  # Wird injected: Zugriff auf TransactionLedger
        treasury_agent=None,  # Wird injected: Zugriff auf Treasury
        velocity_tracker: Optional[VelocityOfMoneyTrackerSubagent] = None,
        inflation_oracle: Optional[RealTimeInflationOracleSubagent] = None,
        multiplier_calc: Optional[SupplyChainMultiplierCalcSubagent] = None,
        stimulus_engine: Optional[ProgrammableStimulusEngineSubagent] = None,
        tax_splitter: Optional[RealTimeTaxSplitterSubagent] = None,
        efficiency_analyzer: Optional[CapitalEfficiencyAnalyzerSubagent] = None,
        cartel_monitor: Optional[SystemicRiskAndCartelMonitorSubagent] = None,
        cb_ledger_twin: Optional[CentralBankLedgerTwinSubagent] = None,
        user_id: str = "default",
        data_root: str = "/data",
    ):
        """
        Args:
            ledger_agent: Agent mit get_all_transactions()-Methode
            treasury_agent: Agent mit get_money_supply()-Methode
            velocity_tracker: Optional vorinitialisierter Velocity-Tracker
            inflation_oracle: Optional vorinitialisierter InflationOracle
            user_id: Tenant-ID für Multi-Tenancy
            data_root: Root-Pfad für Datenausgabe
        """
        self.ledger = ledger_agent
        self.treasury = treasury_agent
        self.velocity_tracker = velocity_tracker or VelocityOfMoneyTrackerSubagent()
        self.inflation_oracle = inflation_oracle or RealTimeInflationOracleSubagent()
        self.multiplier_calc = multiplier_calc or SupplyChainMultiplierCalcSubagent()
        self.stimulus_engine = stimulus_engine or ProgrammableStimulusEngineSubagent()
        self.tax_splitter = tax_splitter or RealTimeTaxSplitterSubagent()
        self.efficiency_analyzer = efficiency_analyzer or CapitalEfficiencyAnalyzerSubagent()
        self.cartel_monitor = cartel_monitor or SystemicRiskAndCartelMonitorSubagent()
        self.cb_ledger_twin = cb_ledger_twin or CentralBankLedgerTwinSubagent()
        self.user_id = user_id
        self.data_root = data_root

        # Zustand
        self._last_report: Optional[Dict[str, Any]] = None
        self._report_history: List[Dict[str, Any]] = []

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def analyze_economy(
        self,
        tender_id: Optional[str] = None,
        period_label: Optional[str] = None,
        money_supply_eur: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Führt die vollständige makroökonomische Analyse durch.

        Args:
            tender_id: Optional auf einen Tender beschränken
            period_label: Perioden-Label (z.B. "2026-08")
            money_supply_eur: Geldmenge (falls nicht vom Treasury abrufbar)

        Returns:
            MacroEconomyReport als standardisiertes JSON
        """
        job_id = str(uuid.uuid4())
        period_label = period_label or datetime.now(timezone.utc).strftime("%Y-%m")

        logger.info(f"Starte Makro-Analyse: Job={job_id}, Periode={period_label}")

        report = {
            "status": "started",
            "job_id": job_id,
            "period_label": period_label,
            "tender_id": tender_id,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "artifacts": [],
            "error": None,
            "logs": [],
            "steps_completed": [],
            "steps_skipped": [],
            "steps_failed": [],
            "results": {},
        }

        try:
            # === 0. Transaktionsdaten & Geldmenge beschaffen ===
            transactions = await self._fetch_transactions(tender_id, period_label)
            if money_supply_eur is None:
                money_supply_eur = await self._fetch_money_supply(period_label)

            report["logs"].append(
                {
                    "level": "INFO",
                    "message": (
                        f"Daten beschafft: {len(transactions)} TX, "
                        f"Geldmenge={money_supply_eur:,.2f} EUR"
                    ),
                }
            )

            if not transactions:
                report["status"] = "NO_DATA"
                report["logs"].append(
                    {
                        "level": "WARN",
                        "message": "Keine Transaktionen für Analyse verfügbar.",
                    }
                )
                return report

            # === 1. VelocityOfMoneyTracker (STEP 1) ===
            try:
                velocity_report = self.velocity_tracker.analyze(
                    transactions=transactions,
                    money_supply_eur=money_supply_eur,
                    tender_id=tender_id,
                    period_label=period_label,
                )
                report["results"]["velocity"] = velocity_report
                report["steps_completed"].append("velocity")

                if velocity_report.get("has_alerts"):
                    for alert in velocity_report.get("alerts", []):
                        report["logs"].append(
                            {
                                "level": "WARN",
                                "step": "velocity",
                                "message": alert["message"],
                            }
                        )
            except Exception as e:
                logger.error(f"Velocity-Tracker fehlgeschlagen: {e}")
                report["steps_failed"].append("velocity")
                report["logs"].append(
                    {"level": "ERROR", "step": "velocity", "message": str(e)}
                )

            # === 2. RealTimeInflationOracle (STEP 2) ===
            try:
                vel_metrics = report.get("results", {}).get("velocity", {}).get("velocity_metrics", {})
                v_tx = vel_metrics.get("velocity_tx", 1.0)

                # GAEB-Positionen beschaffen (Mock für jetzt)
                gaeb_positions = self._fetch_gaeb_positions(tender_id)

                inflation_report = self.inflation_oracle.measure_inflation(
                    gaeb_positions=gaeb_positions,
                    money_supply_eur=money_supply_eur,
                    velocity_tx=v_tx,
                    period_label=period_label,
                    tender_id=tender_id,
                )
                report["results"]["inflation"] = inflation_report
                report["steps_completed"].append("inflation")

                if inflation_report.get("has_alerts"):
                    for alert in inflation_report.get("alerts", []):
                        report["logs"].append(
                            {
                                "level": "WARN",
                                "step": "inflation",
                                "message": alert["message"],
                            }
                        )
            except Exception as e:
                logger.error(f"InflationOracle fehlgeschlagen: {e}")
                report["steps_failed"].append("inflation")
                report["logs"].append(
                    {"level": "ERROR", "step": "inflation", "message": str(e)}
                )

            # === 3. SupplyChainMultiplierCalc (STEP 3) ===
            try:
                # Initialausgabe: Geldmenge × Velocity / Transaktionsanzahl (Heuristik)
                total_tx_volume = sum(
                    float(tx.get("amount_eur", 0.0)) for tx in transactions
                )
                initial_spending = money_supply_eur  # Näherung: Geldmenge = initiale Ausgabe

                multiplier_report = self.multiplier_calc.calculate_multiplier(
                    transactions=transactions,
                    initial_spending_eur=initial_spending,
                    tender_id=tender_id,
                    period_label=period_label,
                )
                report["results"]["supply_chain"] = multiplier_report
                report["steps_completed"].append("supply_chain")

                if multiplier_report.get("has_alerts"):
                    for alert in multiplier_report.get("alerts", []):
                        report["logs"].append(
                            {
                                "level": "WARN",
                                "step": "supply_chain",
                                "message": alert["message"],
                            }
                        )
            except Exception as e:
                logger.error(f"SupplyChainMultiplier fehlgeschlagen: {e}")
                report["steps_failed"].append("supply_chain")
                report["logs"].append(
                    {"level": "ERROR", "step": "supply_chain", "message": str(e)}
                )

            # === 4. ProgrammableStimulusEngine (STEP 4) ===
            try:
                vel_data = report.get("results", {}).get("velocity", {})
                inf_data = report.get("results", {}).get("inflation", {})
                mul_data = report.get("results", {}).get("supply_chain", {})

                stimulus_decision = self.stimulus_engine.decide_stimulus(
                    velocity_report=vel_data,
                    inflation_report=inf_data,
                    multiplier_report=mul_data,
                    money_supply_eur=money_supply_eur,
                    tender_id=tender_id,
                    period_label=period_label,
                )
                report["results"]["stimulus"] = stimulus_decision
                report["steps_completed"].append("stimulus")

                if stimulus_decision.get("has_alerts"):
                    for alert in stimulus_decision.get("alerts", []):
                        report["logs"].append(
                            {
                                "level": "WARN",
                                "step": "stimulus",
                                "message": alert["message"],
                            }
                        )
            except Exception as e:
                logger.error(f"StimulusEngine fehlgeschlagen: {e}")
                report["steps_failed"].append("stimulus")
                report["logs"].append(
                    {"level": "ERROR", "step": "stimulus", "message": str(e)}
                )

            # === 5. RealTimeTaxSplitter (STEP 5) ===
            try:
                tax_report = self.tax_splitter.split_taxes(
                    transactions=transactions,
                    tender_id=tender_id,
                    period_label=period_label,
                )
                report["results"]["tax_split"] = tax_report
                report["steps_completed"].append("tax_splitter")
            except Exception as e:
                logger.error(f"TaxSplitter fehlgeschlagen: {e}")
                report["steps_failed"].append("tax_splitter")
                report["logs"].append(
                    {"level": "ERROR", "step": "tax_splitter", "message": str(e)}
                )

            # === 6. CapitalEfficiencyAnalyzer (STEP 6) ===
            try:
                projects = self._generate_mock_projects(5)
                efficiency_report = self.efficiency_analyzer.analyze_efficiency(
                    projects=projects,
                    transactions=transactions,
                    period_label=period_label,
                )
                report["results"]["capital_efficiency"] = efficiency_report
                report["steps_completed"].append("capital_efficiency")
            except Exception as e:
                logger.error(f"CapitalEfficiencyAnalyzer fehlgeschlagen: {e}")
                report["steps_failed"].append("capital_efficiency")

            # === 7. SystemicRiskAndCartelMonitor (STEP 7) ===
            try:
                cartel_report = self.cartel_monitor.analyze_network(
                    transactions=transactions,
                    tender_id=tender_id,
                    period_label=period_label,
                )
                report["results"]["cartel_monitor"] = cartel_report
                report["steps_completed"].append("cartel_monitor")
            except Exception as e:
                logger.error(f"CartelMonitor fehlgeschlagen: {e}")
                report["steps_failed"].append("cartel_monitor")

            # === 8. CentralBankLedgerTwin (STEP 8) ===
            try:
                ledger_report = self.cb_ledger_twin.generate_balance_sheet(
                    money_supply_eur=money_supply_eur,
                    velocity_report=report.get("results", {}).get("velocity", {}),
                    inflation_report=report.get("results", {}).get("inflation", {}),
                    stimulus_report=report.get("results", {}).get("stimulus", {}),
                    tax_report=report.get("results", {}).get("tax_split", {}),
                    period_label=period_label,
                )
                report["results"]["cb_ledger"] = ledger_report
                report["steps_completed"].append("cb_ledger")
            except Exception as e:
                logger.error(f"CBLedgerTwin fehlgeschlagen: {e}")
                report["steps_failed"].append("cb_ledger")

            # Alle implementierten Steps erledigt
            for step in self.PIPELINE_STEPS:
                if step["id"] in ("velocity", "inflation", "supply_chain", "stimulus", "tax_splitter", "capital_efficiency", "cartel_monitor", "cb_ledger"):
                    continue  # Bereits ausgeführt
                if not step["implemented"]:
                    report["steps_skipped"].append(step["id"])
                    continue

            # === Aggregation: MacroEconomyHealthIndex (MEHI) ===
            report["macro_economy_health_index"] = self._calculate_mehi(report)

            # === Abschluss ===
            report["status"] = "completed"
            report["artifacts"].append(
                {
                    "type": "macro_report",
                    "format": "json",
                    "path": self._save_report(report, job_id),
                    "metadata": {
                        "period": period_label,
                        "steps_completed": len(report["steps_completed"]),
                        "mehi": report["macro_economy_health_index"]["score"],
                    },
                }
            )

            self._last_report = report
            self._report_history.append(
                {
                    "job_id": job_id,
                    "period": period_label,
                    "mehi": report["macro_economy_health_index"]["score"],
                    "timestamp": report["timestamp"],
                }
            )

            logger.info(
                f"Makro-Analyse abgeschlossen: Job={job_id}, "
                f"MEHI={report['macro_economy_health_index']['score']:.2f}"
            )
            return report

        except Exception as e:
            logger.error(f"Makro-Analyse fatal fehlgeschlagen: {e}", exc_info=True)
            report["status"] = "failed"
            report["error"] = str(e)
            report["logs"].append(
                {"level": "ERROR", "message": f"Fataler Fehler: {e}"}
            )
            return report

    def get_last_report(self) -> Optional[Dict[str, Any]]:
        """Gibt den letzten MacroEconomyReport zurück."""
        return self._last_report

    def get_report_history(self) -> List[Dict[str, Any]]:
        """Gibt die Report-Historie zurück."""
        return self._report_history

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Gibt den Implementierungsstatus aller Pipeline-Steps zurück."""
        return {
            "total_steps": len(self.PIPELINE_STEPS),
            "implemented": sum(1 for s in self.PIPELINE_STEPS if s["implemented"]),
            "pending": sum(1 for s in self.PIPELINE_STEPS if not s["implemented"]),
            "steps": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "agent_index": s["agent_index"],
                    "implemented": s["implemented"],
                }
                for s in self.PIPELINE_STEPS
            ],
        }

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def _fetch_transactions(
        self, tender_id: Optional[str], period_label: str
    ) -> List[Dict[str, Any]]:
        """
        Beschafft Transaktionen aus dem Ledger.
        Fällt auf Mock-Daten zurück, wenn kein Ledger verfügbar.
        """
        if self.ledger and hasattr(self.ledger, "get_all_transactions"):
            try:
                return await self.ledger.get_all_transactions(tender_id)
            except Exception as e:
                logger.warning(f"Ledger-Abfrage fehlgeschlagen: {e}")

        # Fallback: Mock-Daten für Entwicklung
        logger.info("Verwende Mock-Transaktionen (kein Ledger verfügbar).")
        return self._generate_mock_transactions(200)

    async def _fetch_money_supply(self, period_label: str) -> float:
        """
        Beschafft die Geldmenge (M1/M2-Äquivalent) vom Treasury.
        """
        if self.treasury and hasattr(self.treasury, "get_money_supply"):
            try:
                return float(await self.treasury.get_money_supply(period_label))
            except Exception as e:
                logger.warning(f"Treasury-Abfrage fehlgeschlagen: {e}")

        # Fallback: Schätzung basierend auf Transaktionsvolumen
        return 5_000_000.0  # 5 Mio EUR Default

    def _fetch_gaeb_positions(
        self, tender_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Beschafft GAEB-Positionen für den InflationOracle.
        In Produktion: aus GAEB DA XML 3.3 Archiv.
        """
        # TODO: In Produktion aus archive_b2g/ oder per GAEB-Reader-Agent laden
        # Für jetzt: Mock-Daten mit realistischem Preisverlauf
        return self._generate_mock_gaeb_positions(30)

    def _generate_mock_gaeb_positions(self, count: int = 30) -> List[Dict[str, Any]]:
        """Generiert synthetische GAEB-Positionen für den InflationOracle."""
        import random

        rng = random.Random(42)
        sectors = ["betonbau", "stahlbau", "erdarbeiten", "elektro", "kanalbau"]
        units_list = ["m³", "m²", "Stk", "kg", "m", "Std"]
        base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

        positions = []
        for i in range(count):
            sector = rng.choice(sectors)
            base_price = rng.uniform(50, 5000)
            months_since_base = i % 24
            inflation_factor = 1.0 + (0.04 * months_since_base / 12)
            current_price = base_price * inflation_factor * rng.uniform(0.95, 1.05)

            positions.append(
                {
                    "position_id": f"POS_{i // 3:03d}",
                    "unit_price_eur": round(current_price, 2),
                    "quantity": round(rng.uniform(10, 1000), 2),
                    "unit": rng.choice(units_list),
                    "sector": sector,
                    "description": f"{sector} Arbeiten Projekt {i % 5}",
                    "timestamp": (base_date + timedelta(days=30 * (i % 24))).isoformat(),
                }
            )
        return positions

    def _generate_mock_projects(self, count: int = 5) -> List[Dict[str, Any]]:
        """Generiert synthetische Projektdaten für den CapitalEfficiencyAnalyzer."""
        import random
        rng = random.Random(42)
        projects = []
        for i in range(count):
            budget = round(rng.uniform(500000, 5_000_000), 2)
            projects.append({
                "project_id": f"PRJ_{i:03d}",
                "budget_eur": budget,
                "revenue_eur": budget * rng.uniform(0.85, 1.05),
                "operating_expenses_eur": budget * rng.uniform(0.60, 0.80),
                "fixed_assets_eur": budget * rng.uniform(0.10, 0.20),
                "working_capital_eur": budget * rng.uniform(0.05, 0.15),
                "current_assets_eur": budget * rng.uniform(0.25, 0.45),
                "current_liabilities_eur": budget * rng.uniform(0.15, 0.35),
                "total_assets_eur": budget * rng.uniform(0.50, 0.70),
                "start_date": "2025-01-15",
                "end_date": "2026-08-01",
                "public_benefit_factor": rng.uniform(1.1, 1.5),
            })
        return projects

    def _calculate_mehi(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Berechnet den MacroEconomyHealthIndex (MEHI) aus allen verfügbaren
        Subagenten-Ergebnissen.

        MEHI = gewichteter Score aus:
          - Velocity-Stabilität (25%)
          - Steuer-Compliance (15%) [noch nicht implementiert]
          - Kapital-Effizienz (15%) [noch nicht implementiert]
          - Lieferketten-Gesundheit (15%) [noch nicht implementiert]
          - Preisstabilität (15%) [noch nicht implementiert]
          - Systemrisiko (15%) [noch nicht implementiert]

        Returns:
            {"score": 0.0-1.0, "grade": "A"-"F", "components": {...}}
        """
        components = {}
        weights = {
            "velocity": 0.20,
            "price_stability": 0.15,
            "supply_chain": 0.15,
            "fiscal_policy": 0.15,
            "tax_compliance": 0.10,
            "capital_efficiency": 0.10,
            "systemic_risk": 0.15,
        }

        # Velocity-Komponente (25%)
        vel = report.get("results", {}).get("velocity", {})
        if vel.get("status") == "ANALYSIS_COMPLETE":
            vel_metrics = vel.get("velocity_metrics", {})
            vel_score = 1.0

            # Abzüge für Alerts
            alert_count = len(vel.get("alerts", []))
            vel_score -= min(0.5, alert_count * 0.1)

            # Abzüge für extreme Werte
            v_tx = vel_metrics.get("velocity_tx", 1.0)
            if v_tx < 0.3:
                vel_score -= 0.3  # Deflationsdruck
            elif v_tx > 8.0:
                vel_score -= 0.3  # Hyperinflation

            # Abzüge für Dispersion
            dispersion = vel_metrics.get("sector_dispersion_cv", 0.0)
            if dispersion > 0.6:
                vel_score -= 0.2

            components["velocity"] = {
                "score": round(max(0.0, min(1.0, vel_score)), 2),
                "weight": weights["velocity"],
                "source": "VelocityOfMoneyTracker",
            }
        else:
            components["velocity"] = {
                "score": 0.5,  # Neutral bei fehlenden Daten
                "weight": weights["velocity"],
                "source": "N/A",
            }

        # Preisstabilitäts-Komponente (15%) — RealTimeInflationOracle
        inf = report.get("results", {}).get("inflation", {})
        if inf.get("status") == "ANALYSIS_COMPLETE":
            inf_score = 1.0
            composite_inf = abs(inf.get("composite_inflation_pct", 0.0))

            # Abzüge basierend auf Inflationshöhe
            if composite_inf > 10:
                inf_score -= 0.5  # Hyperinflation
            elif composite_inf > 5:
                inf_score -= 0.25  # Erhöhte Inflation
            elif composite_inf > 2:
                inf_score -= 0.05  # Leicht erhöht
            # 0-2%: optimal, keine Abzüge

            # Abzüge für Deflation
            if inf.get("composite_inflation_pct", 0) < -1:
                inf_score -= 0.3

            # Abzüge für Alerts
            alert_count = len(inf.get("alerts", []))
            inf_score -= min(0.3, alert_count * 0.1)

            components["price_stability"] = {
                "score": round(max(0.0, min(1.0, inf_score)), 2),
                "weight": weights["price_stability"],
                "source": "RealTimeInflationOracle",
            }
        else:
            components["price_stability"] = {
                "score": 0.5,
                "weight": weights["price_stability"],
                "source": "N/A",
            }

        # Supply-Chain-Komponente (15%) — SupplyChainMultiplierCalc
        sc = report.get("results", {}).get("supply_chain", {})
        if sc.get("status") == "ANALYSIS_COMPLETE":
            sc_score = 1.0
            mm = sc.get("multiplier_metrics", {})
            composite_k = mm.get("composite_multiplier", 1.5)

            # Abzüge basierend auf Multiplikator
            if composite_k < 0.8:
                sc_score -= 0.5  # Kontraktion
            elif composite_k < 1.0:
                sc_score -= 0.25  # Schwach
            elif composite_k > 3.0:
                sc_score -= 0.1  # Ungewöhnlich hoch (Datenqualität?)

            # Abzüge für geringe regionale Bindung
            retention = sc.get("regional_multiplier", {}).get("local_retention_rate", 0.5)
            if retention < 0.35:
                sc_score -= 0.2

            # Abzüge für Alerts
            alert_count = len(sc.get("alerts", []))
            sc_score -= min(0.3, alert_count * 0.1)

            components["supply_chain"] = {
                "score": round(max(0.0, min(1.0, sc_score)), 2),
                "weight": weights["supply_chain"],
                "source": "SupplyChainMultiplierCalc",
            }
        else:
            components["supply_chain"] = {
                "score": 0.5,
                "weight": weights["supply_chain"],
                "source": "N/A",
            }

        # Fiskalpolitik-Komponente (15%) — ProgrammableStimulusEngine
        stim = report.get("results", {}).get("stimulus", {})
        if stim.get("status") == "DECISION_COMPLETE":
            stim_score = 1.0
            decision = stim.get("decision", {})
            mode = decision.get("mode", "NEUTRAL")

            # Abzüge für unerwünschte Modi
            if mode == "EMERGENCY":
                stim_score -= 0.3  # Notfall — System unter Stress
            elif mode == "CONTRACTIONARY":
                stim_score -= 0.15  # Abschöpfung — Wirtschaft überhitzt

            # Abzüge für Risiko
            risk = stim.get("risk_assessment", {})
            if risk.get("veto_recommended"):
                stim_score -= 0.4

            # Abzüge für Alerts
            alert_count = len(stim.get("alerts", []))
            stim_score -= min(0.3, alert_count * 0.1)

            components["fiscal_policy"] = {
                "score": round(max(0.0, min(1.0, stim_score)), 2),
                "weight": weights["fiscal_policy"],
                "source": "ProgrammableStimulusEngine",
            }
        else:
            components["fiscal_policy"] = {
                "score": 0.5,
                "weight": weights["fiscal_policy"],
                "source": "N/A",
            }

        # Systemrisiko-Komponente (15%) — SystemicRiskAndCartelMonitor
        scm = report.get("results", {}).get("cartel_monitor", {})
        if scm.get("status") == "ANALYSIS_COMPLETE":
            scm_score = 1.0 - scm.get("risk_score", 0.0) * 0.8
            alert_count = len(scm.get("alerts", []))
            scm_score -= min(0.4, alert_count * 0.1)
            components["systemic_risk"] = {
                "score": round(max(0.0, min(1.0, scm_score)), 2),
                "weight": weights["systemic_risk"],
                "source": "SystemicRiskAndCartelMonitor",
            }
        else:
            components["systemic_risk"] = {
                "score": 0.5, "weight": weights["systemic_risk"], "source": "N/A",
            }

        # Weitere Komponenten (Default: 0.5 = neutral)
        for key in ["tax_compliance", "capital_efficiency"]:
            components[key] = {
                "score": 0.5, "weight": weights[key], "source": "Not yet implemented",
            }

        # Gewichteter Score
        total_score = sum(
            c["score"] * c["weight"] for c in components.values()
        )

        # Note (gleiche Skala wie CHI)
        if total_score >= 0.8:
            grade = "A"
        elif total_score >= 0.6:
            grade = "B"
        elif total_score >= 0.4:
            grade = "C"
        elif total_score >= 0.2:
            grade = "D"
        else:
            grade = "F"

        return {
            "score": round(total_score, 4),
            "grade": grade,
            "components": components,
            "interpretation": self._interpret_mehi(total_score, grade),
        }

    def _interpret_mehi(self, score: float, grade: str) -> str:
        """Liefert eine menschenlesbare Interpretation des MEHI."""
        if grade == "A":
            return "Gesunde Makroökonomie: Stabile Velocity, keine systemischen Risiken."
        elif grade == "B":
            return "Weitgehend gesund: Leichte Ungleichgewichte, beobachtbar."
        elif grade == "C":
            return "Erhöhte Aufmerksamkeit: Sektorale Verwerfungen oder Velocity-Anomalien."
        elif grade == "D":
            return "Kritisch: Mehrere Risikoindikatoren schlagen an. Eingriff empfohlen."
        else:
            return "Alarm: Systemisches Risiko. Sofortige Intervention erforderlich."

    def _save_report(self, report: Dict[str, Any], job_id: str) -> str:
        """
        Speichert den MacroEconomyReport als JSON im Tenant-Verzeichnis.

        Pfad: /data/{user_id}/macro/reports/{period_label}/{job_id}.json
        Fällt auf /tmp zurück, wenn data_root nicht schreibbar ist.
        """
        period = report.get("period_label", "unknown")
        dir_path = os.path.join(
            self.data_root, self.user_id, "macro", "reports", period
        )
        try:
            os.makedirs(dir_path, exist_ok=True)
        except OSError:
            # Fallback: /tmp für Tests/Entwicklung
            import tempfile
            dir_path = os.path.join(tempfile.gettempdir(), "agent_x_macro", self.user_id, "reports", period)
            os.makedirs(dir_path, exist_ok=True)
            logger.warning(f"data_root nicht schreibbar, verwende {dir_path}")

        filepath = os.path.join(dir_path, f"{job_id}.json")
        with open(filepath, "w") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"Report gespeichert: {filepath}")
        return filepath

    def _generate_mock_transactions(self, count: int = 200) -> List[Dict[str, Any]]:
        """Generiert synthetische Transaktionen für Entwicklung/Tests."""
        import random

        rng = random.Random(42)
        sectors = ["bau", "technik", "ausbau", "planung", "umwelt"]
        regions = ["NI", "NW", "BY", "BE", "HH"]
        types = ["payment", "payment", "payment", "deposit", "retention", "refund"]
        senders = [f"GU_{i}" for i in range(1, 6)] + [f"Sub_{i}" for i in range(1, 16)]
        receivers = [f"Sub_{i}" for i in range(1, 16)] + [f"Lieferant_{i}" for i in range(1, 11)]

        transactions = []
        for _ in range(count):
            sector = rng.choice(sectors)
            transactions.append(
                {
                    "sender": rng.choice(senders),
                    "receiver": rng.choice(receivers),
                    "amount_eur": round(rng.lognormvariate(mu=9.5, sigma=1.2), 2),
                    "timestamp": (datetime.now(timezone.utc) - timedelta(days=rng.randint(0, 30))).isoformat(),
                    "sector": sector,
                    "region_code": rng.choice(regions),
                    "category": rng.choice(types),
                    "description": f"Zahlung {sector} Projekt {rng.randint(1, 5)}",
                }
            )

        # Sicherstellen, dass Sender != Receiver
        for tx in transactions:
            if tx["sender"] == tx["receiver"]:
                tx["receiver"] = f"Other_{rng.randint(1, 50)}"

        return transactions


# ============================================================================
# SYNCHRONER WRAPPER (für nicht-async Umgebungen)
# ============================================================================
class SyncMacroEconomyOrchestrator(MacroEconomyOrchestrator):
    """
    Synchroner Wrapper für Umgebungen ohne asyncio (Tests, CLI).
    Überschreibt analyze_economy mit synchroner Ausführung.
    """

    def analyze_economy(
        self,
        tender_id: Optional[str] = None,
        period_label: Optional[str] = None,
        money_supply_eur: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Synchrone Version von analyze_economy."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Läuft bereits in einem Event Loop — verwende run_coroutine_threadsafe
            # oder falle auf direkten sync-Aufruf zurück
            logger.warning(
                "SyncOrchestrator in laufendem Event Loop — "
                "verwende sync Fallback-Pfad."
            )

        # Direkter synchroner Pfad (umgeht async)
        job_id = str(uuid.uuid4())
        period_label = period_label or datetime.now(timezone.utc).strftime("%Y-%m")

        report = {
            "status": "started",
            "job_id": job_id,
            "period_label": period_label,
            "tender_id": tender_id,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "artifacts": [],
            "error": None,
            "logs": [],
            "steps_completed": [],
            "steps_skipped": [],
            "steps_failed": [],
            "results": {},
        }

        try:
            # Mock-Transaktionen
            transactions = self._generate_mock_transactions(200)
            if money_supply_eur is None:
                money_supply_eur = 5_000_000.0

            # Velocity-Analyse
            velocity_report = self.velocity_tracker.analyze(
                transactions=transactions,
                money_supply_eur=money_supply_eur,
                tender_id=tender_id,
                period_label=period_label,
            )
            report["results"]["velocity"] = velocity_report
            report["steps_completed"].append("velocity")

            # Inflation-Analyse
            vel_metrics = velocity_report.get("velocity_metrics", {})
            v_tx = vel_metrics.get("velocity_tx", 1.0)
            gaeb_positions = self._fetch_gaeb_positions(tender_id)

            inflation_report = self.inflation_oracle.measure_inflation(
                gaeb_positions=gaeb_positions,
                money_supply_eur=money_supply_eur,
                velocity_tx=v_tx,
                period_label=period_label,
                tender_id=tender_id,
            )
            report["results"]["inflation"] = inflation_report
            report["steps_completed"].append("inflation")

            # Supply-Chain-Multiplikator
            multiplier_report = self.multiplier_calc.calculate_multiplier(
                transactions=transactions,
                initial_spending_eur=money_supply_eur,
                tender_id=tender_id,
                period_label=period_label,
            )
            report["results"]["supply_chain"] = multiplier_report
            report["steps_completed"].append("supply_chain")

            # Stimulus-Entscheidung
            stimulus_decision = self.stimulus_engine.decide_stimulus(
                velocity_report=velocity_report,
                inflation_report=inflation_report,
                multiplier_report=multiplier_report,
                money_supply_eur=money_supply_eur,
                tender_id=tender_id,
                period_label=period_label,
            )
            report["results"]["stimulus"] = stimulus_decision
            report["steps_completed"].append("stimulus")

            # Steuerzerlegung
            tax_report = self.tax_splitter.split_taxes(
                transactions=transactions,
                tender_id=tender_id,
                period_label=period_label,
            )
            report["results"]["tax_split"] = tax_report
            report["steps_completed"].append("tax_splitter")

            # Kapitaleffizienz
            projects = self._generate_mock_projects(5)
            efficiency_report = self.efficiency_analyzer.analyze_efficiency(
                projects=projects,
                transactions=transactions,
                period_label=period_label,
            )
            report["results"]["capital_efficiency"] = efficiency_report
            report["steps_completed"].append("capital_efficiency")

            # Kartell-Monitor
            cartel_report = self.cartel_monitor.analyze_network(
                transactions=transactions,
                tender_id=tender_id,
                period_label=period_label,
            )
            report["results"]["cartel_monitor"] = cartel_report
            report["steps_completed"].append("cartel_monitor")

            # Zentralbank-Bilanz
            ledger_report = self.cb_ledger_twin.generate_balance_sheet(
                money_supply_eur=money_supply_eur,
                velocity_report=velocity_report,
                inflation_report=inflation_report,
                stimulus_report=stimulus_decision,
                tax_report=tax_report,
                period_label=period_label,
            )
            report["results"]["cb_ledger"] = ledger_report
            report["steps_completed"].append("cb_ledger")

            # Alle implementierten Steps erledigt — keine Skipped mehr
            for step in self.PIPELINE_STEPS:
                if not step["implemented"]:
                    report["steps_skipped"].append(step["id"])

            # MEHI berechnen
            report["macro_economy_health_index"] = self._calculate_mehi(report)

            report["status"] = "completed"
            report["artifacts"].append(
                {
                    "type": "macro_report",
                    "format": "json",
                    "path": self._save_report(report, job_id),
                    "metadata": {
                        "period": period_label,
                        "steps_completed": len(report["steps_completed"]),
                        "mehi": report["macro_economy_health_index"]["score"],
                    },
                }
            )

            self._last_report = report
            self._report_history.append(
                {
                    "job_id": job_id,
                    "period": period_label,
                    "mehi": report["macro_economy_health_index"]["score"],
                    "timestamp": report["timestamp"],
                }
            )

            return report

        except Exception as e:
            logger.error(f"Sync-Analyse fehlgeschlagen: {e}", exc_info=True)
            report["status"] = "failed"
            report["error"] = str(e)
            return report


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("MacroEconomyOrchestrator — Smoke Test")
    print("=" * 60)

    orch = SyncMacroEconomyOrchestrator(user_id="test_tenant")

    # Pipeline-Status prüfen
    status = orch.get_pipeline_status()
    print(f"\nPipeline-Status: {status['implemented']}/{status['total_steps']} implementiert")
    for s in status["steps"]:
        icon = "✅" if s["implemented"] else "⏳"
        print(f"  {icon} {s['name']} (Agent 17.{s['agent_index']})")

    # Analyse durchführen
    print("\nFühre Makro-Analyse durch...")
    report = orch.analyze_economy(tender_id="TED-2026-0815-KLAERANLAGE-NORD")

    print(f"\nStatus: {report['status']}")
    print(f"Periode: {report['period_label']}")
    print(f"Steps completed: {report['steps_completed']}")
    print(f"Steps skipped: {report['steps_skipped']}")

    mehi = report.get("macro_economy_health_index", {})
    print(f"\nMEHI Score: {mehi.get('score', 'N/A')}")
    print(f"MEHI Grade: {mehi.get('grade', 'N/A')}")
    print(f"Interpretation: {mehi.get('interpretation', 'N/A')}")

    # Velocity-Details
    vel = report.get("results", {}).get("velocity", {})
    if vel.get("velocity_metrics"):
        vm = vel["velocity_metrics"]
        print(f"\nVelocity TX: {vm.get('velocity_tx')}")
        print(f"Velocity Income: {vm.get('velocity_income')}")
        print(f"Sektor-Dispersion: {vm.get('sector_dispersion_cv')}")
        print(f"Alerts: {len(vel.get('alerts', []))}")

    # Report-Historie
    history = orch.get_report_history()
    print(f"\nReport-Historie: {len(history)} Einträge")

    print("\n✅ Smoke Test abgeschlossen.")
