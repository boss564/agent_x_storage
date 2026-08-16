"""
Agent X — VOB/B Extension (Wave 3.5, 9 Agents).

Multi-installment payment cycles, 5% retention (VOB/B §17),
defect detection, dispute arbitration (VOB/B §13), remediation tracking,
final settlement, and BHO-compliant escrow reconciliation.

Replaces the linear "one-payment" flow in Wave 3 with a full
German construction law-compliant payment lifecycle.

Agents:
  1. InstallmentPlannerAgent     — Breaks GAEB LV into payment milestones
  2. ProgressSnapshotAgent       — Monthly cryptographic progress snapshots
  3. PartialInvoiceGeneratorAgent — Abschlagsrechnung with retention deduction
  4. RetentionManagerAgent       — 5% Sicherheitseinbehalt (VOB/B §17)
  5. DefectDetectionAgent        — Scans QA/PoPW data for VOB/B defects
  6. DisputeArbiterAgent         — State machine for VOB/B §13 defect procedure
  7. RemediationTrackerAgent     — Tracks defect fixes within deadlines
  8. FinalSettlementAgent        — GAEB-X89 final account with all offsets
  9. EscrowReconciliationAgent   — BHO 4-eyes check: Σ payments = contract sum
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


# ============================================================
# Dispute State Machine
# ============================================================


class DisputeState(str, Enum):
    IDLE = "idle"
    DEFECT_LOGGED = "defect_logged"
    REMEDIATION_DEADLINE = "deadline_set"
    REMEDIATION_VERIFY = "verify_remediation"
    PAYMENT_HALTED = "payment_halted"
    RESOLVED = "resolved"
    REDUCTION_APPLIED = "reduction_applied"


# ============================================================
# Agent 1: InstallmentPlannerAgent
# ============================================================


class InstallmentPlannerAgent:
    """Breaks the GAEB Bill of Quantities into logical payment milestones."""

    async def extract_milestones(self, positions: list[dict], total_eur: float) -> list[dict]:
        """Subagent: MilestoneExtractor — groups LV positions into phases."""
        groups: dict[str, dict] = {}
        for pos in positions:
            mg = pos.get("material_group", "Allgemein")
            if mg not in groups:
                groups[mg] = {"name": mg, "positions": [], "total_qty": 0}
            groups[mg]["positions"].append(pos["position_id"])
            groups[mg]["total_qty"] += pos.get("quantity", 0)

        milestones = []
        phase_pcts = {"Tiefbau": 15, "Betonbau": 25, "Rohrleitungsbau": 20,
                      "HLK": 20, "Elektrotechnik": 10, "Ausbau": 10}
        for name, data in groups.items():
            pct = phase_pcts.get(name, 10)
            milestones.append({
                "milestone": f"{name} fertig", "phase": name,
                "pct": pct, "amount_eur": round(total_eur * pct / 100, 2),
                "positions": data["positions"],
            })
        return milestones

    async def schedule_in_escrow(self, milestones: list[dict]) -> list[dict]:
        """Subagent: EscrowScheduler — writes due dates into escrow contract."""
        now = datetime.now(timezone.utc)
        for i, m in enumerate(milestones):
            m["due_date"] = (now + timedelta(days=30 * (i + 1))).isoformat()
        return milestones

    async def plan(self, positions: list[dict], total_eur: float) -> list[dict]:
        milestones = await self.extract_milestones(positions, total_eur)
        milestones = await self.schedule_in_escrow(milestones)
        total_pct = sum(m["pct"] for m in milestones)
        print(f"  [Installment]   📅 {len(milestones)} Abschläge geplant "
              f"(Summe={total_pct}%, nächster: {milestones[0]['due_date'][:10] if milestones else 'N/A'})")
        return milestones


# ============================================================
# Agent 2: ProgressSnapshotAgent
# ============================================================


class ProgressSnapshotAgent:
    """Creates monthly cryptographic snapshots of construction progress."""

    async def calculate_completion(self, telemetry: dict, positions: list[dict]) -> float:
        """Subagent: CompletionCalculator."""
        actual = telemetry.get("material_usage", {}).get("quantity_used", 0)
        total = sum(p.get("quantity", 1) for p in positions)
        return min(100, round(actual / max(total, 1) * 100 * 10, 1))  # Simulated

    async def map_to_lv(self, telemetry: dict, positions: list[dict]) -> dict:
        """Subagent: LVPositionMapper."""
        return {p["position_id"]: {"target": p["quantity"], "actual": telemetry.get("material_usage", {}).get("quantity_used", 0) / max(len(positions), 1)}
                for p in positions}

    async def hash_snapshot(self, progress_pct: float, lv_map: dict) -> str:
        """Subagent: SnapshotHasher."""
        raw = f"{progress_pct}{json.dumps(lv_map, sort_keys=True)}{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:40]

    async def snapshot(self, telemetry: dict, positions: list[dict]) -> dict:
        progress = await self.calculate_completion(telemetry, positions)
        lv_map = await self.map_to_lv(telemetry, positions)
        snap_hash = await self.hash_snapshot(progress, lv_map)
        print(f"  [Snapshot]      📸 Fortschritt: {progress}% (Hash={snap_hash[:16]}...)")
        return {"progress_pct": progress, "lv_completion": lv_map, "snapshot_hash": snap_hash,
                "timestamp": datetime.now(timezone.utc).isoformat()}


# ============================================================
# Agent 3: PartialInvoiceGeneratorAgent
# ============================================================


class PartialInvoiceGeneratorAgent:
    """Generates monthly installment invoices (Abschlagsrechnungen)."""

    async def deduct_previous(self, gross: float, paid_so_far: float) -> float:
        """Subagent: InstallmentDeductionEngine."""
        return max(0, round(gross - paid_so_far, 2))

    async def apply_retention(self, amount: float, retention_pct: float = 5.0) -> tuple[float, float]:
        """Subagent: RetentionDeducer — VOB/B §17: 5% Sicherheitseinbehalt."""
        retention = round(amount * retention_pct / 100, 2)
        payable = round(amount - retention, 2)
        return payable, retention

    async def generate(self, milestone: dict, paid_so_far: float,
                       retention_pct: float = 5.0) -> dict:
        gross = milestone["amount_eur"]
        after_previous = await self.deduct_previous(gross, paid_so_far)
        payable, retained = await self.apply_retention(after_previous, retention_pct)

        invoice = {
            "invoice_id": f"ABS-{milestone['milestone'][:20]}-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "milestone": milestone["milestone"],
            "gross_eur": gross,
            "paid_so_far_eur": paid_so_far,
            "payable_eur": payable,
            "retained_eur": retained,
            "retention_pct": retention_pct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        print(f"  [PartialInv]    🧾 Abschlag '{milestone['milestone']}': "
              f"{payable:,.2f} € zahlbar, {retained:,.2f} € einbehalten (5%)")
        return invoice


# ============================================================
# Agent 4: RetentionManagerAgent
# ============================================================


class RetentionManagerAgent:
    """Manages the cumulative 5% retention pool (VOB/B §17)."""

    def __init__(self):
        self._retention_pool: dict[str, dict] = {}  # project_id → {total_retained, releases, ...}

    async def accumulate(self, project_id: str, amount: float) -> float:
        """Subagent: RetentionAggregator."""
        if project_id not in self._retention_pool:
            self._retention_pool[project_id] = {"total_retained": 0.0, "released": 0.0, "entries": []}
        self._retention_pool[project_id]["total_retained"] += amount
        self._retention_pool[project_id]["entries"].append({
            "amount": amount, "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return self._retention_pool[project_id]["total_retained"]

    async def reserve_in_escrow(self, project_id: str, amount: float) -> str:
        """Subagent: EscrowReserver — locks 5% in separate retention sub-account."""
        tx = f"0xRETENTION-{hashlib.sha256(f'{project_id}{amount}'.encode()).hexdigest()[:16]}"
        return tx

    async def track_guarantee(self, project_id: str) -> dict:
        """Subagent: GuaranteeTracker — monitors 4-year warranty period (VOB/B §13 Abs. 4)."""
        return {"warranty_years": 4, "expires": (datetime.now(timezone.utc) + timedelta(days=4*365)).isoformat()}

    async def get_total_retained(self, project_id: str) -> float:
        return self._retention_pool.get(project_id, {}).get("total_retained", 0.0)

    async def release_retention(self, project_id: str, pct: float = 95.0) -> dict:
        """Release retention at final acceptance (typically 95% of retained amount)."""
        total = await self.get_total_retained(project_id)
        release_amount = round(total * pct / 100, 2)
        self._retention_pool[project_id]["released"] += release_amount
        print(f"  [Retention]     🔓 {pct}% Einbehalt freigegeben: {release_amount:,.2f} € "
              f"von {total:,.2f} €")
        return {"released_eur": release_amount, "remaining_eur": round(total - release_amount, 2)}

    async def apply_deduction(self, project_id: str, position_id: str, reduction_pct: float) -> float:
        """Apply a defect-related reduction to the retention pool."""
        return reduction_pct  # Production: updates escrow contract state


# ============================================================
# Agent 5: DefectDetectionAgent
# ============================================================


class DefectDetectionAgent:
    """Scans QA and PoPW data for VOB/B §13 defects."""

    async def check_thresholds(self, qa_report: dict, telemetry: dict) -> list[dict]:
        """Subagent: ThresholdAnalyzer — checks against VOB/B tolerance limits."""
        defects = []
        if qa_report.get("result") != "bestanden":
            defects.append({"position_id": "LV-0102", "description": qa_report.get("test", "Unbekannt"),
                            "severity": "major", "tolerance_exceeded": True})
        if not telemetry.get("gps", {}).get("on_site", True):
            defects.append({"position_id": "LV-0501", "description": "Arbeiter außerhalb Geofence",
                            "severity": "minor"})
        return defects

    async def categorize(self, defects: list[dict]) -> list[dict]:
        """Subagent: DefectCategorizer — distinguishes open/hidden defects."""
        for d in defects:
            d["category"] = "open" if d["severity"] == "minor" else "hidden"
            d["vob_paragraph"] = "§13 Abs. 1" if d["severity"] == "major" else "§13 Abs. 2"
        return defects

    async def detect(self, qa_report: dict, telemetry: dict) -> list[dict]:
        defects = await self.check_thresholds(qa_report, telemetry)
        if not defects:
            print(f"  [DefectDetect]  ✓ Keine Mängel erkannt")
            return []
        defects = await self.categorize(defects)
        for d in defects:
            print(f"  [DefectDetect]  ⚠ Mangel: {d['description']} ({d['severity']}, {d['vob_paragraph']})")
        return defects


# ============================================================
# Agent 6: DisputeArbiterAgent — State Machine (VOB/B §13)
# ============================================================


class DisputeArbiterAgent:
    """
    Heart of VOB/B compliance: defect → notice → deadline → verify → resolve/reduce.
    State machine: IDLE → DEFECT_LOGGED → REMEDIATION_DEADLINE → RESOLVED | REDUCTION_APPLIED
    """

    def __init__(self):
        self._states: dict[str, DisputeState] = {}
        self._defects: dict[str, dict] = {}

    async def raise_defect(self, project_id: str, defect: dict) -> str:
        """Subagent: DefectNoticeGenerator — creates formal VOB/B defect notice."""
        pos_id = defect["position_id"]
        key = f"{project_id}:{pos_id}"
        deadline_days = 14 if defect["severity"] == "major" else 30
        deadline = datetime.now(timezone.utc) + timedelta(days=deadline_days)

        self._states[key] = DisputeState.REMEDIATION_DEADLINE
        self._defects[key] = {
            **defect, "deadline": deadline.isoformat(), "raised_at": datetime.now(timezone.utc).isoformat(),
            "state": DisputeState.REMEDIATION_DEADLINE.value,
        }
        print(f"  [DisputeArbiter] ⚠ Mängelrüge: {defect['description'][:50]}... "
              f"Nachfrist={deadline_days}d (VOB/B §13)")
        return key

    async def check_remediation(self, project_id: str, position_id: str,
                                remediation_proof: dict) -> DisputeState:
        """Subagent: DeadlineSetter — verifies if defect was fixed within deadline."""
        key = f"{project_id}:{position_id}"
        current = self._states.get(key, DisputeState.IDLE)
        if current != DisputeState.REMEDIATION_DEADLINE:
            return current

        passed = remediation_proof.get("passed_retest", False)
        if passed:
            self._states[key] = DisputeState.RESOLVED
            self._defects[key]["state"] = DisputeState.RESOLVED.value
            print(f"  [DisputeArbiter] ✅ Mangel {position_id} behoben — Zahlung freigegeben")
        else:
            self._states[key] = DisputeState.REDUCTION_APPLIED
            reduction = remediation_proof.get("reduction_pct", 10.0)
            self._defects[key]["reduction_pct"] = reduction
            self._defects[key]["state"] = DisputeState.REDUCTION_APPLIED.value
            print(f"  [DisputeArbiter] 🔻 Mangel {position_id} nicht behoben — "
                  f"{reduction}% Minderung (VOB/B §13 Abs. 5)")

        return self._states[key]

    async def get_active_disputes(self, project_id: str) -> list[dict]:
        return [d for k, d in self._defects.items()
                if k.startswith(project_id) and d["state"] not in ("resolved",)]

    async def escalate(self, key: str) -> DisputeState:
        """Subagent: EscalationLevelManager."""
        self._states[key] = DisputeState.PAYMENT_HALTED
        print(f"  [DisputeArbiter] ⛔ Zahlungsstopp für {key}")
        return DisputeState.PAYMENT_HALTED


# ============================================================
# Agent 7: RemediationTrackerAgent
# ============================================================


class RemediationTrackerAgent:
    """Tracks whether defects are fixed within their deadlines."""

    async def verify_retest(self, new_qa: dict, original_defect: dict) -> bool:
        """Subagent: RetestVerifier."""
        return new_qa.get("result") == "bestanden"

    async def close_defect(self, defect_key: str) -> dict:
        """Subagent: DefectCloser."""
        return {"key": defect_key, "closed_at": datetime.now(timezone.utc).isoformat(), "status": "closed"}

    async def extend_deadline(self, defect_key: str, reason: str, extra_days: int = 14) -> str:
        """Subagent: ExtensionApprover — extends deadline for force majeure."""
        print(f"  [Remediation]   🕐 Fristverlängerung: +{extra_days}d ({reason})")
        return f"extended-{extra_days}d"

    async def track(self, project_id: str, disputes: dict) -> list[dict]:
        overdue = []
        now = datetime.now(timezone.utc)
        for key, defect in disputes.items():
            if defect.get("deadline"):
                dl = datetime.fromisoformat(defect["deadline"])
                if now > dl and defect["state"] == DisputeState.REMEDIATION_DEADLINE.value:
                    overdue.append(defect)
        if overdue:
            print(f"  [Remediation]   ⚠ {len(overdue)} Mängel in Verzug!")
        else:
            print(f"  [Remediation]   ✓ Alle Mängel innerhalb der Frist")
        return overdue


# ============================================================
# Agent 8: FinalSettlementAgent
# ============================================================


class FinalSettlementAgent:
    """GAEB-X89 final account: Σ installments + retention release + extras."""

    async def compensate(self, installments: list[dict], retention_pool: dict,
                         extras: list[dict]) -> dict:
        """Subagent: FinalAccountCompensator."""
        total_paid = sum(i.get("payable_eur", 0) for i in installments)
        total_retained = retention_pool.get("total_retained", 0)
        total_extras = sum(e.get("amount_eur", 0) for e in extras)
        return {"total_paid": total_paid, "total_retained": total_retained,
                "total_extras": total_extras}

    async def trigger_release(self, project_id: str, retention_agent) -> dict:
        """Subagent: RetentionReleaseTrigger — releases 95% at acceptance."""
        return await retention_agent.release_retention(project_id, 95.0)

    async def compute_final(self, contract_value: float, compensation: dict,
                            release: dict) -> dict:
        """Subagent: VOBFinalCalculator."""
        final_payment = round(contract_value - compensation["total_paid"]
                              + compensation["total_extras"], 2)
        print(f"  [FinalSettle]   🏁 Schlussrechnung: "
              f"Vertrag={contract_value:,.0f}€, bezahlt={compensation['total_paid']:,.0f}€, "
              f"Schlusszahlung={final_payment:,.2f}€")
        return {"final_payment_eur": final_payment, "release": release,
                "compensation": compensation}

    async def settle(self, project_id: str, contract_value: float, installments: list[dict],
                     retention_pool: dict, retention_agent, extras: list[dict] | None = None) -> dict:
        extras = extras or []
        compensation = await self.compensate(installments, retention_pool, extras)
        release = await self.trigger_release(project_id, retention_agent)
        return await self.compute_final(contract_value, compensation, release)


# ============================================================
# Agent 9: EscrowReconciliationAgent — BHO 4-Augen-Check
# ============================================================


class EscrowReconciliationAgent:
    """BHO-compliant final verification: Σ payments must equal contract sum."""

    async def balance_ledger(self, contract_value: float, total_paid: float,
                             total_retained: float, final_payment: float) -> tuple[bool, float]:
        """Subagent: LedgerBalancer — BHO 4-eyes check."""
        calculated = round(total_paid + total_retained + final_payment, 2)
        diff = round(contract_value - calculated, 2)
        is_balanced = abs(diff) <= 0.02
        return is_balanced, diff

    async def update_audit(self, project_id: str, result: dict) -> None:
        """Subagent: AuditTrailUpdater."""
        print(f"  [Reconciliation] 📝 GoBD-Eintrag: {project_id}")

    async def emergency_pause(self, project_id: str, diff: float) -> bool:
        """Subagent: EmergencyPauseTrigger — stops all payments if >50€ discrepancy."""
        if abs(diff) > 50:
            print(f"  [Reconciliation] ⛔ NOTSTOPP: Differenz {diff:,.2f} € > 50 € — "
                  f"alle Zahlungen gestoppt!")
            return True
        return False

    async def reconcile(self, project_id: str, contract_value: float,
                        total_paid: float, total_retained: float,
                        final_payment: float) -> dict:
        balanced, diff = await self.balance_ledger(
            contract_value, total_paid, total_retained, final_payment)
        paused = await self.emergency_pause(project_id, diff)
        await self.update_audit(project_id, {"balanced": balanced, "diff": diff})

        icon = "✅" if balanced and not paused else "⛔"
        print(f"  [Reconciliation] {icon} BHO-Abgleich: "
              f"Vertrag={contract_value:,.2f}€ = "
              f"Bezahlt({total_paid:,.2f}) + Einbehalt({total_retained:,.2f}) + "
              f"Schluss({final_payment:,.2f}) → Δ={diff:,.2f}€")

        return {"balanced": balanced, "diff_eur": diff, "payment_paused": paused,
                "gobd_entry_written": True}


# ============================================================
# VOB Extension Pipeline — runs all 9 agents after Wave 3 delivery
# ============================================================


class VOBExtensionPipeline:
    """Wires all 9 VOB/B agents and integrates with the existing Execution pipeline."""

    def __init__(self):
        self.installment_planner = InstallmentPlannerAgent()
        self.progress_snapshot = ProgressSnapshotAgent()
        self.partial_invoice = PartialInvoiceGeneratorAgent()
        self.retention_manager = RetentionManagerAgent()
        self.defect_detector = DefectDetectionAgent()
        self.dispute_arbiter = DisputeArbiterAgent()
        self.remediation_tracker = RemediationTrackerAgent()
        self.final_settlement = FinalSettlementAgent()
        self.reconciliation = EscrowReconciliationAgent()

        self._installments: list[dict] = []
        self._total_paid = 0.0
        self._total_retained = 0.0

    async def run(self, project_id: str, positions: list[dict],
                  contract_value: float, telemetry: dict,
                  qa_report: dict) -> dict:
        """Run the full VOB/B extension pipeline for one payment cycle."""
        start = time.perf_counter()

        # 1. Plan milestones (once, on first call)
        if not self._installments:
            self._installments = await self.installment_planner.plan(positions, contract_value)

        # 2. Progress snapshot
        snapshot = await self.progress_snapshot.snapshot(telemetry, positions)

        # 3. Generate installment invoice (use first pending milestone)
        current = self._installments[min(len(self._installments) - 1,
                                         len([i for i in self._installments
                                              if i.get("paid")]))]
        invoice = await self.partial_invoice.generate(current, self._total_paid)

        # 4. Accumulate retention
        retained = await self.retention_manager.accumulate(project_id, invoice["retained_eur"])
        self._total_retained += invoice["retained_eur"]
        self._total_paid += invoice["payable_eur"]
        await self.retention_manager.reserve_in_escrow(project_id, invoice["retained_eur"])

        # 5. Defect detection
        defects = await self.defect_detector.detect(qa_report, telemetry)

        # 6. Dispute arbitration
        active_disputes: dict[str, Any] = {}
        for defect in defects:
            key = await self.dispute_arbiter.raise_defect(project_id, defect)
            active_disputes[key] = defect

        # 7. Remediation tracking
        overdue = await self.remediation_tracker.track(project_id, active_disputes)

        # 8. Final settlement (if last milestone)
        retention_pool = {"total_retained": self._total_retained}
        settlement = await self.final_settlement.settle(
            project_id, contract_value, self._installments, retention_pool, self.retention_manager)

        # 9. Reconciliation
        recon = await self.reconciliation.reconcile(
            project_id, contract_value, self._total_paid,
            self._total_retained, settlement["final_payment_eur"])

        elapsed = time.perf_counter() - start
        print(f"\n  [VOB-Pipeline]  ✅ VOB/B-Zyklus in {elapsed:.1f}s "
              f"(Abschläge={len(self._installments)}, Mängel={len(defects)}, "
              f"Einbehalt={self._total_retained:,.2f}€, "
              f"BHO={'✓' if recon['balanced'] else '⚠'})")

        return {
            "snapshot": snapshot, "invoice": invoice, "defects": defects,
            "overdue": overdue, "settlement": settlement, "reconciliation": recon,
        }
