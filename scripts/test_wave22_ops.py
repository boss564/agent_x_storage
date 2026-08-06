#!/usr/bin/env python3
"""
Wave 22 E2E Test: Ops Security — Secure Relay & Automated Deployment Engine.
Testet alle 9 Root-Agenten mit ihren 36 Subagenten.

Usage:
    python scripts/test_wave22_ops.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Lazy imports: each test function imports only the classes it needs.
# The full 50-class import exhausts memory in constrained environments (OOM → SIGKILL).
# Per-function imports keep the working set small.

PASSED = 0
FAILED = 0


def check(desc: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✅ {desc}")
    else:
        FAILED += 1
        print(f"  ❌ {desc}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ================================================================
# Agent 1: KeyVaultManager
# ================================================================


def test_a1_key_vault() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        KeyVaultManager, HSMConnector, KeyRotationScheduler, SigningProxy, AuditLogWriter,
    )
    section("Agent 1: KeyVaultManager (4 Subagents)")

    hsm = HSMConnector().connect({"available": True, "provider": "aws-kms"})
    check("1.1 HSM: connected", hsm["connected"])

    rot = KeyRotationScheduler().schedule([{"last_rotation": "2020-01-01"}])
    check("1.2 Rotation: 1 due", rot["rotation_due"] == 1)

    sig = SigningProxy().sign("0xdeadbeef", "key-001")
    check("1.3 Signer: signature generated", sig["signature"].startswith("0x"))

    audit = AuditLogWriter().log("sign", "key-001", {"reason": "test"})
    check("1.4 Audit: entry created", "audit_hash" in audit)

    kv = KeyVaultManager().evaluate()
    check("1.5 KV: hsm present", "hsm" in kv)
    check("1.6 KV: signer ready", kv["signer_ready"])


# ================================================================
# Agent 2: GasOptimizer
# ================================================================


def test_a2_gas_optimizer() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        GasOptimizer, FeeEstimator, ResubmissionEngine, ChainProfiler, MEVProtectionAdvisor,
    )
    section("Agent 2: GasOptimizer (4 Subagents)")

    fee = FeeEstimator().estimate("ethereum")
    check("2.1 Fee: base > 0", fee["base_fee_gwei"] > 0)
    check("2.2 Fee: total >= base", fee["total_gwei"] >= fee["base_fee_gwei"])

    resub = ResubmissionEngine().resubmit({"gas_price_gwei": 20}, 5)
    check("2.3 Resubmit: action=RESUBMIT (5 blocks)", resub["action"] == "RESUBMIT")

    prof = ChainProfiler().profile("gnosis")
    check("2.4 Profile: chain=gnosis", prof["chain"] == "gnosis")

    mev = MEVProtectionAdvisor().advise(200_000)
    check("2.5 MEV: FLASHBOTS for 200k", mev["strategy"] == "FLASHBOTS")
    mev2 = MEVProtectionAdvisor().advise(5_000)
    check("2.6 MEV: PUBLIC for 5k", mev2["strategy"] == "PUBLIC")

    gs = GasOptimizer().evaluate("gnosis", 50000)
    check("2.7 Gas: fee present", "fee" in gs)
    check("2.8 Gas: mev advice present", "mev_advice" in gs)


# ================================================================
# Agent 3: NonceManager
# ================================================================


def test_a3_nonce_manager() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        NonceManager, NonceTracker, GapDetector, ConflictResolver, ChainStateReconciler,
    )
    section("Agent 3: NonceManager (4 Subagents)")

    track = NonceTracker().track("gnosis", "0xDefaultAddress")
    check("3.1 Track: nonce > 0", track["current_nonce"] > 0)

    gaps = GapDetector().detect([1, 2, 3, 5, 6])
    check("3.2 Gaps: 1 gap (4)", gaps["gap_count"] == 1)

    res = ConflictResolver().resolve(40, 42)
    check("3.3 Conflict: RESYNC when local < chain", res["action"] == "RESYNC")
    res2 = ConflictResolver().resolve(42, 42)
    check("3.4 Conflict: PROCEED when equal", res2["action"] == "PROCEED")

    rec = ChainStateReconciler().reconcile(["gnosis", "polygon"], "0xAddr")
    check("3.5 Reconcile: 2 chains", len(rec) == 2)

    nm = NonceManager().evaluate("gnosis")
    check("3.6 Nonce: tracking present", "tracking" in nm)


# ================================================================
# Agent 4: MetaTxEngine
# ================================================================


def test_a4_meta_tx() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        MetaTxEngine, UserOpBuilder, PaymasterIntegrator, BundlerClient, EntryPointValidator,
    )
    section("Agent 4: MetaTxEngine (4 Subagents)")

    uo = UserOpBuilder().build("0xTarget", "0xData", "0xSender")
    check("4.1 UserOp: hash generated", "userOpHash" in uo)
    check("4.2 UserOp: sender set", uo["sender"] == "0xSender")

    pm = PaymasterIntegrator().integrate()
    check("4.3 Paymaster: sponsor enabled", pm["sponsor_enabled"])

    bundler = BundlerClient().submit(uo, "gnosis")
    check("4.4 Bundler: submitted", bundler["status"] == "SUBMITTED")

    val = EntryPointValidator().validate(uo)
    check("4.5 Validator: valid", val["valid"])

    mt = MetaTxEngine().evaluate("0xT", "0xD", "0xS")
    check("4.6 MetaTx: user_op present", "user_op" in mt)
    check("4.7 MetaTx: paymaster present", "paymaster" in mt)


# ================================================================
# Agent 5: AutotaskScheduler
# ================================================================


def test_a5_autotasks() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        AutotaskScheduler, CronScheduler, SandboxExecutor, WebhookListener, ConditionEvaluator,
    )
    section("Agent 5: AutotaskScheduler (4 Subagents)")

    cron = CronScheduler().schedule([{"id": "task-1"}])
    check("5.1 Cron: 1 scheduled", cron["scheduled"] == 1)

    sb = SandboxExecutor().execute("cleanup", {"dry": True})
    check("5.2 Sandbox: executed", sb["status"] == "EXECUTED")

    wh = WebhookListener().listen("/hooks/inbound")
    check("5.3 Webhook: endpoint set", wh["endpoint"] == "/hooks/inbound")

    ce = ConditionEvaluator().evaluate_condition("value > 100", {"value": 150})
    check("5.4 Condition: met", ce["met"])

    at = AutotaskScheduler().evaluate()
    check("5.5 Autotasks: status=READY", at["status"] == "READY")


# ================================================================
# Agent 6: WebhookIntegrator
# ================================================================


def test_a6_webhooks() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        WebhookIntegrator, WebhookReceiver, SignatureVerifier, RateLimiter, PayloadValidator,
    )
    section("Agent 6: WebhookIntegrator (4 Subagents)")

    recv = WebhookReceiver().receive({"event": "test"}, "10.0.0.1")
    check("6.1 Receiver: received", recv["received"])

    sig = SignatureVerifier().verify("0xsig", "payload", "secret")
    check("6.2 Signature: valid", sig["valid"])

    rl = RateLimiter().check("10.0.0.1", 50)
    check("6.3 Rate limit: allowed (50 < 100)", rl["allowed"])
    rl2 = RateLimiter().check("10.0.0.2", 150)
    check("6.4 Rate limit: blocked (150 > 100)", not rl2["allowed"])

    pv = PayloadValidator().validate({"name": "test"}, {"required_fields": ["name"]})
    check("6.5 Payload: valid", pv["valid"])

    wi = WebhookIntegrator().evaluate()
    check("6.6 Webhook: receiver ready", wi["receiver_ready"])


# ================================================================
# Agent 7: ConditionExecutor
# ================================================================


def test_a7_conditions() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        ConditionExecutor, ThresholdTrigger, TimeBasedTrigger, EventBasedTrigger, ActionDispatcher,
    )
    section("Agent 7: ConditionExecutor (4 Subagents)")

    tt = ThresholdTrigger().check(95, 80, "above")
    check("7.1 Threshold: triggered (95 > 80)", tt["triggered"])
    tt2 = ThresholdTrigger().check(30, 50, "above")
    check("7.2 Threshold: not triggered (30 < 50)", not tt2["triggered"])

    tb = TimeBasedTrigger().check("2020-01-01T00:00:00Z")
    check("7.3 Time: due (past)", tb["due"])

    eb = EventBasedTrigger().match("Transfer", ["Transfer(address,address,uint256)"])
    check("7.4 Event: matched", eb["matched"])

    ad = ActionDispatcher().dispatch("PAUSE", {"contract": "0xEscrow"})
    check("7.5 Dispatch: executed", ad["status"] == "EXECUTED")

    ce = ConditionExecutor().evaluate()
    check("7.6 Condition: ARMED", ce["status"] == "ARMED")


# ================================================================
# Agent 8: DeployVerifier
# ================================================================


def test_a8_deploy_verify() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        DeployVerifier, BytecodeComparator, SourceVerifier, StorageLayoutChecker, CompilerFlagValidator,
    )
    section("Agent 8: DeployVerifier (4 Subagents)")

    bc = BytecodeComparator().compare("0x6080604052", "0x6080604052")
    check("8.1 Bytecode: match", bc["match"])

    sv = SourceVerifier().verify("contract Test {}", "gnosis", "0xAddr")
    check("8.2 Source: pending", sv["verification_status"] == "PENDING")

    sl = StorageLayoutChecker().check({"slots": ["slot1", "slot2"]}, {"slots": ["slot2", "slot3"]})
    check("8.3 Storage: 1 collision (slot2)", sl["collision_count"] == 1)
    check("8.4 Storage: not safe", not sl["safe"])

    cf = CompilerFlagValidator().validate("0.8.20", ["optimizer_enabled", "200"])
    check("8.5 Compiler: all ok", cf["all_ok"])

    dv = DeployVerifier().evaluate("0x6080", "0x6080", "contract Test {}")
    check("8.6 DeployVerify: source verified", dv["source_verified"])


# ================================================================
# Agent 9: SecureDeployOrchestrator
# ================================================================


def test_a9_secure_deploy() -> None:
    from agents_b2g.ops.relay_orchestrator import (
        SecureDeployOrchestrator, MultiSigApprover, StagedRolloutManager, RollbackGuard, DeploymentAuditor,
    )
    section("Agent 9: SecureDeployOrchestrator (4 Subagents)")

    ms = MultiSigApprover().approve({"contract": "EscrowVault"}, ["s1", "s2", "s3"])
    check("9.1 MultiSig: 3/3 >= 2 required", ms["approved"])

    staged = StagedRolloutManager().plan(100)
    check("9.2 Staged: >= 1 stage", len(staged["stages"]) >= 1)

    rb = RollbackGuard().prepare("dep-001")
    check("9.3 Rollback: ready", rb["rollback_ready"])

    audit = DeploymentAuditor().audit({"contract": "Test"}, "SUCCESS")
    check("9.4 Audit: hash generated", "deployment_hash" in audit)

    sd = SecureDeployOrchestrator().evaluate("dep-001")
    check("9.5 Deploy: READY", sd["status"] == "READY_TO_DEPLOY")


# ================================================================
# Config
# ================================================================


def test_config() -> None:
    from agents_b2g.ops.relay_orchestrator import RelayConfig
    section("Configuration")

    check("Cfg: 10 chains", len(RelayConfig.SUPPORTED_CHAINS) == 10)
    check("Cfg: Max retries=3", RelayConfig.MAX_RETRIES == 3)
    check("Cfg: Multisig sigs=2", RelayConfig.MULTISIG_REQUIRED_SIGS == 2)
    check("Cfg: Staged rollout=10%", RelayConfig.DEPLOY_STAGED_ROLLOUT_PCT == 10)
    check("Cfg: ERC4337 entrypoint set", RelayConfig.ERC4337_ENTRYPOINT.startswith("0x"))


# ================================================================
# Main
# ================================================================


def main() -> int:
    print("=" * 55)
    print("  Wave 22 E2E: Ops Security & Secure Deployment Engine")
    print("  9 Root-Agenten × 4 Subagenten = 36 Tests")
    print("=" * 55)

    test_a1_key_vault()
    test_a2_gas_optimizer()
    test_a3_nonce_manager()
    test_a4_meta_tx()
    test_a5_autotasks()
    test_a6_webhooks()
    test_a7_conditions()
    test_a8_deploy_verify()
    test_a9_secure_deploy()
    test_config()

    total = PASSED + FAILED
    print(f"\n{'='*55}")
    print(f"  Results: {PASSED}/{total} passed")
    if FAILED > 0:
        print(f"  ❌ {FAILED} FAILED")
    print(f"{'='*55}")

    if FAILED == 0:
        print(f"\n  🚀 ALLE TESTS BESTANDEN — Wave 22 ist bereit!")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
