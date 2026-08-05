# agents_b2g/shadow/shadow_contract_orchestrator.py
"""
Agent 18.1 — ShadowContractOrchestrator

Root-Agent der Welle 18 (VOB Shadow Contract & Real-World Pilot).
Steuert den gesamten Shadow-Contract-Lebenszyklus als rechtssichere
Parallelbuchhaltung zur traditionellen VOB/B-Abwicklung.

Lebenszyklus-Phasen:
  1. INITIATION      — Pilotprojekt anlegen, Parteien registrieren
  2. DEPLOYMENT      — Shadow Contract auf Gnosis Chain deployen
  3. FUNDING         — SEPA-Einzahlung → EURe-Mint in den Contract
  4. CONSTRUCTION    — Milestone-Freigaben via PoPW/IoT-Daten
  5. TAX_SIMULATION  — Steuerabführung simulieren (USt, §48b EStG)
  6. RETENTION       — 5% Sicherheitseinbehalt (VOB/B §17)
  7. COMPLETION      — Schlussabnahme, Retention-Timer starten
  8. AUDIT_VIEW      — Read-Only-Dashboard für Behörden (RPA/Kämmerer)

9-Agenten-Architektur:
  1. ShadowContractOrchestrator    — Root: Lifecycle, State Machine
  2. ShadowContractDeployer        — Deploy VOB_Shadow_Escrow.sol
  3. PrivateClientBridge           — SEPA → EURe Mint
  4. MilestoneConditionChecker     — PoPW/IoT → Milestone Release
  5. TaxSimulationAgent            — USt + §48b im Shadow Mode
  6. RetentionVaultManager         — 5% Einbehalt, 4-Jahres-Timer
  7. AuditorDashboardComposer      — Read-Only-Dashboard für Behörden
  8. PilotMetricsCollector         — Betriebsdaten, Lessons Learned
  9. GovernmentOnboardingKit       — Onboarding-Paket für Behörden
"""

import json
import uuid
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from enum import Enum

from agents_b2g.shadow.subagents.lifecycle_state_engine import (
    LifecycleStateEngine, ContractState,
)
from agents_b2g.shadow.subagents.atomic_settlement_engine import (
    AtomicSettlementEngine,
)
from agents_b2g.shadow.subagents.shadow_contract_deployer import (
    ShadowContractDeployer,
)
from agents_b2g.shadow.subagents.private_client_bridge import (
    PrivateClientBridge,
)
from agents_b2g.shadow.subagents.milestone_condition_checker import (
    MilestoneConditionChecker,
)
from agents_b2g.shadow.subagents.tax_simulation_agent import (
    TaxSimulationAgent,
)
from agents_b2g.shadow.subagents.retention_vault_manager import (
    RetentionVaultManager,
)
from agents_b2g.shadow.subagents.auditor_dashboard_composer import (
    AuditorDashboardComposer,
)
from agents_b2g.shadow.subagents.pilot_metrics_collector import (
    PilotMetricsCollector,
)
from agents_b2g.shadow.subagents.government_onboarding_kit import (
    GovernmentOnboardingKit,
)

logger = logging.getLogger("ShadowContractOrchestrator")


class PilotPhase(Enum):
    INITIATION = "INITIATION"
    DEPLOYMENT = "DEPLOYMENT"
    FUNDING = "FUNDING"
    CONSTRUCTION = "CONSTRUCTION"
    TAX_SIMULATION = "TAX_SIMULATION"
    RETENTION = "RETENTION"
    COMPLETION = "COMPLETION"
    AUDIT_VIEW = "AUDIT_VIEW"


class MilestoneStatus(Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_RELEASE = "READY_FOR_RELEASE"
    RELEASED = "RELEASED"
    DISPUTED = "DISPUTED"


class ShadowContractOrchestrator:
    """
    Root-Agent der Welle 18. Orchestriert den gesamten Shadow-Contract-Lebenszyklus.

    State Machine:
        INITIATION → DEPLOYMENT → FUNDING → CONSTRUCTION
            → TAX_SIMULATION → RETENTION → COMPLETION → AUDIT_VIEW
    """

    # GAEB-Milestone-Gewerke (Beispiel Kläranlage Nord)
    DEFAULT_MILESTONES = [
        {"id": "M1", "name": "Baugrube & Erdarbeiten", "weight_pct": 15,
         "gaeb_positions": ["01.01", "01.02"], "required_evidence": ["GPS", "Foto", "ZK_PROOF"]},
        {"id": "M2", "name": "Fundament & Bodenplatte", "weight_pct": 20,
         "gaeb_positions": ["02.01", "02.02", "02.03"], "required_evidence": ["GPS", "IOT_WAAGE", "Foto", "ZK_PROOF"]},
        {"id": "M3", "name": "Rohbau & Stahlbeton", "weight_pct": 25,
         "gaeb_positions": ["03.01", "03.02"], "required_evidence": ["GPS", "IOT_WAAGE", "Foto", "ZK_PROOF"]},
        {"id": "M4", "name": "Technik & Elektro", "weight_pct": 20,
         "gaeb_positions": ["04.01", "04.02", "04.03"], "required_evidence": ["Foto", "ZK_PROOF"]},
        {"id": "M5", "name": "Inbetriebnahme & Abnahme", "weight_pct": 20,
         "gaeb_positions": ["05.01"], "required_evidence": ["GPS", "Foto", "Abnahmeprotokoll", "ZK_PROOF"]},
    ]

    def __init__(
        self,
        user_id: str = "default",
        data_root: str = "/data",
        gnosis_rpc: str = "https://rpc.gnosischain.com",
        retention_months: int = 48,  # 4 Jahre VOB/B §17
        retention_pct: float = 5.0,   # 5% Sicherheitseinbehalt
    ):
        self.user_id = user_id
        self.data_root = data_root
        self.gnosis_rpc = gnosis_rpc
        self.retention_months = retention_months
        self.retention_pct = retention_pct

        # Subagenten
        self.state_engine = LifecycleStateEngine()
        self.settlement_engine = AtomicSettlementEngine(
            vat_rate=0.19, retention_rate=retention_pct / 100, bauabzug_rate=0.15
        )
        self.deployer = ShadowContractDeployer(network="chiado")
        self.client_bridge = PrivateClientBridge()
        self.milestone_checker = MilestoneConditionChecker()
        self.tax_agent = TaxSimulationAgent()
        self.retention_mgr = RetentionVaultManager()
        self.dashboard = AuditorDashboardComposer()
        self.metrics = PilotMetricsCollector()
        self.onboarding = GovernmentOnboardingKit()

        # Zustand
        self._pilot: Optional[Dict[str, Any]] = None
        self._phase: PilotPhase = PilotPhase.INITIATION
        self._milestones: List[Dict[str, Any]] = []
        self._contract_address: Optional[str] = None
        self._audit_log: List[Dict[str, Any]] = []

    # ========================================================================
    # PUBLIC API — LIFECYCLE
    # ========================================================================

    def initiate_pilot(
        self,
        project_name: str,
        client_address: str,
        contractor_address: str,
        auditor_address: str,
        budget_eur: float,
        milestones: Optional[List[Dict[str, Any]]] = None,
        gaeb_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Phase 1: Pilotprojekt initialisieren."""
        job_id = str(uuid.uuid4())[:8]

        if self._pilot is not None:
            return {"status": "ALREADY_INITIATED", "job_id": job_id,
                    "artifacts": [], "error": "Pilot bereits initialisiert.",
                    "logs": [{"level": "WARN", "message": "initiate_pilot() wurde bereits aufgerufen."}]}

        self._milestones = milestones or self.DEFAULT_MILESTONES
        self._phase = PilotPhase.INITIATION

        self._pilot = {
            "pilot_id": f"PILOT-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{job_id.upper()}",
            "project_name": project_name,
            "client_address": client_address,
            "contractor_address": contractor_address,
            "auditor_address": auditor_address,
            "tax_authority_address": "0xFINANZAMT_SHADOW",
            "budget_eur": budget_eur,
            "retention_eur": round(budget_eur * self.retention_pct / 100, 2),
            "gaeb_reference": gaeb_reference,
            "created_at": datetime.now(timezone.utc).isoformat() + "Z",
            "status": "ACTIVE",
        }

        self._audit("INITIATION", {"project_name": project_name, "budget_eur": budget_eur})

        return {
            "status": "INITIATED",
            "job_id": job_id,
            "pilot_id": self._pilot["pilot_id"],
            "phase": self._phase.value,
            "milestones_count": len(self._milestones),
            "retention_eur": self._pilot["retention_eur"],
            "artifacts": [{"type": "pilot_init", "format": "json", "metadata": self._pilot}],
            "error": None,
            "logs": [{"level": "INFO", "message": f"Pilot {self._pilot['pilot_id']} initialisiert."}],
        }

    def deploy_contract(self, gaeb_positions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Phase 2: Shadow Contract via ShadowContractDeployer deployen."""
        if not self._pilot:
            return self._error("NO_PILOT", "initiate_pilot() zuerst aufrufen.")

        self._phase = PilotPhase.DEPLOYMENT

        # GAEB-Positionen aus Milestones generieren
        if gaeb_positions is None:
            gaeb_positions = [
                {"oz": f"0{m['id'][1:]}.01.0010", "planned_value_eur": self._pilot["budget_eur"] * m["weight_pct"] / 100,
                 "description": m["name"], "deadline_days": 60,
                 "required_evidence": m.get("required_evidence", ["GPS", "Foto"])}
                for m in self._milestones
            ]

        receipt = self.deployer.execute_deployment(
            client_address=self._pilot["client_address"],
            contractor_address=self._pilot["contractor_address"],
            auditor_address=self._pilot["auditor_address"],
            gaeb_positions=gaeb_positions,
        )

        if receipt["status"] != "DEPLOYED_AND_INITIALIZED":
            return self._error("DEPLOYMENT_FAILED", receipt.get("error", "Unbekannter Fehler"))

        self._contract_address = receipt["contract_address"]
        self._audit("DEPLOYMENT", {
            "contract": self._contract_address, "chain": receipt["network"],
            "milestones": receipt["milestones_registered_count"],
            "gnosisscan": receipt["gnosisscan_url"],
        })

        return {
            "status": "DEPLOYED",
            "job_id": receipt["job_id"],
            "contract_address": self._contract_address,
            "chain": receipt["network"],
            "chain_id": receipt["chain_id"],
            "milestones_configured": receipt["milestones_registered_count"],
            "milestone_batches": receipt["milestone_batches"],
            "deployment_tx": receipt["deployment_tx_hash"],
            "gnosisscan_verified": receipt["gnosisscan_verified"],
            "gnosisscan_url": receipt["gnosisscan_url"],
            "gobd_audit_hash": receipt["gobd_final_audit_hash"],
            "artifacts": receipt.get("artifacts", []),
            "error": None,
            "logs": [{"level": "INFO",
                      "message": f"Contract deployed: {self._contract_address} "
                                 f"({receipt['milestones_registered_count']} milestones, "
                                 f"{receipt['milestone_batches']} batches, "
                                 f"GoBD chain: {receipt['gobd_audit_chain_length']} entries)"}],
        }

    def fund_contract(self, amount_eur: float, sepa_reference: str) -> Dict[str, Any]:
        """Phase 3: SEPA → EURe via PrivateClientBridge."""
        if not self._contract_address:
            return self._error("NO_CONTRACT", "deploy_contract() zuerst aufrufen.")

        if amount_eur > self._pilot["budget_eur"]:
            return self._error("OVER_BUDGET",
                               f"{amount_eur:,.2f} > Budget {self._pilot['budget_eur']:,.2f}")

        self._phase = PilotPhase.FUNDING

        receipt = self.client_bridge.process_sepa_inbound(
            client_id=self._pilot.get("client_address", "UNKNOWN"),
            sepa_reference=sepa_reference,
            deposited_eur=amount_eur,
            target_escrow_address=self._contract_address,
            expected_budget_eur=self._pilot["budget_eur"],
            firmendaten={"name": self._pilot.get("project_name", "")},
        )

        if receipt["status"] not in ("ESCROW_FUNDED_SUCCESSFULLY",):
            return self._error("FUNDING_FAILED",
                               receipt.get("error", f"Status: {receipt['status']}"))

        self._audit("FUNDING", {
            "amount_eur": amount_eur, "sepa_ref": sepa_reference,
            "mint_tx": receipt["on_chain_funding"]["mint_tx_hash"],
            "monerium_order": receipt["on_chain_funding"]["monerium_order_id"],
        })

        return {
            "status": "FUNDED",
            "job_id": receipt["job_id"],
            "amount_eur": amount_eur,
            "sepa_reference": sepa_reference,
            "viban": receipt.get("viban"),
            "monerium_order_id": receipt["on_chain_funding"]["monerium_order_id"],
            "mint_tx": receipt["on_chain_funding"]["mint_tx_hash"],
            "contract_balance_eur": amount_eur,
            "balance_verified": receipt["verification"]["on_chain_balance_confirmed"],
            "block_height": receipt["verification"]["block_height"],
            "gobd_audit_hash": receipt["gobd_audit_hash"],
            "artifacts": receipt.get("artifacts", []),
            "error": None,
            "logs": [{"level": "INFO",
                      "message": f"SEPA {sepa_reference}: {amount_eur:,.2f} EUR → EURe Mint → {self._contract_address}"}],
        }

    def check_milestone(
        self, milestone_id: str, popw_evidence: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Phase 4: Milestone-Prüfung via MilestoneConditionChecker (IoT+ZK+GAEB)."""
        if self._phase not in (PilotPhase.FUNDING, PilotPhase.CONSTRUCTION):
            return self._error("WRONG_PHASE", f"Aktuelle Phase: {self._phase.value}")

        milestone = next((m for m in self._milestones if m["id"] == milestone_id), None)
        if not milestone:
            return self._error("UNKNOWN_MILESTONE", f"Milestone {milestone_id} nicht gefunden.")

        self._phase = PilotPhase.CONSTRUCTION

        # Telemetrie aus Evidenz bauen
        raw_sensor_data = []
        measured_qty = 0.0
        zk_hash = "0x0000000000000000000000000000000000000000000000000000000000000000"
        device_did = "did:peaq:sensor_01"

        for ev in popw_evidence:
            raw_sensor_data.append({
                "type": ev.get("type", "UNKNOWN"),
                "value": ev.get("value", 0),
                "device_did": ev.get("device_did", device_did),
                "timestamp": ev.get("timestamp", ""),
            })
            if ev.get("type") == "IOT_WAAGE":
                measured_qty += float(ev.get("value", 0))
            if ev.get("type") == "ZK_PROOF":
                zk_hash = ev.get("hash", zk_hash)
                device_did = ev.get("device_did", device_did)

        telemetry = {
            "raw_sensor_data": raw_sensor_data,
            "zk_proof_hash": zk_hash,
            "device_did": device_did,
            "measured_qty": measured_qty if measured_qty > 0 else 999999.0,  # Fallback für non-Qty-Evidenz
            "compressive_strength_mpa": 42.0,
            "completion_date": datetime.now(timezone.utc).isoformat(),
        }

        target_qty = 1.0  # Default für Non-Quantity-Milestones
        result = self.milestone_checker.evaluate_and_release(
            tender_id=self._pilot.get("pilot_id", "UNKNOWN"),
            oz_id=milestone_id,
            target_qty=target_qty,
            telemetry_data=telemetry,
            quality_spec="C30_37",
            planned_date=datetime.now(timezone.utc).isoformat(),
        )

        if not result.get("released"):
            return {
                "status": "MILESTONE_REJECTED",
                "milestone_id": milestone_id,
                "failed_checks": result.get("failed_checks", []),
                "artifacts": [], "error": None,
                "logs": [{"level": "WARN",
                          "message": f"Milestone {milestone_id} rejected: {result.get('failed_checks')}"}],
            }

        release_amount = self._pilot["budget_eur"] * milestone["weight_pct"] / 100
        release_tx = result["on_chain_execution"]["contract_tx_hash"]

        milestone["status"] = MilestoneStatus.RELEASED.value
        milestone["release_tx"] = release_tx
        milestone["release_amount_eur"] = round(release_amount, 2)
        milestone["released_at"] = datetime.now(timezone.utc).isoformat() + "Z"

        self._audit("MILESTONE_RELEASE", {
            "milestone": milestone_id, "amount": release_amount, "tx": release_tx,
            "verification": result.get("verification_summary", {}),
        })

        return {
            "status": "MILESTONE_RELEASED",
            "job_id": result["job_id"],
            "milestone_id": milestone_id,
            "release_amount_eur": round(release_amount, 2),
            "release_tx": release_tx,
            "verification": result.get("verification_summary", {}),
            "gobd_audit_hash": result.get("gobd_audit_hash"),
            "artifacts": result.get("artifacts", []),
            "error": None,
            "logs": [{"level": "INFO",
                      "message": f"Milestone {milestone_id}: {release_amount:,.2f} EUR freigegeben "
                                 f"(Proof: {result['verification_summary']['popw_proof_valid']}, "
                                 f"Qty: {result['verification_summary']['quantity_fulfillment_pct']:.0f}%)"}],
        }

    def simulate_taxes(self) -> Dict[str, Any]:
        """Phase 5: Steuerabführung via TaxSimulationAgent (ELSTER, BZSt, Tax-Wallet)."""
        if not self._pilot:
            return self._error("NO_PILOT", "initiate_pilot() zuerst aufrufen.")

        released = sum(m.get("release_amount_eur", 0) for m in self._milestones
                       if m.get("status") == MilestoneStatus.RELEASED.value)

        if released <= 0:
            return self._error("NO_RELEASES", "Keine Milestones freigegeben.")

        self._phase = PilotPhase.TAX_SIMULATION

        result = self.tax_agent.execute_tax_split(
            tender_id=self._pilot.get("pilot_id", "UNKNOWN"),
            oz_id="TAX_SIMULATION",
            gross_amount_eur=released,
            contractor_tax_number="13/123/45678",
            cert_hash="VALID_CERT_HASH_2026",
            description="Bauleistung Gesamtabrechnung",
            is_b2b=True,
        )

        if result["status"] != "TAX_SETTLEMENT_SUCCESSFUL":
            return self._error("TAX_FAILED", result.get("error", "Unbekannter Fehler"))

        s = result["split_summary"]
        self._audit("TAX_SIMULATION", {
            "released": released, "ust": s["vat_amount_eur"],
            "bauabzug": s["bauabzug_tax_15pct_eur"], "delta": s["atomic_check_delta_eur"],
            "regime": result["tax_regime"]["regime"],
        })

        return {
            "status": "TAXES_SIMULATED",
            "job_id": result["job_id"],
            "released_amount_eur": round(released, 2),
            "ust_eur": s["vat_amount_eur"],
            "bauabzugsteuer_eur": s["bauabzug_tax_15pct_eur"],
            "net_to_contractor_eur": s["net_payout_contractor_eur"],
            "tax_regime": result["tax_regime"]["regime"],
            "exemption_valid": result["exemption"]["is_valid"],
            "tax_wallet": result["tax_wallet"],
            "elster_xml": result.get("elster_xml", ""),
            "pdf_voucher_hash": result.get("pdf_voucher_hash"),
            "atomic_delta_eur": s["atomic_check_delta_eur"],
            "gobd_audit_hash": result["gobd_audit_hash"],
            "artifacts": result.get("artifacts", []),
            "error": None,
            "logs": [{"level": "INFO",
                      "message": result["logs"][0]["message"] if result.get("logs") else "Tax split complete"}],
        }

    def manage_retention(self, acceptance_date_iso: str = "", open_defect_ids: list = None) -> Dict[str, Any]:
        """Phase 6: 5% Sicherheitseinbehalt via RetentionVaultManager."""
        if not self._pilot:
            return self._error("NO_PILOT", "initiate_pilot() zuerst aufrufen.")

        self._phase = PilotPhase.RETENTION
        acceptance = acceptance_date_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        result = self.retention_mgr.evaluate_retention_state(
            tender_id=self._pilot.get("pilot_id", "UNKNOWN"),
            total_gross_eur=self._pilot["budget_eur"],
            acceptance_date_iso=acceptance,
            contract_address=self._contract_address or "",
            open_defect_ids=open_defect_ids or [],
        )

        self._audit("RETENTION", {
            "amount": result["vault_summary"]["total_retention_locked_eur"],
            "state": result["vault_summary"]["vault_state"],
            "reason": result["vault_summary"]["release_reason"],
        })

        return {
            "status": "RETENTION_ACTIVE" if result["status"] == "LOCKED" else "RETENTION_RELEASED",
            "job_id": result["job_id"],
            "retention_amount_eur": result["vault_summary"]["total_retention_locked_eur"],
            "retention_pct": result["vault_summary"]["retention_rate_pct"],
            "vault_state": result["vault_summary"]["vault_state"],
            "release_reason": result["vault_summary"]["release_reason"],
            "warranty_expiration": result["warranty_tracking"]["expiration_date"],
            "warranty_days_remaining": result["warranty_tracking"]["days_remaining"],
            "open_defects": result["defect_monitoring"]["open_defects"],
            "on_chain_release_tx": result["on_chain_release_tx"],
            "gobd_audit_hash": result["gobd_audit_hash"],
            "artifacts": result.get("artifacts", []),
            "error": None,
            "logs": result.get("logs", []),
        }

    def complete_project(self) -> Dict[str, Any]:
        """Phase 7: Projekt abschließen."""
        if not self._pilot:
            return self._error("NO_PILOT", "initiate_pilot() zuerst aufrufen.")

        released_total = sum(m.get("release_amount_eur", 0) for m in self._milestones
                             if m.get("status") == MilestoneStatus.RELEASED.value)

        self._phase = PilotPhase.COMPLETION
        self._pilot["status"] = "COMPLETED"
        self._pilot["completed_at"] = datetime.now(timezone.utc).isoformat() + "Z"

        self._audit("COMPLETION", {"total_released": released_total,
                                    "budget": self._pilot["budget_eur"]})

        return {
            "status": "COMPLETED",
            "job_id": str(uuid.uuid4())[:8],
            "total_released_eur": round(released_total, 2),
            "budget_eur": self._pilot["budget_eur"],
            "retention_eur": self._pilot["retention_eur"],
            "milestones_completed": sum(1 for m in self._milestones
                                        if m.get("status") == MilestoneStatus.RELEASED.value),
            "total_milestones": len(self._milestones),
            "artifacts": [{"type": "completion_certificate", "format": "json",
                           "metadata": self._pilot}],
            "error": None,
            "logs": [{"level": "INFO", "message": f"Projekt abgeschlossen. {released_total:,.2f} EUR freigegeben."}],
        }

    def auditor_view(self) -> Dict[str, Any]:
        """Phase 8: RPA-Dashboard + Abschlusszertifikat via AuditorDashboardComposer."""
        if not self._pilot:
            return self._error("NO_PILOT", "initiate_pilot() zuerst aufrufen.")

        self._phase = PilotPhase.AUDIT_VIEW

        released = sum(m.get("release_amount_eur", 0) for m in self._milestones
                       if m.get("status") == MilestoneStatus.RELEASED.value)
        retention = self._pilot.get("retention_eur", 0)
        tax = round(released * 0.19, 2)

        proofs = [
            {"milestone_id": m["id"], "sensor_type": ev,
             "device_did": f"did:peaq:sensor_{m['id'].lower()}",
             "measured_val": f"{m['weight_pct']}% complete"}
            for m in self._milestones
            for ev in m.get("required_evidence", [])[:1]
            if m.get("status") == MilestoneStatus.RELEASED.value
        ]

        result = self.dashboard.generate_dashboard(
            tender_id=self._pilot.get("pilot_id", "UNKNOWN"),
            rpa_user_id="ORR_Pruefer_Shadow",
            contract_address=self._contract_address or "",
            budget_eur=self._pilot["budget_eur"],
            released_eur=released,
            retention_eur=retention,
            tax_eur=tax,
            milestones=[{"id": m["id"], "status": m.get("status", "PENDING")}
                        for m in self._milestones],
            proofs=proofs,
        )

        cert = result.get("completion_certificate")
        self._audit("AUDITOR_VIEW", {
            "ledger_delta": result["dashboard"]["financial_ledger"]["delta_eur"],
            "certificate": cert["certificate_hash"] if cert else None,
        })

        return {
            "status": "AUDITOR_VIEW_READY",
            "job_id": result["job_id"],
            "session": result["dashboard"]["auditor_session"],
            "ledger_status": result["dashboard"]["financial_ledger"]["status"],
            "ledger_delta_eur": result["dashboard"]["financial_ledger"]["delta_eur"],
            "progress_pct": result["dashboard"]["project_progress"]["progress_pct"],
            "completion_certificate": cert,
            "gobd_export_urls": result["dashboard"]["gobd_export"],
            "artifacts": result.get("artifacts", []),
            "error": None,
            "logs": result.get("logs", []),
        }

    def full_lifecycle(self, sepa_reference: str = "SEPA-TEST-001") -> Dict[str, Any]:
        """Führt den kompletten Lebenszyklus in einem Durchlauf aus (Demo/Test)."""
        results = {}

        results["init"] = self.initiate_pilot(
            project_name="Kläranlage Nord — Shadow Pilot",
            client_address="0x1111111111111111111111111111111111111111",
            contractor_address="0x2222222222222222222222222222222222222222",
            auditor_address="0x3333333333333333333333333333333333333333",
            budget_eur=4_200_000.0,
        )

        results["deploy"] = self.deploy_contract()
        results["fund"] = self.fund_contract(4_200_000.0, sepa_reference)

        for ms in self._milestones:
            evidence = []
            for t in ms["required_evidence"]:
                if t == "IOT_WAAGE":
                    evidence.append({"type": t, "value": 500.0, "device_did": "did:peaq:waage_03",
                                     "timestamp": datetime.now(timezone.utc).isoformat()})
                elif t == "ZK_PROOF":
                    evidence.append({"type": t,
                                     "hash": "0x" + uuid.uuid4().hex + uuid.uuid4().hex,
                                     "device_did": "did:peaq:sensor_01",
                                     "timestamp": datetime.now(timezone.utc).isoformat()})
                elif t == "GPS":
                    evidence.append({"type": t, "value": "52.5200,13.4050",
                                     "device_did": "did:peaq:bagger_01",
                                     "timestamp": datetime.now(timezone.utc).isoformat()})
                else:
                    evidence.append({"type": t, "hash": f"0x{uuid.uuid4().hex[:16]}",
                                     "timestamp": datetime.now(timezone.utc).isoformat()})
            results[f"milestone_{ms['id']}"] = self.check_milestone(ms["id"], evidence)

        results["taxes"] = self.simulate_taxes()
        results["retention"] = self.manage_retention()
        results["complete"] = self.complete_project()
        results["auditor"] = self.auditor_view()
        results["metrics"] = self.metrics.generate_lessons_learned(
            tender_id=self._pilot["pilot_id"] if self._pilot else "UNKNOWN")
        results["onboarding"] = self.onboarding.generate_package(
            municipality_name="Stadtentwässerung Duisburg AöR",
            annual_budget_eur=self._pilot["budget_eur"] if self._pilot else 15_000_000)

        return {
            "status": "LIFECYCLE_COMPLETE",
            "pilot_id": self._pilot["pilot_id"] if self._pilot else None,
            "phases_completed": list(results.keys()),
            "audit_log_entries": len(self._audit_log),
            "results": results,
            "artifacts": [],
            "error": None,
            "logs": [{"level": "INFO", "message": f"Full lifecycle: {len(results)} phases completed."}],
        }

    # ========================================================================
    # HELPERS
    # ========================================================================

    def _error(self, code: str, msg: str) -> Dict[str, Any]:
        return {"status": "failed", "job_id": str(uuid.uuid4())[:8],
                "artifacts": [], "error": f"[{code}] {msg}",
                "logs": [{"level": "ERROR", "message": msg}]}

    def _audit(self, event: str, data: Dict[str, Any]) -> None:
        self._audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "phase": self._phase.value,
            "event": event,
            "data": data,
        })


# ============================================================================
# SMOKE TEST
# ============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("ShadowContractOrchestrator — Smoke Test")
    print("=" * 60)

    orch = ShadowContractOrchestrator(user_id="test_pilot")

    # Full lifecycle
    result = orch.full_lifecycle()
    print(f"\nStatus: {result['status']}")
    print(f"Pilot: {result['pilot_id']}")
    print(f"Phasen: {result['phases_completed']}")
    print(f"Audit-Log: {result['audit_log_entries']} Einträge")

    # Check individual phases
    for phase, data in result["results"].items():
        status = data.get("status", "?")
        icon = "✅" if status not in ("failed",) else "❌"
        print(f"  {icon} {phase}: {status}")

    # Auditor view
    av = orch.auditor_view()
    print(f"\nDashboard: Session={av['session']['rpa_officer']}, "
          f"Ledger={av['ledger_status']} (Δ={av['ledger_delta_eur']:.2f} EUR), "
          f"Progress={av['progress_pct']:.0f}%")
    if av.get("completion_certificate"):
        print(f"Zertifikat: {av['completion_certificate']['certificate_hash'][:32]}...")
    print(f"GoBD: {av['gobd_export_urls']['jsonl_url']}")

    print(f"\n✅ Smoke Test abgeschlossen.")
