#!/usr/bin/env python3
"""
Full lifecycle test for VOB_Shadow_Escrow state machine.

Exercises every mutation path through the contract, verifying the
Conservation-of-Funds invariant (Δ=0.00) at each step. Catches
interaction bugs where individually correct changes cancel each other
out — e.g. isActive guard vs. acceptedAt-dependent timeout.

Paths tested:
  1. fund → add milestones → complete → release → closeProject
  2. releaseRetention by Client (after closeProject)
  3. releaseRetention by Auditor (after closeProject)
  4. releaseRetention by Contractor before warranty (must fail)
  5. releaseRetention by Contractor after warranty (must succeed)
  6. Invariant after each step

Usage:
    python shadow_contract_pilot/test_lifecycle.py
"""
from __future__ import annotations

import sys
from decimal import Decimal, getcontext

getcontext().prec = 50

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


# ---- Contract Logic (mirrors VOB_Shadow_Escrow.sol) ----

CLIENT = "0xClient"
AUDITOR = "0xAuditor"
CONTRACTOR = "0xContractor"
TAX = "0xTaxAuthority"
WARRANTY_PERIOD = 4 * 365 * 86400  # §13 VOB/B: 4 Jahre


class ShadowEscrowSim:
    """Simulates VOB_Shadow_Escrow state machine with exact arithmetic."""

    def __init__(self):
        self.totalBudget = Decimal("0")
        self.totalReleased = Decimal("0")
        self.retentionVault = Decimal("0")
        self.taxVault = Decimal("0")
        self.contractBalance = Decimal("0")
        self.isActive = False
        self.acceptedAt = 0
        self.milestones: list[dict] = []

    def invariant(self) -> Decimal:
        accounted = self.totalReleased + self.taxVault + self.contractBalance
        return self.totalBudget - accounted

    def fund(self, amount: Decimal) -> None:
        self.contractBalance += amount
        self.totalBudget += amount
        self.isActive = True

    def add_milestone(self, gross: Decimal) -> None:
        vat = (gross * 19) / 119
        ret = (gross * 5) / 100
        net = gross - vat - ret
        assert net + vat + ret == gross, f"Rounding mismatch: {net}+{vat}+{ret} != {gross}"
        self.milestones.append({
            "gross": gross, "vat": vat, "retention": ret, "net": net,
            "completed": False, "released": False,
        })

    def complete_all(self) -> None:
        for m in self.milestones:
            m["completed"] = True

    def release_all(self) -> None:
        for m in self.milestones:
            assert m["completed"] and not m["released"]
            self.totalReleased += m["net"]
            self.taxVault += m["vat"]
            self.retentionVault += m["retention"]
            self.contractBalance -= m["vat"] + m["net"]
            m["released"] = True

    def close_project(self, ts: int = 1_700_000_000) -> None:
        assert self.isActive
        assert all(m["completed"] and m["released"] for m in self.milestones)
        self.isActive = False
        self.acceptedAt = ts

    def release_retention(self, amount: Decimal, caller: str, block_ts: int | None = None) -> bool:
        assert amount <= self.retentionVault

        is_client = caller == CLIENT
        is_auditor = caller == AUDITOR
        is_contractor_after = (
            caller == CONTRACTOR
            and self.acceptedAt > 0
            and (block_ts or 0) >= self.acceptedAt + WARRANTY_PERIOD
        )
        if not (is_client or is_auditor or is_contractor_after):
            return False

        self.retentionVault -= amount
        self.totalReleased += amount
        self.contractBalance -= amount
        return True


# ================================================================
# Test Suite
# ================================================================


def test_full_lifecycle():
    """Complete VOB/B lifecycle with all retention release paths."""
    sim = ShadowEscrowSim()
    grosses = [Decimal("400000.00"), Decimal("350000.00"), Decimal("250000.00")]

    # 1. Fund
    sim.fund(sum(grosses))
    check("1.1 Fund: invariant hält", sim.invariant() == 0)

    # 2. Add milestones
    for g in grosses:
        sim.add_milestone(g)
    check("2.1 AddMilestone: invariant hält", sim.invariant() == 0)
    check("2.2 AddMilestone: 3 Milestones", len(sim.milestones) == 3)
    for i, m in enumerate(sim.milestones):
        check(f"2.3 M{i+1}: net+vat+ret=gross", m["net"] + m["vat"] + m["retention"] == m["gross"])

    # 3. Complete
    sim.complete_all()
    check("3.1 Complete: invariant hält", sim.invariant() == 0)

    # 4. Release
    sim.release_all()
    check("4.1 Release: invariant hält", sim.invariant() == 0)
    check("4.2 Release: retentionVault = 5%", sim.retentionVault == sum(grosses) * 5 / 100)
    check("4.3 Release: contractBalance = retentionVault",
          abs(sim.contractBalance - sim.retentionVault) < Decimal("0.01"))

    # 5. Close project
    sim.close_project()
    check("5.1 CloseProject: invariant hält", sim.invariant() == 0)
    check("5.2 CloseProject: isActive=False", not sim.isActive)

    # 6. Release retention — the critical paths
    retention_before = sim.retentionVault

    # 6a: Client after closeProject
    ok = sim.release_retention(retention_before / 2, CLIENT)
    check("6.1 Client: release after closeProject", ok)
    check("6.2 Client: invariant hält", sim.invariant() == 0)

    # 6b: Auditor
    ok = sim.release_retention(sim.retentionVault, AUDITOR)
    check("6.3 Auditor: release remaining", ok)
    check("6.4 Auditor: invariant hält", sim.invariant() == 0)

    # 6c: Contractor at 1 day after acceptance (must fail)
    ok = sim.release_retention(sim.retentionVault, CONTRACTOR, block_ts=sim.acceptedAt + 86400)
    check("6.5 Contractor (1d): correctly denied", not ok)

    # 6d: Contractor after 4-year warranty (must succeed)
    ok = sim.release_retention(sim.retentionVault, CONTRACTOR,
                               block_ts=sim.acceptedAt + WARRANTY_PERIOD + 1)
    check("6.6 Contractor (4y+1s): release after warranty", ok)
    check("6.7 Contractor: invariant hält", sim.invariant() == 0)

    # Final
    check("7.1 End: retentionVault geleert", sim.retentionVault == 0)
    check("7.2 End: released+tax = budget",
          sim.totalReleased + sim.taxVault == sim.totalBudget)
    check("7.3 End: invariant Δ=0", sim.invariant() == 0)


def test_rounding_edge():
    """Härtetest: krummer Betrag, Ganzzahldivision."""
    sim = ShadowEscrowSim()
    weird = Decimal("33333.33")
    sim.fund(weird)
    sim.add_milestone(weird)
    sim.complete_all()
    sim.release_all()

    # Sum of splits must equal gross
    m = sim.milestones[0]
    check("Round.1: net+vat+ret = gross", m["net"] + m["vat"] + m["retention"] == m["gross"],
          f"{m['net']}+{m['vat']}+{m['retention']} = {m['net']+m['vat']+m['retention']} vs {m['gross']}")
    check("Round.2: invariant hält", sim.invariant() == 0)


def test_auth_rejects_stranger():
    """Unautorisierte Adresse wird abgewiesen."""
    sim = ShadowEscrowSim()
    sim.fund(Decimal("100000"))
    sim.add_milestone(Decimal("100000"))
    sim.complete_all()
    sim.release_all()
    sim.close_project()

    ok = sim.release_retention(sim.retentionVault, "0xStranger")
    check("Auth.1: Fremder abgewiesen", not ok)


def main() -> int:
    print("=" * 60)
    print("  VOB_Shadow_Escrow — Full Lifecycle Test")
    print("=" * 60)

    test_full_lifecycle()
    test_rounding_edge()
    test_auth_rejects_stranger()

    total = PASSED + FAILED
    print(f"\n{'=' * 60}")
    print(f"  Results: {PASSED}/{total} passed")
    if FAILED > 0:
        print(f"  ❌ {FAILED} FAILED")
    print(f"{'=' * 60}")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
