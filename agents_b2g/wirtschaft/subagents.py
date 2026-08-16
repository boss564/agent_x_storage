"""Fach-Subagenten der 9 Wirtschaftsagenten (Baustein 3).

Subagents are internal modules: they enable their parent agent's core tasks
but hold NO authority outside the parent (Gewaltenteilung). External action
always goes through the parent WirtschaftAgent.
"""
from typing import Any, Dict, List, Optional


class FachSubagent:
    """Base: internal module bound to a parent agent. No own authority."""
    name = "fach_subagent"

    def __init__(self, parent: Optional[Any] = None):
        self.parent = parent


# ================= Klasse A — Kapital & Liquiditaet ========================

class PoolManager(FachSubagent):
    name = "pool_manager"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pools: Dict[str, Dict[str, Any]] = {}

    def read_pool(self, pool_id: str) -> Dict[str, Any]:
        return dict(self._pools.get(pool_id, {}))

    def write_pool(self, pool_id: str, delta: float) -> Dict[str, Any]:
        pool = self._pools.setdefault(pool_id, {"balance": 0.0})
        pool["balance"] = pool.get("balance", 0.0) + delta
        return pool


class GasBank(FachSubagent):
    name = "gas_bank"

    def reserve(self) -> float:
        if self.parent is not None and hasattr(self.parent, "gas_monitor"):
            return self.parent.gas_monitor.gas
        return 0.0

    def top_up(self, amount: float) -> float:
        if self.parent is not None and hasattr(self.parent, "gas_monitor"):
            self.parent.gas_monitor.refuel(amount)
        return self.reserve()


class ReserveManager(FachSubagent):
    name = "reserve_manager"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accounts: Dict[str, float] = {}

    def balance(self, account: str) -> float:
        return self._accounts.get(account, 0.0)

    def allocate(self, account: str, amount: float) -> float:
        self._accounts[account] = self._accounts.get(account, 0.0) + amount
        return self._accounts[account]


class YieldCalculator(FachSubagent):
    name = "yield_calculator"

    def compute_yield(self, principal: float, rate: float, periods: int = 1) -> float:
        return principal * rate * periods


class StakingContract(FachSubagent):
    name = "staking_contract"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stakes: Dict[str, float] = {}

    def deposit(self, validator: str, amount: float) -> float:
        self._stakes[validator] = self._stakes.get(validator, 0.0) + amount
        return self._stakes[validator]

    def withdraw(self, validator: str, amount: float) -> float:
        current = self._stakes.get(validator, 0.0)
        withdrawn = min(current, amount)
        self._stakes[validator] = current - withdrawn
        return withdrawn


class RewardDistributor(FachSubagent):
    name = "reward_distributor"

    def distribute(self, total_reward: float, stakes: Dict[str, float]) -> Dict[str, float]:
        total_stake = sum(stakes.values())
        if total_stake <= 0:
            return {}
        return {v: total_reward * (s / total_stake) for v, s in stakes.items()}


# ================= Klasse B — Ausfuehrung & Abwicklung =====================

class MintEngine(FachSubagent):
    name = "mint_engine"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._minted = 0.0

    def mint(self, amount: float) -> Dict[str, Any]:
        self._minted += amount
        return {"minted": amount, "total_minted": self._minted}


class SupplyOracle(FachSubagent):
    name = "supply_oracle"

    def __init__(self, parent=None, cap: float = float("inf")):
        super().__init__(parent)
        self.cap = cap

    def total_supply(self) -> float:
        engine = getattr(self.parent, "mint_engine", None)
        return engine._minted if engine else 0.0

    def check_cap(self, amount: float) -> bool:
        return self.total_supply() + amount <= self.cap


class LedgerCommitter(FachSubagent):
    name = "ledger_committer"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ledger: List[Dict[str, Any]] = []

    def commit(self, entry: Dict[str, Any]) -> int:
        self._ledger.append(entry)
        return len(self._ledger) - 1


class SettlementVerifier(FachSubagent):
    name = "settlement_verifier"

    def verify(self, entry: Dict[str, Any]) -> bool:
        # BHO zero-sum consistency: debits == credits
        return abs(entry.get("debits", 0.0) - entry.get("credits", 0.0)) < 1e-9


class GasPricer(FachSubagent):
    name = "gas_pricer"

    def price(self, base: float = 1.0, congestion: float = 0.0) -> float:
        return base * (1.0 + max(0.0, congestion))


class FeeCollector(FachSubagent):
    name = "fee_collector"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collected = 0.0

    def collect(self, amount: float) -> float:
        self._collected += amount
        return self._collected


# ================= Klasse C — Governance & Risiko ==========================

class BurnVerifier(FachSubagent):
    name = "burn_verifier"

    def verify_burn_criteria(self, amount: float, supply: float) -> bool:
        return amount > 0 and amount <= supply


class DeflationController(FachSubagent):
    name = "deflation_controller"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._burned = 0.0

    def reduce_supply(self, amount: float) -> Dict[str, Any]:
        self._burned += amount
        return {"burned": amount, "total_burned": self._burned}


class PolicyStore(FachSubagent):
    name = "policy_store"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._denied = set()
        self._rules: Dict[str, Any] = {}

    def deny(self, aktion: str) -> None:
        self._denied.add(aktion)

    def allow(self, aktion: str) -> None:
        self._denied.discard(aktion)

    def is_denied(self, aktion: str) -> bool:
        return aktion in self._denied

    def store_policy(self, name: str, rule: Any) -> None:
        self._rules[name] = rule

    def load_policy(self, name: str) -> Optional[Any]:
        return self._rules.get(name)


class ComplianceEngine(FachSubagent):
    name = "compliance_engine"

    def __init__(self, parent=None, policy: Optional[PolicyStore] = None):
        super().__init__(parent)
        self.policy = policy or PolicyStore(parent)

    def check(self, request: Dict[str, Any]) -> Dict[str, Any]:
        aktion = request.get("aktion")
        requester = request.get("requester")
        if self.policy.is_denied(aktion):
            return {"decision": "DENY", "grund": f"policy_denies:{aktion}"}
        if not requester:
            return {"decision": "DENY", "grund": "no_requester"}
        return {"decision": "GRANT", "grund": "policy_ok"}


class RiskScorer(FachSubagent):
    name = "risk_scorer"

    def score(self, activity: Dict[str, Any]) -> float:
        # Simple heuristic score in [0,1]; higher = riskier
        volume = float(activity.get("volume", 0.0))
        velocity = float(activity.get("velocity", 0.0))
        return min(1.0, (volume / 1e6) * 0.5 + (velocity / 100.0) * 0.5)


class AnomalyDetector(FachSubagent):
    name = "anomaly_detector"

    def __init__(self, parent=None, threshold: float = 0.8):
        super().__init__(parent)
        self.threshold = threshold

    def detect(self, risk_score: float) -> bool:
        return risk_score >= self.threshold
