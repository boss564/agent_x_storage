#!/usr/bin/env python3
# scripts/test_wave17_macro.py
"""
E2E-Test für Welle 17 (MacroEconomy Engine).
Validiert die gesamte 8-Stufen-Pipeline mit realistischen Testdaten.

Stufen:
  1. VelocityOfMoneyTracker      — Umlaufgeschwindigkeit
  2. RealTimeInflationOracle     — GAEB-Preisindex
  3. SupplyChainMultiplierCalc   — Keynesianischer Multiplikator
  4. ProgrammableStimulusEngine  — Fiskalimpuls-Entscheidung
  5. RealTimeTaxSplitter         — Steuerzerlegung
  6. CapitalEfficiencyAnalyzer   — ROIC, CCC, WCR
  7. SystemicRiskAndCartelMonitor — Kartell-/Monopolerkennung
  8. CentralBankLedgerTwin       — Zentralbank-Bilanz + Dashboard
"""

import json
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List

# Pfad setzen
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents_b2g.macro.subagents.velocity_of_money_tracker import VelocityOfMoneyTrackerSubagent
from agents_b2g.macro.subagents.real_time_inflation_oracle import RealTimeInflationOracleSubagent
from agents_b2g.macro.subagents.supply_chain_multiplier_calc import SupplyChainMultiplierCalcSubagent
from agents_b2g.macro.subagents.programmable_stimulus_engine import ProgrammableStimulusEngineSubagent
from agents_b2g.macro.subagents.real_time_tax_splitter import RealTimeTaxSplitterSubagent
from agents_b2g.macro.subagents.capital_efficiency_analyzer import CapitalEfficiencyAnalyzerSubagent
from agents_b2g.macro.subagents.systemic_risk_and_cartel_monitor import SystemicRiskAndCartelMonitorSubagent
from agents_b2g.macro.subagents.central_bank_ledger_twin import CentralBankLedgerTwinSubagent

# ============================================================================
# TEST DATA GENERATION
# ============================================================================

def generate_test_data() -> Dict[str, Any]:
    """Erzeugt realistische Testdaten über 12 Monate."""
    import random
    rng = random.Random(42)

    sectors = ["bau", "technik", "ausbau", "tiefbau", "elektro", "kanal"]
    regions = ["NI", "NW", "BY", "BE", "HH"]
    types = ["payment", "payment", "payment", "deposit", "retention", "refund"]
    companies = [f"Firma_{i}" for i in range(1, 31)]
    base_date = datetime(2025, 8, 1, tzinfo=timezone.utc)

    # 500 Transaktionen über 12 Monate
    transactions = []
    for i in range(500):
        tx_date = base_date + timedelta(days=i % 365)
        sector = rng.choice(sectors)
        transactions.append({
            "sender": rng.choice(companies),
            "receiver": rng.choice(companies),
            "amount_eur": round(rng.lognormvariate(mu=9.0, sigma=1.3), 2),
            "timestamp": tx_date.isoformat(),
            "sector": sector,
            "region_code": rng.choice(regions),
            "category": rng.choice(types),
            "description": f"{sector} Arbeiten Projekt {rng.randint(1, 5)}",
            "tier": rng.choices([0, 1, 2, 3, 4], weights=[5, 30, 35, 20, 10])[0],
            "cpv_code": "45232400",
            "construction_service": sector != "planung",
            "freistellungsattest": rng.random() > 0.7,
            "gemeinde": rng.choice(["Hannover", "Berlin", "München", "Köln"]),
            "receiver_type": "business",
        })

    # GAEB-Positionen
    units_list = ["m³", "m²", "Stk", "kg", "m", "Std"]
    gaeb_positions = []
    for i in range(60):
        sector = rng.choice(sectors)
        base_price = rng.uniform(50, 5000)
        months_since_base = i % 12
        inflation_factor = 1.0 + (0.04 * months_since_base / 12)
        current_price = base_price * inflation_factor * rng.uniform(0.95, 1.05)
        gaeb_positions.append({
            "position_id": f"POS_{i // 3:03d}",
            "unit_price_eur": round(current_price, 2),
            "quantity": round(rng.uniform(10, 1000), 2),
            "unit": rng.choice(units_list),
            "sector": sector,
            "description": f"{sector} Arbeiten Projekt {i % 5}",
            "timestamp": (base_date + timedelta(days=30 * (i % 12))).isoformat(),
        })

    # Projekte
    projects = []
    for i in range(5):
        budget = round(rng.uniform(500000, 5_000_000), 2)
        projects.append({
            "project_id": f"PRJ_{i:03d}",
            "tender_id": f"TED-2026-{1000+i:04d}",
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

    # Kartell-Muster injizieren
    transactions.append({
        "sender": "GU_Alpha", "receiver": "Sub_Beta",
        "amount_eur": 500000, "timestamp": "2026-07-01T00:00:00Z",
        "sector": "bau", "region_code": "NI", "category": "payment",
        "description": "Betonbauarbeiten", "tier": 0,
        "construction_service": True, "freistellungsattest": False,
    })
    transactions.append({
        "sender": "Sub_Beta", "receiver": "GU_Alpha",
        "amount_eur": 450000, "timestamp": "2026-07-15T00:00:00Z",
        "sector": "bau", "region_code": "NI", "category": "payment",
        "description": "Stahlbauarbeiten", "tier": 1,
        "construction_service": True, "freistellungsattest": False,
    })

    return {
        "transactions": transactions,
        "gaeb_positions": gaeb_positions,
        "projects": projects,
        "money_supply_eur": 5_000_000.0,
        "tender_id": "TED-2026-0815-KLAERANLAGE-NORD",
        "period_label": "2026-08",
    }

# ============================================================================
# MAIN TEST
# ============================================================================

def test_wave17():
    """Haupttest: Durchläuft alle 8 Subagenten mit Assertions."""
    print("=" * 70)
    print("  WAVE 17 — MACROECONOMY ENGINE E2E TEST")
    print("  Validierung der 8-Stufen-Makro-Pipeline")
    print("=" * 70)

    data = generate_test_data()
    tx = data["transactions"]
    gaeb = data["gaeb_positions"]
    projects = data["projects"]
    ms = data["money_supply_eur"]
    tender = data["tender_id"]
    period = data["period_label"]

    print(f"\n  Testdaten: {len(tx)} TX, {len(gaeb)} GAEB-Positionen, "
          f"{len(projects)} Projekte, M={ms:,.0f} EUR")

    results = {}
    passed = 0
    failed = 0

    # ========================================================================
    # STEP 1: VelocityOfMoneyTracker
    # ========================================================================
    print("\n── Step 1: VelocityOfMoneyTracker ──")
    try:
        vel = VelocityOfMoneyTrackerSubagent(period_days=30)
        # Historische Basis aufbauen
        for m in range(6, 0, -1):
            vel._update_history({
                "period": f"2026-{m:02d}", "velocity_tx": 1.25,
                "velocity_income": 0.85, "total_volume": 4_200_000,
                "money_supply_eur": 5_000_000, "transaction_count": 180,
                "dispersion": 0.3, "alerts_count": 0,
            })
        r1 = vel.analyze(tx, money_supply_eur=ms, tender_id=tender, period_label=period)
        assert r1["status"] == "ANALYSIS_COMPLETE", f"Status: {r1['status']}"
        v_tx = r1["velocity_metrics"]["velocity_tx"]
        assert v_tx > 0, f"Velocity muss > 0 sein: {v_tx}"
        assert "sector_breakdown" in r1["velocity_metrics"]
        print(f"  ✅ V_TX={v_tx:.3f}, Income={r1['velocity_metrics']['velocity_income']:.3f}, "
              f"Alerts={len(r1.get('alerts', []))}")
        results["velocity"] = r1
        passed += 1
    except Exception as e:
        print(f"  ❌ Fehlgeschlagen: {e}")
        results["velocity"] = {"error": str(e)}
        failed += 1

    # ========================================================================
    # STEP 2: RealTimeInflationOracle
    # ========================================================================
    print("\n── Step 2: RealTimeInflationOracle ──")
    try:
        inf = RealTimeInflationOracleSubagent()
        r2 = inf.measure_inflation(
            gaeb_positions=gaeb, money_supply_eur=ms,
            velocity_tx=v_tx, period_label=period, tender_id=tender,
        )
        assert r2["status"] == "ANALYSIS_COMPLETE", f"Status: {r2['status']}"
        fisher = r2["price_indices"]["fisher_index"]
        assert 70 < fisher < 200, f"Fisher-Index {fisher} außerhalb Plausibilitätsbereich"
        print(f"  ✅ Fisher={fisher:.2f}, Composite Inflation={r2['composite_inflation_pct']:.2f}%, "
              f"BKI={r2['bki_comparison']['bki_annualized_inflation_pct']:.2f}%")
        results["inflation"] = r2
        passed += 1
    except Exception as e:
        print(f"  ❌ Fehlgeschlagen: {e}")
        results["inflation"] = {"error": str(e)}
        failed += 1

    # ========================================================================
    # STEP 3: SupplyChainMultiplierCalc
    # ========================================================================
    print("\n── Step 3: SupplyChainMultiplierCalc ──")
    try:
        mul = SupplyChainMultiplierCalcSubagent()
        r3 = mul.calculate_multiplier(
            transactions=tx, initial_spending_eur=ms,
            tender_id=tender, period_label=period,
        )
        assert r3["status"] == "ANALYSIS_COMPLETE", f"Status: {r3['status']}"
        k = r3["multiplier_metrics"]["composite_multiplier"]
        assert 0.5 < k < 5.0, f"Multiplikator {k} außerhalb Plausibilitätsbereich"
        print(f"  ✅ k_composite={k:.3f}, Keynes={r3['multiplier_metrics']['keynesian_multiplier']:.3f}, "
              f"Regional={r3['regional_multiplier']['local_retention_rate']*100:.1f}%")
        results["multiplier"] = r3
        passed += 1
    except Exception as e:
        print(f"  ❌ Fehlgeschlagen: {e}")
        results["multiplier"] = {"error": str(e)}
        failed += 1

    # ========================================================================
    # STEP 4: ProgrammableStimulusEngine
    # ========================================================================
    print("\n── Step 4: ProgrammableStimulusEngine ──")
    try:
        stim = ProgrammableStimulusEngineSubagent()
        r4 = stim.decide_stimulus(
            velocity_report=r1,
            inflation_report=r2,
            multiplier_report=r3,
            money_supply_eur=ms,
            tender_id=tender,
            period_label=period,
        )
        assert r4["status"] == "DECISION_COMPLETE", f"Status: {r4['status']}"
        mode = r4["decision"]["mode"]
        assert mode in ("NEUTRAL", "EXPANSIONARY", "CONTRACTIONARY", "EMERGENCY")
        print(f"  ✅ Modus={mode}, Betrag={r4['decision']['stimulus_amount_eur']:,.0f} EUR, "
              f"Typ={r4['decision']['stimulus_type']}")
        results["stimulus"] = r4
        passed += 1
    except Exception as e:
        print(f"  ❌ Fehlgeschlagen: {e}")
        results["stimulus"] = {"error": str(e)}
        failed += 1

    # ========================================================================
    # STEP 5: RealTimeTaxSplitter
    # ========================================================================
    print("\n── Step 5: RealTimeTaxSplitter ──")
    try:
        tax = RealTimeTaxSplitterSubagent()
        r5 = tax.split_taxes(transactions=tx, tender_id=tender, period_label=period)
        assert r5["status"] == "ANALYSIS_COMPLETE", f"Status: {r5['status']}"
        total_tax = r5["tax_summary"]["total_tax_eur"]
        assert total_tax > 0, f"Steueraufkommen muss > 0 sein: {total_tax}"
        sec13b = r5["tax_summary"]["section_13b_transactions"]
        print(f"  ✅ Steuern={total_tax:,.0f} EUR, §13b={sec13b}, "
              f"Bauabzug={r5['tax_summary']['bauabzugsteuer_transactions']}")
        results["tax"] = r5
        passed += 1
    except Exception as e:
        print(f"  ❌ Fehlgeschlagen: {e}")
        results["tax"] = {"error": str(e)}
        failed += 1

    # ========================================================================
    # STEP 6: CapitalEfficiencyAnalyzer
    # ========================================================================
    print("\n── Step 6: CapitalEfficiencyAnalyzer ──")
    try:
        ceff = CapitalEfficiencyAnalyzerSubagent()
        r6 = ceff.analyze_efficiency(
            projects=projects, transactions=tx, period_label=period,
        )
        assert r6["status"] == "ANALYSIS_COMPLETE", f"Status: {r6['status']}"
        roic = r6["portfolio_summary"]["roic_pct"]
        assert -10 < roic < 60, f"ROIC {roic}% außerhalb Plausibilitätsbereich"
        print(f"  ✅ ROIC={roic:.1f}%, CCC={r6['portfolio_summary']['ccc_days']:.0f}d, "
              f"WCR={r6['portfolio_summary']['wcr']:.2f}")
        results["capital"] = r6
        passed += 1
    except Exception as e:
        print(f"  ❌ Fehlgeschlagen: {e}")
        results["capital"] = {"error": str(e)}
        failed += 1

    # ========================================================================
    # STEP 7: SystemicRiskAndCartelMonitor
    # ========================================================================
    print("\n── Step 7: SystemicRiskAndCartelMonitor ──")
    try:
        cart = SystemicRiskAndCartelMonitorSubagent()
        r7 = cart.analyze_network(transactions=tx, tender_id=tender, period_label=period)
        assert r7["status"].startswith("ANALYSIS_COMPLETE"), f"Status: {r7['status']}"
        risk = r7["risk_score"]
        assert 0 <= risk <= 1, f"Risk Score {risk} außerhalb [0,1]"
        mutuals = len(r7.get("cartel_indicators", {}).get("mutual_payments", []))
        print(f"  ✅ Risk={risk:.2f}, Nodes={r7['network_metrics']['nodes']}, "
              f"Mutual Payments={mutuals}, Alerts={len(r7.get('alerts', []))}")
        # Die injizierten Kartell-Muster MÜSSEN erkannt werden
        assert mutuals >= 1, f"Erwartete mindestens 1 gegenseitige Zahlung, gefunden: {mutuals}"
        print(f"  ✅ Kartell-Muster korrekt erkannt!")
        results["cartel"] = r7
        passed += 1
    except Exception as e:
        print(f"  ❌ Fehlgeschlagen: {e}")
        results["cartel"] = {"error": str(e)}
        failed += 1

    # ========================================================================
    # STEP 8: CentralBankLedgerTwin
    # ========================================================================
    print("\n── Step 8: CentralBankLedgerTwin ──")
    try:
        cb = CentralBankLedgerTwinSubagent()
        r8 = cb.generate_balance_sheet(
            money_supply_eur=ms,
            velocity_report=r1,
            inflation_report=r2,
            stimulus_report=r4,
            tax_report=r5,
            period_label=period,
        )
        assert r8["status"] == "BALANCE_SHEET_GENERATED", f"Status: {r8['status']}"
        bs = r8["balance_sheet"]
        assert bs["is_balanced"], f"Bilanz nicht ausgeglichen: Δ={bs['delta_eur']}"
        assert bs["liabilities"]["eure_in_circulation"] > 0
        taylor = r8["taylor_rule"]["recommended_rate_pct"]
        assert 0 <= taylor <= 15, f"Taylor-Zins {taylor}% außerhalb Plausibilitätsbereich"
        dashboard = r8["dashboard"]["overall_assessment"]
        print(f"  ✅ Bilanz Δ={bs['delta_eur']:.2f} EUR, Taylor={taylor:.1f}%, "
              f"Dashboard={dashboard}")
        results["cb_ledger"] = r8
        passed += 1
    except Exception as e:
        print(f"  ❌ Fehlgeschlagen: {e}")
        results["cb_ledger"] = {"error": str(e)}
        failed += 1

    # ========================================================================
    # FINAL REPORT
    # ========================================================================
    print("\n" + "=" * 70)
    print(f"  WAVE 17 E2E-TEST: {passed}/8 BESTANDEN, {failed}/8 FEHLGESCHLAGEN")
    print("=" * 70)

    # Report speichern (temp dir — keine persistenten Artefakte im Repo)
    import tempfile
    report_dir = Path(tempfile.gettempdir()) / "agent_x_wave17_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"wave17_e2e_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "test": "wave17_e2e",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "passed": passed,
            "failed": failed,
            "total": 8,
            "test_data_summary": {
                "transactions": len(tx),
                "gaeb_positions": len(gaeb),
                "projects": len(projects),
                "money_supply_eur": ms,
            },
            "results": results,
        }, f, indent=2, ensure_ascii=False, default=str)

    print(f"  Report: {report_path}")

    if failed > 0:
        print("\n❌ TEST FEHLGESCHLAGEN")
        sys.exit(1)
    else:
        print("\n✅ ALLE 8 STUFEN ERFOLGREICH — Welle 17 ist produktionsbereit.")
        sys.exit(0)


if __name__ == "__main__":
    test_wave17()
