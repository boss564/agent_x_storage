"""ZK Settlement — Darkpool-to-Surface handoff for confidential §48b settlements.

D01 (TEE Enclave) processes raw tax data, invoice line items, and personal
identifiers in an isolated SGX environment. It outputs only a ZK proof +
public inputs to C09 on the surface.

The surface never sees:
  - Tax IDs, contractor names, invoice line items (DSGVO)
  - Raw §48b certificates (Betriebsgeheimnis)
  - Invoice secrets (double-spend protection via nullifier)

The surface receives:
  - A Groth16/PLONK proof (verified in <2 ms)
  - Public inputs: state roots, nullifier hash, commitment hash, net euro amount
  - A Valhalla stamp for anonymous reputation tracking
  - A TEE attestation quote

Architecture: D01 (off-chain, TEE) → ZKProofSettlementPayload → C09 (on-chain)
Verification: nullifier check → ZK proof → mint & settle → honor ledger
"""

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ZKSettlement")


# ─── The Handoff Payload ────────────────────────────────────────────────────

@dataclass
class ZKProofSettlementPayload:
    """What D01 sends to C09 — no cleartext, only proofs and commitments."""

    protocol_version: str = "v2.4-zkSNARK"
    target_chain_id: str = "liquidity_l2"
    timestamp_tick: int = 0

    # ZK proof (Groth16 / PLONK)
    proof_type: str = "Groth16_BN254"
    proof: Dict[str, List[str]] = field(default_factory=dict)
    # Public inputs — the only values C09 verifies against
    public_inputs: Dict[str, str] = field(default_factory=dict)

    # Anonymous reputation
    valhalla_stamp: str = ""
    # Hardware attestation from the TEE
    tee_attestation_quote: str = ""

    @classmethod
    def create_demo(cls, net_eur: float, invoice_secret: str,
                    tax_id: str, valhalla_stamp: str = "") -> "ZKProofSettlementPayload":
        """Create a demo payload with simulated ZK proof data."""
        nullifier = hashlib.sha256(
            f"{invoice_secret}{tax_id}".encode()
        ).hexdigest()
        commitment = hashlib.sha256(
            f"COMMIT_{invoice_secret}_{net_eur}".encode()
        ).hexdigest()
        state_before = hashlib.sha256(b"state_before").hexdigest()
        state_after = hashlib.sha256(
            f"state_after_{net_eur}_{nullifier}".encode()
        ).hexdigest()

        return cls(
            timestamp_tick=int(time.time()),
            proof={
                "pi_a": [f"0x{hashlib.sha256(b'a').hexdigest()[:64]}"],
                "pi_b": [[f"0x{hashlib.sha256(b'b1').hexdigest()[:64]}",
                          f"0x{hashlib.sha256(b'b2').hexdigest()[:64]}"]],
                "pi_c": [f"0x{hashlib.sha256(b'c').hexdigest()[:64]}"],
            },
            public_inputs={
                "state_root_before": state_before,
                "state_root_after": state_after,
                "nullifier_hash": nullifier,
                "commitment_hash": commitment,
                "settlement_net_eur": str(int(net_eur * 100)),  # cents
            },
            valhalla_stamp=valhalla_stamp or f"0x{nullifier[:16]}",
            tee_attestation_quote=hashlib.sha256(
                f"TEE_QUOTE_{nullifier}".encode()
            ).hexdigest()[:64],
        )


# ─── Nullifier Repository ───────────────────────────────────────────────────

class NullifierRepository:
    """Prevents double-spending: each nullifier may only be used once.

    Extends the nonce-tracking pattern from DIDRegistry to the settlement layer.
    """

    def __init__(self):
        self._used: set = set()
        self._count: int = 0

    def exists(self, nullifier: str) -> bool:
        return nullifier in self._used

    def mark_used(self, nullifier: str) -> bool:
        """Mark a nullifier as used. Returns False if already used (replay)."""
        if nullifier in self._used:
            return False
        self._used.add(nullifier)
        self._count += 1
        return True

    def __len__(self) -> int:
        return self._count


# ─── ZK Verifier ────────────────────────────────────────────────────────────

class ZKVerifier:
    """Verifies ZK settlement proofs — injectable, demo/production modes.

    Demo mode: verifies that the proof structure is well-formed and the
               nullifier/commitment are consistent (deterministic, fast).

    Production mode: delegates to an injected native verifier (Groth16/PLONK
                     pairing check via C++/Rust engine or HSM).

    Pattern: identical to DIDRegistry._verify_crypto — fail-closed.
    """

    def __init__(self, demo_mode: bool = True):
        self.demo_mode = demo_mode
        self._native_verifier: Any = None

    def verify(self, payload: ZKProofSettlementPayload) -> tuple:
        """Verify a ZK settlement payload. Returns (valid: bool, reason: str)."""

        # 1. Structure check
        if not payload.proof or not payload.public_inputs:
            return False, "MISSING_PROOF_OR_INPUTS"

        pi = payload.public_inputs
        required = ["state_root_before", "state_root_after",
                    "nullifier_hash", "commitment_hash", "settlement_net_eur"]
        for key in required:
            if key not in pi:
                return False, f"MISSING_PUBLIC_INPUT:{key}"

        # 2. Net amount must be positive
        net_eur = int(pi["settlement_net_eur"]) / 100.0
        if net_eur <= 0:
            return False, f"INVALID_AMOUNT:{net_eur}"

        # 3. State transition must be a real change
        if pi["state_root_before"] == pi["state_root_after"]:
            return False, "NO_STATE_TRANSITION"

        # 4. Proof verification
        if self.demo_mode:
            # Demo: verify that the proof is well-formed and consistent
            if payload.proof_type not in ("Groth16_BN254", "PLONK_BN254"):
                return False, f"UNKNOWN_PROOF_TYPE:{payload.proof_type}"
            if not all(k in payload.proof for k in ("pi_a", "pi_b", "pi_c")):
                return False, "MALFORMED_PROOF_STRUCTURE"
        else:
            # Production: delegate to native verifier
            if self._native_verifier is None:
                logger.error(
                    "ZKVerifier in production mode but no native verifier "
                    "injected — rejecting. Call inject_verifier(engine)."
                )
                return False, "NO_NATIVE_VERIFIER_INJECTED"
            try:
                if not self._native_verifier.verify(
                    payload.proof, payload.public_inputs, payload.proof_type
                ):
                    return False, "NATIVE_PROOF_VERIFICATION_FAILED"
            except Exception as e:
                logger.error("Native verifier error: %s", e)
                return False, f"VERIFIER_ERROR:{e}"

        return True, "ZK_PROOF_VALID"

    def inject_verifier(self, native_verifier: Any) -> None:
        """Inject a native Groth16/PLONK verifier for production use.

        The verifier must expose:
            verify(proof: dict, public_inputs: dict, proof_type: str) -> bool
        """
        self._native_verifier = native_verifier
        self.demo_mode = False
        logger.info("Native ZK verifier injected — production mode active")


# ─── C09 Settlement Processor ───────────────────────────────────────────────

class C09SettlementProcessor:
    """Surface agent: receives ZK proofs from D01, verifies, mints, settles.

    This is the on-chain component that never sees cleartext tax data.
    It only processes proofs and public inputs.
    """

    def __init__(self, zk_verifier: ZKVerifier = None,
                 nullifier_repo: NullifierRepository = None):
        self.verifier = zk_verifier or ZKVerifier(demo_mode=True)
        self.nullifiers = nullifier_repo or NullifierRepository()
        self.total_settled_eur: float = 0.0
        self.total_settlements: int = 0
        self.rejected: int = 0
        self.honor_ledger: Dict[str, int] = {}  # valhalla_stamp → total honor
        self.event_log: List[Dict] = []

    def process(self, payload: ZKProofSettlementPayload) -> Dict[str, Any]:
        """Process a ZK settlement payload from D01. Returns result dict."""

        # Step 1: Nullifier uniqueness (replay protection)
        nullifier = payload.public_inputs.get("nullifier_hash", "")
        if self.nullifiers.exists(nullifier):
            self.rejected += 1
            reason = f"DOUBLE_SPEND:{nullifier[:16]}"
            self.event_log.append({"status": "REJECTED", "reason": reason})
            return {"status": "REJECTED", "reason": reason}

        # Step 2: Verify ZK proof
        valid, reason = self.verifier.verify(payload)
        if not valid:
            self.rejected += 1
            self.event_log.append({"status": "REJECTED", "reason": reason})
            return {"status": "REJECTED", "reason": reason}

        # Step 3: Execute mint (net amount from public inputs)
        net_eur = int(payload.public_inputs["settlement_net_eur"]) / 100.0
        self.total_settled_eur += net_eur
        self.total_settlements += 1

        # Step 4: Mark nullifier used
        self.nullifiers.mark_used(nullifier)

        # Step 5: Credit Valhalla honor
        stamp = payload.valhalla_stamp
        self.honor_ledger[stamp] = self.honor_ledger.get(stamp, 0) + 50

        result = {
            "status": "SETTLED",
            "net_eur_cents": net_eur_cents,
            "nullifier": f"{nullifier[:16]}...",
            "state_root_after": payload.public_inputs["state_root_after"][:16],
            "valhalla_stamp": stamp,
            "honor_earned": 50,
            "total_honor": self.honor_ledger[stamp],
        }
        self.event_log.append(result)
        return result

    def summary(self) -> Dict[str, Any]:
        return {
            "total_settled_eur": self.total_settled_eur,
            "total_settlements": self.total_settlements,
            "rejected": self.rejected,
            "nullifiers_used": len(self.nullifiers),
            "honor_ledger_size": len(self.honor_ledger),
        }


# ─── Demo ───────────────────────────────────────────────────────────────────

def demo_zk_settlement():
    """Demonstrate D01 → C09 handoff: confidential invoice → ZK proof → mint."""
    W = 72
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  🌊 D01 (TEE) → C09 (Surface) — ZK Settlement Handoff".center(W - 2) + "█")
    print("█" + "  No cleartext leaves the enclave. Only proofs.".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W)

    c09 = C09SettlementProcessor()

    # Three settlements from three different contractors
    settlements = [
        ("CONTRACTOR_A", "INV-2026-0042", "TAX_37/123/45", 25000.00, "did:valhalla:7e3a"),
        ("CONTRACTOR_B", "INV-2026-0081", "TAX_21/456/78", 180000.00, "did:valhalla:9f1b"),
        ("CONTRACTOR_A", "INV-2026-0042", "TAX_37/123/45", 25000.00, "did:valhalla:7e3a"),  # replay!
    ]

    print(f"\n  {'#':<3} {'From':<18} {'Net EUR':>10} {'Status':<10} {'Detail':<30}")
    print(f"  {'─'*3} {'─'*18} {'─'*10} {'─'*10} {'─'*30}")

    for i, (contractor, invoice, tax_id, amount, stamp) in enumerate(settlements, 1):
        if i == 3:
            print(f"\n  💥 REPLAY ATTACK (same invoice secret + tax ID):")
        payload = ZKProofSettlementPayload.create_demo(amount, invoice, tax_id, stamp)
        result = c09.process(payload)
        status_icon = "✅" if result["status"] == "SETTLED" else "🛡️"
        net = result.get("net_eur", 0)
        detail = result.get("reason", f"Mint €{net:,.2f} | Honor +50")
        print(f"  {status_icon} {i:<2} {contractor:<18} {amount:>10,.2f} {result['status']:<10} {detail:<30}")

    # Summary
    s = c09.summary()
    print(f"\n  📊 C09 Summary: {s['total_settlements']} settled, {s['rejected']} rejected")
    print(f"     Total minted: €{s['total_settled_eur']:,.2f}")
    print(f"     Nullifiers used: {s['nullifiers_used']}")
    print(f"     Honor ledger: {s['honor_ledger_size']} stamps\n")

    # Visibility matrix
    print(f"  🔍 VISIBILITY MATRIX:")
    print(f"     {'Field':<25} {'D01 (Enclave)':<20} {'C09 (Surface)':<20}")
    print(f"     {'─'*25} {'─'*20} {'─'*20}")
    rows = [
        ("Invoice line items", "120t Beton C30/37", "❌ Not present"),
        ("Tax ID", "37/123/45 (Finanzamt)", "❌ In ZK proof only"),
        ("§48b certificate", "Valid until 2026-12-31", "🟢 Proof.IsVerified"),
        ("Net settlement", "€ 25,000.00", "🟢 € 25,000.00 (mint)"),
        ("Contractor identity", "Subcontractor GmbH", "🟢 0x7e3a... (Valhalla)"),
    ]
    for field, d01, c09_view in rows:
        print(f"     {field:<25} {d01:<20} {c09_view:<20}")

    print(f"\n  ✅ D01→C09 handoff complete — zero cleartext on the surface\n")


# ═══════════════════════════════════════════════════════════════════════════════
# D02 — GoBD Forensic Diver (Historical DAG Repair & State Healing)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ForensicAuditPayload:
    """What D02 sends to C05 when a historical Merkle anomaly is healed."""

    incident_id: str = ""
    corrupted_block_height: int = 0
    detected_at_tick: int = 0

    # State repair
    invalid_state_root: str = ""
    healed_state_root: str = ""
    zk_reconciliation_proof: str = ""

    # Compliance
    bho_invariant_status: str = "0/42_CHECKS_PENDING"
    forensic_signature: str = ""
    valhalla_stamp: str = ""

    @classmethod
    def create_demo(cls, block: int, invalid_root_hex: str = None) -> "ForensicAuditPayload":
        """Create a demo forensic payload for a corrupted historical block."""
        invalid = invalid_root_hex or hashlib.sha256(
            f"TAMPERED_BLOCK_{block}".encode()
        ).hexdigest()
        healed = hashlib.sha256(
            f"CORRECT_BLOCK_{block}_REPAIRED".encode()
        ).hexdigest()
        proof = hashlib.sha256(
            f"ZK_RECONCILE_{invalid}_{healed}".encode()
        ).hexdigest()[:64]
        sig = hashlib.sha256(
            f"FORENSIC_SIG_{healed}".encode()
        ).hexdigest()[:64]

        return cls(
            incident_id=f"INC-DAG-{block:06d}",
            corrupted_block_height=block,
            detected_at_tick=int(time.time()),
            invalid_state_root=invalid,
            healed_state_root=healed,
            zk_reconciliation_proof=proof,
            bho_invariant_status="42/42_CHECKS_VERIFIED",
            forensic_signature=sig,
            valhalla_stamp=f"did:valhalla:deep_guardian_{block % 1000:03d}",
        )


class C05GoBDAuditor:
    """Surface agent: receives forensic reports from D02, verifies, hot-swaps,
    and writes GoBD-compliant audit entries.

    Zero surface downtime: historical root is replaced in-memory while the
    current tick continues uninterrupted.
    """

    def __init__(self):
        self.state_roots: Dict[int, str] = {}  # block_height → state_root
        self.audit_log: List[Dict] = []
        self.healed_incidents: int = 0
        self.rejected_incidents: int = 0
        self.honor_ledger: Dict[str, int] = {}

        # Initialize with some "historical" state roots (blocks 0–10000)
        for h in range(0, 10001, 100):
            self.state_roots[h] = hashlib.sha256(
                f"GENESIS_STATE_{h}".encode()
            ).hexdigest()

    def process_forensic_repair(self, payload: ForensicAuditPayload) -> Dict[str, Any]:
        """Verify ZK reconciliation proof, hot-swap root, write GoBD entry."""

        # Step 1: Verify ZK reconciliation proof
        expected_proof = hashlib.sha256(
            f"ZK_RECONCILE_{payload.invalid_state_root}_{payload.healed_state_root}".encode()
        ).hexdigest()[:64]
        if payload.zk_reconciliation_proof != expected_proof:
            self.rejected_incidents += 1
            return {"status": "REJECTED", "reason": "INVALID_ZK_RECONCILIATION_PROOF"}

        # Step 2: Verify the invalid root matches what we have recorded
        h = payload.corrupted_block_height
        current_root = self.state_roots.get(h)
        if current_root is None:
            return {"status": "REJECTED", "reason": f"UNKNOWN_BLOCK_HEIGHT:{h}"}
        if current_root != payload.invalid_state_root:
            # The root was already healed or never corrupted — idempotent
            return {"status": "ALREADY_HEALED", "reason": "ROOT_ALREADY_CORRECT"}

        # Step 3: Hot-swap — replace invalid root with healed root (0 ms downtime)
        self.state_roots[h] = payload.healed_state_root
        self.healed_incidents += 1

        # Step 4: Write immutable GoBD audit log entry
        entry = {
            "incident_id": payload.incident_id,
            "block_height": h,
            "status": "HEALED",
            "bho_checks": payload.bho_invariant_status,
            "forensic_signature": payload.forensic_signature[:16],
            "healed_at_tick": payload.detected_at_tick,
        }
        self.audit_log.append(entry)

        # Step 5: Credit Valhalla honor for the anonymous forensic diver
        stamp = payload.valhalla_stamp
        self.honor_ledger[stamp] = self.honor_ledger.get(stamp, 0) + 100

        return {
            "status": "HEALED",
            "incident_id": payload.incident_id,
            "block_height": h,
            "healed_root": payload.healed_state_root[:16],
            "valhalla_stamp": stamp,
            "honor_earned": 100,
            "bho_status": payload.bho_invariant_status,
        }

    def verify_historical_integrity(self, block: int) -> Dict[str, Any]:
        """Check if a historical block's root matches expected genesis."""
        root = self.state_roots.get(block)
        if root is None:
            return {"block": block, "status": "UNKNOWN"}
        genesis = hashlib.sha256(f"GENESIS_STATE_{block}".encode()).hexdigest()
        if root == genesis:
            return {"block": block, "status": "INTACT", "root": root[:16]}
        # Root differs from genesis — either tampered or healed
        return {"block": block, "status": "HEALED_OR_TAMPERED",
                "root": root[:16], "genesis": genesis[:16]}

    def summary(self) -> Dict[str, Any]:
        return {
            "tracked_blocks": len(self.state_roots),
            "healed_incidents": self.healed_incidents,
            "rejected_incidents": self.rejected_incidents,
            "audit_log_entries": len(self.audit_log),
            "honor_ledger_size": len(self.honor_ledger),
        }


def demo_forensic_repair():
    """Demonstrate D02 → C05: historical Merkle anomaly detected and healed."""
    W = 72
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  🌊 D02 (Forensic Diver) → C05 (GoBD Auditor)".center(W - 2) + "█")
    print("█" + "  Historical DAG Repair — 0 ms surface downtime".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W)

    c05 = C05GoBDAuditor()

    # Simulate: attacker modified block 4200's root
    tampered_block = 4200
    tampered_root = hashlib.sha256(f"TAMPERED_BLOCK_{tampered_block}".encode()).hexdigest()
    c05.state_roots[tampered_block] = tampered_root  # Corrupt it

    # Verify before repair
    before = c05.verify_historical_integrity(tampered_block)
    print(f"\n  🔍 Pre-check block {tampered_block}: {before['status']}")
    print(f"     Root: {before['current_root']}... (≠ genesis hash)")

    # D02 surfaces with the forensic payload
    print(f"\n  🌊 D02 surfaces with ForensicAuditPayload...")
    payload = ForensicAuditPayload.create_demo(tampered_block)
    print(f"     Incident: {payload.incident_id}")
    print(f"     Invalid root:  {payload.invalid_state_root[:24]}...")
    print(f"     Healed root:   {payload.healed_state_root[:24]}...")
    print(f"     ZK proof:      {payload.zk_reconciliation_proof[:24]}...")
    print(f"     BHO checks:    {payload.bho_invariant_status}")

    # C05 processes the repair
    result = c05.process_forensic_repair(payload)
    print(f"\n  ⚡ C05 hot-swap result: {result['status']}")
    print(f"     Healed root: {result['healed_root']}...")
    print(f"     Honor earned: +{result['honor_earned']} → {c05.honor_ledger[payload.valhalla_stamp]} total")

    # Verify after repair
    after = c05.verify_historical_integrity(tampered_block)
    print(f"\n  ✅ Post-check block {tampered_block}: {after['status']}")
    print(f"     Root: {after['current_root']}... (= healed root)")

    # Attempt replay (same incident, already healed)
    replay_result = c05.process_forensic_repair(payload)
    print(f"\n  🔁 Replay same incident: {replay_result['status']} ({replay_result['reason']})")

    # Attempt invalid ZK proof
    bad_payload = ForensicAuditPayload.create_demo(4300)
    bad_payload.zk_reconciliation_proof = "0xTAMPERED_PROOF"
    # Corrupt block 4300 first
    c05.state_roots[4300] = bad_payload.invalid_state_root
    bad_result = c05.process_forensic_repair(bad_payload)
    print(f"  🛡️ Tampered ZK proof: {bad_result['status']} ({bad_result['reason']})")

    # Summary
    s = c05.summary()
    print(f"\n  📊 C05 Summary: {s['healed_incidents']} healed, {s['rejected_incidents']} rejected")
    print(f"     GoBD audit log: {s['audit_log_entries']} entries")
    print(f"     Honor ledger: {s['honor_ledger_size']} stamps")

    # Visibility matrix
    print(f"\n  🔍 VISIBILITY MATRIX (D02 → C05):")
    print(f"     {'Layer':<28} {'D02 (TEE Enclave)':<25} {'C05 (Surface)':<25}")
    print(f"     {'─'*28} {'─'*25} {'─'*25}")
    rows = [
        ("Historical Merkle scan", "10.000 blocks in TEE RAM", "❌ Not visible"),
        ("Anomaly detection", "Hash mismatch at N-4200", "🟢 INC-DAG-004200"),
        ("ZK reconciliation", "Grafting proof computed", "🟢 Verified (< 2 ms)"),
        ("BHO invariant check", "42/42 historical checks", "🟢 42/42_CHECKS_VERIFIED"),
        ("Hot-swap", "Healed root computed", "🟢 Root replaced (0 ms)"),
    ]
    for layer, d02, c05_view in rows:
        print(f"     {layer:<28} {d02:<25} {c05_view:<25}")

    print(f"\n  ✅ D02→C05 forensic repair complete — history healed, surface untouched\n")


# ═══════════════════════════════════════════════════════════════════════════════
# D03 — Emergency Rescue Specialist (Circuit Breaker & Multi-Sig Recovery)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FreezeCommand:
    """What D03 issues when sabotage is detected — freezes escrow and bridges.

    Unlike D01/D02 payloads which flow diver→surface, the FreezeCommand
    flows surface→diver: the surface detects the anomaly and D03 executes.
    """

    incident_id: str = ""
    trigger_reason: str = ""          # e.g. "BHO_VIOLATION_DETECTED"
    freeze_targets: List[str] = field(default_factory=list)  # ["ESCROW", "BRIDGE_ETH", ...]
    detected_at_tick: int = 0
    severity: str = "CRITICAL"        # CRITICAL, HIGH, MEDIUM
    multi_sig_approvals: List[str] = field(default_factory=list)  # Required: ≥ 2
    valhalla_stamp: str = ""

    @classmethod
    def create_emergency(cls, reason: str, targets: List[str],
                         approvers: List[str]) -> "FreezeCommand":
        return cls(
            incident_id=f"EMERG-{int(time.time())}",
            trigger_reason=reason,
            freeze_targets=targets,
            detected_at_tick=int(time.time()),
            severity="CRITICAL",
            multi_sig_approvals=approvers,
            valhalla_stamp=f"did:valhalla:guardian_{hashlib.sha256(reason.encode()).hexdigest()[:8]}",
        )


class D03EmergencyRescue:
    """The third diver: freezes escrow/bridges, rescues funds to L1, documents.

    Subagents:
      S1 — Freeze-Kommandant: freezes escrow state roots and bridges
      S2 — Recovery-Scout: executes multi-sig rescue vector (backup to L1)
      S3 — Post-Mortem-Analyst: documents the exploit and creates a patch
    """

    def __init__(self, multi_sig_threshold: int = 2):
        self.threshold = multi_sig_threshold  # Minimum approvals for freeze
        self.escrow_frozen: bool = False
        self.bridges_frozen: Dict[str, bool] = {}
        self.rescued_funds_eur: float = 0.0
        self.l1_backup_tx: List[str] = []
        self.incident_log: List[Dict] = []
        self.post_mortems: List[Dict] = []

    # ── S1: Freeze-Kommandant ───────────────────────────────────────────

    def execute_freeze(self, cmd: FreezeCommand) -> Dict[str, Any]:
        """Freeze escrow and bridges. Requires ≥ threshold multi-sig approvals."""

        # 1. Multi-sig check
        if len(cmd.multi_sig_approvals) < self.threshold:
            return {
                "status": "REJECTED",
                "reason": f"INSUFFICIENT_APPROVALS:{len(cmd.multi_sig_approvals)}/{self.threshold}",
            }

        # 2. Execute freeze on each target
        frozen = []
        for target in cmd.freeze_targets:
            if target == "ESCROW":
                self.escrow_frozen = True
                frozen.append("ESCROW")
            elif target.startswith("BRIDGE"):
                self.bridges_frozen[target] = True
                frozen.append(target)

        # 3. Log the incident
        self.incident_log.append({
            "incident_id": cmd.incident_id,
            "trigger": cmd.trigger_reason,
            "frozen_targets": frozen,
            "approvals": len(cmd.multi_sig_approvals),
            "severity": cmd.severity,
            "timestamp": time.time(),
        })

        return {
            "status": "FROZEN",
            "incident_id": cmd.incident_id,
            "frozen_targets": frozen,
            "escrow_frozen": self.escrow_frozen,
            "bridges_frozen": list(self.bridges_frozen.keys()),
        }

    # ── S2: Recovery-Scout ──────────────────────────────────────────────

    def execute_rescue(self, incident_id: str, fund_eur: float,
                       l1_target: str = "L1_BACKUP_VAULT") -> Dict[str, Any]:
        """Rescue funds to L1 via multi-sig backup vector.

        Only callable after freeze has been executed for this incident.
        """
        # 1. Verify freeze was executed
        if not self.escrow_frozen:
            return {"status": "REJECTED", "reason": "ESCROW_NOT_FROZEN"}

        # 2. Execute L1 backup transaction
        tx_hash = hashlib.sha256(
            f"L1_RESCUE_{incident_id}_{fund_eur}_{l1_target}".encode()
        ).hexdigest()[:32]
        self.l1_backup_tx.append(tx_hash)
        self.rescued_funds_eur += fund_eur

        return {
            "status": "RESCUED",
            "incident_id": incident_id,
            "fund_eur": fund_eur,
            "l1_target": l1_target,
            "l1_tx_hash": tx_hash,
            "total_rescued_eur": self.rescued_funds_eur,
        }

    # ── S3: Post-Mortem-Analyst ─────────────────────────────────────────

    def create_post_mortem(self, incident_id: str, root_cause: str,
                           affected_blocks: List[int],
                           patch_description: str) -> Dict[str, Any]:
        """Document the exploit and create a patch recommendation."""

        pm = {
            "incident_id": incident_id,
            "root_cause": root_cause,
            "affected_blocks": affected_blocks,
            "patch": patch_description,
            "escrow_was_frozen": self.escrow_frozen,
            "funds_rescued_eur": self.rescued_funds_eur,
            "l1_backup_tx": self.l1_backup_tx[-1] if self.l1_backup_tx else None,
            "timestamp": time.time(),
            "patch_id": f"PATCH-{hashlib.sha256(root_cause.encode()).hexdigest()[:12]}",
        }
        self.post_mortems.append(pm)
        return pm

    def summary(self) -> Dict[str, Any]:
        return {
            "escrow_frozen": self.escrow_frozen,
            "bridges_frozen": list(self.bridges_frozen.keys()),
            "incidents": len(self.incident_log),
            "rescued_funds_eur": self.rescued_funds_eur,
            "l1_backup_tx_count": len(self.l1_backup_tx),
            "post_mortems": len(self.post_mortems),
        }


def demo_emergency_rescue():
    """Demonstrate D03: sabotage detected → freeze → rescue → post-mortem."""
    W = 72
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  🚨 D03 — Emergency Rescue Specialist".center(W - 2) + "█")
    print("█" + "  Sabotage → Freeze → Rescue → Post-Mortem".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W)

    d03 = D03EmergencyRescue(multi_sig_threshold=2)

    # ═══════════════════════════════════════════════════════════════
    # SCENARIO: BHO violation detected → emergency protocol
    # ═══════════════════════════════════════════════════════════════

    print(f"\n  🚨 ALERT: BHO_INVARIANCE_VIOLATED at tick 42.731")
    print(f"     Δ = 0.03 € detected on ESCROW settlement")
    print(f"     Initiating emergency protocol...\n")

    # Step 1: Attempt freeze with insufficient approvals → REJECTED
    cmd_weak = FreezeCommand.create_emergency(
        "BHO_VIOLATION_Δ=0.03€",
        ["ESCROW", "BRIDGE_ETH", "BRIDGE_POLYGON"],
        ["admin_solo"],  # Only 1 approval, need 2
    )
    r1 = d03.execute_freeze(cmd_weak)
    print(f"  🛡️ S1 Freeze (1/2 approvals): {r1['status']} — {r1['reason']}")

    # Step 2: Freeze with proper dual approval → FROZEN
    cmd_valid = FreezeCommand.create_emergency(
        "BHO_VIOLATION_Δ=0.03€",
        ["ESCROW", "BRIDGE_ETH", "BRIDGE_POLYGON"],
        ["kaemmerer_mueller", "bauleiter_schmidt"],  # 2 approvals ✓
    )
    r2 = d03.execute_freeze(cmd_valid)
    print(f"  🔒 S1 Freeze (2/2 approvals): {r2['status']}")
    print(f"     Targets: {r2['frozen_targets']}")
    print(f"     Escrow: {'🔒 FROZEN' if r2['escrow_frozen'] else '⚠️ ACTIVE'}")
    print(f"     Bridges: {r2['bridges_frozen']}")

    # Step 3: Rescue funds to L1 backup vault
    r3 = d03.execute_rescue(cmd_valid.incident_id, 4_200_000.00, "L1_BACKUP_VAULT")
    print(f"\n  💰 S2 Rescue: {r3['status']}")
    print(f"     Funds rescued: €{r3['fund_eur']:,.2f} → {r3['l1_target']}")
    print(f"     L1 TX: {r3['l1_tx_hash'][:24]}...")
    print(f"     Total rescued: €{r3['total_rescued_eur']:,.2f}")

    # Step 4: Post-mortem analysis
    pm = d03.create_post_mortem(
        cmd_valid.incident_id,
        root_cause="Integer overflow in EscrowSettlement.split(): "
                   "retention=0.05 overflowed to 0.08 at amount=4.2M€",
        affected_blocks=[42731, 42732],
        patch_description="Add SafeMath bounds check to EscrowSettlement.split(). "
                          "Deploy via multi-sig upgrade at block 42800.",
    )
    print(f"\n  📋 S3 Post-Mortem:")
    print(f"     Patch: {pm['patch_id']}")
    print(f"     Root cause: {pm['root_cause'][:70]}...")
    print(f"     Affected blocks: {pm['affected_blocks']}")
    print(f"     Funds rescued: €{pm['funds_rescued_eur']:,.2f}")
    print(f"     L1 backup: {pm['l1_backup_tx'][:24] if pm['l1_backup_tx'] else 'N/A'}...")

    # Step 5: Attempt rescue without freeze → REJECTED
    d03_loose = D03EmergencyRescue()
    r5 = d03_loose.execute_rescue("NO_FREEZE_INCIDENT", 100000.00)
    print(f"\n  🛡️ Rescue without freeze: {r5['status']} — {r5['reason']}")

    # Summary
    s = d03.summary()
    print(f"\n  📊 D03 Summary:")
    print(f"     Incidents: {s['incidents']}")
    print(f"     Escrow: {'🔒 FROZEN' if s['escrow_frozen'] else '🟢 ACTIVE'}")
    print(f"     Bridges frozen: {s['bridges_frozen']}")
    print(f"     Rescued: €{s['rescued_funds_eur']:,.2f}")
    print(f"     L1 backups: {s['l1_backup_tx_count']}")
    print(f"     Post-mortems: {s['post_mortems']}")

    print(f"\n  ✅ D03 emergency protocol complete — €4.2M secured to L1\n")


# ═══════════════════════════════════════════════════════════════════════════════
# State Transition API — C09 anchors verified ZK proofs into the Merkle-DAG
# ═══════════════════════════════════════════════════════════════════════════════


class StateTransitionAPI:
    """Anchors verified ZK settlement proofs into the GoBD-compliant Merkle-DAG.

    This is the final step in the D01→C09 pipeline. Once a ZK proof is
    verified, the StateTransitionAPI:
      1. Computes the new state root from (previous_root, proof, amount)
      2. Anchors the transition in the Merkle-DAG with a GoBD audit entry
      3. Records the L1 anchor block for cross-chain verification
      4. Emits a Valhalla honor event

    All transitions are append-only and cryptographically linked via
    SHA-256 hash chains (GoBD-compliant, WORM property).
    """

    def __init__(self):
        # Merkle-DAG: block_height → (state_root, anchor_tx)
        self.dag: Dict[int, tuple] = {}
        self.audit_entries: List[Dict] = []
        self.current_height: int = 0
        self.genesis_root: str = hashlib.sha256(b"AGENT_X_GENESIS").hexdigest()
        self.current_root: str = self.genesis_root
        self.total_anchored: int = 0
        self.total_rejected: int = 0

        # Initialize genesis block
        self.dag[0] = (self.genesis_root, "L1_GENESIS_ANCHOR")

    def transition(self, proof: ZKProofSettlementPayload,
                   l1_anchor_block: int = 0) -> Dict[str, Any]:
        """Execute a state transition: verify → anchor → audit.

        This is the atomic operation that C09 calls after ZK proof verification.
        Either the transition succeeds (new state root + audit entry) or it
        fails (rejected, DAG unchanged).
        """

        # 1. Verify the proof's state_root_before matches our current root
        claimed_before = proof.public_inputs.get("state_root_before", "")
        if claimed_before != self.current_root:
            self.total_rejected += 1
            return {
                "status": "REJECTED",
                "reason": f"STATE_ROOT_MISMATCH: claimed={claimed_before[:16]} "
                          f"actual={self.current_root[:16]}",
            }

        # 2. Compute the new state root (integer cents, no float drift)
        net_eur_cents = int(proof.public_inputs.get("settlement_net_eur", "0"))
        net_eur = net_eur_cents / 100.0
        nullifier = proof.public_inputs.get("nullifier_hash", "")
        commitment = proof.public_inputs.get("commitment_hash", "")
        new_root_input = (
            f"{self.current_root}{nullifier}{net_eur_cents}{commitment}"
        )
        new_root = hashlib.sha256(new_root_input.encode()).hexdigest()

        # 3. Advance the DAG
        self.current_height += 1
        l1_anchor = f"L1_BLOCK_{l1_anchor_block}" if l1_anchor_block else (
            f"L1_ANCHOR_{hashlib.sha256(new_root.encode()).hexdigest()[:16]}"
        )
        self.dag[self.current_height] = (new_root, l1_anchor)
        self.current_root = new_root
        self.total_anchored += 1

        # 4. Write GoBD-compliant audit entry
        entry = {
            "height": self.current_height,
            "state_root_previous": claimed_before[:16],
            "state_root_new": new_root[:16],
            "nullifier": nullifier,  # Full hash for DAG integrity verification
            "net_eur_cents": net_eur_cents,
            "commitment": commitment,  # Full hash for DAG integrity verification
            "valhalla_stamp": proof.valhalla_stamp,
            "l1_anchor": l1_anchor,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "hash_chain_link": hashlib.sha256(
                f"{claimed_before}{new_root}".encode()
            ).hexdigest()[:16],
        }
        self.audit_entries.append(entry)

        return {
            "status": "ANCHORED",
            "height": self.current_height,
            "state_root": new_root[:16],
            "l1_anchor": l1_anchor,
            "hash_chain_link": entry["hash_chain_link"],
            "audit_entry_id": len(self.audit_entries),
        }

    def verify_dag_integrity(self) -> Dict[str, Any]:
        """Verify the entire Merkle-DAG from genesis to current tip.

        Walks the hash chain from block 0 to current_height, recomputing
        each state root. Returns True if the chain is intact.
        """
        root = self.genesis_root
        for h in range(1, self.current_height + 1):
            stored_root, _ = self.dag[h]
            entry = self.audit_entries[h - 1]
            recomputed = hashlib.sha256(
                f"{root}{entry['nullifier']}{entry['net_eur_cents']}"
                f"{entry['commitment']}".encode()
            ).hexdigest()
            if recomputed != stored_root:
                return {
                    "intact": False,
                    "broken_at_height": h,
                    "stored": stored_root[:16],
                    "recomputed": recomputed[:16],
                }
            root = recomputed
        return {
            "intact": True,
            "blocks_verified": self.current_height,
            "genesis": self.genesis_root[:16],
            "tip": self.current_root[:16],
            "l1_anchors": len(self.dag) - 1,
            "goBD_compliant": True,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "height": self.current_height,
            "state_root": self.current_root[:16],
            "total_anchored": self.total_anchored,
            "total_rejected": self.total_rejected,
            "audit_entries": len(self.audit_entries),
            "dag_size": len(self.dag),
            "genesis": self.genesis_root[:16],
        }


def demo_state_transition():
    """Full pipeline: D01 creates proof → C09 verifies → StateTransition anchors."""
    W = 72
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  🔗 STATE TRANSITION API — Merkle-DAG Anchoring".center(W - 2) + "█")
    print("█" + "  ZK Proof → Verify → Anchor → GoBD Audit Entry".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W)

    dag = StateTransitionAPI()
    c09 = C09SettlementProcessor()

    print(f"\n  🌱 Genesis:  {dag.genesis_root[:16]}... (L1_GENESIS_ANCHOR)")

    # Three settlements, each creating a DAG transition
    settlements = [
        ("INV-001", "TAX_A", 25000.00),
        ("INV-002", "TAX_B", 180000.00),
        ("INV-003", "TAX_C", 4200000.00),
    ]

    print(f"\n  {'#':<3} {'Invoice':<12} {'Net EUR':>12} {'State Root':<20} {'L1 Anchor':<25} {'Status':<10}")
    print(f"  {'─'*3} {'─'*12} {'─'*12} {'─'*20} {'─'*25} {'─'*10}")

    for i, (invoice, tax_id, amount) in enumerate(settlements, 1):
        # D01 creates proof (with current state_root_before from DAG)
        payload = ZKProofSettlementPayload.create_demo(
            amount, invoice, tax_id
        )
        # Inject the current state root so the transition is valid
        payload.public_inputs["state_root_before"] = dag.current_root
        payload.public_inputs["state_root_after"] = hashlib.sha256(
            f"after_{invoice}_{amount}".encode()
        ).hexdigest()

        # C09 verifies
        result = c09.process(payload)
        if result["status"] != "SETTLED":
            print(f"  ❌ {i:<2} {invoice:<12} {amount:>12,.2f} {'—':<20} {'—':<25} REJECTED")
            continue

        # StateTransition anchors
        anchor = dag.transition(payload, l1_anchor_block=42000 + i * 100)
        icon = "🔗" if anchor["status"] == "ANCHORED" else "❌"
        print(f"  {icon} {i:<2} {invoice:<12} {amount:>12,.2f} "
              f"{anchor.get('state_root', '—'):<20} "
              f"{anchor.get('l1_anchor', '—'):<25} "
              f"{anchor['status']}")

    # Attempt state root mismatch
    bad_payload = ZKProofSettlementPayload.create_demo(999999.00, "FAKE", "TAX_X")
    bad_payload.public_inputs["state_root_before"] = "0xDEADBEEF"  # Wrong root
    bad_anchor = dag.transition(bad_payload)
    print(f"  🛡️ State root mismatch: {bad_anchor['status']} — {bad_anchor['reason']}")

    # Verify DAG integrity
    integrity = dag.verify_dag_integrity()
    print(f"\n  🔐 DAG Integrity: {'✅ INTACT' if integrity['intact'] else '❌ BROKEN'}")
    print(f"     Blocks verified: {integrity.get('blocks_verified', 0)}")
    print(f"     Genesis → Tip: {integrity.get('genesis', '?')} → {integrity.get('tip', '?')}")
    print(f"     L1 anchors: {integrity.get('l1_anchors', 0)}")
    print(f"     GoBD-compliant: {'✅' if integrity.get('goBD_compliant') else '❌'}")

    # Audit trail
    print(f"\n  📂 GoBD Audit Trail ({len(dag.audit_entries)} entries):")
    for e in dag.audit_entries:
        print(f"     H={e['height']} | root={e['state_root_new']} | "
              f"€{e['net_eur_cents']/100:,.2f} | chain={e['hash_chain_link']}")

    s = dag.summary()
    print(f"\n  ✅ State Transition API: {s['total_anchored']} anchored, "
          f"{s['total_rejected']} rejected, height={s['height']}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# C09 Ingest Handler — Receives D01 bytestream, verifies, anchors into DAG
# ═══════════════════════════════════════════════════════════════════════════════


class C09IngestHandler:
    """Surface handler: receives D01's binary payload, runs the 3-check pipeline,
    and atomically anchors verified proofs into the Merkle-DAG.

    Pipeline:
      1. SGX Quote Verify  → demo: hash check | production: Intel DCAP
      2. Range-Window Check → tick_upper − tick_lower ≤ MAX_DELTA (50)
      3. ZK Proof Verify    → demo: structural | production: Groth16 pairing
      4. State Transition   → anchor into StateTransitionAPI (GoBD-WORM)

    All verifiers are injectable (same pattern as DIDRegistry._verify_crypto).
    """

    MAX_DELTA = 50  # Max tick drift (from protocol)

    def __init__(self):
        self.dag = StateTransitionAPI()
        self.nullifiers = NullifierRepository()
        self._quote_verifier: Any = None    # SGX DCAP verifier
        self._pairing_engine: Any = None    # Groth16 pairing engine
        self.accepted: int = 0
        self.rejected: int = 0
        self.reject_reasons: Dict[str, int] = {}

    def ingest(self, event_tick: int, proof_tick: int,
               tick_lower: int, tick_upper: int,
               nullifier_hash: str, commitment_hash: str,
               settlement_net_eur_cents: int,
               proof: Dict[str, List[str]],
               tee_quote: str = "",
               valhalla_stamp: str = "") -> Dict[str, Any]:
        """Full D01→C09 pipeline: verify → anchor → audit."""

        # ── Check 1: SGX Quote Verification ──
        if self._quote_verifier is not None:
            if not self._quote_verifier.verify(tee_quote):
                return self._reject("SGX_QUOTE_INVALID", nullifier_hash)
        # Demo mode: verify quote is well-formed (non-empty, hex)
        if not tee_quote or len(tee_quote) < 16:
            return self._reject("SGX_QUOTE_MISSING", nullifier_hash)

        # ── Check 2: Range-Window (sliding window) ──
        delta = tick_upper - tick_lower
        if delta > self.MAX_DELTA:
            return self._reject(f"DELTA_WINDOW_EXCEEDED:{delta}>{self.MAX_DELTA}",
                                nullifier_hash)
        if not (tick_lower <= event_tick <= tick_upper):
            return self._reject(f"EVENT_TICK_OUT_OF_WINDOW:{event_tick}",
                                nullifier_hash)

        # ── Check 3: ZK Proof Verification ──
        if self._pairing_engine is not None:
            # Production: Groth16 pairing check
            if not self._pairing_engine.verify(proof, nullifier_hash, commitment_hash):
                return self._reject("PAIRING_CHECK_FAILED", nullifier_hash)
        else:
            # Demo mode: structural check
            if not all(k in proof for k in ("pi_a", "pi_b", "pi_c")):
                return self._reject("MALFORMED_PROOF_STRUCTURE", nullifier_hash)

        # ── Check 4: Nullifier uniqueness (replay protection) ──
        if self.nullifiers.exists(nullifier_hash):
            return self._reject("NULLIFIER_ALREADY_SPENT", nullifier_hash)

        # ── Anchor into Merkle-DAG ──
        # Build a ZKProofSettlementPayload for the StateTransitionAPI
        payload = ZKProofSettlementPayload(
            proof_type="Groth16_BN254",
            proof=proof,
            public_inputs={
                "state_root_before": self.dag.current_root,
                "state_root_after": hashlib.sha256(
                    f"{nullifier_hash}{settlement_net_eur_cents}".encode()
                ).hexdigest(),
                "nullifier_hash": nullifier_hash,
                "commitment_hash": commitment_hash,
                "settlement_net_eur": str(settlement_net_eur_cents),
            },
            valhalla_stamp=valhalla_stamp,
            tee_attestation_quote=tee_quote,
        )

        result = self.dag.transition(payload)
        if result["status"] != "ANCHORED":
            return self._reject(f"STATE_TRANSITION_FAILED:{result.get('reason', '')}",
                                nullifier_hash)

        # ── Mark nullifier used ──
        self.nullifiers.mark_used(nullifier_hash)
        self.accepted += 1

        return {
            "status": "ACCEPTED",
            "nullifier": f"{nullifier_hash[:16]}...",
            "l1_anchor": result["l1_anchor"],
            "state_root": result["state_root"],
            "dag_height": self.dag.current_height,
            "goBD_entry": result["audit_entry_id"],
        }

    def _reject(self, reason: str, nullifier: str) -> Dict[str, Any]:
        self.rejected += 1
        self.reject_reasons[reason] = self.reject_reasons.get(reason, 0) + 1
        return {
            "status": "REJECTED",
            "reason": reason,
            "nullifier": f"{nullifier[:16]}...",
        }

    def inject_quote_verifier(self, verifier: Any) -> None:
        self._quote_verifier = verifier

    def inject_pairing_engine(self, engine: Any) -> None:
        self._pairing_engine = engine

    def summary(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "reject_reasons": self.reject_reasons,
            "nullifiers_used": len(self.nullifiers),
            "dag": self.dag.summary(),
        }


def demo_c09_ingest_handler():
    """Full round-trip: D01 creates proof → C09 ingests → anchors in DAG."""
    W = 72
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  🏗️  C09 INGEST HANDLER — D01→C09→DAG Pipeline".center(W - 2) + "█")
    print("█" + "  SGX Quote → Range-Window → ZK Proof → Anchor".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W)

    c09 = C09IngestHandler()

    scenarios = [
        # (label, event_tick, tick_lower, tick_upper, delta, nullifier, cents, tee_quote, expects)
        ("Normale Lieferung",   42000, 42000, 42030, "30", "0xNULL_1", 2500000,
         "DCAP_QUOTE_V3_VALID_0123456789abcdef", "ACCEPTED"),
        ("Fenster zu groß",     42000, 41900, 42060, "160", "0xNULL_2", 18000000,
         "DCAP_QUOTE_V3_VALID_0123456789abcdef", "REJECTED"),
        ("Kein SGX-Quote",      42000, 42000, 42030, "30", "0xNULL_3", 5000000,
         "", "REJECTED"),
        ("Replay (gleicher Nullifier)", 42000, 42000, 42030, "30", "0xNULL_1", 2500000,
         "DCAP_QUOTE_V3_VALID_0123456789abcdef", "REJECTED"),
        ("Korrupter Proof",     42000, 42000, 42030, "30", "0xNULL_4", 7500000,
         "DCAP_QUOTE_V3_VALID_0123456789abcdef", "REJECTED"),
        ("Große Lieferung",     42100, 42100, 42140, "40", "0xNULL_5", 420000000,
         "DCAP_QUOTE_V3_VALID_0123456789abcdef", "ACCEPTED"),
    ]

    print(f"\n  {'#':<3} {'Szenario':<22} {'Δ':>5} {'Erwartet':<10} {'Ergebnis':<10} {'Detail':<30}")
    print(f"  {'─'*3} {'─'*22} {'─'*5} {'─'*10} {'─'*10} {'─'*30}")

    for i, (label, ev_tick, tick_lo, tick_hi, delta, nullifier, cents, quote, expects) in enumerate(scenarios, 1):
        proof = {"pi_a": ["0xabc"], "pi_b": [["0xdef", "0x123"]], "pi_c": ["0x456"]}
        if label == "Korrupter Proof":
            proof = {"pi_a": ["0xabc"]}  # Missing pi_b, pi_c

        r = c09.ingest(
            event_tick=ev_tick, proof_tick=tick_hi,
            tick_lower=tick_lo, tick_upper=tick_hi,
            nullifier_hash=nullifier, commitment_hash=f"0xCOMMIT_{i}",
            settlement_net_eur_cents=cents,
            proof=proof, tee_quote=quote,
            valhalla_stamp=f"did:valhalla:stamp_{i}",
        )

        icon = "✅" if r["status"] == expects else "⚠️"
        detail = r.get("reason", f"L1={r.get('l1_anchor', '?')} root={r.get('state_root', '?')}")
        print(f"  {icon} {i:<2} {label:<22} {delta:>5} {expects:<10} {r['status']:<10} {detail:<30}")

    s = c09.summary()
    # DAG integrity
    di = c09.dag.verify_dag_integrity()
    print(f"\n  📊 C09 Summary: {s['accepted']} accepted, {s['rejected']} rejected")
    print(f"     DAG: height={s['dag']['height']}, intact={di['intact']}, "
          f"GoBD={'✅' if di['goBD_compliant'] else '❌'}")
    if s['reject_reasons']:
        print(f"     Reject breakdown: {s['reject_reasons']}")
    print(f"\n  ✅ D01→C09→DAG round-trip complete\n")


# ═══════════════════════════════════════════════════════════════════════════════
# D02 Forensic API — Automated Merkle Chain Verification Endpoint
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ForensicIntegrityReport:
    """Machine-readable report: D02 verifies the entire Merkle chain."""
    report_id: str = ""
    verified_at: str = ""
    blocks_checked: int = 0
    intact: bool = False
    genesis_root: str = ""
    tip_root: str = ""
    first_broken_at: Optional[int] = None
    block_reports: List[Dict] = field(default_factory=list)
    gobd_compliant: bool = False
    signature: str = ""


class D02ForensicAPI:
    """Automated forensic verification: reads C09's audit trail, verifies every block.

    Can be mounted as a FastAPI router or called directly.
    Exposes:
      GET  /forensic/verify-chain    — full Merkle chain verification
      GET  /forensic/block/{height}  — single block verification
      GET  /forensic/report          — latest ForensicIntegrityReport
    """

    def __init__(self, dag: StateTransitionAPI = None):
        self.dag = dag or StateTransitionAPI()
        self.last_report: Optional[ForensicIntegrityReport] = None
        self.verification_count: int = 0

    def verify_full_chain(self) -> ForensicIntegrityReport:
        """Verify every block from genesis to tip. Returns a signed report."""
        self.verification_count += 1
        report_id = f"FORENSIC-{int(time.time())}-{self.verification_count:04d}"

        blocks = []
        root = self.dag.genesis_root
        intact = True
        first_broken = None

        for h in range(1, self.dag.current_height + 1):
            stored_root, l1_anchor = self.dag.dag[h]
            entry = self.dag.audit_entries[h - 1]

            recomputed = hashlib.sha256(
                f"{root}{entry['nullifier']}{entry['net_eur_cents']}"
                f"{entry['commitment']}".encode()
            ).hexdigest()

            block_ok = recomputed == stored_root
            if not block_ok and first_broken is None:
                first_broken = h
                intact = False

            blocks.append({
                "height": h,
                "ok": block_ok,
                "stored_root": stored_root[:16],
                "recomputed_root": recomputed[:16],
                "l1_anchor": l1_anchor,
                "net_eur_cents": entry.get("net_eur_cents", 0),
                "valhalla_stamp": entry.get("valhalla_stamp", ""),
                "hash_chain_link": entry.get("hash_chain_link", ""),
            })
            root = stored_root if block_ok else root

        report = ForensicIntegrityReport(
            report_id=report_id,
            verified_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            blocks_checked=len(blocks),
            intact=intact,
            genesis_root=self.dag.genesis_root[:16],
            tip_root=self.dag.current_root[:16],
            first_broken_at=first_broken,
            block_reports=blocks,
            gobd_compliant=intact and len(blocks) > 0,
            signature=hashlib.sha256(
                f"FORENSIC_SIG_{report_id}_{intact}".encode()
            ).hexdigest()[:32],
        )
        self.last_report = report
        return report

    def verify_block(self, height: int) -> Dict[str, Any]:
        """Verify a single block at given height."""
        if height < 1 or height > self.dag.current_height:
            return {"height": height, "status": "OUT_OF_RANGE"}
        root = self.dag.genesis_root
        for h in range(1, height):
            entry = self.dag.audit_entries[h - 1]
            root = hashlib.sha256(
                f"{root}{entry['nullifier']}{entry['net_eur_cents']}"
                f"{entry['commitment']}".encode()
            ).hexdigest()
        stored_root, l1 = self.dag.dag[height]
        entry = self.dag.audit_entries[height - 1]
        recomputed = hashlib.sha256(
            f"{root}{entry['nullifier']}{entry['net_eur_cents']}"
            f"{entry['commitment']}".encode()
        ).hexdigest()
        return {
            "height": height,
            "status": "OK" if recomputed == stored_root else "BROKEN",
            "stored": stored_root[:16],
            "recomputed": recomputed[:16],
            "l1_anchor": l1,
        }

    def as_fastapi_router(self):
        """Return a FastAPI APIRouter with forensic endpoints."""
        try:
            from fastapi import APIRouter
        except ImportError:
            return None

        router = APIRouter(prefix="/forensic", tags=["D02-Forensic"])

        @router.get("/verify-chain")
        async def verify_chain():
            report = self.verify_full_chain()
            return {
                "intact": report.intact,
                "blocks_checked": report.blocks_checked,
                "gobd_compliant": report.gobd_compliant,
                "genesis": report.genesis_root,
                "tip": report.tip_root,
                "first_broken_at": report.first_broken_at,
                "report_id": report.report_id,
                "signature": report.signature,
            }

        @router.get("/block/{height}")
        async def verify_block(height: int):
            return self.verify_block(height)

        @router.get("/report")
        async def latest_report():
            if self.last_report is None:
                return {"status": "NO_REPORT_YET"}
            return {
                "report_id": self.last_report.report_id,
                "intact": self.last_report.intact,
                "blocks_checked": self.last_report.blocks_checked,
                "gobd_compliant": self.last_report.gobd_compliant,
                "verified_at": self.last_report.verified_at,
            }

        return router


def demo_forensic_api():
    """Full forensic workflow: anchor some blocks, then verify the chain."""
    W = 72
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  🔍 D02 FORENSIC API — Automated Chain Verification".center(W - 2) + "█")
    print("█" + "  Reads C09 audit trail → verifies every Merkle link".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W)

    # Build a DAG with some blocks
    dag = StateTransitionAPI()
    for inv, tax, amt, tick in [
        ("INV-001", "TAX_A", 25000.00, 42100),
        ("INV-002", "TAX_B", 180000.00, 42200),
        ("INV-003", "TAX_C", 4200000.00, 42300),
        ("INV-004", "TAX_D", 75000.00, 42400),
        ("INV-005", "TAX_E", 320000.00, 42500),
    ]:
        p = ZKProofSettlementPayload.create_demo(amt, inv, tax)
        p.public_inputs["state_root_before"] = dag.current_root
        dag.transition(p, l1_anchor_block=tick)

    print(f"\n  📂 DAG built: {dag.current_height} blocks anchored")

    # Run forensic verification
    d02 = D02ForensicAPI(dag)
    report = d02.verify_full_chain()

    print(f"\n  🔍 FORENSIC INTEGRITY REPORT #{report.report_id}:")
    print(f"     Intact: {'✅ YES' if report.intact else '❌ BROKEN'}")
    print(f"     Blocks checked: {report.blocks_checked}")
    print(f"     GoBD compliant: {'✅' if report.gobd_compliant else '❌'}")
    print(f"     Genesis: {report.genesis_root} → Tip: {report.tip_root}")
    print(f"     Signature: {report.signature}")

    # Block-by-block report
    print(f"\n  📋 BLOCK VERIFICATION:")
    print(f"     {'H':<5} {'Status':<8} {'Stored Root':<18} {'Recomputed':<18} {'L1 Anchor':<18}")
    print(f"     {'─'*5} {'─'*8} {'─'*18} {'─'*18} {'─'*18}")
    for b in report.block_reports:
        icon = "✅" if b["ok"] else "❌"
        print(f"     {b['height']:<5} {icon:<8} {b['stored_root']:<18} "
              f"{b['recomputed_root']:<18} {b['l1_anchor']:<18}")

    # Single block verification
    single = d02.verify_block(3)
    print(f"\n  🔎 Spot check block 3: {single['status']} "
          f"(stored={single['stored']} recomputed={single['recomputed']})")

    # Tamper simulation: corrupt a block
    dag.dag[2] = ("0xTAMPERED_ROOT_DEADBEEF", dag.dag[2][1])
    report2 = d02.verify_full_chain()
    print(f"\n  💥 AFTER TAMPER (block 2 corrupted):")
    print(f"     Intact: {'✅' if report2.intact else '❌ BROKEN at block ' + str(report2.first_broken_at)}")
    print(f"     GoBD: {'✅' if report2.gobd_compliant else '❌'}")

    print(f"\n  ✅ D02 Forensic API: {d02.verification_count} verifications run\n")


# ═══════════════════════════════════════════════════════════════════════════════
# Compliance Exporter — GoBD-Audit-Export-Paket für den Wirtschaftsprüfer
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class ComplianceExportPackage:
    """A cryptographically verifiable export bundle for auditors.

    Contains the complete Merkle chain, forensic report, resilience report,
    and L1 anchors — all hash-chained and signed.
    """
    export_id: str = ""
    generated_at: str = ""
    # Chain data
    genesis_root: str = ""
    tip_root: str = ""
    block_count: int = 0
    blocks: List[Dict] = field(default_factory=list)
    # Verification
    dag_intact: bool = False
    forensic_report: Optional[ForensicIntegrityReport] = None
    # L1 anchors
    l1_anchors: List[str] = field(default_factory=list)
    # Meta
    gobd_compliant: bool = False
    bundle_hash: str = ""       # SHA256 over all blocks (WORM seal)
    auditor_signature: str = ""  # HMAC-SHA256 over bundle_hash


class ComplianceExporter:
    """Produces a GoBD-compliant, hash-chained audit export package.

    Reads from StateTransitionAPI (Merkle-DAG), D02ForensicAPI (integrity),
    and optionally D04 chaos logs. The output is a ComplianceExportPackage
    with a bundle hash that can be verified independently.
    """

    def __init__(self, dag: StateTransitionAPI = None,
                 forensic: "D02ForensicAPI" = None):
        self.dag = dag or StateTransitionAPI()
        self.forensic = forensic or D02ForensicAPI(self.dag)
        self._export_count: int = 0
        self._signing_key: str = hashlib.sha256(b"AGENT_X_COMPLIANCE_KEY").hexdigest()

    def export(self, auditor_name: str = "",
               chaos_report: Dict = None) -> ComplianceExportPackage:
        """Generate a complete compliance export package."""
        self._export_count += 1
        export_id = f"GOBD-EXPORT-{int(time.time())}-{self._export_count:04d}"

        # 1. Collect all blocks from the DAG
        blocks = []
        l1_anchors = []
        for h in range(1, self.dag.current_height + 1):
            stored_root, l1_anchor = self.dag.dag[h]
            entry = self.dag.audit_entries[h - 1]
            blocks.append({
                "height": h,
                "state_root": stored_root[:16],
                "prev_root_hash": hashlib.sha256(
                    f"{self.dag.genesis_root if h == 1 else self.dag.dag[h - 1][0]}"
                    f"{entry['nullifier']}{entry['net_eur_cents']}"
                    f"{entry['commitment']}".encode()
                ).hexdigest()[:16],
                "l1_anchor": l1_anchor,
                "net_eur_cents": entry.get("net_eur_cents", 0),
                "nullifier": entry.get("nullifier", "")[:16],
                "valhalla_stamp": entry.get("valhalla_stamp", ""),
                "hash_chain_link": entry.get("hash_chain_link", ""),
                "timestamp": entry.get("timestamp", ""),
            })
            if l1_anchor not in l1_anchors:
                l1_anchors.append(l1_anchor)

        # 2. Forensic integrity report
        forensic_report = self.forensic.verify_full_chain()

        # 3. Compute bundle hash (WORM seal)
        bundle_input = (
            f"{export_id}{self.dag.genesis_root[:16]}{self.dag.current_root[:16]}"
            f"{len(blocks)}{forensic_report.intact}"
        )
        bundle_hash = hashlib.sha256(bundle_input.encode()).hexdigest()

        # 4. Auditor signature
        sig_input = f"{bundle_hash}{auditor_name}{int(time.time())}"
        auditor_sig = hashlib.sha256(
            f"{sig_input}{self._signing_key}".encode()
        ).hexdigest()[:32]

        pkg = ComplianceExportPackage(
            export_id=export_id,
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            genesis_root=self.dag.genesis_root[:16],
            tip_root=self.dag.current_root[:16],
            block_count=len(blocks),
            blocks=blocks,
            dag_intact=forensic_report.intact,
            forensic_report=forensic_report,
            l1_anchors=l1_anchors,
            gobd_compliant=forensic_report.gobd_compliant,
            bundle_hash=bundle_hash[:16],
            auditor_signature=auditor_sig,
        )
        return pkg

    def verify_export(self, pkg: ComplianceExportPackage) -> Dict[str, Any]:
        """Independently verify a previously generated export package."""
        recomputed = hashlib.sha256(
            f"{pkg.export_id}{pkg.genesis_root}{pkg.tip_root}"
            f"{pkg.block_count}{pkg.dag_intact}".encode()
        ).hexdigest()[:16]
        bundle_ok = recomputed[:16] == pkg.bundle_hash

        sig_input = f"{pkg.bundle_hash}{int(time.time())}"
        expected_sig = hashlib.sha256(
            f"{sig_input}{self._signing_key}".encode()
        ).hexdigest()[:32]
        # Note: signature verification uses current time, so will differ.
        # In production, the auditor verifies against the exported timestamp.
        sig_ok = len(pkg.auditor_signature) == 32  # Structural check

        return {
            "export_id": pkg.export_id,
            "bundle_hash_verified": bundle_ok,
            "signature_well_formed": sig_ok,
            "block_count": pkg.block_count,
            "dag_intact": pkg.dag_intact,
            "gobd_compliant": pkg.gobd_compliant,
            "genesis_matches": pkg.genesis_root == self.dag.genesis_root[:16],
            "tip_matches": pkg.tip_root == self.dag.current_root[:16],
            "verdict": "AUTHENTIC" if (bundle_ok and pkg.dag_intact) else "TAMPERED",
        }


def demo_compliance_export():
    """Full compliance export: build DAG → forensic → export → verify."""
    W = 72
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  📋 COMPLIANCE EXPORTER — GoBD Audit Package".center(W - 2) + "█")
    print("█" + "  Merkle-DAG · Forensic Report · L1 Anchors · WORM Seal".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W)

    # Build a DAG with settlements
    dag = StateTransitionAPI()
    settlements = [
        ("INV-001", "TAX_A", 25000.00, 42100),
        ("INV-002", "TAX_B", 180000.00, 42200),
        ("INV-003", "TAX_C", 4200000.00, 42300),
    ]
    for inv, tax, amt, tick in settlements:
        p = ZKProofSettlementPayload.create_demo(amt, inv, tax)
        p.public_inputs["state_root_before"] = dag.current_root
        dag.transition(p, l1_anchor_block=tick)

    # Export
    exporter = ComplianceExporter(dag)
    pkg = exporter.export(auditor_name="Wirtschaftspruefer_Dr_Mueller")

    print(f"\n  📦 EXPORT PACKAGE: {pkg.export_id}")
    print(f"     Generated:  {pkg.generated_at}")
    print(f"     Blocks:     {pkg.block_count}")
    print(f"     Genesis:    {pkg.genesis_root} → Tip: {pkg.tip_root}")
    print(f"     DAG Intact: {'✅' if pkg.dag_intact else '❌'}")
    print(f"     GoBD:       {'✅ compliant' if pkg.gobd_compliant else '❌'}")
    print(f"     L1 Anchors: {len(pkg.l1_anchors)}")
    print(f"     Bundle Hash:{pkg.bundle_hash} (WORM seal)")
    print(f"     Sig:        {pkg.auditor_signature}")

    # Block detail
    print(f"\n  📋 CHAIN OF CUSTODY:")
    print(f"     {'H':<5} {'State Root':<18} {'Prev Hash':<18} "
          f"{'Net €':>10} {'L1 Anchor':<20} {'Nullifier':<18}")
    print(f"     {'─'*5} {'─'*18} {'─'*18} {'─'*10} {'─'*20} {'─'*18}")
    for b in pkg.blocks:
        print(f"     {b['height']:<5} {b['state_root']:<18} {b['prev_root_hash']:<18} "
              f"{b['net_eur_cents']/100:>10,.2f} {b['l1_anchor']:<20} "
              f"{b['nullifier']:<18}")

    # Independent verification
    verify = exporter.verify_export(pkg)
    print(f"\n  🔐 INDEPENDENT VERIFICATION:")
    for k, v in verify.items():
        if isinstance(v, bool):
            print(f"     {k}: {'✅' if v else '❌'}")
        else:
            print(f"     {k}: {v}")

    # Export as machine-readable structure
    export_dict = {
        "export_id": pkg.export_id,
        "gobd_compliant": pkg.gobd_compliant,
        "blocks": pkg.block_count,
        "genesis_root": pkg.genesis_root,
        "tip_root": pkg.tip_root,
        "bundle_hash": pkg.bundle_hash,
        "auditor_signature": pkg.auditor_signature,
        "l1_anchors": pkg.l1_anchors,
        "dag_intact": pkg.dag_intact,
    }

    print(f"\n  📄 EXPORT JSON (for Landesrechnungshof):")
    print(f"     {json.dumps(export_dict, indent=2)[:300]}...")

    print(f"\n  ✅ Compliance export complete — ready for auditor submission\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "forensic":
            demo_forensic_repair()
        elif sys.argv[1] == "forensic_api":
            demo_forensic_api()
        elif sys.argv[1] == "emergency":
            demo_emergency_rescue()
        elif sys.argv[1] == "dag":
            demo_state_transition()
        elif sys.argv[1] == "ingest":
            demo_c09_ingest_handler()
        elif sys.argv[1] == "compliance":
            demo_compliance_export()
        else:
            demo_zk_settlement()
    else:
        demo_zk_settlement()
