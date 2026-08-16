"""Die 9 konkreten Wirtschaftsagenten (Baustein 3)."""
from agents_b2g.wirtschaft.base import WirtschaftAgent
from agents_b2g.wirtschaft.profiles import profil_fuer
from agents_b2g.wirtschaft.subagents import (
    PoolManager, GasBank, ReserveManager, YieldCalculator,
    StakingContract, RewardDistributor, MintEngine, SupplyOracle,
    LedgerCommitter, SettlementVerifier, GasPricer, FeeCollector,
    BurnVerifier, DeflationController, PolicyStore, ComplianceEngine,
    RiskScorer, AnomalyDetector,
)


class _WirtschaftAgentBase(WirtschaftAgent):
    """Shared: wire the competence profile on construction."""
    AGENT_NAME = None

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        if self.AGENT_NAME:
            self.competence = profil_fuer(self.AGENT_NAME)


# --- Klasse A ---

class LiquidityAgent(_WirtschaftAgentBase):
    AGENT_NAME = "liquidity"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.pool_manager = PoolManager(parent=self)
        self.gas_bank = GasBank(parent=self)


class TreasuryAgent(_WirtschaftAgentBase):
    AGENT_NAME = "treasury"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.reserve_manager = ReserveManager(parent=self)
        self.yield_calculator = YieldCalculator(parent=self)


class StakingAgent(_WirtschaftAgentBase):
    AGENT_NAME = "staking"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.staking_contract = StakingContract(parent=self)
        self.reward_distributor = RewardDistributor(parent=self)


# --- Klasse B ---

class MinterAgent(_WirtschaftAgentBase):
    AGENT_NAME = "minter"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.mint_engine = MintEngine(parent=self)
        self.supply_oracle = SupplyOracle(parent=self)


class SettlementAgent(_WirtschaftAgentBase):
    AGENT_NAME = "settlement"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.ledger_committer = LedgerCommitter(parent=self)
        self.settlement_verifier = SettlementVerifier(parent=self)


class PaymasterAgent(_WirtschaftAgentBase):
    AGENT_NAME = "paymaster"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.gas_pricer = GasPricer(parent=self)
        self.fee_collector = FeeCollector(parent=self)


# --- Klasse C ---

class BurnAgent(_WirtschaftAgentBase):
    AGENT_NAME = "burn"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.burn_verifier = BurnVerifier(parent=self)
        self.deflation_controller = DeflationController(parent=self)


class RetentionAgent(_WirtschaftAgentBase):
    AGENT_NAME = "retention"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.policy_store = PolicyStore(parent=self)
        self.compliance_engine = ComplianceEngine(parent=self, policy=self.policy_store)


class RiskAuditorAgent(_WirtschaftAgentBase):
    AGENT_NAME = "risk_auditor"

    def __init__(self, agent_id, **kwargs):
        super().__init__(agent_id, **kwargs)
        self.risk_scorer = RiskScorer(parent=self)
        self.anomaly_detector = AnomalyDetector(parent=self)


AGENT_CLASSES = {
    "liquidity": LiquidityAgent, "treasury": TreasuryAgent, "staking": StakingAgent,
    "minter": MinterAgent, "settlement": SettlementAgent, "paymaster": PaymasterAgent,
    "burn": BurnAgent, "retention": RetentionAgent, "risk_auditor": RiskAuditorAgent,
}


def create_agent(name, agent_id=None, **kwargs):
    """Create one of the 9 Wirtschaftsagenten by name."""
    cls = AGENT_CLASSES.get(name)
    if cls is None:
        raise ValueError(f"unknown wirtschaft agent: {name}")
    return cls(agent_id or f"{name}-1", **kwargs)
