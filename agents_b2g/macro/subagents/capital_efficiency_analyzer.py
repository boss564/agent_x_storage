# agents_b2g/macro/subagents/capital_efficiency_analyzer.py
"""
Agent 17.5 — CapitalEfficiencyAnalyzer

Misst die Kapitaleffizienz im Agent-X-B2G-Ökosystem. Bewertet, wie
effizient öffentliche Gelder in Bauprojekten eingesetzt werden.

Theoretische Grundlagen:
  1. ROIC (Return on Invested Capital):
     ROIC = NOPAT / Invested Capital
     NOPAT = EBIT × (1 − tax_rate)

  2. Working Capital Ratio:
     WCR = Current Assets / Current Liabilities
     → Liquiditätsindikator für Bauprojekte

  3. Kapitalbindungsdauer:
     Durchschnittliche Dauer zwischen Auszahlung und Fertigstellung
     → Misst, wie lange öffentliche Gelder gebunden sind

  4. Cash Conversion Cycle (CCC):
     CCC = DIO + DSO − DPO
     DIO = Days Inventory Outstanding
     DSO = Days Sales Outstanding (Debitorenlaufzeit)
     DPO = Days Payables Outstanding (Kreditorenlaufzeit)

  5. Kapitalumschlag:
     Asset Turnover = Revenue / Total Assets
     → Wie viel Umsatz generiert 1€ eingesetztes Kapital?

  6. Öffentliche Kapitaleffizienz (Public ROIC):
     PROIC = (Projektnutzen − Projektkosten) / Eingesetztes Kapital
     → Gesamtwirtschaftliche Rendite öffentlicher Investitionen

Features:
  - ROIC pro Projekt und Portfolio
  - Cash Conversion Cycle (Debitoren-/Kreditorenlaufzeiten)
  - Kapitalbindungsdauer und -kosten
  - Working-Capital-Quote mit Frühwarnung
  - Asset Turnover nach Sektor/Region
  - Öffentlicher ROIC (Kosten-Nutzen-Verhältnis)
  - Benchmarking gegen ifo/DIW-Bauwirtschaftsdaten
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from statistics import mean, stdev, median

logger = logging.getLogger("CapitalEfficiencyAnalyzer")


class CapitalEfficiencyAnalyzerSubagent:
    """
    Subagent 17.5: Kapitaleffizienz-Analyse für öffentliche Bauprojekte.
    """

    # Benchmarks für die Bauwirtschaft (Quelle: ifo, Deutsche Bundesbank, DIW)
    BENCHMARKS = {
        "roic_median": 0.08,           # 8% ROIC (Bau-Hauptgewerbe)
        "roic_top_quartile": 0.15,     # 15% ROIC (Top 25%)
        "working_capital_ratio": 1.3,   # WCR > 1.3 = gesund
        "cash_conversion_cycle_days": 45,  # 45 Tage CCC (Median Bau)
        "asset_turnover": 1.8,         # 1.8× Asset Turnover (Bau)
        "kapitalbindung_months": 18,    # 18 Monate Ø Kapitalbindung
        "public_roic_minimum": 0.05,    # 5% Mindest-PROIC (Wirtschaftlichkeit)
    }

    def __init__(
        self,
        cost_of_capital: float = 0.04,      # 4% Kapitalkostensatz (10J Bundesanleihe)
        tax_rate: float = 0.30,              # 30% effektiver Steuersatz
        alert_wcr_low: float = 0.8,          # WCR < 0.8 → Liquiditätsalarm
        alert_ccc_high: float = 90,          # CCC > 90 Tage → Ineffizienz
        alert_roic_low: float = 0.0,         # ROIC < 0 → Wertvernichtung
    ):
        """
        Args:
            cost_of_capital: Kapitalkostensatz (WACC-Proxy)
            tax_rate: Effektiver Unternehmenssteuersatz
            alert_wcr_low: WCR-Schwellwert für Liquiditätsalarm
            alert_ccc_high: CCC-Schwellwert für Ineffizienz-Alarm
            alert_roic_low: ROIC-Schwellwert für Wertvernichtung
        """
        self.cost_of_capital = cost_of_capital
        self.tax_rate = tax_rate
        self.alert_wcr_low = alert_wcr_low
        self.alert_ccc_high = alert_ccc_high
        self.alert_roic_low = alert_roic_low

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def analyze_efficiency(
        self,
        projects: List[Dict[str, Any]],
        transactions: List[Dict[str, Any]],
        period_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Hauptmethode: Analysiert die Kapitaleffizienz aller Projekte.

        Args:
            projects: Projekt-Daten (budget, costs, revenue, timeline, assets, liabilities)
            transactions: Zugehörige Transaktionsdaten
            period_label: Perioden-Label

        Returns:
            Capital-Efficiency-Report
        """
        period_label = period_label or datetime.now(timezone.utc).strftime("%Y-%m")
        job_id = f"capeff_{period_label}"

        logger.info(f"Kapitaleffizienz-Analyse für {len(projects)} Projekte")

        if not projects:
            return {
                "status": "NO_DATA",
                "job_id": job_id,
                "artifacts": [],
                "error": None,
                "logs": [{"level": "WARN", "message": "Keine Projektdaten."}],
            }

        try:
            # === 1. ROIC pro Projekt ===
            roic_analysis = self._calculate_roic(projects)

            # === 2. Cash Conversion Cycle ===
            ccc_analysis = self._calculate_ccc(projects, transactions)

            # === 3. Working Capital ===
            wc_analysis = self._calculate_working_capital(projects)

            # === 4. Kapitalbindung ===
            kapitalbindung = self._calculate_kapitalbindung(projects)

            # === 5. Asset Turnover ===
            turnover = self._calculate_asset_turnover(projects)

            # === 6. Public ROIC ===
            public_roic = self._calculate_public_roic(projects)

            # === 7. Portfolio-Aggregation ===
            portfolio = self._aggregate_portfolio(
                roic_analysis, ccc_analysis, wc_analysis, turnover
            )

            # === 8. Benchmarking ===
            benchmarks = self._benchmark_efficiency(portfolio)

            # === 9. Alerts ===
            alerts = self._generate_alerts(
                portfolio, wc_analysis, ccc_analysis, roic_analysis
            )

            report = {
                "status": "ANALYSIS_COMPLETE",
                "job_id": job_id,
                "period_label": period_label,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
                "artifacts": [
                    {
                        "type": "capital_efficiency_report",
                        "format": "json",
                        "metadata": {
                            "period": period_label,
                            "portfolio_roic_pct": round(portfolio["roic_pct"], 2),
                            "project_count": len(projects),
                        },
                    }
                ],
                "error": None,
                "logs": [
                    {
                        "level": "INFO",
                        "message": (
                            f"Kapitaleffizienz: ROIC={portfolio['roic_pct']:.1f}%, "
                            f"CCC={portfolio['ccc_days']:.0f}d, "
                            f"WCR={portfolio['wcr']:.2f}, "
                            f"AssetTurnover={portfolio['asset_turnover']:.2f}×"
                        ),
                    }
                ],
                "roic_analysis": roic_analysis,
                "cash_conversion_cycle": ccc_analysis,
                "working_capital": wc_analysis,
                "kapitalbindung": kapitalbindung,
                "asset_turnover": turnover,
                "public_roic": public_roic,
                "portfolio_summary": portfolio,
                "benchmark_comparison": benchmarks,
                "alerts": alerts,
                "has_alerts": len(alerts) > 0,
            }

            logger.info(f"Kapitaleffizienz-Analyse: ROIC={portfolio['roic_pct']:.1f}%")
            return report

        except Exception as e:
            logger.error(f"Kapitaleffizienz-Analyse fehlgeschlagen: {e}", exc_info=True)
            return {
                "status": "failed",
                "job_id": job_id,
                "artifacts": [],
                "error": str(e),
                "logs": [{"level": "ERROR", "message": str(e)}],
            }

    # ========================================================================
    # ROIC CALCULATION
    # ========================================================================

    def _calculate_roic(
        self, projects: List[Dict]
    ) -> Dict[str, Any]:
        """
        ROIC = NOPAT / Invested Capital

        NOPAT = (Revenue − OpEx − D&A) × (1 − tax_rate)
        Invested Capital = Fixed Assets + Working Capital
        """
        results = []
        total_nopat = 0.0
        total_invested_capital = 0.0

        for p in projects:
            revenue = float(p.get("revenue_eur", p.get("budget_eur", 0.0)))
            opex = float(p.get("operating_expenses_eur", 0.0))
            depreciation = float(p.get("depreciation_eur", revenue * 0.05))
            fixed_assets = float(p.get("fixed_assets_eur", revenue * 0.15))
            working_capital = float(p.get("working_capital_eur", revenue * 0.10))

            ebit = revenue - opex - depreciation
            nopat = ebit * (1.0 - self.tax_rate)
            invested_capital = fixed_assets + working_capital

            roic = nopat / invested_capital if invested_capital > 0 else 0.0

            total_nopat += nopat
            total_invested_capital += invested_capital

            results.append({
                "project_id": p.get("project_id", p.get("tender_id", "UNKNOWN")),
                "revenue_eur": round(revenue, 2),
                "ebit_eur": round(ebit, 2),
                "nopat_eur": round(nopat, 2),
                "invested_capital_eur": round(invested_capital, 2),
                "roic_pct": round(roic * 100, 2),
                "value_creation": "Wertschaffung" if roic > self.cost_of_capital else "Wertvernichtung",
                "spread_pct": round((roic - self.cost_of_capital) * 100, 2),
            })

        portfolio_roic = total_nopat / total_invested_capital if total_invested_capital > 0 else 0.0

        return {
            "projects": results,
            "portfolio_roic_pct": round(portfolio_roic * 100, 2),
            "total_nopat_eur": round(total_nopat, 2),
            "total_invested_capital_eur": round(total_invested_capital, 2),
            "cost_of_capital_pct": round(self.cost_of_capital * 100, 2),
            "economic_profit_eur": round(
                total_nopat - total_invested_capital * self.cost_of_capital, 2
            ),
        }

    # ========================================================================
    # CASH CONVERSION CYCLE
    # ========================================================================

    def _calculate_ccc(
        self,
        projects: List[Dict],
        transactions: List[Dict],
    ) -> Dict[str, Any]:
        """
        CCC = DIO + DSO − DPO

        DIO = Days Inventory Outstanding = Ø Lagerdauer
        DSO = Days Sales Outstanding = Ø Debitorenlaufzeit
        DPO = Days Payables Outstanding = Ø Kreditorenlaufzeit
        """
        # Aus Transaktionen Debitoren-/Kreditorenlaufzeiten berechnen
        payment_delays = []
        receipt_delays = []

        for tx in transactions:
            created = tx.get("created_at", tx.get("timestamp", ""))
            settled = tx.get("settled_at", tx.get("settlement_date", ""))

            if created and settled:
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    settled_dt = datetime.fromisoformat(settled.replace("Z", "+00:00"))
                    delay = (settled_dt - created_dt).days

                    tx_type = tx.get("category", tx.get("type", "payment"))
                    if tx_type in ("invoice", "receivable"):
                        receipt_delays.append(delay)
                    else:
                        payment_delays.append(delay)
                except (ValueError, TypeError):
                    pass

        # DSO: Ø Debitorenlaufzeit
        dso = mean(receipt_delays) if receipt_delays else 30.0
        # DPO: Ø Kreditorenlaufzeit
        dpo = mean(payment_delays) if payment_delays else 25.0
        # DIO: Annahme Bauwirtschaft ~15 Tage Materiallager
        dio = 15.0

        ccc = dio + dso - dpo

        return {
            "dio_days": dio,
            "dso_days": round(dso, 1),
            "dpo_days": round(dpo, 1),
            "ccc_days": round(ccc, 1),
            "interpretation": self._interpret_ccc(ccc),
            "transactions_analyzed": len(payment_delays) + len(receipt_delays),
        }

    def _interpret_ccc(self, ccc: float) -> str:
        """Interpretiert den Cash Conversion Cycle."""
        if ccc < 0:
            return "NEGATIV: Lieferanten finanzieren das Projekt — optimal"
        elif ccc < 30:
            return "SEHR GUT: Kurze Kapitalbindung, effizientes Cash-Management"
        elif ccc < 60:
            return "GUT: Typisch für Bauwirtschaft mit Anzahlungen"
        elif ccc < 90:
            return "ERHÖHT: Verbesserungspotential bei Debitorenmanagement"
        else:
            return "KRITISCH: Lange Kapitalbindung — Liquiditätsrisiko"

    # ========================================================================
    # WORKING CAPITAL
    # ========================================================================

    def _calculate_working_capital(
        self, projects: List[Dict]
    ) -> Dict[str, Any]:
        """
        Working Capital = Umlaufvermögen − Kurzfristige Verbindlichkeiten
        WCR = Current Assets / Current Liabilities
        """
        results = []
        total_ca = 0.0
        total_cl = 0.0

        for p in projects:
            current_assets = float(p.get("current_assets_eur", 0.0))
            current_liabilities = float(p.get("current_liabilities_eur", 0.0))

            # Falls keine Daten: Schätzung
            budget = float(p.get("budget_eur", p.get("revenue_eur", 0.0)))
            if current_assets <= 0:
                current_assets = budget * 0.35  # 35% Umlaufvermögen
            if current_liabilities <= 0:
                current_liabilities = budget * 0.25  # 25% kurzfristige Verb.

            wcr = current_assets / current_liabilities if current_liabilities > 0 else 0.0
            net_wc = current_assets - current_liabilities

            total_ca += current_assets
            total_cl += current_liabilities

            status = "GESUND" if wcr > 1.2 else ("OK" if wcr > 0.8 else "KRITISCH")

            results.append({
                "project_id": p.get("project_id", p.get("tender_id", "UNKNOWN")),
                "current_assets_eur": round(current_assets, 2),
                "current_liabilities_eur": round(current_liabilities, 2),
                "net_working_capital_eur": round(net_wc, 2),
                "wcr": round(wcr, 2),
                "status": status,
            })

        portfolio_wcr = total_ca / total_cl if total_cl > 0 else 0.0

        return {
            "projects": results,
            "portfolio_wcr": round(portfolio_wcr, 2),
            "total_current_assets_eur": round(total_ca, 2),
            "total_current_liabilities_eur": round(total_cl, 2),
            "net_working_capital_eur": round(total_ca - total_cl, 2),
        }

    # ========================================================================
    # KAPITALBINDUNG
    # ========================================================================

    def _calculate_kapitalbindung(
        self, projects: List[Dict]
    ) -> Dict[str, Any]:
        """
        Kapitalbindungsdauer: Zeit zwischen erster Auszahlung und Fertigstellung.
        """
        results = []
        durations = []

        for p in projects:
            start = p.get("start_date", p.get("first_payment_date", ""))
            end = p.get("end_date", p.get("completion_date", ""))

            if start and end:
                try:
                    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")[:10])
                    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")[:10])
                    months = (end_dt - start_dt).days / 30.44
                    durations.append(months)
                except (ValueError, TypeError):
                    months = 18.0  # Default
            else:
                months = 18.0

            budget = float(p.get("budget_eur", p.get("revenue_eur", 0.0)))
            kapitalkosten = budget * self.cost_of_capital * (months / 12)

            results.append({
                "project_id": p.get("project_id", p.get("tender_id", "UNKNOWN")),
                "bindungsdauer_months": round(months, 1),
                "kapitalkosten_eur": round(kapitalkosten, 2),
                "budget_eur": round(budget, 2),
            })

        avg_duration = mean(durations) if durations else 18.0
        total_kapitalkosten = sum(r["kapitalkosten_eur"] for r in results)

        return {
            "projects": results,
            "average_duration_months": round(avg_duration, 1),
            "total_kapitalkosten_eur": round(total_kapitalkosten, 2),
            "benchmark_months": self.BENCHMARKS["kapitalbindung_months"],
        }

    # ========================================================================
    # ASSET TURNOVER
    # ========================================================================

    def _calculate_asset_turnover(
        self, projects: List[Dict]
    ) -> Dict[str, Any]:
        """
        Asset Turnover = Revenue / Total Assets
        """
        results = []
        total_revenue = 0.0
        total_assets = 0.0

        for p in projects:
            revenue = float(p.get("revenue_eur", p.get("budget_eur", 0.0)))
            assets = float(p.get("total_assets_eur", revenue * 0.6))

            turnover = revenue / assets if assets > 0 else 0.0
            total_revenue += revenue
            total_assets += assets

            results.append({
                "project_id": p.get("project_id", p.get("tender_id", "UNKNOWN")),
                "revenue_eur": round(revenue, 2),
                "total_assets_eur": round(assets, 2),
                "asset_turnover": round(turnover, 2),
            })

        portfolio_turnover = total_revenue / total_assets if total_assets > 0 else 0.0

        return {
            "projects": results,
            "portfolio_asset_turnover": round(portfolio_turnover, 2),
            "total_revenue_eur": round(total_revenue, 2),
            "total_assets_eur": round(total_assets, 2),
        }

    # ========================================================================
    # PUBLIC ROIC
    # ========================================================================

    def _calculate_public_roic(
        self, projects: List[Dict]
    ) -> Dict[str, Any]:
        """
        Public ROIC = (Gesamtwirtschaftlicher Nutzen − Kosten) / Kapitaleinsatz
        """
        results = []
        total_benefit = 0.0
        total_cost = 0.0
        total_capital = 0.0

        for p in projects:
            budget = float(p.get("budget_eur", p.get("revenue_eur", 0.0)))
            # Öffentlicher Nutzen: Budget × Nutzen-Faktor (je nach Projekttyp)
            benefit_factor = float(p.get("public_benefit_factor", 1.3))
            public_benefit = budget * benefit_factor
            public_cost = budget * 1.05  # 5% Overhead
            capital = float(p.get("total_assets_eur", budget * 0.6))

            proic = (public_benefit - public_cost) / capital if capital > 0 else 0.0

            total_benefit += public_benefit
            total_cost += public_cost
            total_capital += capital

            results.append({
                "project_id": p.get("project_id", p.get("tender_id", "UNKNOWN")),
                "budget_eur": round(budget, 2),
                "public_benefit_eur": round(public_benefit, 2),
                "public_cost_eur": round(public_cost, 2),
                "capital_eur": round(capital, 2),
                "public_roic_pct": round(proic * 100, 2),
                "is_economic": proic > self.BENCHMARKS["public_roic_minimum"],
            })

        portfolio_proic = (
            (total_benefit - total_cost) / total_capital if total_capital > 0 else 0.0
        )

        return {
            "projects": results,
            "portfolio_public_roic_pct": round(portfolio_proic * 100, 2),
            "total_public_benefit_eur": round(total_benefit, 2),
            "total_public_cost_eur": round(total_cost, 2),
            "net_public_value_eur": round(total_benefit - total_cost, 2),
        }

    # ========================================================================
    # PORTFOLIO AGGREGATION
    # ========================================================================

    def _aggregate_portfolio(
        self,
        roic: Dict,
        ccc: Dict,
        wc: Dict,
        turnover: Dict,
    ) -> Dict[str, Any]:
        """Aggregiert alle Metriken auf Portfolio-Ebene."""
        return {
            "project_count": len(roic.get("projects", [])),
            "roic_pct": roic.get("portfolio_roic_pct", 0.0),
            "ccc_days": ccc.get("ccc_days", 0.0),
            "wcr": wc.get("portfolio_wcr", 0.0),
            "asset_turnover": turnover.get("portfolio_asset_turnover", 0.0),
            "economic_profit_eur": roic.get("economic_profit_eur", 0.0),
            "net_working_capital_eur": wc.get("net_working_capital_eur", 0.0),
        }

    # ========================================================================
    # BENCHMARKING
    # ========================================================================

    def _benchmark_efficiency(self, portfolio: Dict) -> Dict[str, Any]:
        """Vergleicht Portfolio-Metriken mit Bauwirtschafts-Benchmarks."""
        comparisons = {}

        # ROIC
        b_roic = self.BENCHMARKS["roic_median"]
        p_roic = portfolio["roic_pct"] / 100
        comparisons["roic"] = {
            "portfolio": round(p_roic * 100, 1),
            "benchmark": round(b_roic * 100, 1),
            "gap_pct": round((p_roic - b_roic) * 100, 1),
            "rating": "ÜBER" if p_roic > b_roic else "UNTER",
        }

        # CCC
        comparisons["ccc"] = {
            "portfolio_days": portfolio["ccc_days"],
            "benchmark_days": self.BENCHMARKS["cash_conversion_cycle_days"],
            "gap_days": round(portfolio["ccc_days"] - self.BENCHMARKS["cash_conversion_cycle_days"], 1),
            "rating": "GUT" if portfolio["ccc_days"] < self.BENCHMARKS["cash_conversion_cycle_days"] else "SCHLECHT",
        }

        # WCR
        comparisons["wcr"] = {
            "portfolio": portfolio["wcr"],
            "benchmark": self.BENCHMARKS["working_capital_ratio"],
            "rating": "GESUND" if portfolio["wcr"] > self.BENCHMARKS["working_capital_ratio"] else "RISIKO",
        }

        # Asset Turnover
        comparisons["turnover"] = {
            "portfolio": portfolio["asset_turnover"],
            "benchmark": self.BENCHMARKS["asset_turnover"],
            "rating": "EFFIZIENT" if portfolio["asset_turnover"] > self.BENCHMARKS["asset_turnover"] else "INEFFIZIENT",
        }

        return comparisons

    # ========================================================================
    # ALERTS
    # ========================================================================

    def _generate_alerts(
        self,
        portfolio: Dict,
        wc: Dict,
        ccc: Dict,
        roic: Dict,
    ) -> List[Dict[str, Any]]:
        """Generiert Kapitaleffizienz-Alerts."""
        alerts = []

        # WCR zu niedrig
        if portfolio["wcr"] < self.alert_wcr_low:
            alerts.append({
                "alert_type": "LOW_WORKING_CAPITAL",
                "severity": "HIGH",
                "message": (
                    f"WCR={portfolio['wcr']:.2f} < {self.alert_wcr_low} — "
                    f"Liquiditätsengpass droht!"
                ),
            })

        # CCC zu lang
        if portfolio["ccc_days"] > self.alert_ccc_high:
            alerts.append({
                "alert_type": "LONG_CCC",
                "severity": "MEDIUM",
                "message": (
                    f"CCC={portfolio['ccc_days']:.0f}d > {self.alert_ccc_high}d — "
                    f"Kapital zu lange gebunden."
                ),
            })

        # ROIC negativ
        if portfolio["roic_pct"] < self.alert_roic_low:
            alerts.append({
                "alert_type": "VALUE_DESTRUCTION",
                "severity": "HIGH",
                "message": (
                    f"ROIC={portfolio['roic_pct']:.1f}% < 0 — WERTVERNICHTUNG!"
                ),
            })

        # ROIC unter Kapitalkosten
        if 0 < portfolio["roic_pct"] / 100 < self.cost_of_capital:
            alerts.append({
                "alert_type": "ROIC_BELOW_WACC",
                "severity": "MEDIUM",
                "message": (
                    f"ROIC={portfolio['roic_pct']:.1f}% < WACC={self.cost_of_capital*100:.1f}% — "
                    f"kein Economic Profit."
                ),
            })

        return alerts


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    import random

    print("=" * 60)
    print("CapitalEfficiencyAnalyzer — Smoke Test")
    print("=" * 60)

    analyzer = CapitalEfficiencyAnalyzerSubagent()

    rng = random.Random(42)
    projects = []
    for i in range(5):
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

    transactions = [
        {"amount_eur": 50000, "timestamp": "2026-01-15T00:00:00Z",
         "settled_at": "2026-02-10T00:00:00Z", "category": "payment"},
        {"amount_eur": 75000, "timestamp": "2026-03-20T00:00:00Z",
         "settled_at": "2026-04-15T00:00:00Z", "category": "invoice"},
    ]

    report = analyzer.analyze_efficiency(projects, transactions)

    print(f"\nStatus: {report['status']}")
    pf = report["portfolio_summary"]
    print(f"ROIC: {pf['roic_pct']:.1f}%")
    print(f"CCC: {pf['ccc_days']:.0f} Tage")
    print(f"WCR: {pf['wcr']:.2f}")
    print(f"Asset Turnover: {pf['asset_turnover']:.2f}×")
    print(f"Economic Profit: {pf['economic_profit_eur']:,.0f} EUR")

    proic = report["public_roic"]
    print(f"\nPublic ROIC: {proic['portfolio_public_roic_pct']:.1f}%")
    print(f"Net Public Value: {proic['net_public_value_eur']:,.0f} EUR")

    print(f"\nBenchmarks:")
    for k, v in report["benchmark_comparison"].items():
        print(f"  {k}: {v['rating']}")

    print(f"\nAlerts: {len(report['alerts'])}")
    for a in report["alerts"]:
        print(f"  [{a['severity']}] {a['message'][:100]}...")

    print(f"\n✅ Smoke Test abgeschlossen.")
