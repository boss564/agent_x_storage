"""
Agent X — Live Monitoring Dashboard.

Terminal-basiertes Echtzeit-Dashboard mit 4-Klassen-KPIs,
Farbcodierung und periodischem Refresh.

Usage:
  python3 agent_x_dashboard.py                # Einmalige Ausgabe
  python3 agent_x_dashboard.py --watch 12     # Alle 12s aktualisieren
  python3 agent_x_dashboard.py --json         # JSON-Output für externe Systeme
  python3 agent_x_dashboard.py --grafana      # Grafana-kompatibler Output

Farbcodierung:
  GRÜN  = Healthy (>80)
  GELB  = Caution (60-80)
  ORANGE = Stressed (40-60)
  ROT   = Critical (<40)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

# ANSI-Farben
GREEN = "\033[92m"
YELLOW = "\033[93m"
ORANGE = "\033[38;5;214m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("T", " ")[:19]


def color_by_score(score, text=None):
    """Farbcodierung nach Score."""
    if score >= 80: return f"{GREEN}{text or score}{RESET}"
    elif score >= 60: return f"{YELLOW}{text or score}{RESET}"
    elif score >= 40: return f"{ORANGE}{text or score}{RESET}"
    return f"{RED}{text or score}{RESET}"


def color_by_level(level):
    """Farbcodierung nach Pressure-Level."""
    c = {"low": GREEN, "moderate": YELLOW, "elevated": ORANGE, "high": RED, "extreme": f"{RED}{BOLD}"}
    return f"{c.get(level, RESET)}{level}{RESET}"


def bar_chart(value, max_val=100, width=30):
    """ASCII-Balkendiagramm."""
    filled = int(min(value, max_val) / max_val * width)
    bar = "█" * filled + "░" * (width - filled)
    return bar


def render_dashboard(decision: dict) -> str:
    """Rendert das vollständige Text-Dashboard."""
    ud = decision.get("unified_decision", {})
    sig = decision.get("class_signals", {})
    gs_score = ud.get("global_state_score", 50)
    gs_state = ud.get("global_state", "unknown")
    sc = ud.get("scenario", {})

    a = sig.get("klasse_a_consensus", {})
    b = sig.get("klasse_b_druckventile", {})
    c = sig.get("klasse_c_lending", {})
    d = sig.get("klasse_d_defi", {})

    ts = decision.get("timestamp", _now_iso())[:19]

    lines = []
    # ─── Header ──────────────────────────────────────────────────────
    lines.append(f"{BOLD}{CYAN}╔{'═' * 78}╗{RESET}")
    lines.append(f"{BOLD}{CYAN}║{RESET} {BOLD}AGENT X — LIVE MONITORING DASHBOARD{RESET}{' ' * 42}{DIM}{ts}{RESET} {BOLD}{CYAN}║{RESET}")
    lines.append(f"{BOLD}{CYAN}╠{'═' * 78}╣{RESET}")

    # ─── Global State ────────────────────────────────────────────────
    state_color = GREEN if gs_score >= 80 else YELLOW if gs_score >= 60 else ORANGE if gs_score >= 40 else RED
    bar = bar_chart(gs_score)
    lines.append(f"{BOLD}{CYAN}║{RESET} {BOLD}GLOBAL STATE{RESET} {state_color}{gs_state.upper():<12}{RESET} "
                 f"{state_color}{gs_score:5.1f}/100{RESET}  [{state_color}{bar}{RESET}] {BOLD}{CYAN}║{RESET}")
    lines.append(f"{BOLD}{CYAN}╠{'═' * 78}╣{RESET}")

    # ─── Klasse A: Konsensus ─────────────────────────────────────────
    ah = a.get("health_detail", {})
    chi = ah.get("chi", 0)
    lines.append(f"{BOLD}{CYAN}║{RESET} {MAGENTA}{BOLD}KLASSE A — KONSENSUS & DETERMINISMUS{RESET}{' ' * 40}{BOLD}{CYAN}║{RESET}")
    lines.append(f"{BOLD}{CYAN}║{RESET}   CHI: {color_by_score(chi)}  |  "
                 f"Finality: {ah.get('finality','?')}  |  "
                 f"Participation: {ah.get('participation',0):.1%}  |  "
                 f"Reorg: {ah.get('reorg_depth',0)}  |  "
                 f"ExitQ: {'STRESS' if ah.get('exit_queue_stress') else 'OK'}"
                 f"{' ' * 17}{BOLD}{CYAN}║{RESET}")

    # ─── Klasse B: Druckventile ─────────────────────────────────────
    gas_idx = b.get("gas_pressure_index", 50)
    mev_idx = b.get("mev_pressure_index", 50)
    blk_idx = b.get("block_pressure_index", 50)
    comb = b.get("combined_pressure_index", 50)
    level = b.get("pressure_level", "moderate")

    lines.append(f"{BOLD}{CYAN}║{RESET} {CYAN}{BOLD}KLASSE B — DRUCKVENTILE (MEV, GAS, PRIORITY FEES){RESET}{' ' * 27}{BOLD}{CYAN}║{RESET}")
    lines.append(f"{BOLD}{CYAN}║{RESET}   "
                 f"Gas: {color_by_score(100-gas_idx)} {gas_idx:5.1f}  [{bar_chart(gas_idx, 100, 12)}]  "
                 f"MEV: {color_by_score(100-mev_idx)} {mev_idx:5.1f}  [{bar_chart(mev_idx, 100, 12)}]  "
                 f"Block: {color_by_score(100-blk_idx)} {blk_idx:5.1f}  [{bar_chart(blk_idx, 100, 12)}]"
                 f"  {BOLD}{CYAN}║{RESET}")
    lines.append(f"{BOLD}{CYAN}║{RESET}   "
                 f"Combined: {color_by_score(100-comb)} {comb:5.1f}  |  "
                 f"Level: {color_by_level(level)}  |  "
                 f"Basefee: {b.get('basefee_current_gwei',0):.1f} gwei  |  "
                 f"PF-P95: {b.get('priority_fee_p95_gwei',0):.1f} gwei  |  "
                 f"Spike: {'YES' if b.get('mev_spike_detected') else 'no'}"
                 f"{' ' * 14}{BOLD}{CYAN}║{RESET}")

    # ─── Klasse C: Lending ───────────────────────────────────────────
    at_risk = c.get("at_risk", 0)
    liquidatable = c.get("liquidatable", 0)
    worst_hf = c.get("worst_hf", float("inf"))
    hf_adj = c.get("critical_hf_adjusted", 1.05)
    hf_color = GREEN if worst_hf > 1.5 else YELLOW if worst_hf > 1.05 else ORANGE if worst_hf > 1.0 else RED
    hf_str = f"{worst_hf:.3f}" if worst_hf != float("inf") else "∞"

    lines.append(f"{BOLD}{CYAN}║{RESET} {CYAN}{BOLD}KLASSE C — LENDING & RISIKO{RESET}{' ' * 51}{BOLD}{CYAN}║{RESET}")
    lines.append(f"{BOLD}{CYAN}║{RESET}   "
                 f"Users: {c.get('users_tracked',0):4d}  |  "
                 f"At-Risk: {ORANGE if at_risk else GREEN}{at_risk:3d}{RESET}  |  "
                 f"Liquidatable: {RED if liquidatable else GREEN}{liquidatable:3d}{RESET}  |  "
                 f"Worst HF: {hf_color}{hf_str}{RESET}  |  "
                 f"Crit-Threshold: {YELLOW if hf_adj > 1.05 else GREEN}{hf_adj:.3f}{RESET}"
                 f"{' ' * 23}{BOLD}{CYAN}║{RESET}")

    # ─── Klasse D: DeFi ──────────────────────────────────────────────
    profit = d.get("total_potential_profit_usd", 0)
    fl_prof = d.get("flash_loan_profitable", 0)
    bots = d.get("mempool_bots", 0)
    mev_risk = d.get("mev_risk", "low")

    lines.append(f"{BOLD}{CYAN}║{RESET} {CYAN}{BOLD}KLASSE D — DEFI-EVENTS{RESET}{' ' * 55}{BOLD}{CYAN}║{RESET}")
    lines.append(f"{BOLD}{CYAN}║{RESET}   "
                 f"FL-Opps: {fl_prof:3d} profitable  |  "
                 f"Cross-Pool: {d.get('cross_pool_opportunities',0):3d}  |  "
                 f"Cross-Chain: {d.get('cross_chain_opportunities',0):3d}  |  "
                 f"Profit: {GREEN if profit > 100 else RESET}${profit:,.0f}{RESET}  |  "
                 f"MEV-Bots: {RED if bots > 2 else GREEN}{bots}{RESET}"
                 f"{' ' * 27}{BOLD}{CYAN}║{RESET}")

    # ─── 5-Step Scenario ─────────────────────────────────────────────
    lines.append(f"{BOLD}{CYAN}╠{'═' * 78}╣{RESET}")
    lines.append(f"{BOLD}{CYAN}║{RESET} {MAGENTA}{BOLD}5-STEP SCENARIO{RESET}{' ' * 63}{BOLD}{CYAN}║{RESET}")

    step_names = [
        ("step_1_timing", "A3-1 Timing"),
        ("step_2_pressure", "B     Druckventile"),
        ("step_3_flash_loan", "D2    Flash-Loan"),
        ("step_4_health_factor", "C2    Health-Factor"),
        ("step_5_routing", "A3-3  Routing"),
    ]

    for key, label in step_names:
        s = sc.get(key, {})
        actionable = s.get("actionable", None)
        if actionable is None:
            icon = "○"
            c = DIM
        elif actionable:
            icon = "✓"
            c = GREEN
        else:
            icon = "✗"
            c = RED
        msg = s.get("message", "?")[:55]
        lines.append(f"{BOLD}{CYAN}║{RESET}   [{c}{icon}{RESET}] {label:<14} {c}{msg}{RESET}{' ' * (55 - len(msg))}{BOLD}{CYAN}║{RESET}")

    # ─── GO/NO-GO ───────────────────────────────────────────────────
    all_clear = sc.get("all_clear", False)
    go_bar = f"{GREEN}████████████ GO ████████████{RESET}" if all_clear else f"{RED}██████████ NO-GO ██████████{RESET}"
    lines.append(f"{BOLD}{CYAN}║{RESET}   {go_bar}{' ' * 42}{BOLD}{CYAN}║{RESET}")
    lines.append(f"{BOLD}{CYAN}║{RESET}   {sc.get('summary', '')[:74]}{BOLD}{CYAN}║{RESET}")

    # ─── Recommendations ─────────────────────────────────────────────
    recs = ud.get("recommended_actions", [])
    if recs:
        lines.append(f"{BOLD}{CYAN}╠{'═' * 78}╣{RESET}")
        lines.append(f"{BOLD}{CYAN}║{RESET} {BOLD}EMPFEHLUNGEN{RESET}{' ' * 65}{BOLD}{CYAN}║{RESET}")
        for rec in recs[:4]:
            lines.append(f"{BOLD}{CYAN}║{RESET}   P{rec['priority']}: {rec['action']:<25} {rec['detail'][:45]}{RESET}{BOLD}{CYAN}║{RESET}")

    # ─── Footer ──────────────────────────────────────────────────────
    lines.append(f"{BOLD}{CYAN}╚{'═' * 78}╝{RESET}")

    return "\n".join(lines)


def watch(interval: int = 12):
    """Periodischer Dashboard-Refresh."""
    from agent_x_orchestrator import run_full_evaluation
    try:
        while True:
            print(CLEAR)
            decision = run_full_evaluation()
            print(render_dashboard(decision))
            print(f"\n{DIM}Refresh: {interval}s | Ctrl+C to exit | Metrics: http://localhost:9090/metrics{RESET}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n{GREEN}Agent X Dashboard stopped.{RESET}")


def json_output():
    """JSON-Output für externe Dashboards."""
    from agent_x_orchestrator import run_full_evaluation
    decision = run_full_evaluation()
    # Kompakte Version für API-Consumer
    ud = decision.get("unified_decision", {})
    sig = decision.get("class_signals", {})
    b = sig.get("klasse_b_druckventile", {})
    a = sig.get("klasse_a_consensus", {})

    payload = {
        "timestamp": decision.get("timestamp"),
        "global_state": {
            "score": ud.get("global_state_score"),
            "state": ud.get("global_state"),
        },
        "consensus": {
            "chi": a.get("health_detail", {}).get("chi"),
            "defi_ops_allowed": a.get("defi_operations_allowed"),
        },
        "pressure": {
            "gas": b.get("gas_pressure_index"),
            "mev": b.get("mev_pressure_index"),
            "block": b.get("block_pressure_index"),
            "combined": b.get("combined_pressure_index"),
            "level": b.get("pressure_level"),
            "basefee_gwei": b.get("basefee_current_gwei"),
            "pf_p95_gwei": b.get("priority_fee_p95_gwei"),
        },
        "lending": {
            "at_risk": sig.get("klasse_c_lending", {}).get("at_risk", 0),
            "liquidatable": sig.get("klasse_c_lending", {}).get("liquidatable", 0),
            "critical_hf": sig.get("klasse_c_lending", {}).get("critical_hf_adjusted", 1.05),
        },
        "defi": {
            "flash_loan_profitable": sig.get("klasse_d_defi", {}).get("flash_loan_profitable", 0),
            "total_profit_usd": sig.get("klasse_d_defi", {}).get("total_potential_profit_usd", 0),
            "mempool_bots": sig.get("klasse_d_defi", {}).get("mempool_bots", 0),
        },
        "scenario": {
            "all_clear": ud.get("scenario", {}).get("all_clear", False),
            "summary": ud.get("scenario", {}).get("summary", ""),
        },
        "recommendations": ud.get("recommended_actions", []),
    }
    print(json.dumps(payload, indent=2))


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agent X — Live Dashboard")
    parser.add_argument("--watch", type=int, metavar="SEC", help="Periodischer Refresh")
    parser.add_argument("--json", action="store_true", help="JSON-Output")
    parser.add_argument("--grafana", action="store_true", help="Grafana-kompatibler Output")
    args = parser.parse_args()

    if args.watch:
        watch(args.watch)
    elif args.json:
        json_output()
    elif args.grafana:
        json_output()
    else:
        from agent_x_orchestrator import run_full_evaluation
        decision = run_full_evaluation()
        print(render_dashboard(decision))
