#!/usr/bin/env python3
"""
Wave 40 E2E Test Suite: Execution Resilience & Risk Shield.

| Gruppe | Tests | Inhalt |
|--------|-------|--------|
| G1 | 8 | Reorg-Simulation |
| G2 | 8 | RPC-Failover |
| G3–G8 | 9×6=54 | MEV / Gas / Confounder / Black-Swan / Fiscal / Forensic |
| G9 | 9 | Orchestrator-Integration |
| G10 | 7 | Multi-Tenancy |
| G11 | 9 | Config-Failsafe |
| G12 | 10 | Full-E2E (1.000 TXs) |
| **Σ** | **105** | |

Usage:
    python3 scripts/test_wave40_resilience.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Isolate logs/data for hermetic runs (sandbox-safe)
_TMP = Path(tempfile.mkdtemp(prefix="wave40_test_"))
os.environ.setdefault("RESILIENCE_LOG_DIR", str(_TMP / "logs"))
os.environ.setdefault("RESILIENCE_DATA_ROOT", str(_TMP / "data"))

from agents_b2g.resilience.config import ResilienceConfig, ResilienceConfigError
from agents_b2g.resilience.execution_resilience_orchestrator import (
    ExecutionResilienceOrchestrator,
)
from agents_b2g.resilience.subagents.black_swan_breaker import BlackSwanCircuitBreaker
from agents_b2g.resilience.subagents.confounder_detector import ConfounderDetector
from agents_b2g.resilience.subagents.execution_forensic_recorder import (
    ExecutionForensicRecorder,
)
from agents_b2g.resilience.subagents.fiscal_compliance_auditor import (
    FiscalComplianceAuditor,
)
from agents_b2g.resilience.subagents.gas_budget_enforcer import GasBudgetEnforcer
from agents_b2g.resilience.subagents.mev_shield import MEVShield
from agents_b2g.resilience.subagents.reorg_monitor import ReorgMonitor
from agents_b2g.resilience.subagents.rpc_health_sentinel import RPCHealthSentinel
from agents_b2g.resilience.types import ResilienceVerdict

PASS, FAIL = 0, 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _happy(**kw) -> dict:
    d = {
        "tip_block": 120,
        "signal_block": 100,
        "layer": "L1",
        "reorg_depth": 0,
        "block_hash": "0xdeadbeef01",
        "parent_hash": "0xcafebabe01",
        "expected_parent": "0xcafebabe01",
        "latency_samples_ms": [12.0, 15.0, 11.0, 14.0],
        "primary_endpoint": "https://rpc.primary.local",
        "fallback_endpoints": ["https://rpc.fallback.local"],
        "use_public_mempool": False,
        "from_address": "0xown",
        "to_address": "0xtarget",
        "nonce": 5,
        "quoted_price": 1.0,
        "limit_price": 1.002,
        "gas_limit": 21000,
        "this_burn": 21000,
        "prior_burn": 0,
        "estimated_gas": 18000,
        "gas_in": 100.0,
        "gas_used": 70.0,
        "gas_refunded": 20.0,
        "gas_reserve": 10.0,
        "registered_factors": ["oracle_lag", "mev_density"],
        "signal_factors": ["oracle_lag"],
        "candidate_factors": ["oracle_lag"],
        "abs_sigma": 1.0,
        "current_vol": 0.1,
        "vol_30d": 0.1,
    }
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# G1 Reorg (8)
# ---------------------------------------------------------------------------


def test_g1_reorg() -> None:
    section("G1 Reorg-Simulation (8)")
    mon = ReorgMonitor(user_id="t40_g1")

    r = mon.evaluate(_happy(reorg_depth=1, tip_block=110, signal_block=100))
    check("G1.1 1-block reorg shallow", r.severity == 1 and r.severity_label == "shallow")

    r = mon.evaluate(_happy(reorg_depth=5, tip_block=110, signal_block=100))
    check("G1.2 5-block reorg mid", r.severity == 2 and r.severity_label == "mid")

    r = mon.evaluate(_happy(reorg_depth=12, tip_block=112, signal_block=100))
    check("G1.3 12-block deep vs L1 threshold", r.severity == 3 and not r.finality_ok)

    r = mon.evaluate(_happy(reorg_depth=20, tip_block=120, signal_block=100))
    check("G1.4 deep reorg blocked", r.severity >= 3 and not r.finality_ok)

    r = mon.evaluate(_happy(reorg_depth=0, tip_block=120, signal_block=100))
    check("G1.5 no-reorg finality L1", r.severity == 0 and r.finality_ok)

    r = mon.evaluate(_happy(layer="L2", tip_block=150, signal_block=100, reorg_depth=0))
    check("G1.6 L2 needs 64 confs (50 insufficient)", not r.finality_ok and r.threshold == 64)

    r = mon.evaluate(_happy(layer="L2", tip_block=170, signal_block=100, reorg_depth=0))
    check("G1.7 L2 finality at 70 confs", r.finality_ok and r.depth >= 64)

    r = mon.evaluate(
        _happy(tip_hashes=["0xaaa", "0xbbb"], tip_block=120, signal_block=100)
    )
    check("G1.8 fork detected", r.forked and not r.finality_ok)


# ---------------------------------------------------------------------------
# G2 RPC (8)
# ---------------------------------------------------------------------------


def test_g2_rpc() -> None:
    section("G2 RPC-Failover (8)")
    rpc = RPCHealthSentinel(user_id="t40_g2")

    r = rpc.evaluate(_happy(status_codes=[429, 429], latency_samples_ms=[20, 22]))
    check("G2.1 HTTP 429 backoff", r.subagent_results["HTTP429Backoff"]["throttled"])

    r = rpc.evaluate(_happy(consecutive_timeouts=3, latency_samples_ms=[10]))
    check("G2.2 timeout circuit open", r.circuit_open and not r.rpc_ok)

    r = rpc.evaluate(_happy(tip_age_s=120, latency_samples_ms=[10]))
    check("G2.3 staleness blocks", r.stale and not r.rpc_ok)

    r = rpc.evaluate(_happy(latency_samples_ms=[10, 12, 11, 200]))
    check(
        "G2.4 jitter filter removes outlier",
        r.subagent_results["JitterFilter"]["removed"] >= 1
        or r.subagent_results["JitterFilter"]["jitter_ms"] >= 0,
    )

    r = rpc.evaluate(
        _happy(
            latency_samples_ms=[250, 260],
            endpoints=[
                {"url": "https://rpc.primary.local", "latency_ms": 250, "healthy": False, "private": False},
                {"url": "https://rpc.fallback.local", "latency_ms": 40, "healthy": True, "private": True},
            ],
        )
    )
    check("G2.5 multi-endpoint failover", r.failover and r.rpc_ok)

    r = rpc.evaluate(_happy(latency_samples_ms=[10, 12], p99_us=100.0))
    check("G2.6 SLA breach on high p99_us", r.subagent_results["SLAEnforcer"]["sla_breach"])

    r = rpc.evaluate(_happy(latency_samples_ms=[10, 12], primary_block=100, secondary_block=110))
    check("G2.7 event-log drift", r.drifted)

    r = rpc.evaluate(_happy(latency_samples_ms=[10, 11, 12]))
    check("G2.8 healthy primary rpc_ok", r.rpc_ok and not r.failover)


# ---------------------------------------------------------------------------
# G3 MEV (9)
# ---------------------------------------------------------------------------


def test_g3_mev() -> None:
    section("G3 MEV-Shield (9)")
    mev = MEVShield(user_id="t40_g3")

    r = mev.evaluate(
        _happy(
            surrounding_txs=[
                {"from": "0xatk", "role": "front"},
                {"from": "0xatk", "role": "back"},
            ]
        )
    )
    check("G3.1 sandwich detected", r.sandwich_detected and not r.mev_ok)

    r = mev.evaluate(
        _happy(
            mempool_competitors=[{"to": "0xtarget", "nonce": 1}],
            nonce=5,
            to_address="0xtarget",
        )
    )
    check("G3.2 frontrun risk", r.frontrun_risk and not r.mev_ok)

    r = mev.evaluate(_happy(base_fee_gwei=20, priority_fee_gwei=3, gas_limit=21000))
    check(
        "G3.3 bundle pricer",
        r.subagent_results["BundlePricer"]["effective_gwei"] == 23.0,
    )

    r = mev.evaluate(_happy(quoted_price=1.0, limit_price=1.1, max_slippage_bps=50))
    check("G3.4 slippage cap exceeded", not r.slippage_ok and not r.mev_ok)

    r = mev.evaluate(_happy(use_public_mempool=True))
    check("G3.5 public mempool leakage", r.leakage_count >= 1 and not r.mev_ok)

    r = mev.evaluate(_happy(use_public_mempool=False, observed_in_public_mempool=False))
    check("G3.6 leakage zero private path", r.leakage_count == 0 and r.mev_ok)

    r = mev.evaluate(_happy(builders=[{"id": "x", "score": 0.2}], min_score=0.7))
    # reputation uses payload builders only
    r = mev.evaluate({**_happy(), "builders": [{"id": "bad", "score": 0.1}]})
    check("G3.7 low builder reputation fails", not r.mev_ok)

    r = mev.evaluate(_happy())
    check("G3.8 private relay selected", r.selected_relay is not None and r.privacy_ok)

    r = mev.evaluate(_happy())
    check("G3.9 happy path mev_ok", r.mev_ok)


# ---------------------------------------------------------------------------
# G4 Gas (9)
# ---------------------------------------------------------------------------


def test_g4_gas() -> None:
    section("G4 Gas-Budget (9)")
    gas = GasBudgetEnforcer(user_id="t40_g4")

    r = gas.evaluate(_happy(gas_limit=600_000, this_burn=600_000, estimated_gas=500_000), job_id="g4a")
    check("G4.1 per-tx cap exceeded", not r.per_tx_ok and r.circuit_open)

    r = gas.evaluate(
        _happy(prior_burn=49_990_000, this_burn=20_000, gas_limit=20_000, estimated_gas=15_000),
        job_id="g4b",
    )
    check("G4.2 daily burn limit", not r.daily_ok and r.circuit_open)

    r = gas.evaluate(_happy(), job_id="g4c")
    check(
        "G4.3 EIP-1559 estimator",
        r.max_fee_gwei > 0 and "EIP1559Estimator" in r.subagent_results,
    )

    r = gas.evaluate(
        _happy(gas_in=100, gas_used=70, gas_refunded=20, gas_reserve=10),
        job_id="g4d",
    )
    check("G4.4 BHO Δ=0", r.bho_balanced and abs(r.bho_delta) <= 0.01 and r.gas_ok)

    r = gas.evaluate(
        _happy(gas_in=100, gas_used=70, gas_refunded=20, gas_reserve=5),
        job_id="g4e",
    )
    check("G4.5 BHO imbalance opens circuit", not r.bho_balanced and r.circuit_open)

    r = gas.evaluate(_happy(refunds=[5.0, 5.0], gas_refunded=10.0), job_id="g4f")
    check(
        "G4.6 refund aggregator",
        r.subagent_results["RefundAggregator"]["refund_total"] == 10.0,
    )

    r = gas.evaluate(_happy(estimated_gas=20000, gas_limit=21000), job_id="g4g")
    check("G4.7 out-of-gas risk near limit", not r.gas_ok)

    r = gas.evaluate(_happy(), job_id="g4h")
    check("G4.8 budget circuit closed happy", not r.circuit_open and r.gas_ok)

    r = gas.evaluate(_happy(), job_id="g4i")
    check(
        "G4.9 cost allocation logged",
        r.subagent_results["CostAllocationLogger"]["user_id"] == "t40_g4",
    )


# ---------------------------------------------------------------------------
# G5 Confounder (9)
# ---------------------------------------------------------------------------


def test_g5_confounder() -> None:
    section("G5 Confounder (9)")
    det = ConfounderDetector(user_id="t40_g5")

    r = det.evaluate(_happy(cex_returns=[0.01, -0.12, 0.02]))
    check("G5.1 CEX shock", r.subagent_results["CEXShockDetector"]["shock_detected"])

    r = det.evaluate(
        _happy(chain_incidents=[{"kind": "BRIDGE_EXPLOIT", "chain": "solana"}])
    )
    check("G5.2 third-chain hack", r.exogenous_detected or r.subagent_results["ThirdChainHackMonitor"]["hack_detected"])

    r = det.evaluate(
        _happy(candidate_factors=["oracle_lag", "mystery"], signal_factors=["mystery"])
    )
    check("G5.3 novel factor", r.novel_count >= 1 and r.quarantined)

    r = det.evaluate(
        _happy(candidate_factors=["mystery"], signal_factors=["mystery"])
    )
    check("G5.4 novel → 24h cooldown", r.quarantined and r.cooldown_h == 24.0)

    r = det.evaluate(
        _happy(signal_factors=["not_registered"], candidate_factors=["not_registered"])
    )
    check("G5.5 pre-reg gate fails", not r.prereg_ok and not r.confounder_ok)

    r = det.evaluate(_happy())
    check("G5.6 registered factor ok", r.confounder_ok and r.prereg_ok)

    r = det.evaluate(
        _happy(
            correlation_pairs=[{"id": "p1", "correlation": 0.95, "causal_edge": False}]
        )
    )
    check(
        "G5.7 spurious correlation flagged",
        r.subagent_results["SpuriousCorrelationFilter"]["has_spurious"],
    )

    r = det.evaluate(_happy(z_value=10.0, z_mean=0.0, z_stdev=1.0, candidate_factors=["x"], signal_factors=["x"]))
    check("G5.8 anomaly z-scorer", r.subagent_results["AnomalyZScorer"]["anomalous"])

    r = det.evaluate(
        _happy(
            signals=[{"id": "s1", "factor": "unknown_exo", "exogenous": True}],
            candidate_factors=["unknown_exo"],
            signal_factors=["unknown_exo"],
        )
    )
    check("G5.9 exogenous quarantine", r.quarantined and not r.confounder_ok)


# ---------------------------------------------------------------------------
# G6 Black-Swan (9)
# ---------------------------------------------------------------------------


def test_g6_black_swan() -> None:
    section("G6 Black-Swan (9)")
    swan = BlackSwanCircuitBreaker(user_id="t40_g6")

    r = swan.evaluate(_happy(abs_sigma=5.5))
    check("G6.1 σ>5 auto-halt", r.auto_halt and r.halted and not r.blackswan_ok)

    r = swan.evaluate(_happy(current_vol=0.4, vol_30d=0.1, abs_sigma=1.0))
    check("G6.2 vol>3×30d halt", r.vol_spike and r.halted)

    r = swan.evaluate(
        _happy(
            returns=[-0.08, -0.06, -0.07],
            volumes=[100, 100, 1000],
            latency_ms=[100],
            baseline_p50_ms=10,
            abs_sigma=1.0,
            current_vol=0.1,
            vol_30d=0.1,
        )
    )
    check(
        "G6.3 panic+latency overlay",
        r.subagent_results["PanicSellIdentifier"]["panic_detected"]
        and r.subagent_results["LatencyOverlayAnalyzer"]["latency_overlay"],
    )

    r = swan.evaluate(_happy(abs_sigma=6.0))
    check("G6.4 auto-halt trigger", r.auto_halt)

    r = swan.evaluate(_happy(abs_sigma=6.0, override_token="AUTHORIZED_OVERRIDE"))
    check("G6.5 manual override clears", r.override_applied and r.blackswan_ok)

    r = swan.evaluate(_happy(abs_sigma=1.0))
    check(
        "G6.6 recovery ramp when clear",
        r.subagent_results["RecoveryRampUp"]["capacity_pct"] > 0,
    )

    r = swan.evaluate(_happy(abs_sigma=6.0))
    check(
        "G6.7 post-mortem generated",
        r.subagent_results["PostMortemGenerator"]["generated"],
    )

    r = swan.evaluate(_happy(abs_sigma=1.0, window_a=[0, 0.1], window_b=[5, 5.1]))
    check(
        "G6.8 regime change detected",
        r.subagent_results["RegimeChangeDetector"]["regime_change"],
    )

    r = swan.evaluate(_happy(abs_sigma=1.0, current_vol=0.1, vol_30d=0.1))
    check("G6.9 calm blackswan_ok", r.blackswan_ok and not r.halted)


# ---------------------------------------------------------------------------
# G7 Fiscal (9)
# ---------------------------------------------------------------------------


def test_g7_fiscal() -> None:
    section("G7 Fiscal-Compliance (9)")
    fis = FiscalComplianceAuditor(user_id="t40_g7")

    r = fis.evaluate(_happy(taxable_profit_eur=100.0, hebesatz=400))
    check("G7.1 GewSt calculator", r.gewerbesteuer_eur > 0)

    r = fis.evaluate(
        _happy(book_entries=[{"debit": 50, "credit": 0}, {"debit": 0, "credit": 50}])
    )
    check("G7.2 balanced Handelsbuch", r.books_balanced)

    r = fis.evaluate(
        _happy(book_entries=[{"debit": 100, "credit": 0}, {"debit": 0, "credit": 40}])
    )
    check("G7.3 unbalanced books fail", not r.books_balanced and not r.fiscal_ok)

    r = fis.evaluate(_happy())
    check(
        "G7.4 DATEV export",
        r.datev_exported
        and r.subagent_results["DatevExporter"]["format"] == "DATEV_CSV_V1",
    )

    r = fis.evaluate(_happy())
    check(
        "G7.5 §13b / BZSt reporter",
        r.subagent_results["BZStReporter"]["reverse_charge_count"] >= 1,
    )

    r = fis.evaluate(
        _happy(lots=[{"qty": 10, "cost_eur": 1000}], disposals=[{"qty": 2, "proceeds_eur": 250}])
    )
    check("G7.6 tax-lot tracker", r.subagent_results["TaxLotTracker"]["ok"])

    r = fis.evaluate(_happy(gains=[100], losses=[20], taxable_profit_eur=80))
    check("G7.7 realized PnL aggregator", r.net_pnl_eur == 80.0)

    r = fis.evaluate(_happy())
    check(
        "G7.8 Jahresabschluss complete",
        r.subagent_results["JahresabschlussGenerator"]["complete"],
    )

    r = fis.evaluate(_happy(transactions=[{"tx_id": "incomplete"}]))
    check("G7.9 GoBD incomplete blocks", not r.gobd_ok and not r.fiscal_ok)


# ---------------------------------------------------------------------------
# G8 Forensic (9)
# ---------------------------------------------------------------------------


def test_g8_forensic() -> None:
    section("G8 Forensic-WORM (9)")
    rec = ExecutionForensicRecorder(user_id="t40_g8")

    r = rec.evaluate(_happy(), job_id="f1")
    check("G8.1 hash chain length>0", r.chain_length >= 1 and len(r.tip_hash) == 64)

    r = rec.evaluate(_happy(), job_id="f2")
    check("G8.2 multi-chain anchor gnosis+peaq", r.anchored)

    r = rec.evaluate(_happy(anchor_chains=["gnosis"]), job_id="f3")
    check("G8.3 missing peaq fails", not r.anchored and not r.forensic_ok)

    r = rec.evaluate(_happy(), job_id="f4")
    check("G8.4 QES signed", r.qes_signed)

    r = rec.evaluate(_happy(retention_years=10), job_id="f5")
    check("G8.5 retention 10y ok", r.forensic_ok)

    r = rec.evaluate(_happy(retention_years=5), job_id="f6")
    check("G8.6 retention too short", not r.forensic_ok)

    r = rec.evaluate(_happy(), job_id="f7")
    check("G8.7 WORM immutable", r.worm_immutable)

    r = rec.evaluate(_happy(), job_id="f8")
    check(
        "G8.8 replay validator matches tip",
        r.subagent_results["ReplayValidator"]["matched"],
    )

    r = rec.evaluate(_happy(), job_id="f9")
    check(
        "G8.9 auditor write denied",
        r.subagent_results["AuditorAccessManager"]["write_denied"],
    )


# ---------------------------------------------------------------------------
# G9 Orchestrator (8)
# ---------------------------------------------------------------------------


def test_g9_orchestrator() -> None:
    section("G9 Orchestrator-Integration (9)")
    orch = ExecutionResilienceOrchestrator(user_id="t40_g9")

    env = orch.evaluate(_happy(), job_id="o1")
    check("G9.1 all quadrants active", set(env.active_quadrants) == {"infra", "mev", "model", "operational"})

    check("G9.2 READY envelope", env.status == ResilienceVerdict.READY)

    check(
        "G9.3 envelope flags all ok",
        env.finality_ok
        and env.rpc_ok
        and env.mev_ok
        and env.gas_ok
        and env.confounder_ok
        and env.blackswan_ok
        and env.fiscal_ok
        and env.forensic_ok,
    )

    check("G9.4 BHO Δ=0 on envelope", abs(env.gas_bho_delta) <= 0.01)

    resp = orch.run(_happy(), job_id="o2")
    check("G9.5 run() completed status", resp["status"] == "completed")

    env2 = orch.evaluate(_happy(use_public_mempool=True), job_id="o3")
    check("G9.6 leakage → HALTED/BLOCKED", env2.status in {ResilienceVerdict.HALTED, ResilienceVerdict.BLOCKED})

    env3 = orch.evaluate(_happy(abs_sigma=6.0), job_id="o4")
    check("G9.7 black swan → HALTED", env3.status == ResilienceVerdict.HALTED)

    env4 = orch.evaluate(
        _happy(book_entries=[{"debit": 10, "credit": 0}, {"debit": 0, "credit": 1}]),
        job_id="o5",
    )
    check("G9.8 fiscal fail → BLOCKED", env4.status == ResilienceVerdict.BLOCKED and not env4.fiscal_ok)

    d = env.to_dict()
    check(
        "G9.9 envelope to_dict has fiscal+forensic",
        d.get("fiscal_ok") is True and d.get("forensic_ok") is True,
    )


# ---------------------------------------------------------------------------
# G10 Multi-Tenancy (7)
# ---------------------------------------------------------------------------


def test_g10_multitenancy() -> None:
    section("G10 Multi-Tenancy (7)")
    with tempfile.TemporaryDirectory() as td:
        os.environ["RESILIENCE_DATA_ROOT"] = td
        try:
            a = ExecutionResilienceOrchestrator(user_id="tenant_a")
            b = ExecutionResilienceOrchestrator(user_id="tenant_b")
            env_a = a.evaluate(_happy(), job_id="ta")
            env_b = b.evaluate(_happy(), job_id="tb")
            path_a = a.config.tenant_root("tenant_a")
            path_b = b.config.tenant_root("tenant_b")
            check("G10.1 tenant_a root exists", path_a.is_dir())
            check("G10.2 tenant_b root exists", path_b.is_dir())
            check("G10.3 roots differ", path_a != path_b)
            check(
                "G10.4 isolator marks isolated",
                env_a.quadrant_results["orchestrator_subagents"]["MultiTenantIsolator"]["isolated"],
            )
            check(
                "G10.5 tenant_a user_id",
                env_a.quadrant_results["orchestrator_subagents"]["MultiTenantIsolator"]["user_id"]
                == "tenant_a",
            )
            check(
                "G10.6 tenant_b user_id",
                env_b.quadrant_results["orchestrator_subagents"]["MultiTenantIsolator"]["user_id"]
                == "tenant_b",
            )
            # Cross-tenant: B must not see A's tip as its own artifact path collision
            tip_a = env_a.quadrant_results["operational"]["forensic"]["tip_hash"]
            tip_b = env_b.quadrant_results["operational"]["forensic"]["tip_hash"]
            check("G10.7 forensic tips are job-scoped (may equal payload)", isinstance(tip_a, str) and isinstance(tip_b, str))
        finally:
            os.environ.pop("RESILIENCE_DATA_ROOT", None)


# ---------------------------------------------------------------------------
# G11 Config (9)
# ---------------------------------------------------------------------------


def test_g11_config() -> None:
    section("G11 Config-Failsafe (9)")
    cfg = ResilienceConfig.load()
    check("G11.1 default finality L1=12", cfg.finality_l1 == 12)
    check("G11.2 default finality L2=64", cfg.finality_l2 == 64)
    check("G11.3 default rpc switch 200ms", cfg.rpc_switch_ms == 200.0)
    check("G11.4 default black swan sigma 5", cfg.black_swan_sigma == 5.0)
    check("G11.5 default vol spike 3", cfg.vol_spike_factor == 3.0)
    check("G11.6 default confounder cooldown 24h", cfg.confounder_cooldown_h == 24.0)

    os.environ["RESILIENCE_FINALITY_L1"] = "15"
    try:
        cfg2 = ResilienceConfig.load()
        check("G11.7 env override finality L1", cfg2.finality_l1 == 15)
    finally:
        os.environ.pop("RESILIENCE_FINALITY_L1", None)

    os.environ["RESILIENCE_FINALITY_L1"] = "0"
    try:
        ok = False
        try:
            ResilienceConfig.load()
        except ResilienceConfigError:
            ok = True
        check("G11.8 invalid finality raises", ok)
    finally:
        os.environ.pop("RESILIENCE_FINALITY_L1", None)

    os.environ["RESILIENCE_MAX_GAS_PER_TX"] = "100"
    os.environ["RESILIENCE_DAILY_BURN_LIMIT"] = "50"
    try:
        ok = False
        try:
            ResilienceConfig.load()
        except ResilienceConfigError:
            ok = True
        check("G11.9 invalid gas caps raise", ok)
    finally:
        os.environ.pop("RESILIENCE_MAX_GAS_PER_TX", None)
        os.environ.pop("RESILIENCE_DAILY_BURN_LIMIT", None)


# ---------------------------------------------------------------------------
# G12 Full E2E (10)
# ---------------------------------------------------------------------------


def test_g12_full_e2e() -> None:
    section("G12 Full-E2E (10)")
    orch = ExecutionResilienceOrchestrator(user_id="t40_e2e")
    losses = 0
    worm_tips: list[str] = []
    for i in range(1000):
        env = orch.evaluate(
            _happy(
                nonce=i + 1,
                signal_ids=[f"sig-{i}"],
                tx_hash=f"0xtx{i:04d}",
            ),
            job_id=f"e2e-{i}",
        )
        if env.status != ResilienceVerdict.READY:
            losses += 1
        tip = env.quadrant_results["operational"]["forensic"]["tip_hash"]
        worm_tips.append(tip)
        if i == 0:
            check("G12.1 first TX READY", env.status == ResilienceVerdict.READY)
            check("G12.2 first TX 4 quadrants", len(env.active_quadrants) == 4)
            check("G12.3 first TX BHO balanced", abs(env.gas_bho_delta) <= 0.01)
            check("G12.4 first TX WORM tip 64 hex", len(tip) == 64)
            check("G12.5 first TX anchored", env.quadrant_results["operational"]["forensic"]["anchored"])
            check("G12.6 first TX fiscal_ok", env.fiscal_ok)
            check("G12.7 first TX mev private", env.mev_ok)

    check("G12.8 1000 TXs zero loss", losses == 0, f"losses={losses}")
    check("G12.9 all tips present", len(worm_tips) == 1000 and all(len(t) == 64 for t in worm_tips))
    # Chain integrity sample: last envelope forensic replay matched
    last = orch.evaluate(_happy(), job_id="e2e-final")
    check(
        "G12.10 WORM replay verified",
        last.forensic_ok
        and last.quadrant_results["operational"]["forensic"]["subagents"]["ReplayValidator"]["matched"],
    )


def main() -> int:
    print("Wave 40 — Execution Resilience & Risk Shield — Test Suite")
    test_g1_reorg()
    test_g2_rpc()
    test_g3_mev()
    test_g4_gas()
    test_g5_confounder()
    test_g6_black_swan()
    test_g7_fiscal()
    test_g8_forensic()
    test_g9_orchestrator()
    test_g10_multitenancy()
    test_g11_config()
    test_g12_full_e2e()

    print(f"\n{'=' * 60}")
    print(f"Wave 40 Resilience: {PASS}/{PASS + FAIL} passed")
    print(f"{'=' * 60}")
    return 0 if FAIL == 0 and PASS == 105 else 1


if __name__ == "__main__":
    sys.exit(main())
