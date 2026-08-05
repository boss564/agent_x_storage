"""
Agent X — Full Module Coverage Test (v2.4.0).

Validiert dass alle Module importierbar sind und im Laufzeit-Graphen
(sys.modules) landen. Testet den SymbolicsAgentOrchestrator auf
echte Modul-Verdrahtung.

Usage:
  python3 test_all_modules.py
"""

import sys
import importlib
import json
import warnings

warnings.filterwarnings("ignore")

# Alle Module des Agent-X-Ökosystems
ALL_MODULES = [
    # Storage Layer
    "agent_x_storage", "agent_x_storage_guardian", "agent_x_archiver",
    "agent_x_seafile", "storage_client",
    # API Clients (8)
    "agent_x_beacon_client", "agent_x_solana_client", "agent_x_flashbots_client",
    "agent_x_jito_client", "agent_x_chainlink_client", "agent_x_pyth_client",
    "agent_x_governance_client", "agent_x_vesting_client",
    # Klasse A — Konsensus (3)
    "agent_x_klasse_a_1_ingestion", "agent_x_klasse_a_2_analytics",
    "agent_x_klasse_a_3_strategie",
    # Druckventile (6)
    "agent_x_klasse_b_pressure_models", "agent_x_klasse_b_pressure_b1_ingestion",
    "agent_x_klasse_b_pressure_b2_analytics", "agent_x_klasse_b_pressure_b3_strategie",
    "agent_x_gas_optimizer", "agent_x_bundle_executor",
    # Klasse B — Lending (5)
    "agent_x_lending_models", "agent_x_lending_b1_ingestion",
    "agent_x_lending_b2_risk", "agent_x_lending_b3_liquidation",
    "agent_x_aave_subscriber",
    # Klasse C — DeFi-Events (4)
    "agent_x_klasse_c_models", "agent_x_klasse_c_1_events",
    "agent_x_klasse_c_2_flashloans", "agent_x_klasse_c_3_arbitrage",
    # Klasse D — Oracle (5)
    "agent_x_klasse_d_oracle_models", "agent_x_klasse_d_1_ingestion",
    "agent_x_klasse_d_2_analytics", "agent_x_klasse_d_3_strategie",
    "agent_x_offchain_scout",
    # Klasse E — DAO/Timelocks (2)
    "agent_x_klasse_e_1_ingestion", "agent_x_klasse_e_2_3_strategie",
    # Klasse F — Sentiment & Whales (1)
    "agent_x_klasse_f_sentiment_whale",
    # Core & Monitoring (4)
    "agent_x_orchestrator", "agent_x_metrics", "agent_x_dashboard", "agent_x_backtest",
]


def test_import_all_modules():
    """Importiert alle Module und zählt Erfolge."""
    loaded = []
    failed = []

    for mod_name in ALL_MODULES:
        try:
            importlib.import_module(mod_name)
            loaded.append(mod_name)
        except Exception as e:
            failed.append((mod_name, str(e)))

    return loaded, failed


def test_orchestrator_wiring():
    """Testet ob der SymbolicsAgentOrchestrator echte Module verwendet."""
    from agent_x_orchestrator import SymbolicsAgentOrchestrator

    orch = SymbolicsAgentOrchestrator()
    wiring = orch.verify_wiring()

    snapshot = {
        "positions": [{"user_address": "0xTest", "health_factor": 1.25, "total_debt_usd": 50000}],
        "gas_price": 45, "block_number": 21000000,
    }
    result = orch.evaluate_snapshot(snapshot)

    return wiring, result


def test_module_count_in_sys_modules():
    """Prüft ob die Lending-Module tatsächlich in sys.modules sind."""
    critical_modules = [
        "agent_x_lending_b2_risk",
        "agent_x_lending_b3_liquidation",
        "agent_x_klasse_b_pressure_b2_analytics",
        "agent_x_klasse_c_2_flashloans",
        "agent_x_klasse_d_2_analytics",
        "agent_x_klasse_e_1_ingestion",
        "agent_x_klasse_f_sentiment_whale",
        "agent_x_gas_optimizer",
    ]

    present = [m for m in critical_modules if m in sys.modules]
    return present, [m for m in critical_modules if m not in sys.modules]


# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  AGENT X — FULL MODULE COVERAGE TEST (v2.4.0)")
    print("=" * 60)
    print()

    # Test 1: Importiere alle Module
    print(f"Test 1: Importiere {len(ALL_MODULES)} Module...")
    loaded, failed = test_import_all_modules()

    green = "\033[92m"
    red = "\033[91m"
    reset = "\033[0m"

    if not failed:
        print(f"  {green}ALL {len(loaded)} MODULES IMPORTED{reset}")
    else:
        print(f"  {green}{len(loaded)} loaded{reset}, {red}{len(failed)} failed{reset}")
        for mod_name, err in failed:
            print(f"    {red}FAIL{reset} {mod_name}: {err[:80]}")

    # Test 2: Orchestrator-Wiring
    print(f"\nTest 2: SymbolicsAgentOrchestrator Wiring...")
    try:
        wiring, result = test_orchestrator_wiring()
        total = wiring["total_expected"]
        present = wiring["present_in_sys_modules"]
        wiring_ok = wiring["wiring_complete"]
        chi = result["chi_score"]
        engaged = result["modules_engaged"]

        color = green if wiring_ok else red
        print(f"  Sys.Modules: {present}/{total} ({color}{'COMPLETE' if wiring_ok else 'MISSING'}{reset})")
        print(f"  Engines loaded: {engaged}")
        print(f"  CHI Score: {chi}/100")
        print(f"  Risk Mode: {result['risk_mode']}")

        if wiring["missing"]:
            print(f"  Missing from sys.modules:")
            for m in wiring["missing"]:
                print(f"    {red}{m}{reset}")
    except Exception as e:
        print(f"  {red}FAIL{reset}: {e}")

    # Test 3: Critical modules in sys.modules
    present_crit, missing_crit = test_module_count_in_sys_modules()
    all_critical = len(missing_crit) == 0
    color = green if all_critical else red
    print(f"\nTest 3: Critical modules in sys.modules: "
          f"{color}{len(present_crit)}/{len(present_crit)+len(missing_crit)}{reset}")
    if missing_crit:
        for m in missing_crit:
            print(f"  {red}MISSING{reset}: {m}")

    # Summary
    all_pass = not failed and wiring_ok and all_critical
    print()
    print("=" * 60)
    if all_pass:
        print(f"  {green}ALL TESTS PASSED — 44 Modules Verified{reset}")
    else:
        print(f"  {red}SOME TESTS FAILED — See details above{reset}")
    print("=" * 60)

    sys.exit(0 if all_pass else 1)
