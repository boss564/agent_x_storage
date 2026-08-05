"""
Agent X — Backtesting Suite.

Replayed historische Marktereignisse (Terra-Crash, FTX, SVB, Flash-Crash)
und evaluiert, ob Agent X die richtigen Entscheidungen getroffen hätte.

Szenarien sind als Block-für-Block-Parameterverläufe definiert.
Jeder Block durchläuft die vollständige 4-Klassen-Pipeline.

Scoring:
  - Precision: Anteil korrekter Action-Signale
  - Recall: Anteil erkannter kritischer Ereignisse
  - Profit Saved: Hypothetisch gerettetes Kapital in USD
  - Response Time: Blöcke bis zur ersten korrekten Reaktion
  - False Positives: Fälschlich ausgelöste Alarme

Usage:
  python3 agent_x_backtest.py                    # Alle Szenarien
  python3 agent_x_backtest.py --scenario terra   # Nur Terra-Crash
  python3 agent_x_backtest.py --report           # Nur Gesamt-Report
"""

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════
# HISTORISCHE SZENARIEN
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class BlockSnapshot:
    """Zustand aller 4 Klassen-Parameter zu einem Zeitpunkt."""
    block: int
    label: str = ""  # Beschreibung dieses Moments

    # Klasse A — Konsensus
    chi: float = 94.0
    participation_rate: float = 0.97
    finality_status: str = "on_time"
    reorg_depth: int = 0
    exit_queue: int = 50
    trusted_validators: list[str] = field(default_factory=lambda: ["validator_101"])

    # Klasse B — Druckventile
    gas_pressure: float = 50.0
    mev_pressure: float = 50.0
    block_pressure: float = 50.0
    basefee_gwei: float = 21.0
    pf_p95_gwei: float = 3.5
    mev_spike: bool = False

    # Klasse C — Lending
    positions_at_risk: int = 0
    positions_liquidatable: int = 0
    worst_hf: float = float("inf")

    # Klasse D — DeFi
    flash_loan_profitable: int = 0
    cross_pool_ops: int = 0
    mempool_bots: int = 0
    potential_profit_usd: float = 0.0

    # Klasse E — DAO/Timelocks (Langzeit-Heuristiken)
    pending_timelocks: list = field(default_factory=list)
    upcoming_unlocks: list = field(default_factory=list)
    active_proposals: list = field(default_factory=list)
    hours_until_next_timelock: float = 9999.0
    days_until_next_unlock: float = 9999.0

    # Erwartetes Verhalten (Ground Truth)
    expected_global_state: str = "healthy"  # healthy | caution | stressed | critical
    expected_action: str = "MONITOR"  # MONITOR | REDUCE | SHUTDOWN | ARBITRAGE | LIQUIDATE
    expected_all_clear: bool = True
    notes: str = ""


# ─── Szenario 1: Terra/LUNA-Crash (Mai 2022) ─────────────────────────

SCENARIO_TERRA_CRASH = {
    "name": "Terra/LUNA Crash (Mai 2022)",
    "description": "UST depegged → LUNA hyperinflation → $40B wiped out in 72h. "
                   "Liquidations cascaded across Anchor Protocol. "
                   "Network: ETH congested, gas spiked 5x. MEV bots extracted $100M+.",
    "date": "2022-05-09",
    "blocks": [
        # Phase 1: Normal (Block 0-5)
        BlockSnapshot(0, "Normaler Markt", chi=94, gas_pressure=35, mev_pressure=20,
                      positions_at_risk=2, positions_liquidatable=0, worst_hf=1.52,
                      flash_loan_profitable=1, mempool_bots=1,
                      expected_global_state="healthy", expected_action="MONITOR", expected_all_clear=True,
                      notes="Alles normal — kein Alarm."),

        # Phase 2: Erste UST-Abweichung (Block 6)
        BlockSnapshot(6, "UST $0.98 — erste Abweichung", chi=88, gas_pressure=45, mev_pressure=35,
                      positions_at_risk=5, positions_liquidatable=0, worst_hf=1.35,
                      flash_loan_profitable=3, mempool_bots=2,
                      expected_global_state="caution", expected_action="MONITOR", expected_all_clear=True,
                      notes="UST leicht unter Peg — Markt noch ruhig, aber Watchlist wächst."),

        # Phase 3: Peg bricht (Block 12)
        BlockSnapshot(12, "UST $0.91 — Peg bricht", chi=82, gas_pressure=62, mev_pressure=55,
                      positions_at_risk=15, positions_liquidatable=3, worst_hf=1.08,
                      flash_loan_profitable=8, mempool_bots=4, potential_profit_usd=25000,
                      expected_global_state="stressed", expected_action="REDUCE", expected_all_clear=False,
                      notes="UST stark abgewichen. HF nahe 1.0 bei 3 Positionen. "
                            "Agent MUSS RISIKO REDUZIEREN."),

        # Phase 4: Kaskade beginnt (Block 18)
        BlockSnapshot(18, "Anchor-Liquidationen starten", chi=70, gas_pressure=78, mev_pressure=72,
                      mev_spike=True,
                      positions_at_risk=45, positions_liquidatable=12, worst_hf=0.91,
                      flash_loan_profitable=15, mempool_bots=7, potential_profit_usd=120000,
                      expected_global_state="critical", expected_action="SHUTDOWN", expected_all_clear=False,
                      notes="Liquidations-Kaskade! 12 Positionen liquidierbar, "
                            "MEV-Spike erkannt. Agent MUSS SHUTDOWN auslösen."),

        # Phase 5: Crash-Peak (Block 24)
        BlockSnapshot(24, "LUNA $0.01 — Totalverlust", chi=45, gas_pressure=92, mev_pressure=88,
                      mev_spike=True,
                      positions_at_risk=120, positions_liquidatable=67, worst_hf=0.34,
                      flash_loan_profitable=25, mempool_bots=12, potential_profit_usd=500000,
                      expected_global_state="critical", expected_action="SHUTDOWN", expected_all_clear=False,
                      notes="Chaos! 67 Positionen liquidiert. Gas 5x Normal. "
                            "Agent muss längst im SHUTDOWN sein."),

        # Phase 6: Nachwehen (Block 36)
        BlockSnapshot(36, "Marktberuhigung nach Crash", chi=55, gas_pressure=68, mev_pressure=45,
                      positions_at_risk=200, positions_liquidatable=89, worst_hf=0.55,
                      flash_loan_profitable=5, mempool_bots=3,
                      expected_global_state="critical", expected_action="SHUTDOWN", expected_all_clear=False,
                      notes="Noch 89 liquidierbare Positionen. Agent sollte SHUTDOWN halten."),
    ],
}

# ─── Szenario 2: FTX-Kollaps (November 2022) ─────────────────────────

SCENARIO_FTX_COLLAPSE = {
    "name": "FTX Collapse (Nov 2022)",
    "description": "Bank run on FTX. SOL crashes -60% in 24h. "
                   "Solana DeFi TVL drops 70%. Jito tips spike. "
                   "MEV extraction on Solana goes extreme.",
    "date": "2022-11-08",
    "blocks": [
        BlockSnapshot(0, "Vor dem Sturm", chi=92, gas_pressure=30, mev_pressure=25, block_pressure=35,
                      positions_at_risk=3, worst_hf=1.45, mempool_bots=1,
                      expected_global_state="healthy", expected_action="MONITOR", expected_all_clear=True),

        BlockSnapshot(4, "FTT fällt -20%", chi=85, gas_pressure=55, mev_pressure=48, block_pressure=52,
                      positions_at_risk=12, positions_liquidatable=2, worst_hf=1.12,
                      flash_loan_profitable=5, mempool_bots=3, potential_profit_usd=15000,
                      expected_global_state="stressed", expected_action="REDUCE", expected_all_clear=False,
                      notes="FTT-Crash. SOL beginnt zu wackeln. Risk REDUCE."),

        BlockSnapshot(8, "SOL -40%", chi=62, gas_pressure=75, mev_pressure=82, block_pressure=78,
                      mev_spike=True,
                      positions_at_risk=35, positions_liquidatable=18, worst_hf=0.78,
                      flash_loan_profitable=20, mempool_bots=9, potential_profit_usd=200000,
                      expected_global_state="critical", expected_action="SHUTDOWN", expected_all_clear=False,
                      notes="SOL im freien Fall. 18 Liquidierungen. SHUTDOWN zwingend."),

        BlockSnapshot(14, "FTX Chapter 11", chi=48, gas_pressure=88, mev_pressure=85, block_pressure=90,
                      mev_spike=True,
                      positions_at_risk=80, positions_liquidatable=45, worst_hf=0.42,
                      flash_loan_profitable=30, mempool_bots=15, potential_profit_usd=750000,
                      expected_global_state="critical", expected_action="SHUTDOWN", expected_all_clear=False,
                      notes="FTX offiziell bankrott. SHUTDOWN halten."),
    ],
}

# ─── Szenario 3: SVB Bank Run (März 2023) ────────────────────────────

SCENARIO_SVB_CRISIS = {
    "name": "SVB/USDC Depeg (März 2023)",
    "description": "SVB collapse → USDC depegs to $0.87. "
                   "DeFi protocols pause. DAI briefly depegs. "
                   "Arbitrageurs buy USDC at discount across DEXes.",
    "date": "2023-03-10",
    "blocks": [
        BlockSnapshot(0, "Normaler Freitag", chi=93, gas_pressure=28, mev_pressure=18, block_pressure=25,
                      positions_at_risk=4, worst_hf=1.55, mempool_bots=1,
                      expected_global_state="healthy", expected_action="MONITOR", expected_all_clear=True),

        BlockSnapshot(3, "SVB News brechen", chi=78, gas_pressure=42, mev_pressure=55, block_pressure=48,
                      positions_at_risk=22, positions_liquidatable=5, worst_hf=1.05,
                      flash_loan_profitable=10, mempool_bots=5, potential_profit_usd=45000,
                      expected_global_state="stressed", expected_action="REDUCE", expected_all_clear=False,
                      notes="USDC-Depeg beginnt. HF critical bei 5 Positionen. REDUCE."),

        BlockSnapshot(6, "USDC $0.87 — DeFi pausiert", chi=68, gas_pressure=70, mev_pressure=78,
                      mev_spike=True,
                      positions_at_risk=55, positions_liquidatable=28, worst_hf=0.65,
                      flash_loan_profitable=18, mempool_bots=8, potential_profit_usd=350000,
                      expected_global_state="critical", expected_action="SHUTDOWN", expected_all_clear=False,
                      notes="USDC 13% unter Peg. Arbitrage möglich, aber extrem riskant. SHUTDOWN."),

        BlockSnapshot(10, "Erholung beginnt", chi=75, gas_pressure=55, mev_pressure=42, block_pressure=58,
                      positions_at_risk=40, positions_liquidatable=15, worst_hf=0.92,
                      flash_loan_profitable=8, mempool_bots=4, potential_profit_usd=80000,
                      expected_global_state="stressed", expected_action="REDUCE", expected_all_clear=False,
                      notes="USDC peg recovered. Noch zu früh für Arbitrage. REDUCE halten."),
    ],
}

# ─── Szenario 4: Bull-Run (gesundes Netzwerk) ────────────────────────

SCENARIO_BULL_RUN = {
    "name": "Bull-Run (Gesundes Netzwerk)",
    "description": "Ideale Marktbedingungen: niedriger Gas, keine Liquidationen, "
                   "Arbitrage-Chancen vorhanden. Agent sollte AGGRESSIV ARBITRAGE fahren.",
    "date": "2024-01-15",
    "blocks": [
        BlockSnapshot(0, "Ruhiger Start", chi=96, gas_pressure=15, mev_pressure=10, block_pressure=20,
                      positions_at_risk=0, worst_hf=2.5, flash_loan_profitable=2,
                      mempool_bots=0, potential_profit_usd=500,
                      expected_global_state="healthy", expected_action="ARBITRAGE", expected_all_clear=True,
                      notes="Perfekte Bedingungen für Arbitrage."),

        BlockSnapshot(3, "Arbitrage-Fenster", chi=95, gas_pressure=12, mev_pressure=8, block_pressure=18,
                      positions_at_risk=0, worst_hf=3.0, flash_loan_profitable=5,
                      mempool_bots=0, potential_profit_usd=3500,
                      expected_global_state="healthy", expected_action="ARBITRAGE", expected_all_clear=True,
                      notes="$3.5k Profit möglich — Arbitrage ausführen!"),

        BlockSnapshot(6, "Profit mitnehmen", chi=94, gas_pressure=18, mev_pressure=12, block_pressure=22,
                      positions_at_risk=0, worst_hf=2.8, flash_loan_profitable=3,
                      mempool_bots=0, potential_profit_usd=1800,
                      expected_global_state="healthy", expected_action="ARBITRAGE", expected_all_clear=True),
    ],
}

# ─── Szenario 5: Flash-Crash (Mai 2021) ──────────────────────────────

SCENARIO_FLASH_CRASH = {
    "name": "Flash-Crash (Mai 2021)",
    "description": "ETH fällt -40% in 15 Minuten auf Binance. "
                   "Liquidations-Kaskade auf Aave + Compound. "
                   "Gas explodiert auf 500+ gwei. Netzwerk überlastet.",
    "date": "2021-05-19",
    "blocks": [
        BlockSnapshot(0, "Normal", chi=90, gas_pressure=25, mev_pressure=15, block_pressure=30,
                      positions_at_risk=5, worst_hf=1.6, mempool_bots=1,
                      expected_global_state="healthy", expected_action="MONITOR",
                      expected_all_clear=True, notes="Normale Bedingungen."),

        BlockSnapshot(2, "ETH -15% in 5min", chi=75, gas_pressure=65, mev_pressure=58, block_pressure=72,
                      positions_at_risk=25, positions_liquidatable=8, worst_hf=0.95,
                      flash_loan_profitable=12, mempool_bots=6, potential_profit_usd=80000,
                      expected_global_state="stressed", expected_action="REDUCE",
                      expected_all_clear=False, notes="Erster Einbruch. 8 liquidierbar. REDUCE."),

        BlockSnapshot(4, "ETH -40% — 500 gwei Gas", chi=42, gas_pressure=95, mev_pressure=92,
                      block_pressure=98, mev_spike=True,
                      positions_at_risk=95, positions_liquidatable=52, worst_hf=0.28,
                      flash_loan_profitable=40, mempool_bots=18, potential_profit_usd=2_000_000,
                      expected_global_state="critical", expected_action="SHUTDOWN",
                      expected_all_clear=False, notes="Chaos! Gas 500 gwei, 52 liquidiert. SHUTDOWN!"),

        BlockSnapshot(8, "Erholung beginnt", chi=65, gas_pressure=58, mev_pressure=35, block_pressure=62,
                      positions_at_risk=60, positions_liquidatable=25, worst_hf=0.72,
                      flash_loan_profitable=8, mempool_bots=3, potential_profit_usd=50000,
                      expected_global_state="stressed", expected_action="REDUCE",
                      expected_all_clear=False, notes="Erholung sichtbar, aber 25 noch liquidierbar."),
    ],
}

# ─── Szenario 6: Aave-Zinserhöhung + Timelock (Mai 2024-Style) ──────

SCENARIO_AAVE_RATE_HIKE = {
    "name": "Aave Zinserhöhung (Mai 2024)",
    "description": "Aave Governance erhöht ETH Borrow Rate von 3% auf 5%. "
                   "48h Timelock. MEV-Bots positionieren sich. "
                   "Liquidation-Risiko steigt vor der Ausführung.",
    "date": "2024-05-15",
    "type": "governance",
    "blocks": [
        # Phase 1: Proposal detected (T-48h)
        BlockSnapshot(0, "T-48h: Proposal detected", chi=92, gas_pressure=30, mev_pressure=25,
                      positions_at_risk=3, worst_hf=1.6, mempool_bots=1,
                      pending_timelocks=[{"action": "setReserveBorrowRate", "hours_until_executable": 48, "impact_score": 7}],
                      hours_until_next_timelock=48,
                      expected_global_state="healthy", expected_action="MONITOR", expected_all_clear=True,
                      notes="Rate-Hike erkannt, aber noch 48h Zeit. Monitoring reicht."),

        # Phase 2: T-24h — MEV-Bots werden aktiv
        BlockSnapshot(24, "T-24h: MEV-Bots erwachen", chi=88, gas_pressure=45, mev_pressure=48,
                      positions_at_risk=8, positions_liquidatable=1, worst_hf=1.25,
                      mempool_bots=3, flash_loan_profitable=3, potential_profit_usd=15000,
                      pending_timelocks=[{"action": "setReserveBorrowRate", "hours_until_executable": 24, "impact_score": 7}],
                      hours_until_next_timelock=24,
                      expected_global_state="caution", expected_action="REDUCE", expected_all_clear=False,
                      notes="T-24h: MEV-Druck steigt. Agent sollte Positionen REDUCE empfehlen."),

        # Phase 3: T-6h — Kritische Phase
        BlockSnapshot(42, "T-6h: Vorbereitung kritisch", chi=82, gas_pressure=62, mev_pressure=58,
                      positions_at_risk=22, positions_liquidatable=5, worst_hf=1.08,
                      mempool_bots=5, flash_loan_profitable=8, potential_profit_usd=80000,
                      pending_timelocks=[{"action": "setReserveBorrowRate", "hours_until_executable": 6, "impact_score": 7}],
                      hours_until_next_timelock=6,
                      expected_global_state="stressed", expected_action="REDUCE", expected_all_clear=False,
                      notes="T-6h: 5 Positionen nahe Liquidation. Agent MUSS REDUCE."),

        # Phase 4: T-0 — Execution
        BlockSnapshot(48, "T-0: Rate-Änderung ausgeführt", chi=78, gas_pressure=75, mev_pressure=72,
                      mev_spike=True,
                      positions_at_risk=35, positions_liquidatable=12, worst_hf=0.92,
                      mempool_bots=8, flash_loan_profitable=15, potential_profit_usd=250000,
                      pending_timelocks=[{"action": "setReserveBorrowRate", "hours_until_executable": 0, "impact_score": 7}],
                      hours_until_next_timelock=0,
                      expected_global_state="critical", expected_action="SHUTDOWN", expected_all_clear=False,
                      notes="Rate-Hike executed! 12 Positionen liquidierbar. Agent muss im SHUTDOWN sein."),

        # Phase 5: T+24h — Nachwehen
        BlockSnapshot(72, "T+24h: Markt passt sich an", chi=84, gas_pressure=50, mev_pressure=40,
                      positions_at_risk=18, positions_liquidatable=4, worst_hf=1.05,
                      mempool_bots=3, flash_loan_profitable=4,
                      hours_until_next_timelock=9999,
                      expected_global_state="caution", expected_action="MONITOR", expected_all_clear=True,
                      notes="Markt beginnt sich anzupassen. Agent kann entspannen."),
    ],
}

# ─── Szenario 7: ARB Token Unlock (März 2024-Style) ─────────────────

SCENARIO_ARB_UNLOCK = {
    "name": "ARB Token Unlock (März 2024)",
    "description": "1.1B ARB tokens unlock over 48 months. Monthly cliff unlocks of ~23M ARB. "
                   "Historical pattern: 20% sold within 24h of unlock → $4M sell pressure. "
                   "Arbitrage opportunity: buy the dip on DEX after unlock.",
    "date": "2024-03-16",
    "type": "governance",
    "blocks": [
        BlockSnapshot(0, "T-7d: Unlock in 7 Tagen", chi=93, gas_pressure=28, mev_pressure=18,
                      positions_at_risk=2, worst_hf=1.8, mempool_bots=1,
                      upcoming_unlocks=[{"token": "ARB", "amount": 23_000_000, "amount_usd": 19_500_000, "days_until": 7}],
                      days_until_next_unlock=7,
                      expected_global_state="healthy", expected_action="MONITOR", expected_all_clear=True,
                      notes="Unlock in 7 Tagen — noch keine Aktion nötig."),

        BlockSnapshot(3, "T-72h: Vorbereitung", chi=91, gas_pressure=35, mev_pressure=30,
                      upcoming_unlocks=[{"token": "ARB", "amount": 23_000_000, "amount_usd": 19_500_000, "days_until": 3}],
                      days_until_next_unlock=3,
                      expected_global_state="healthy", expected_action="MONITOR", expected_all_clear=True,
                      notes="72h vor Unlock. Kurse noch stabil. Hedge-Strategie evaluieren."),

        BlockSnapshot(6, "T-24h: ARB beginnt zu fallen", chi=85, gas_pressure=48, mev_pressure=45,
                      positions_at_risk=8, positions_liquidatable=2, worst_hf=1.15,
                      mempool_bots=3, flash_loan_profitable=5, potential_profit_usd=35000,
                      upcoming_unlocks=[{"token": "ARB", "amount": 23_000_000, "amount_usd": 19_500_000, "days_until": 1}],
                      days_until_next_unlock=1,
                      expected_global_state="caution", expected_action="REDUCE", expected_all_clear=False,
                      notes="T-24h: ARB -5%. Pre-Unlock-Druck beginnt. Agent sollte ARB-Exposure REDUCE."),

        BlockSnapshot(7, "Unlock-Tag: ARB -12%", chi=78, gas_pressure=65, mev_pressure=62,
                      positions_at_risk=25, positions_liquidatable=8, worst_hf=0.88,
                      mempool_bots=6, flash_loan_profitable=12, potential_profit_usd=120000,
                      upcoming_unlocks=[{"token": "ARB", "amount": 23_000_000, "amount_usd": 17_000_000, "days_until": 0}],
                      days_until_next_unlock=30,
                      expected_global_state="stressed", expected_action="REDUCE", expected_all_clear=False,
                      notes="Unlock-Tag! +$4M Verkaufsdruck. ARB -12%. Flash-Loans möglich, aber riskant."),

        BlockSnapshot(8, "T+24h: Erholung beginnt", chi=82, gas_pressure=42, mev_pressure=35,
                      positions_at_risk=15, positions_liquidatable=3, worst_hf=1.02,
                      mempool_bots=2, flash_loan_profitable=6, potential_profit_usd=45000,
                      days_until_next_unlock=30,
                      expected_global_state="caution", expected_action="MONITOR", expected_all_clear=True,
                      notes="T+24h: ARB erholt sich. DEX-Arbitrage war profitabel. Agent kann wieder MONITOR."),
    ],
}

# ─── Szenario 8: Compound Collateral-Faktor-Änderung ─────────────────

SCENARIO_COMPOUND_CF_CHANGE = {
    "name": "Compound WBTC Collateral-Änderung",
    "description": "Compound Governance senkt WBTC Collateral Factor von 80% auf 70%. "
                   "48h Timelock. Betroffene User haben $200M+ in WBTC-Positionen. "
                   "Ohne Vorbereitung werden viele Positionen unter Wasser geraten.",
    "date": "2024-08-01",
    "type": "governance",
    "blocks": [
        BlockSnapshot(0, "T-48h: Proposal passed", chi=90, gas_pressure=32, mev_pressure=22,
                      positions_at_risk=5, worst_hf=1.45, mempool_bots=1,
                      pending_timelocks=[{"action": "setCollateralFactor", "hours_until_executable": 48, "impact_score": 8}],
                      hours_until_next_timelock=48,
                      expected_global_state="healthy", expected_action="MONITOR", expected_all_clear=True,
                      notes="CF-Änderung erkannt. 48h Zeit. Noch kein Grund zur Panik."),

        BlockSnapshot(24, "T-24h: Erste Positionen wackeln", chi=84, gas_pressure=40, mev_pressure=38,
                      positions_at_risk=15, positions_liquidatable=3, worst_hf=1.12,
                      mempool_bots=2,
                      pending_timelocks=[{"action": "setCollateralFactor", "hours_until_executable": 24, "impact_score": 8}],
                      hours_until_next_timelock=24,
                      expected_global_state="caution", expected_action="REDUCE", expected_all_clear=False,
                      notes="T-24h: 3 Positionen nahe Liquidation. Agent MUSS WBTC-User warnen."),

        BlockSnapshot(40, "T-8h: Vor der Ausführung", chi=76, gas_pressure=58, mev_pressure=55,
                      positions_at_risk=35, positions_liquidatable=12, worst_hf=0.95,
                      mempool_bots=5, flash_loan_profitable=10, potential_profit_usd=120000,
                      pending_timelocks=[{"action": "setCollateralFactor", "hours_until_executable": 8, "impact_score": 8}],
                      hours_until_next_timelock=8,
                      expected_global_state="stressed", expected_action="REDUCE", expected_all_clear=False,
                      notes="T-8h: 12 Positionen werden liquidierbar nach CF-Change. Dringend REDUCE."),

        BlockSnapshot(48, "T-0: CF-Änderung live", chi=68, gas_pressure=72, mev_pressure=68,
                      mev_spike=True,
                      positions_at_risk=60, positions_liquidatable=28, worst_hf=0.72,
                      mempool_bots=9, flash_loan_profitable=18, potential_profit_usd=350000,
                      pending_timelocks=[{"action": "setCollateralFactor", "hours_until_executable": 0, "impact_score": 8}],
                      hours_until_next_timelock=0,
                      expected_global_state="critical", expected_action="SHUTDOWN", expected_all_clear=False,
                      notes="CF-Change executed! 28 Positionen unter Wasser. SHUTDOWN!"),

        BlockSnapshot(56, "T+8h: Liquidations-Welle", chi=72, gas_pressure=55, mev_pressure=42,
                      positions_at_risk=45, positions_liquidatable=18, worst_hf=0.81,
                      mempool_bots=4, flash_loan_profitable=8, potential_profit_usd=80000,
                      hours_until_next_timelock=9999,
                      expected_global_state="stressed", expected_action="REDUCE", expected_all_clear=False,
                      notes="Noch 18 liquidierbar. Agent sollte REDUCE halten."),
    ],
}

ALL_SCENARIOS = [
    SCENARIO_TERRA_CRASH,
    SCENARIO_FTX_COLLAPSE,
    SCENARIO_SVB_CRISIS,
    SCENARIO_BULL_RUN,
    SCENARIO_FLASH_CRASH,
    SCENARIO_AAVE_RATE_HIKE,
    SCENARIO_ARB_UNLOCK,
    SCENARIO_COMPOUND_CF_CHANGE,
]


# ═══════════════════════════════════════════════════════════════════════
# BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class BlockResult:
    """Ergebnis eines einzelnen Block-Backtests."""
    block: int
    label: str
    expected_state: str
    actual_state: str
    expected_action: str
    actual_actions: list[str]
    match: bool  # State matched?
    action_correct: bool  # Action matched?
    all_clear_match: bool  # GO/NO-GO matched?
    response_delay: int = 0  # Blöcke bis zur ersten korrekten Reaktion
    profit_saved_usd: float = 0.0
    false_positive: bool = False


@dataclass
class ScenarioResult:
    """Ergebnis eines kompletten Szenario-Backtests."""
    scenario_name: str
    date: str
    total_blocks: int
    state_accuracy: float  # % State korrekt
    action_precision: float  # % Actions korrekt
    recall_critical: float  # % kritische Events erkannt
    avg_response_delay: float  # Ø Blöcke bis Reaktion
    total_profit_saved_usd: float
    false_positives: int
    false_negatives: int
    block_results: list[dict]
    grade: str  # A-F
    summary: str


class BacktestRunner:
    """Replayed Szenarien und bewertet Agent-X-Entscheidungen."""

    def __init__(self):
        self.results: list[ScenarioResult] = []

    def run_all(self) -> list[ScenarioResult]:
        for scenario in ALL_SCENARIOS:
            result = self.run_scenario(scenario)
            self.results.append(result)
        return self.results

    def run_scenario(self, scenario: dict) -> ScenarioResult:
        """Führt ein Szenario Block für Block aus."""
        self._reset_agent()  # Neuer Agent für neues Szenario
        name = scenario["name"]
        date = scenario["date"]
        blocks = scenario["blocks"]
        block_results = []
        first_critical_block = None
        agent_reacted_at = None

        states_correct = 0
        actions_correct = 0
        false_positives = 0
        false_negatives = 0
        total_profit = 0.0

        for snap in blocks:
            # Evaluiere Agent X mit diesen Parametern
            decision = self._evaluate_snapshot(snap)
            ud = decision.get("unified_decision", {})
            sig = decision.get("class_signals", {})

            actual_state = ud.get("global_state", "unknown")
            actual_actions = [r["action"] for r in ud.get("recommended_actions", [])]

            # State match
            state_match = actual_state == snap.expected_global_state

            # Action match (fuzzy — z.B. SHUTDOWN matched EMERGENCY_SHUTDOWN)
            action_aliases = {
                "SHUTDOWN": ["SHUTDOWN", "EMERGENCY_SHUTDOWN"],
                "REDUCE": ["REDUCE", "REDUCE_EXPOSURE"],
                "ARBITRAGE": ["ARBITRAGE", "EXECUTE_ARBITRAGE"],
                "LIQUIDATE": ["LIQUIDATE", "LIQUIDATE_WATCHLIST"],
                "MONITOR": ["MONITOR"],
            }
            expected_aliases = action_aliases.get(snap.expected_action, [snap.expected_action])
            action_match = any(
                any(alias in actual for alias in expected_aliases)
                for actual in actual_actions
            )

            # All-Clear match
            all_clear = ud.get("scenario", {}).get("all_clear", False)
            all_clear_match = all_clear == snap.expected_all_clear

            # Kritische Events (SHUTDOWN oder REDUCE erwartet)
            is_critical = snap.expected_action in ("SHUTDOWN", "REDUCE")
            is_critical_actual = any(
                any(alias in a for alias in ("SHUTDOWN", "EMERGENCY", "REDUCE"))
                for a in actual_actions
            )

            # Response-Delay
            if is_critical and first_critical_block is None:
                first_critical_block = snap.block

            if is_critical and is_critical_actual and agent_reacted_at is None:
                agent_reacted_at = snap.block

            # False positive: Agent triggered ALARM but nothing was wrong
            fp = (not is_critical and is_critical_actual)
            # False negative: Something WAS wrong but Agent didn't react
            fn = (is_critical and not is_critical_actual)

            if fp:
                false_positives += 1
            if fn:
                false_negatives += 1

            if state_match:
                states_correct += 1
            if action_match:
                actions_correct += 1

            # Profit saved: Wenn Agent SHUTDOWN/REDUCE rechtzeitig → Kapital geschützt
            if is_critical_actual and snap.positions_liquidatable > 0:
                saved = snap.positions_liquidatable * 5000  # ~$5k pro geretteter Position
                total_profit += saved

            response_delay = (agent_reacted_at - first_critical_block
                            if first_critical_block and agent_reacted_at else -1)

            block_results.append({
                "block": snap.block,
                "label": snap.label,
                "expected_state": snap.expected_global_state,
                "actual_state": actual_state,
                "expected_action": snap.expected_action,
                "actual_actions": actual_actions,
                "state_match": state_match,
                "action_match": action_match,
                "all_clear_match": all_clear_match,
                "false_positive": fp,
                "false_negative": fn,
                "global_state_score": ud.get("global_state_score", 0),
            })

        n = len(blocks)
        state_acc = states_correct / n * 100 if n else 0
        action_prec = actions_correct / n * 100 if n else 0
        recall_crit = (n - false_negatives) / n * 100 if n else 0
        avg_delay = (agent_reacted_at - first_critical_block
                    if first_critical_block and agent_reacted_at else n)

        grade = self._compute_grade(state_acc, action_prec, recall_crit, false_positives)

        return ScenarioResult(
            scenario_name=name,
            date=date,
            total_blocks=n,
            state_accuracy=round(state_acc, 1),
            action_precision=round(action_prec, 1),
            recall_critical=round(recall_crit, 1),
            avg_response_delay=avg_delay,
            total_profit_saved_usd=round(total_profit, 2),
            false_positives=false_positives,
            false_negatives=false_negatives,
            block_results=block_results,
            grade=grade,
            summary=self._generate_summary(name, state_acc, action_prec, recall_crit,
                                           avg_delay, false_positives, false_negatives, grade),
        )

    def _evaluate_snapshot(self, snap: BlockSnapshot) -> dict:
        """Führt die vollständige 4-Klassen-Evaluierung für einen Snapshot durch."""
        import time
        from agent_x_orchestrator import SymbolicsAgent

        # Position-Daten aus Snapshot
        positions = []
        total_positions = max(snap.positions_liquidatable, snap.positions_at_risk)
        for i in range(total_positions):
            if i < snap.positions_liquidatable:
                hf = snap.worst_hf
            elif i < snap.positions_at_risk:
                hf = min(snap.worst_hf + 0.15, 1.50) if snap.worst_hf != float("inf") else 1.15
            else:
                hf = 1.5
            positions.append({
                "user_address": f"0xVictim{i}",
                "health_factor": round(hf, 3),
                "total_debt_usd": 10000 + i * 5000,
            })

        flash_loans = []
        for i in range(snap.flash_loan_profitable):
            flash_loans.append({
                "tx_hash": f"0xfl{i}",
                "protocol": "AaveV3",
                "net_profit_usd": snap.potential_profit_usd / max(1, snap.flash_loan_profitable),
                "profitable": True,
            })

        cross_pool = []
        for i in range(snap.cross_pool_ops):
            cross_pool.append({
                "id": f"cp{i}",
                "net_profit_usd": snap.potential_profit_usd / max(1, snap.cross_pool_ops or 1),
                "executable": True,
            })

        now_unix = time.time()
        eth_slots = [
            {"slot": 9_000_000 + snap.block + i, "proposer_index": f"v_{100+i}",
             "unix_timestamp": now_unix + i * 12, "offset_ms": i * 12000}
            for i in range(10)
        ]

        # Verwende denselben Agent für das gesamte Szenario (graduelle Transition)
        agent = getattr(self, "_agent", None)
        if agent is None:
            agent = SymbolicsAgent(capital=100_000)
            self._agent = agent

        return agent.evaluate(
            consensus_health_index=snap.chi,
            exit_queue_length=snap.exit_queue,
            participation_rate=snap.participation_rate,
            finality_status=snap.finality_status,
            reorg_depth=snap.reorg_depth,
            eth_slots=eth_slots,
            sol_slots=None,
            trusted_validators=snap.trusted_validators if snap.trusted_validators else None,
            gas_pressure_index=snap.gas_pressure,
            mev_pressure_index=snap.mev_pressure,
            block_pressure_index=snap.block_pressure,
            basefee_current_gwei=snap.basefee_gwei,
            priority_fee_p95_gwei=snap.pf_p95_gwei,
            mev_spike_detected=snap.mev_spike,
            health_factors=positions if positions else None,
            flash_loan_opportunities=flash_loans if flash_loans else None,
            mempool_bots_count=snap.mempool_bots,
            cross_pool_opportunities=cross_pool if cross_pool else None,
            pending_timelocks=snap.pending_timelocks if snap.pending_timelocks else None,
            upcoming_unlocks=snap.upcoming_unlocks if snap.upcoming_unlocks else None,
            active_proposals=snap.active_proposals if snap.active_proposals else None,
        )

    def _reset_agent(self):
        """Setzt den Agenten für ein neues Szenario zurück."""
        self._agent = None

    def _compute_grade(self, state_acc, action_prec, recall_crit, fp):
        score = (state_acc * 0.3 + action_prec * 0.35 + recall_crit * 0.35)
        if fp > 2:
            score -= fp * 3
        score = max(0, min(100, score))
        if score >= 90: return "A+"
        elif score >= 80: return "A"
        elif score >= 70: return "B"
        elif score >= 60: return "C"
        elif score >= 50: return "D"
        else: return "F"

    def _generate_summary(self, name, sa, ap, rc, delay, fp, fn, grade):
        lines = []
        lines.append(f"Szenario: {name}")
        lines.append(f"Grade: {grade}")
        lines.append(f"State Accuracy: {sa:.1f}%")
        lines.append(f"Action Precision: {ap:.1f}%")
        lines.append(f"Critical Recall: {rc:.1f}%")

        if delay >= 0:
            lines.append(f"Response Delay: {delay} Blöcke")
        else:
            lines.append("Response Delay: N/A (kein kritisches Event)")

        if fp > 0:
            lines.append(f"⚠️ False Positives: {fp} (Agent hat fälschlich Alarm ausgelöst)")
        if fn > 0:
            lines.append(f"❌ False Negatives: {fn} (Agent hat Krise NICHT erkannt!)")

        if grade in ("A+", "A"):
            lines.append("✅ Agent X hätte diese Krise GEMEISTERT.")
        elif grade in ("B", "C"):
            lines.append("⚠️ Agent X hätte teilweise reagiert — Optimierung nötig.")
        else:
            lines.append("❌ Agent X hätte VERSAGT — kritische Schwachstelle!")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# REPORT GENERATOR
# ═══════════════════════════════════════════════════════════════════════

def generate_report(results: list[ScenarioResult]) -> str:
    """Erstellt einen vollständigen Backtest-Report."""
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    lines = []
    lines.append(f"{BOLD}{CYAN}{'═' * 70}{RESET}")
    lines.append(f"{BOLD}{CYAN}  AGENT X — BACKTEST REPORT{RESET}")
    lines.append(f"{BOLD}{CYAN}  {datetime.now(timezone.utc).isoformat()[:19]} UTC{RESET}")
    lines.append(f"{BOLD}{CYAN}{'═' * 70}{RESET}")
    lines.append("")

    # Gesamtscore
    avg_grade_score = 0
    total_profit = 0
    total_fp = 0
    total_fn = 0
    for r in results:
        grade_map = {"A+": 100, "A": 90, "B": 75, "C": 60, "D": 45, "F": 20}
        avg_grade_score += grade_map.get(r.grade, 50)
        total_profit += r.total_profit_saved_usd
        total_fp += r.false_positives
        total_fn += r.false_negatives

    avg_score = avg_grade_score / len(results) if results else 0
    overall = "A" if avg_score >= 90 else "B" if avg_score >= 75 else "C" if avg_score >= 60 else "D" if avg_score >= 45 else "F"

    color = GREEN if overall in ("A", "A+") else YELLOW if overall in ("B", "C") else RED
    lines.append(f"  {BOLD}GESAMTNOTE:{RESET} {color}{overall} ({avg_score:.0f}/100){RESET}")
    lines.append(f"  Hypothetisch gerettet: {GREEN}${total_profit:,.0f}{RESET}")
    lines.append(f"  False Positives: {YELLOW}{total_fp}{RESET}  |  False Negatives: {RED}{total_fn}{RESET}")
    lines.append("")

    # Szenario-Tabelle
    lines.append(f"{BOLD}  {'Szenario':<35} {'Blöcke':<7} {'State':<7} {'Action':<7} {'Recall':<7} {'Delay':<7} {'Grade':<5}{RESET}")
    lines.append(f"  {'─' * 75}")

    for r in results:
        g = r.grade
        gc = GREEN if g in ("A+", "A") else YELLOW if g in ("B", "C") else RED
        lines.append(
            f"  {r.scenario_name[:34]:<35} {r.total_blocks:<7} "
            f"{r.state_accuracy:<7.1f} {r.action_precision:<7.1f} "
            f"{r.recall_critical:<7.1f} {r.avg_response_delay:<7} {gc}{g:<5}{RESET}"
        )

    lines.append("")
    lines.append(f"{BOLD}{'─' * 70}{RESET}")
    lines.append(f"{BOLD}  DETAILS PRO SZENARIO{RESET}")
    lines.append(f"{BOLD}{'─' * 70}{RESET}")

    for r in results:
        lines.append("")
        lines.append(f"  {BOLD}{r.scenario_name}{RESET} ({r.date})")
        lines.append(f"  Grade: {GREEN if r.grade in ('A+','A') else YELLOW if r.grade in ('B','C') else RED}{r.grade}{RESET}")
        lines.append(f"  {r.summary.replace(chr(10), chr(10) + '  ')}")
        lines.append(f"  Profit gerettet: ${r.total_profit_saved_usd:,.0f}")

        # Timeline
        lines.append(f"\n  {BOLD}Block-Timeline:{RESET}")
        for br in r.block_results:
            icon = "✅" if br["state_match"] else "❌"
            lines.append(
                f"    B{br['block']:>3d} {icon} State={br['actual_state']:<10s} "
                f"(expected={br['expected_state']:<10s}) "
                f"Action={'OK' if br['action_match'] else 'MISS'}"
                f"{' ⚡FP' if br['false_positive'] else ''}"
                f"{' 🔴FN' if br['false_negative'] else ''}"
            )

    lines.append("")
    lines.append(f"{BOLD}{CYAN}{'═' * 70}{RESET}")
    lines.append(f"{BOLD}{CYAN}  KEY FINDINGS{RESET}")
    lines.append(f"{BOLD}{CYAN}{'═' * 70}{RESET}")

    # Key findings
    if total_fn > 0:
        lines.append(f"  {RED}❌ KRITISCH: {total_fn} False Negatives — Agent erkennt Krisen nicht zuverlässig!{RESET}")
        lines.append(f"     → Critical-Threshold senken oder Gas-Pressure-Gewichtung erhöhen")
    if total_fp > 3:
        lines.append(f"  {YELLOW}⚠️ {total_fp} False Positives — Agent zu empfindlich{RESET}")
        lines.append(f"     → MIN_CHI_FOR_HF_WARNING erhöhen oder MEV-Pressure-Threshold anheben")
    if avg_score >= 85:
        lines.append(f"  {GREEN}✅ Agent X besteht alle Szenarien mit Bravour{RESET}")
        lines.append(f"     → Bereit für Live-Test mit Paper-Trading")
    if total_profit > 1_000_000:
        lines.append(f"  {GREEN}💰 ${total_profit:,.0f} hypothetisch gerettet{RESET}")
        lines.append(f"     → Selbst bei einem großen Crash schützt Agent X signifikantes Kapital")
    if avg_score < 60:
        lines.append(f"  {RED}❌ Agent X IST NICHT PRODUKTIONSBEREIT{RESET}")
        lines.append(f"     → Dringende Optimierung der Conditional Logic erforderlich")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agent X — Backtesting Suite")
    parser.add_argument("--scenario", choices=["terra", "ftx", "svb", "bull", "flash", "aave", "arb", "compound", "governance", "all"],
                        default="all", help="Szenario auswählen (default: all)")
    parser.add_argument("--report", action="store_true", help="Nur Gesamt-Report")
    parser.add_argument("--json", action="store_true", help="JSON-Output")
    args = parser.parse_args()

    runner = BacktestRunner()

    scenario_map = {
        "terra": [SCENARIO_TERRA_CRASH],
        "ftx": [SCENARIO_FTX_COLLAPSE],
        "svb": [SCENARIO_SVB_CRISIS],
        "bull": [SCENARIO_BULL_RUN],
        "flash": [SCENARIO_FLASH_CRASH],
        "aave": [SCENARIO_AAVE_RATE_HIKE],
        "arb": [SCENARIO_ARB_UNLOCK],
        "compound": [SCENARIO_COMPOUND_CF_CHANGE],
        "governance": [SCENARIO_AAVE_RATE_HIKE, SCENARIO_ARB_UNLOCK, SCENARIO_COMPOUND_CF_CHANGE],
        "all": ALL_SCENARIOS,
    }

    selected = scenario_map.get(args.scenario, ALL_SCENARIOS)
    results = []
    for scenario in selected:
        result = runner.run_scenario(scenario)
        results.append(result)

    if args.json:
        output = []
        for r in results:
            output.append({
                "scenario": r.scenario_name,
                "date": r.date,
                "grade": r.grade,
                "state_accuracy": r.state_accuracy,
                "action_precision": r.action_precision,
                "recall_critical": r.recall_critical,
                "avg_response_delay": r.avg_response_delay,
                "total_profit_saved_usd": r.total_profit_saved_usd,
                "false_positives": r.false_positives,
                "false_negatives": r.false_negatives,
                "block_results": r.block_results,
            })
        print(json.dumps(output, indent=2))
    else:
        report = generate_report(results)
        print(report)

    # Exit-Code: Fehlschlag wenn F-Grade
    has_failing = any(r.grade == "F" for r in results)
    sys.exit(1 if has_failing else 0)
