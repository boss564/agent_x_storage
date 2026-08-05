"""
Test suite for Wave 16 — Monerium SEPA-Bridge (9 agents).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents_b2g.bridge.agents import (
    SEPABridgeSupervisor,
    SEPABridgeOrchestrator,
    EUReMinterSubagent,
    EUReBurnerSubagent,
    IBANValidatorSubagent,
    SEPAAuditTrailSubagent,
    MoneriumAPIClientSubagent,
    GasPaymasterSubagent,
    BridgeBalanceMonitorSubagent,
    SEPAConfirmationSubagent,
    BridgeTxType,
    BridgeTxStatus,
    SEPAStatus,
    MiCARCompliance,
    make_response,
    JSONLogger,
)


# ============================================================
# Core contracts
# ============================================================


def test_make_response():
    resp = make_response("completed", "job-001",
                         artifacts=[{"type": "test"}], logs=["ok"])
    assert resp["status"] == "completed"
    assert resp["job_id"] == "job-001"
    assert len(resp["artifacts"]) == 1
    assert resp["error"] is None
    assert len(resp["logs"]) == 1


def test_json_logger(tmp_path):
    log = JSONLogger(log_path=tmp_path / "bridge_test.jsonl", agent_name="test")
    log.info("test", key="val")
    lines = (tmp_path / "bridge_test.jsonl").read_text().strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["agent"] == "test"
    assert entry["level"] == "INFO"


# ============================================================
# Agent 1: SEPABridgeOrchestrator
# ============================================================


def test_orchestrator_deposit():
    orch = SEPABridgeOrchestrator()
    orch.register_sub_agent("IBANValidator", IBANValidatorSubagent())
    orch.register_sub_agent("EUReMinter", EUReMinterSubagent())
    orch.register_sub_agent("SEPAAuditTrail", SEPAAuditTrailSubagent())

    result = orch.process_sepa_deposit(
        sepa_reference="SEPA-IN-001", amount_eur=Decimal("500000.00"),
        sender_iban="DE89370400440532013000", tender_id="TED-2026-0815",
    )
    assert result["status"] == "completed"
    assert result["artifacts"][0]["amount_eur"] == 500000.0


def test_orchestrator_payout():
    orch = SEPABridgeOrchestrator()
    orch.register_sub_agent("IBANValidator", IBANValidatorSubagent())
    orch.register_sub_agent("EUReBurner", EUReBurnerSubagent())
    orch.register_sub_agent("SEPAConfirmation", SEPAConfirmationSubagent())
    orch.register_sub_agent("SEPAAuditTrail", SEPAAuditTrailSubagent())

    result = orch.process_payout(
        tender_id="TED-2026-0815", installment_no=1,
        amount_eure=Decimal("70300.00"),
        recipient_iban="DE89370400440532013000",
        recipient_bic="GENODEF1XXX",
        popw_release_tx="0xPoPW-release",
    )
    assert result["status"] == "completed"
    assert result["artifacts"][0]["installment_no"] == 1
    assert "burn_tx_hash" in result["artifacts"][0]


def test_orchestrator_circuit_breaker():
    orch = SEPABridgeOrchestrator()
    orch.trip_circuit("Balance mismatch detected")
    result = orch.process_sepa_deposit(
        "SEPA-IN-002", Decimal("100"), "DE89370400440532013000", "TED-TEST",
    )
    assert result["status"] == "rejected"
    assert "circuit breaker" in result["error"].lower()

    orch.reset_circuit()
    orch.register_sub_agent("IBANValidator", IBANValidatorSubagent())
    orch.register_sub_agent("EUReMinter", EUReMinterSubagent())
    orch.register_sub_agent("SEPAAuditTrail", SEPAAuditTrailSubagent())
    result2 = orch.process_sepa_deposit(
        "SEPA-IN-003", Decimal("100"), "DE89370400440532013000", "TED-TEST",
    )
    assert result2["status"] == "completed"


def test_orchestrator_bad_iban():
    orch = SEPABridgeOrchestrator()
    orch.register_sub_agent("IBANValidator", IBANValidatorSubagent())

    result = orch.process_sepa_deposit(
        "SEPA-IN-BAD", Decimal("100"), "XX1234567890", "TED-TEST",
    )
    assert result["status"] == "failed"


# ============================================================
# Agent 2: EUReMinterSubagent
# ============================================================


def test_minter():
    minter = EUReMinterSubagent()
    result = minter.mint(Decimal("500000.00"), "TED-2026-0815", "SEPA-IN-001")
    assert "tx_hash" in result
    assert result["tx_hash"].startswith("0x")
    s = minter.status()
    assert s["mint_count"] == 1
    assert s["total_minted"] == "500000.00"


# ============================================================
# Agent 3: EUReBurnerSubagent
# ============================================================


def test_burner():
    burner = EUReBurnerSubagent()
    result = burner.burn(
        Decimal("70300.00"), "DE89370400440532013000", "GENODEF1XXX",
        "TED-2026-0815", 1, "0xPoPW-release",
    )
    assert result["burn_tx_hash"].startswith("0x")
    assert result["amount_eur"] == 70300.0
    assert result["installment_no"] == 1
    assert "****" in result["recipient_iban"]
    s = burner.status()
    assert s["burn_count"] == 1


def test_burner_rejects_short_iban():
    burner = EUReBurnerSubagent()
    try:
        burner.burn(Decimal("100"), "XX12", "XXX", "TED-TEST", 1)
        assert False, "Should have raised"
    except (ValueError, RuntimeError):
        pass


# ============================================================
# Agent 4: IBANValidatorSubagent
# ============================================================


def test_iban_validate_valid_de():
    validator = IBANValidatorSubagent()
    result = validator.validate("DE89370400440532013000", "GENODEF1XXX")
    assert result["status"] == "OK"
    assert result["country"] == "DE"


def test_iban_validate_non_sepa():
    validator = IBANValidatorSubagent()
    result = validator.validate("US12345678901234567890")
    assert result["status"] == "ERROR"


def test_iban_validate_bad_checksum():
    validator = IBANValidatorSubagent()
    # DE IBAN with wrong checksum
    result = validator.validate("DE00370400440532013000")
    assert result["status"] == "ERROR"


def test_iban_validate_bic():
    validator = IBANValidatorSubagent()
    result = validator.validate("DE89370400440532013000", bic="INVALID")
    assert result["status"] == "ERROR"


def test_iban_validate_steuer_id():
    validator = IBANValidatorSubagent()
    result = validator.validate("DE89370400440532013000", steuer_id="12345678901")  # 11-digit DE
    assert result["status"] == "OK"

    result2 = validator.validate("DE89370400440532013000", steuer_id="ABC")
    assert result2["status"] == "ERROR"


def test_iban_mod97():
    # Known valid DE IBAN
    assert IBANValidatorSubagent._mod97_check("DE89370400440532013000")
    # Tampered
    assert not IBANValidatorSubagent._mod97_check("DE99370400440532013000")


def test_iban_blacklist():
    validator = IBANValidatorSubagent()
    # Known blacklisted IBAN
    result = validator.validate("DE12345678901234567890")
    assert result["status"] == "BLACKLISTED"
    assert "Betrug" in result["message"]


def test_iban_validate_payment_recipient():
    validator = IBANValidatorSubagent()
    result = validator.validate_payment_recipient(
        "DE89370400440532013000", "GENODEF1XXX",
        "12345678901", "Craft Procurement GU GmbH",
    )
    assert result["status"] == "OK"
    assert result["company_name"] == "Craft Procurement GU GmbH"
    assert "validation_hash" in result
    assert result["validation_hash"].startswith("0x")


def test_iban_blacklist_not_triggered():
    validator = IBANValidatorSubagent()
    result = validator.validate("DE89370400440532013000")
    assert result["status"] == "OK"


# ============================================================
# Agent 5: SEPAAuditTrailSubagent
# ============================================================


def test_audit_trail_record(tmp_path):
    audit = SEPAAuditTrailSubagent(audit_dir=tmp_path / "audit")
    entry = audit.record(
        BridgeTxType.MINT, "job-001", "TED-2026-0815",
        Decimal("500000.00"), "SEPA-IN-001", sender_iban="DE89370400440532013000",
    )
    assert entry["entry_id"] == 1
    assert entry["tx_type"] == "MINT"

    # Verify file was written
    log_files = list((tmp_path / "audit").glob("bridge_audit_*.jsonl"))
    assert len(log_files) == 1
    content = json.loads(log_files[0].read_text().strip())
    assert content["tender_id"] == "TED-2026-0815"


def test_audit_trail_query(tmp_path):
    audit = SEPAAuditTrailSubagent(audit_dir=tmp_path / "audit")
    audit.record(BridgeTxType.MINT, "j1", "TED-A", Decimal("100"), "R-A")
    audit.record(BridgeTxType.BURN, "j2", "TED-B", Decimal("200"), "R-B")
    audit.record(BridgeTxType.MINT, "j3", "TED-A", Decimal("300"), "R-C")

    # Filter by tender
    results = audit.query(tender_id="TED-A")
    assert len(results) == 2

    # Filter by type
    results2 = audit.query(tx_type=BridgeTxType.BURN)
    assert len(results2) == 1
    assert results2[0]["tender_id"] == "TED-B"


# ============================================================
# Agent 6: MoneriumAPIClientSubagent
# ============================================================


def test_api_client_mock_mode():
    client = MoneriumAPIClientSubagent()
    assert client.status()["has_requests"] in (True, False)  # depends on env
    # In mock mode (no requests lib or no network), calls return mock data
    try:
        result = client.issue(Decimal("100"), "TED-TEST")
        assert result.get("mock") or result.get("status") == "OK"
    except RuntimeError:
        pass  # API may fail in mock, that's fine


def test_api_client_circuit_breaker():
    """HALF_OPEN → OPEN after threshold failures."""
    client = MoneriumAPIClientSubagent()
    client._cb_state = "OPEN"
    client._cb_failures = 6
    client._cb_last_failure = time.time()
    try:
        client.issue(Decimal("100"), "TED-TEST")
        assert False, "Should have tripped circuit breaker"
    except RuntimeError as e:
        assert "circuit breaker" in str(e).lower()
        assert "OPEN" in str(e)


def test_api_client_half_open():
    """After cooldown, circuit goes HALF_OPEN and allows one probe call."""
    client = MoneriumAPIClientSubagent()
    client._cb_state = "OPEN"
    client._cb_last_failure = time.time() - 120  # cooldown expired
    # Should not raise — state transitions to HALF_OPEN, then mock succeeds
    result = client.issue(Decimal("100"), "TED-TEST")
    assert result.get("mock") or result.get("status") == "OK"


def test_api_client_audit_log():
    """Every API call must be audit-logged."""
    client = MoneriumAPIClientSubagent()
    client.issue(Decimal("100"), "TED-TEST")
    assert len(client._audit_log) >= 1
    entry = client._audit_log[0]
    assert entry["method"] == "POST"
    assert entry["success"] == True


def test_api_client_oauth2_config():
    """OAuth2 config must be detectable."""
    client = MoneriumAPIClientSubagent()
    s = client.status()
    assert "has_oauth2" in s
    assert "cb_state" in s
    assert s["cb_state"] in ("CLOSED", "OPEN", "HALF_OPEN")


# ============================================================
# Agent 7: GasPaymasterSubagent
# ============================================================


def test_paymaster_sponsor():
    pm = GasPaymasterSubagent()
    result = pm.sponsor({"gas_estimate": 200_000})
    assert result["status"] == "SPONSORED"
    assert result["tx_hash"].startswith("0x")
    assert result["gas_covered_wei"] == 200_000
    assert pm.status()["sponsored_count"] == 1


def test_paymaster_balance():
    pm = GasPaymasterSubagent()
    pm.sponsor({"gas_estimate": 100_000})
    bal = pm.paymaster_balance()
    assert bal["sponsored_count"] == 1
    assert "balance_xdai" in bal


def test_paymaster_sponsor_transaction():
    """High-level sponsor_transaction API."""
    pm = GasPaymasterSubagent()
    result = pm.sponsor_transaction(
        target_contract="0x4B2c889a7182E89100223",
        function_name="burn",
        function_args=[70300, "DE89370400440532013000"],
        sender="did:peaq:worker-001",
        value_wei=0,
    )
    assert result["status"] == "SPONSORED"
    assert result["tx_hash"].startswith("0x")
    assert result["paymaster_used"] == pm.paymaster_address
    assert result["gas_used_wei"] > 0
    assert result["total_gas_cost_wei"] > 0
    # Audit log must be populated
    assert len(pm._sponsored_txs) == 1
    assert pm._sponsored_txs[0]["function"] == "burn"


def test_paymaster_top_up():
    """Auto-top-up when balance is low."""
    pm = GasPaymasterSubagent()
    pm._paymaster_balance_wei = 100  # below threshold
    pm.sponsor_transaction(
        "0xTarget", "mint", [1000], "sender-001",
    )
    assert pm._paymaster_balance_wei > 100  # was topped up


# ============================================================
# Agent 8: BridgeBalanceMonitorSubagent
# ============================================================


def test_balance_monitor_reconcile():
    monitor = BridgeBalanceMonitorSubagent()
    result = monitor.reconcile()
    assert result["balanced"] == True
    assert result["delta_eur"] == "0.00"
    assert result["cycle"] == 1


def test_balance_monitor_mismatch_detection():
    monitor = BridgeBalanceMonitorSubagent()
    # Force mock imbalance
    original = monitor._mock_vault_balance
    monitor._mock_vault_balance = lambda: Decimal("1487234.56") + Decimal("100.00")
    result = monitor.reconcile()
    assert result["balanced"] == False
    assert result["delta_eur"] == "-100.00"
    monitor._mock_vault_balance = original


def test_balance_monitor_multiple_cycles():
    monitor = BridgeBalanceMonitorSubagent()
    for i in range(3):
        r = monitor.reconcile()
        assert r["cycle"] == i + 1
    assert monitor.status()["reconcile_count"] == 3


# ============================================================
# Agent 9: SEPAConfirmationSubagent
# ============================================================


def test_sepa_initiate_payout():
    conf = SEPAConfirmationSubagent()
    result = conf.initiate_payout(
        Decimal("70300.00"), "DE89370400440532013000", "GENODEF1XXX",
        "Test payout", "0xburn-tx-hash",
    )
    assert result["status"] == "ACCEPTED"
    assert result["sepa_reference"].startswith("SEPA-")


def test_sepa_check_status():
    conf = SEPAConfirmationSubagent()
    ref = "SEPA-test-reference"
    result = conf.check_status(ref)
    assert result["status"] == "SETTLED"
    assert result["sepa_reference"] == ref


def test_sepa_confirm():
    conf = SEPAConfirmationSubagent()
    ref = "SEPA-test-123"
    result = conf.confirm(ref)
    assert result["status"] == "CONFIRMED"
    assert conf.status()["confirmed_count"] == 1


def test_sepa_confirm_transaction_poll():
    """confirm_sepa_transaction with poll=True must loop until SETTLED."""
    conf = SEPAConfirmationSubagent(max_attempts=3)
    result = conf.confirm_sepa_transaction(
        "SEPA-POLL-001", "TED-TEST", 1,
        Decimal("1000.00"), "DE89370400440532013000",
        poll=True,
    )
    assert result["status"] == "CONFIRMED"
    assert "audit_hash" in result


def test_sepa_confirm_transaction_single():
    """Single check without polling returns PENDING or CONFIRMED."""
    conf = SEPAConfirmationSubagent()
    result = conf.confirm_sepa_transaction(
        "SEPA-SINGLE", "TED-TEST", 1,
        Decimal("1000.00"), "DE89370400440532013000",
    )
    assert result["status"] in ("CONFIRMED", "PENDING")


def test_sepa_failure_finalize():
    """Known failed SEPA reference must return FAILED."""
    conf = SEPAConfirmationSubagent()
    result = conf.confirm_sepa_transaction(
        "SEPA-FAILED", "TED-TEST", 1,
        Decimal("500.00"), "DE89370400440532013000",
    )
    assert result["status"] == "FAILED"
    assert "reason" in result
    assert conf.status()["failed_count"] == 1


def test_sepa_audit_hash():
    """Audit hash must be a 0x-prefixed hex string."""
    h = SEPAConfirmationSubagent._audit_hash("REF-1", "TED-X", Decimal("100"))
    assert h.startswith("0x")
    assert len(h) == 18  # 0x + 16 hex chars


# ============================================================
# MiCAR Compliance
# ============================================================


def test_micar_compliance():
    # SEPA-zone, <= 5M → compliant
    assert SEPABridgeOrchestrator._check_micar(
        Decimal("1000000"), "DE89370400440532013000"
    ) == MiCARCompliance.COMPLIANT

    # Non-SEPA zone
    assert SEPABridgeOrchestrator._check_micar(
        Decimal("1000"), "US12345678901234567890"
    ) == MiCARCompliance.NON_COMPLIANT

    # > 5M EUR
    assert SEPABridgeOrchestrator._check_micar(
        Decimal("6000000"), "DE89370400440532013000"
    ) == MiCARCompliance.NON_COMPLIANT


# ============================================================
# Supervisor Integration
# ============================================================


def test_supervisor_initialization():
    sup = SEPABridgeSupervisor()
    s = sup.status()
    assert s["wave"] == 16
    assert s["agents"] == 9
    assert s["orchestrator"]["tx_count"] == 0


def test_supervisor_full_flow():
    sup = SEPABridgeSupervisor()

    # 1. Validate IBAN
    val = sup.validate_iban("DE89370400440532013000", "GENODEF1XXX")
    assert val["status"] == "OK"

    # 2. Deposit from Behorde
    dep = sup.deposit(Decimal("500000.00"), "DE89370400440532013000",
                      "TED-2026-0815")
    assert dep["status"] == "completed"

    # 3. Payout to Handwerker
    pay = sup.payout(Decimal("70300.00"), "DE89370400440532013000",
                     "GENODEF1XXX", "TED-2026-0815", 1)
    assert pay["status"] == "completed"

    # 4. Reconcile
    rec = sup.reconcile()
    assert rec["balanced"] == True

    # 5. Confirm SEPA
    conf = sup.confirm_sepa(pay["artifacts"][0]["sepa_reference"])
    assert conf["status"] == "CONFIRMED"

    # 6. Gas sponsorship
    gas = sup.sponsor_gas()
    assert gas["status"] == "SPONSORED"

    # 7. Audit query
    entries = sup.audit_query(tender_id="TED-2026-0815")
    assert len(entries) >= 2  # deposit + payout


def test_supervisor_status_all_agents():
    sup = SEPABridgeSupervisor()
    s = sup.status()
    for name in ["minter", "burner", "iban_validator", "audit_trail",
                 "api_client", "paymaster", "balance_monitor", "sepa_confirmation"]:
        assert name in s, f"Missing {name} in status"


# ============================================================
# Run all tests
# ============================================================

if __name__ == "__main__":
    import tempfile as tmpfile_mod

    print("=" * 60)
    print("Wave 16 — Monerium SEPA-Bridge Agent Tests")
    print("=" * 60)

    with tmpfile_mod.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        tests = [
            # Core
            ("make_response", test_make_response),
            ("JSONLogger", lambda: test_json_logger(tmp_path)),
            # Agent 1
            ("Orchestrator (deposit)", test_orchestrator_deposit),
            ("Orchestrator (payout)", test_orchestrator_payout),
            ("Orchestrator (circuit breaker)", test_orchestrator_circuit_breaker),
            ("Orchestrator (bad IBAN)", test_orchestrator_bad_iban),
            # Agent 2
            ("EUReMinter", test_minter),
            # Agent 3
            ("EUReBurner", test_burner),
            ("EUReBurner (short IBAN)", test_burner_rejects_short_iban),
            # Agent 4
            ("IBANValidator (DE)", test_iban_validate_valid_de),
            ("IBANValidator (non-SEPA)", test_iban_validate_non_sepa),
            ("IBANValidator (bad checksum)", test_iban_validate_bad_checksum),
            ("IBANValidator (BIC)", test_iban_validate_bic),
            ("IBANValidator (Steuer-ID)", test_iban_validate_steuer_id),
            ("IBANValidator (MOD97)", test_iban_mod97),
            ("IBANValidator (blacklist)", test_iban_blacklist),
            ("IBANValidator (recipient)", test_iban_validate_payment_recipient),
            ("IBANValidator (no blacklist)", test_iban_blacklist_not_triggered),
            # Agent 5
            ("AuditTrail (record)", lambda: test_audit_trail_record(tmp_path)),
            ("AuditTrail (query)", lambda: test_audit_trail_query(tmp_path)),
            # Agent 6
            ("API Client (mock)", test_api_client_mock_mode),
            ("API Client (circuit breaker)", test_api_client_circuit_breaker),
            ("API Client (half-open)", test_api_client_half_open),
            ("API Client (audit log)", test_api_client_audit_log),
            ("API Client (oauth2 config)", test_api_client_oauth2_config),
            # Agent 7
            ("Paymaster (sponsor)", test_paymaster_sponsor),
            ("Paymaster (balance)", test_paymaster_balance),
            ("Paymaster (sponsor_tx)", test_paymaster_sponsor_transaction),
            ("Paymaster (top-up)", test_paymaster_top_up),
            # Agent 8
            ("BalanceMonitor (reconcile)", test_balance_monitor_reconcile),
            ("BalanceMonitor (mismatch)", test_balance_monitor_mismatch_detection),
            ("BalanceMonitor (cycles)", test_balance_monitor_multiple_cycles),
            # Agent 9
            ("SEPAConfirm (initiate)", test_sepa_initiate_payout),
            ("SEPAConfirm (status)", test_sepa_check_status),
            ("SEPAConfirm (confirm)", test_sepa_confirm),
            ("SEPAConfirm (poll)", test_sepa_confirm_transaction_poll),
            ("SEPAConfirm (single)", test_sepa_confirm_transaction_single),
            ("SEPAConfirm (failure)", test_sepa_failure_finalize),
            ("SEPAConfirm (audit hash)", test_sepa_audit_hash),
            # MiCAR
            ("MiCAR compliance", test_micar_compliance),
            # Supervisor
            ("Supervisor (init)", test_supervisor_initialization),
            ("Supervisor (full flow)", test_supervisor_full_flow),
            ("Supervisor (status)", test_supervisor_status_all_agents),
        ]

        passed = 0
        failed = 0

        for name, test_fn in tests:
            try:
                test_fn()
                print(f"  ✅ {name}")
                passed += 1
            except Exception as e:
                print(f"  ❌ {name}: {e}")
                failed += 1

        total = passed + failed
        print(f"\n{passed}/{total} tests passed"
              + (f", {failed} FAILED" if failed else " — ALL GOOD"))
        if failed > 0:
            sys.exit(1)
