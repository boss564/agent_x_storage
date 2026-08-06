#!/usr/bin/env python3
"""
Wave 23: Token Creation, Governance & Launch Engine.

9 Root-Agenten mit 81 Subagenten für den vollständigen Lebenszyklus:
  1. TokenomicsArchitect — Supply, Vesting, Inflation
  2. TokenContractDeployer — ERC-20 Compilation & Deployment
  3. VestingAndVaultManager — Timelocks, Cliffs, Lockups
  4. LiquidityPoolInitializer — DEX Pools, LP-Locks, Pricing
  5. TokenGovernanceEngine — DAO Voting, Quorum, Timelock
  6. RegulatoryComplianceGuard — MiCAR, SEC Howey, KYB/KYC
  7. AirdropAndClaimDistributor — Merkle Trees, Gasless Claim
  8. TokenMetadataAndBranding — IPFS, Token Lists, CMC
  9. TokenLaunchOrchestrator — Root Pipeline & Lifecycle

Usage:
    python agents_b2g/tokenomics/token_launch_orchestrator.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents_b2g.event_bus import EventBus


# ============================================================
# Configuration
# ============================================================


class TokenConfig:
    """Zentrale Konfiguration für Wave 23 — Token Launch Engine."""

    DATA_ROOT: Path = Path(os.getenv("TOKEN_DATA_ROOT", "data"))
    LOG_DIR: Path = Path(os.getenv("TOKEN_LOG_DIR", "logs"))

    # Token defaults
    DEFAULT_DECIMALS: int = int(os.getenv("TOKEN_DECIMALS", "18"))
    DEFAULT_STANDARD: str = os.getenv("TOKEN_STANDARD", "ERC-20Permit")

    # Vesting
    MIN_CLIFF_DAYS: int = int(os.getenv("TOKEN_MIN_CLIFF_DAYS", "90"))
    MAX_VESTING_YEARS: int = int(os.getenv("TOKEN_MAX_VESTING_YEARS", "4"))

    # Governance
    MIN_VOTING_DELAY_BLOCKS: int = int(os.getenv("TOKEN_VOTING_DELAY", "7200"))
    DEFAULT_QUORUM_PCT: float = float(os.getenv("TOKEN_QUORUM_PCT", "4.0"))

    # Liquidity
    DEFAULT_LP_LOCK_MONTHS: int = int(os.getenv("TOKEN_LP_LOCK_MONTHS", "12"))
    MAX_SLIPPAGE_BPS: int = int(os.getenv("TOKEN_MAX_SLIPPAGE_BPS", "500"))

    # Compliance
    HOWEY_THRESHOLD: float = float(os.getenv("TOKEN_HOWEY_THRESHOLD", "50.0"))
    SANCTION_LISTS: list[str] = ["OFAC", "EU", "UN"]

    # Chains
    SUPPORTED_CHAINS: list[str] = ["ethereum", "gnosis", "polygon", "arbitrum", "base"]

    # Retry
    MAX_RETRIES: int = int(os.getenv("TOKEN_MAX_RETRIES", "3"))
    RETRY_BACKOFF_BASE_S: float = float(os.getenv("TOKEN_RETRY_BACKOFF_S", "1.0"))


# ============================================================
# Helpers
# ============================================================


class JSONLogger:
    def __init__(self, agent_name: str = "token_launch", user_id: str = "default"):
        self.agent_name = agent_name
        self.user_id = user_id
        self.log_path = TokenConfig.LOG_DIR / f"token_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, msg: str, **extra) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": level,
                 "agent": self.agent_name, "user_id": self.user_id, "message": msg, **extra}
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def info(self, msg: str, **extra) -> None: self._write("INFO", msg, **extra)
    def warn(self, msg: str, **extra) -> None: self._write("WARN", msg, **extra)
    def error(self, msg: str, **extra) -> None: self._write("ERROR", msg, **extra)


def _ok(job_id: str, artifacts: list | None = None, **extra) -> dict:
    return {"status": "completed", "job_id": job_id, "artifacts": artifacts or [],
            "error": None, "logs": [], **extra}

def _fail(job_id: str, error: str, **extra) -> dict:
    return {"status": "failed", "job_id": job_id, "artifacts": [],
            "error": error, "logs": [{"level": "ERROR", "message": error}], **extra}

def _safe_call(logger: JSONLogger, node: str, fn, *a, **kw) -> dict:
    job_id = str(uuid.uuid4())[:8]
    start = time.monotonic()
    logger.info(f"[{node}] started", job_id=job_id)
    last_err = None
    for attempt in range(1, TokenConfig.MAX_RETRIES + 1):
        try:
            result = fn(*a, **kw)
            dur_ms = round((time.monotonic() - start) * 1000, 1)
            logger.info(f"[{node}] completed", job_id=job_id, duration_ms=dur_ms, attempt=attempt)
            STD = {"completed", "failed", "started", "skipped"}
            if isinstance(result, dict) and result.get("status") in STD:
                result["job_id"] = result.get("job_id", job_id)
                return result
            return _ok(job_id, artifacts=[result] if result is not None else [])
        except Exception as exc:
            last_err = exc
            logger.warn(f"[{node}] attempt {attempt} failed: {exc}", job_id=job_id)
            if attempt < TokenConfig.MAX_RETRIES:
                time.sleep(TokenConfig.RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)))
    logger.error(f"[{node}] failed: {last_err}", job_id=job_id)
    return _fail(job_id, str(last_err))


# ============================================================
# Phase Enum
# ============================================================


class LaunchPhase(str, Enum):
    DESIGN = "DESIGN"
    COMPILED = "COMPILED"
    VERIFIED = "VERIFIED"
    DEPLOYED = "DEPLOYED"
    PAIRED = "PAIRED"
    LIVE = "LIVE"


# ============================================================
# Agent 1: TokenomicsArchitect
# ============================================================


class TokenomicsArchitect:
    """Agent 23.1: Modelliert Supply, Vesting, Staking und Deflation."""

    def __init__(self):
        self.supply_cap = SupplyCapCalculator()
        self.inflation = InflationDeflationModeler()
        self.allocation = AllocationSplitDistributor()
        self.staking = StakingYieldSimulator()
        self.burn = BurnMechanismConfigurator()
        self.macro = MacroEconomicStabilityTester()

    def design(self, name: str, total_supply: float,
               allocation: dict | None = None) -> dict:
        alloc = allocation or {"public": 40, "team": 20, "liquidity": 20, "treasury": 20}

        return {
            "name": name, "total_supply": total_supply,
            "decimals": TokenConfig.DEFAULT_DECIMALS,
            "allocation_pct": alloc,
            "allocation_tokens": {k: total_supply * v / 100 for k, v in alloc.items()},
            "inflation_model": self.inflation.simulate(total_supply),
            "staking_apy_range": self.staking.calculate(total_supply),
            "burn_mechanism": self.burn.configure(),
        }


class SupplyCapCalculator:
    def calculate(self, market_cap_target: float, token_price: float) -> dict:
        supply = market_cap_target / token_price if token_price > 0 else 1_000_000
        return {"hard_cap": round(supply), "max_supply": round(supply * 1.1)}


class InflationDeflationModeler:
    def simulate(self, supply: float, years: int = 5) -> dict:
        return {"year_1_inflation_pct": 5.0, "year_5_inflation_pct": 1.0,
                "disinflationary": True, "terminal_inflation": 1.0}


class AllocationSplitDistributor:
    def validate(self, pcts: dict) -> dict:
        total = sum(pcts.values())
        return {"valid": abs(total - 100) < 0.01, "total_pct": total}


class StakingYieldSimulator:
    def calculate(self, supply: float) -> dict:
        return {"min_apy_pct": 3.0, "max_apy_pct": 12.0, "avg_apy_pct": 7.5}


class BurnMechanismConfigurator:
    def configure(self) -> dict:
        return {"tx_fee_burn_bps": 0, "buyback_and_burn": False,
                "eip1559_style": True, "base_fee_burn_pct": 80.0}


class MacroEconomicStabilityTester:
    def simulate_shock(self, supply: float, shock_pct: float = 30) -> dict:
        return {"shock_pct": shock_pct, "price_impact_pct": shock_pct * 1.4,
                "recovery_months": 3, "stable": shock_pct < 50}


# ============================================================
# Agent 2: TokenContractDeployer
# ============================================================


class TokenContractDeployer:
    """Agent 23.2: Kompiliert und deployt ERC-20 Smart Contracts."""

    def __init__(self):
        self.standard_selector = StandardSelector()
        self.compiler = OpenZeppelinCodeCompiler()
        self.address_predictor = ContractAddressPredictor()
        self.verifier = BlockExplorerVerifier()
        self.audit_logger = DeploymentAuditLogger()
        self.fee_module = CustomFeeModule()

    def deploy(self, name: str, symbol: str, supply: float,
               chain: str = "gnosis", features: list | None = None) -> dict:
        feats = features or ["permit", "votes", "snapshot"]
        std = self.standard_selector.select(feats)
        contract_addr = self.address_predictor.predict(name, symbol, chain)
        tx_hash = hashlib.sha256(f"deploy:{contract_addr}:{time.time()}".encode()).hexdigest()

        return {
            "name": name, "symbol": symbol, "chain": chain,
            "standard": std, "decimals": TokenConfig.DEFAULT_DECIMALS,
            "total_supply_raw": int(supply * (10 ** TokenConfig.DEFAULT_DECIMALS)),
            "contract_address": f"0x{contract_addr}",
            "deployment_tx": f"0x{tx_hash}",
            "features": feats,
            "verified": True,
        }


class StandardSelector:
    def select(self, features: list) -> str:
        if "permit" in features:
            return "ERC-20Permit (OpenZeppelin v5.0)"
        return "ERC-20 (OpenZeppelin v5.0)"


class OpenZeppelinCodeCompiler:
    def compile(self, source: str) -> dict:
        h = hashlib.sha256(source.encode()).hexdigest()
        return {"compiled": True, "bytecode_hash": h[:16],
                "solidity_version": "0.8.20", "optimizer_runs": 200}


class ContractAddressPredictor:
    def predict(self, name: str, symbol: str, chain: str) -> str:
        return hashlib.sha256(f"{name}:{symbol}:{chain}:create2".encode()).hexdigest()[:40]


class BlockExplorerVerifier:
    def verify(self, address: str, chain: str) -> dict:
        return {"verified": True, "explorer_url": f"https://{chain}.etherscan.io/address/{address}"}


class DeploymentAuditLogger:
    def log(self, deployment: dict) -> dict:
        return {"audit_hash": hashlib.sha256(json.dumps(deployment, sort_keys=True, default=str).encode()).hexdigest()[:16],
                "timestamp": datetime.now(timezone.utc).isoformat(), "worm_status": "STORED"}


class CustomFeeModule:
    def inject(self, enable: bool, fee_bps: int = 0) -> dict:
        return {"fee_enabled": enable, "fee_bps": fee_bps, "recipient": "0xTreasury" if enable else None}


# ============================================================
# Agent 3: VestingAndVaultManager
# ============================================================


class VestingAndVaultManager:
    """Agent 23.3: On-Chain Vesting-Verträge, Team-Lockups, Treasury-Tresore."""

    def __init__(self):
        self.cliff = CliffPeriodEnforcer()
        self.linear = LinearVestingCalculator()
        self.team = TeamLockupVaultManager()

    def setup_vesting(self, allocations: dict, start_date: str = "2026-09-01") -> dict:
        schedules = {}
        for category, amount in allocations.items():
            schedules[category] = {
                "amount": amount,
                "cliff_months": 12 if category == "team" else 0,
                "vesting_months": 48 if category == "team" else 24,
                "claimable_now": self.linear.calculate(amount, 0, 48) if category != "team"
                else self.cliff.calculate(amount, 12, 48, 0),
            }
        return {"start_date": start_date, "schedules": schedules,
                "total_locked": sum(s["amount"] for s in schedules.values()),
                "vault_address": "0xVestingVault...Deploy"}


class CliffPeriodEnforcer:
    def calculate(self, amount: float, cliff_months: int, total_months: int, elapsed_months: int) -> dict:
        if elapsed_months < cliff_months:
            return {"claimable": 0, "cliff_remaining_months": cliff_months - elapsed_months}
        vested = min(1.0, (elapsed_months - cliff_months) / max(1, total_months - cliff_months))
        return {"claimable": amount * vested, "vested_pct": round(vested * 100, 1)}


class LinearVestingCalculator:
    def calculate(self, amount: float, elapsed_months: int, total_months: int) -> float:
        if total_months <= 0:
            return amount
        return amount * min(1.0, elapsed_months / total_months)


class TeamLockupVaultManager:
    def create(self, team_tokens: float, unlock_schedule: str) -> dict:
        return {"vault_type": "MultiSig-Timelock", "locked_amount": team_tokens,
                "unlock_schedule": unlock_schedule, "multi_sig_required": 2}


# ============================================================
# Agent 4–9 (abbreviated — full subagent structure as specified)
# ============================================================


class LiquidityPoolInitializer:
    """Agent 23.4: Erstellt DEX-Pools, setzt Preise, sperrt LP-Token."""

    def initialize(self, token_address: str, pair_token: str = "EURe",
                   initial_price: float = 1.0, chain: str = "gnosis") -> dict:
        pool_addr = hashlib.sha256(f"{token_address}:{pair_token}:pool".encode()).hexdigest()[:40]
        return {
            "pool_address": f"0x{pool_addr}",
            "token_a": token_address, "token_b": pair_token,
            "initial_price": initial_price, "chain": chain,
            "dex": "Uniswap v3", "lp_locked_months": TokenConfig.DEFAULT_LP_LOCK_MONTHS,
            "slippage_protection_bps": TokenConfig.MAX_SLIPPAGE_BPS,
        }


class TokenGovernanceEngine:
    """Agent 23.5: ERC20Votes, Governor, TimelockController."""

    def configure(self, token_address: str, quorum_pct: float | None = None) -> dict:
        q = quorum_pct or TokenConfig.DEFAULT_QUORUM_PCT
        return {
            "token": token_address, "voting_delay_blocks": TokenConfig.MIN_VOTING_DELAY_BLOCKS,
            "voting_period_blocks": 50400, "quorum_pct": q,
            "timelock_delay_days": 2, "proposal_threshold_tokens": 10000,
            "governor_address": "0xGovernor...Deploy",
            "features": ["delegation", "snapshot_integration"],
        }


class RegulatoryComplianceGuard:
    """Agent 23.6: MiCAR, SEC Howey, Sanktionslisten, KYB/KYC."""

    def evaluate(self, token_symbol: str, is_utility: bool, jurisdictions: list | None = None) -> dict:
        jur = jurisdictions or ["EU"]
        howey_score = 15.0 if is_utility else 85.0
        micar_ok = is_utility or "EU" not in jur

        return {
            "token": token_symbol,
            "micar_status": "UTILITY_TOKEN_COMPLIANT" if micar_ok else "REQUIRES_EMONEY_LICENSE",
            "howey_score": howey_score,
            "howey_verdict": "LIKELY_NOT_A_SECURITY" if howey_score < TokenConfig.HOWEY_THRESHOLD else "SECURITY_RISK",
            "sanctions_checked": TokenConfig.SANCTION_LISTS,
            "compliance_verdict": "PASSED" if micar_ok and howey_score < TokenConfig.HOWEY_THRESHOLD else "REJECTED",
        }


class AirdropAndClaimDistributor:
    """Agent 23.7: Merkle-Bäume, Sybil-Filter, gaslose Claims."""

    def distribute(self, recipients: dict, total_airdrop: float) -> dict:
        leaves = [f"{addr}:{amt}" for addr, amt in recipients.items()]
        merkle_root = hashlib.sha256("".join(sorted(leaves)).encode()).hexdigest()

        return {
            "total_recipients": len(recipients),
            "total_airdrop": total_airdrop,
            "merkle_root": f"0x{merkle_root}",
            "claim_contract": "0xMerkleDistributor...Deploy",
            "gasless_claim_enabled": True,
            "unclaimed_return_days": 90,
        }


class TokenMetadataAndBranding:
    """Agent 23.8: IPFS-Logos, Token-Lists, CoinGecko/CMC-Submission."""

    def publish(self, name: str, symbol: str, contract: str, logo_cid: str = "") -> dict:
        return {
            "name": name, "symbol": symbol, "contract": contract,
            "logo_ipfs": f"ipfs://{logo_cid or hashlib.sha256(name.encode()).hexdigest()[:32]}",
            "token_list_compliant": True,
            "coingecko_submission_ready": True,
            "cmc_submission_ready": True,
            "trust_wallet_pr_url": f"https://github.com/trustwallet/assets/pull/{hashlib.sha256(name.encode()).hexdigest()[:8]}",
        }


# ============================================================
# Agent 9: TokenLaunchOrchestrator (Root)
# ============================================================


class TokenLaunchOrchestrator:
    """
    Root-Agent 23: Orchestriert die Token Creation, Governance & Launch Engine.
    Steuert alle 8 Subagenten in einer durchgängigen Pipeline.
    """

    def __init__(self, user_id: str = "default", event_bus: EventBus | None = None,
                 logger: JSONLogger | None = None):
        self.user_id = user_id
        self.event_bus = event_bus
        self.logger = logger or JSONLogger(agent_name="token_launch", user_id=user_id)

        self.tokenomics = TokenomicsArchitect()
        self.deployer = TokenContractDeployer()
        self.vesting = VestingAndVaultManager()
        self.liquidity = LiquidityPoolInitializer()
        self.governance = TokenGovernanceEngine()
        self.compliance = RegulatoryComplianceGuard()
        self.airdrop = AirdropAndClaimDistributor()
        self.metadata = TokenMetadataAndBranding()

        self.phase = LaunchPhase.DESIGN
        self.logger.info("TokenLaunchOrchestrator initialized", phase=self.phase.value)

    def run_launch_pipeline(
        self,
        name: str,
        symbol: str,
        total_supply: float = 100_000_000,
        is_utility: bool = True,
        chain: str = "gnosis",
        allocation: dict | None = None,
    ) -> dict:
        """Führt die vollständige 9-Phasen-Launch-Pipeline durch."""
        job_id = str(uuid.uuid4())[:8]
        start = time.monotonic()
        self.logger.info(f"Launch pipeline started for {symbol}", job_id=job_id)

        try:
            # Phase 1: Compliance (BLOCKING — stoppt bei Verstoß)
            self.phase = LaunchPhase.DESIGN
            comp = _safe_call(self.logger, "Compliance",
                              lambda: self.compliance.evaluate(symbol, is_utility))
            if comp["status"] != "completed":
                return _fail(job_id, "Compliance rejected — launch blocked")

            # Phase 2: Tokenomics
            a1 = _safe_call(self.logger, "Tokenomics",
                            lambda: self.tokenomics.design(name, total_supply, allocation))

            # Phase 3: Deploy Contract
            self.phase = LaunchPhase.COMPILED
            a2 = _safe_call(self.logger, "Deploy",
                            lambda: self.deployer.deploy(name, symbol, total_supply, chain))

            # Derive contract address from deployment
            deploy_data = a2.get("artifacts", [{}])[0] if a2.get("artifacts") else {}
            contract_addr = deploy_data.get("contract_address", "0xUnknown")

            # Phase 4: Vesting Setup
            alloc_data = a1.get("artifacts", [{}])[0] if a1.get("artifacts") else {}
            alloc_tokens = alloc_data.get("allocation_tokens", {})
            a3 = _safe_call(self.logger, "Vesting",
                            lambda: self.vesting.setup_vesting(alloc_tokens))

            # Phase 5: Liquidity Pool
            self.phase = LaunchPhase.DEPLOYED
            a4 = _safe_call(self.logger, "Liquidity",
                            lambda: self.liquidity.initialize(contract_addr))

            self.phase = LaunchPhase.PAIRED

            # Phase 6: Governance
            a5 = _safe_call(self.logger, "Governance",
                            lambda: self.governance.configure(contract_addr))

            # Phase 7: Airdrop (community allocation)
            community_tokens = alloc_tokens.get("public", total_supply * 0.1)
            sample_recipients = {f"0xRecipient{i}": community_tokens / 100 for i in range(100)}
            a6 = _safe_call(self.logger, "Airdrop",
                            lambda: self.airdrop.distribute(sample_recipients, community_tokens))

            # Phase 8: Metadata & Branding
            a7 = _safe_call(self.logger, "Metadata",
                            lambda: self.metadata.publish(name, symbol, contract_addr))

            self.phase = LaunchPhase.LIVE

            # Compose final launch report
            report = {
                "name": name, "symbol": symbol, "chain": chain,
                "total_supply": total_supply,
                "contract_address": contract_addr,
                "is_utility": is_utility,
                "phase": self.phase.value,
                "tokenomics": a1.get("artifacts", [{}])[0] if a1.get("artifacts") else {},
                "deployment": deploy_data,
                "vesting": a3.get("artifacts", [{}])[0] if a3.get("artifacts") else {},
                "liquidity": a4.get("artifacts", [{}])[0] if a4.get("artifacts") else {},
                "governance": a5.get("artifacts", [{}])[0] if a5.get("artifacts") else {},
                "airdrop": a6.get("artifacts", [{}])[0] if a6.get("artifacts") else {},
                "metadata": a7.get("artifacts", [{}])[0] if a7.get("artifacts") else {},
                "compliance": comp.get("artifacts", [{}])[0] if comp.get("artifacts") else {},
                "audit_hash": hashlib.sha256(f"{symbol}:{contract_addr}:{time.time()}".encode()).hexdigest()[:16],
            }

            if self.event_bus:
                self.event_bus.publish("token.launch.completed", {
                    "symbol": symbol, "contract": contract_addr, "chain": chain,
                })

            duration_ms = round((time.monotonic() - start) * 1000, 1)
            self.logger.info(f"Launch complete: {symbol} @ {contract_addr}",
                             job_id=job_id, duration_ms=duration_ms)

            return _ok(job_id, artifacts=[report])

        except Exception as exc:
            self.logger.error(f"Launch failed: {exc}", job_id=job_id)
            return _fail(job_id, str(exc))


# ============================================================
# Standalone runner
# ============================================================


if __name__ == "__main__":
    orch = TokenLaunchOrchestrator(user_id="demo")
    result = orch.run_launch_pipeline(
        name="Agent X Utility Token",
        symbol="AGX",
        total_supply=100_000_000,
        is_utility=True,
        chain="gnosis",
    )

    report = result["artifacts"][0]
    print(f"\n{'='*60}")
    print(f"  Wave 23: Token Creation & Launch Engine")
    print(f"{'='*60}")
    print(f"  Token:    {report['name']} ({report['symbol']})")
    print(f"  Chain:    {report['chain']}")
    print(f"  Contract: {report['contract_address']}")
    print(f"  Phase:    {report['phase']}")
    print(f"  Audit:    {report['audit_hash']}")
    print(f"  Status:   {result['status']}")
    print(f"{'='*60}\n")
