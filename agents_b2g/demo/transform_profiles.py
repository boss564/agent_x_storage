"""Demo Transform Profiles — Differentiated rates per agent.

Each agent applies DIFFERENT fees, retentions, and aggregations.
This creates visibly different numbers at each pipeline step —
the core of the investor/commune pitch demo.

The 9 agents are organized in 3 acts:
  Act 1 — DePIN & Hardware (A1–A3): Micro-transactions, 0.01%-0.1% fees
  Act 2 — Z3 Legal Engine (A4–A6): VOB/B settlement, 5% retention, 15% tax
  Act 3 — Dynamic Tokenomics (A7–A9): Mint, burn, stake, treasury
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class TransformProfile:
    """How one agent transforms input volume into output volume."""
    agent_id: str
    agent_name: str
    act: int
    act_name: str
    emoji: str
    description: str
    # Transformation parameters
    fee_rate: float          # Fraction of input taken as fee
    retention_rate: float    # Fraction of input retained (escrow, lockup)
    burn_rate: float = 0.0   # Fraction destroyed
    aggregation: int = 1     # N events → 1 batch
    # Subagent definitions
    subagents: List[str] = field(default_factory=list)
    # API endpoints
    endpoints: List[str] = field(default_factory=list)


# ── The 9 Profiles — Different for Every Agent ─────────────────────────────

PROFILES: Dict[str, TransformProfile] = {
    # ═══════════ ACT 1: DePIN & Hardware ═══════════
    "A1_Sensor_Ingest": TransformProfile(
        agent_id="A1",
        agent_name="Sensor-Ingest-Agent",
        act=1,
        act_name="DePIN & Hardware",
        emoji="📡",
        description="Empfängt Rohdaten von ESP32 (MQTT), validiert Signaturen, aggregiert 100:1 zu Batches",
        fee_rate=0.0001,       # 0.01% Gas fee
        retention_rate=0.0,
        aggregation=100,
        subagents=["MQTT-Listener", "Validator", "Batcher"],
        endpoints=["POST /telemetry/mqtt", "POST /telemetry/validate", "POST /telemetry/batch"],
    ),
    "A2_Bridge_Relayer": TransformProfile(
        agent_id="A2",
        agent_name="Bridge-Relayer-Agent",
        act=1,
        act_name="DePIN & Hardware",
        emoji="🔗",
        description="Erstellt Merkle-Proofs, synchronisiert State zwischen Chains, simuliert Latenz",
        fee_rate=0.0005,       # 0.05% bridge fee
        retention_rate=0.0,
        aggregation=1,
        subagents=["Proof-Generator", "State-Syncer", "Latency-Simulator"],
        endpoints=["POST /bridge/proof", "POST /bridge/sync"],
    ),
    "A3_DePIN_Wallet": TransformProfile(
        agent_id="A3",
        agent_name="DePIN-Wallet-Agent",
        act=1,
        act_name="DePIN & Hardware",
        emoji="💳",
        description="Führt Mikro-Payouts durch, gleicht Wallet-Bestände aus, aggregiert Übersicht",
        fee_rate=0.001,        # 0.1% wallet fee
        retention_rate=0.0,
        aggregation=1,
        subagents=["Payout-Manager", "Balancer", "Aggregator"],
        endpoints=["POST /wallet/payout", "POST /wallet/balance", "GET /wallet/summary"],
    ),

    # ═══════════ ACT 2: Z3 Legal Engine ═══════════
    "A4_VOB_Settlement": TransformProfile(
        agent_id="A4",
        agent_name="VOB-Settlement-Agent",
        act=2,
        act_name="Z3 Legal Engine",
        emoji="⚖️",
        description="Führt Z3-Proof durch, teilt Brutto in Netto/Steuer/Einbehalt, verwaltet Escrow",
        fee_rate=0.005,        # 0.5% settlement fee
        retention_rate=0.05,   # 5% security retention (VOB/B §17)
        aggregation=1,
        subagents=["Z3-Prover", "Multi-Splitter", "Escrow-Manager"],
        endpoints=["POST /z3/prove", "POST /settlement/split", "POST /escrow/lock"],
    ),
    "A5_Legal_Compliance": TransformProfile(
        agent_id="A5",
        agent_name="Legal-Compliance-Agent",
        act=2,
        act_name="Z3 Legal Engine",
        emoji="📂",
        description="GoBD-WORM-Archivierung, §48b-Bauabzugssteuer (15%), Audit-Trail",
        fee_rate=0.0,          # no fee — this is a mandatory compliance function
        retention_rate=0.15,   # 15% construction withholding tax (§48b EStG)
        aggregation=1,
        subagents=["GoBD-Archiver", "Tax-Calculator", "Audit-Trail"],
        endpoints=["POST /compliance/archive", "POST /compliance/tax", "GET /compliance/audit"],
    ),
    "A6_Settlement_Executor": TransformProfile(
        agent_id="A6",
        agent_name="Settlement-Executor-Agent",
        act=2,
        act_name="Z3 Legal Engine",
        emoji="💵",
        description="Führt finale Aufteilung durch, gibt Einbehalt nach 4 Jahren frei, prüft BHO Δ=0",
        fee_rate=0.01,         # 1% execution fee
        retention_rate=0.0,
        aggregation=1,
        subagents=["Multi-Splitter", "Escrow-Handler", "BHO-Checker"],
        endpoints=["POST /executor/split", "POST /executor/release", "POST /executor/bho"],
    ),

    # ═══════════ ACT 3: Dynamic Tokenomics ═══════════
    "A7_Token_Minter": TransformProfile(
        agent_id="A7",
        agent_name="Token-Minter-Agent",
        act=3,
        act_name="Dynamic Tokenomics",
        emoji="🪙",
        description="Prägt Tokens aus Settlement-Erlösen, verbrennt 0.5% Supply, zieht System-Gebühr",
        fee_rate=0.02,         # 2% mint fee
        retention_rate=0.0,
        burn_rate=0.005,       # 0.5% burn
        aggregation=1,
        subagents=["Minter", "Burner", "Fee-Collector"],
        endpoints=["POST /token/mint", "POST /token/burn", "POST /token/fee"],
    ),
    "A8_Staking_Pool": TransformProfile(
        agent_id="A8",
        agent_name="Staking-Pool-Agent",
        act=3,
        act_name="Dynamic Tokenomics",
        emoji="🏦",
        description="Sperrt 80% der Tokens (Lockup), berechnet 12% APY, verwaltet Unstaking-Queue",
        fee_rate=0.0,          # no fee
        retention_rate=0.80,   # 80% lockup
        burn_rate=0.0,
        aggregation=1,
        subagents=["Lockup-Manager", "Yield-Calculator", "Unstaking-Queue"],
        endpoints=["POST /staking/lock", "POST /staking/yield", "POST /staking/unlock"],
    ),
    "A9_Treasury_Governance": TransformProfile(
        agent_id="A9",
        agent_name="Treasury-&-Governance-Agent",
        act=3,
        act_name="Dynamic Tokenomics",
        emoji="🛡️",
        description="Verwaltet Reserve-Fonds (2%), gewichtet Governance-Stimmen, Notfall-Stopp",
        fee_rate=0.02,         # 2% treasury fee
        retention_rate=0.0,
        burn_rate=0.0,
        aggregation=1,
        subagents=["Reserve-Manager", "Vote-Weighting", "Emergency-Break"],
        endpoints=["POST /treasury/reserve", "POST /governance/vote", "POST /emergency/halt"],
    ),
}


def get_profile(agent_key: str) -> TransformProfile:
    """Get a single agent's transform profile."""
    if agent_key not in PROFILES:
        raise KeyError(f"Unknown agent '{agent_key}'. Valid: {list(PROFILES.keys())}")
    return PROFILES[agent_key]


def get_act(act_number: int) -> List[TransformProfile]:
    """Get all profiles for an act."""
    return [p for p in PROFILES.values() if p.act == act_number]
