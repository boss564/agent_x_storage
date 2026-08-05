"""
Subagent: PoPWBonusAuditor — PoPW Certificate Integrity Verification.

Verifies that Proof-of-Physical-Work certificates cited in a bid (X84)
actually exist on-chain and in the DKG, with correct metrics and timestamps.

Checks:
  1. DKG existence — does the cited PoPW node exist in the graph?
  2. Temporal consistency — no future-dated events
  3. Metric accuracy — claimed vs. actual on-time/delivery/waste percentages
  4. Bonus calculation — overclaiming detection (claimed > calculated)
  5. Duplicate usage — same proof across multiple bids

Usage:
    auditor = PoPWBonusAuditor()
    result = auditor.audit_popw_bonus(tender_id, popw_citations, claimed_bonus_pct)
    # result["status"]: AUDIT_PASSED / AUDIT_WARNING / AUDIT_FAILED
"""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("PoPWBonusAuditor")


class PoPWBonusAuditor:
    """Cryptographic integrity check for PoPW quality bonus certificates."""

    # Mock DKG records for testing (production: Neo4j GraphRAG query)
    _MOCK_DKG: dict[str, dict] = {
        "0x1c7b90a2": {
            "node_id": "0x1c7b90a2",
            "owner_did": "did:peaq:0xContractor42",
            "project_ref": "PROJ-2025-001",
            "metrics": {"termintreue": 96.8, "verschnitt": 5.6, "maengelfrei": 100.0},
            "timestamp": "2026-06-15T10:00:00Z",
            "chain": "peaq",
            "tx_hash": "0xpeaq-1c7b90a2b5e4f3...",
            "zk_proof_hash": "0xa1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e",
        },
        "0x9f8e7d6c": {
            "node_id": "0x9f8e7d6c",
            "owner_did": "did:peaq:0xContractor42",
            "project_ref": "PROJ-2025-003",
            "metrics": {"termintreue": 94.2, "verschnitt": 4.8, "maengelfrei": 98.5},
            "timestamp": "2026-07-20T14:30:00Z",
            "chain": "gnosis",
            "tx_hash": "0xgnosis-9f8e7d6c...",
            "zk_proof_hash": "0xf1e2d3c4b5a697887766554433221100abcdef0123456789abcdef0123456789",
        },
        "0xabe54321": {
            "node_id": "0xabe54321",
            "owner_did": "did:peaq:0xOtherContractor",
            "project_ref": "PROJ-2024-012",
            "metrics": {"termintreue": 88.0, "verschnitt": 7.2, "maengelfrei": 95.0},
            "timestamp": "2025-12-01T08:00:00Z",
            "chain": "peaq",
            "tx_hash": "0xpeaq-abe54321...",
            "zk_proof_hash": "0x00a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0",
        },
    }

    def __init__(self, dkg_adapter: Any = None, chain_adapter: Any = None):
        self.dkg = dkg_adapter
        self.chain = chain_adapter
        self._seen_hashes: dict[str, list[str]] = defaultdict(list)  # hash → tender_ids

    # ============================================================
    # Main audit
    # ============================================================

    def audit_popw_bonus(self, tender_id: str,
                         popw_citations: list[dict[str, Any]],
                         claimed_bonus_percent: float,
                         bidder_did: str = "") -> dict[str, Any]:
        """Verify all cited PoPW certificates and recalculate bonus.

        Args:
            tender_id: ID of the tender
            popw_citations: List of cited PoPW certificates from the bid
            claimed_bonus_percent: Bonus percentage claimed by the bidder
            bidder_did: DID of the bidder (for ownership verification)
        """

        logger.info(f"PoPW audit for {tender_id}: {len(popw_citations)} citations, "
                     f"claimed bonus={claimed_bonus_percent}%, did={bidder_did[:30]}...")

        results: dict[str, Any] = {
            "tender_id": tender_id,
            "bidder_did": bidder_did,
            "claimed_bonus_percent": claimed_bonus_percent,
            "verified_bonus_percent": 0.0,
            "bonus_deviation_percent": 0.0,
            "status": "AUDIT_PASSED",
            "findings": [],
            "citations_checked": 0,
            "citations_valid": 0,
            "citations_invalid": 0,
            "zk_proofs_verified": 0,
            "zk_proofs_invalid": 0,
            "invalid_citations": [],
        }

        if not popw_citations:
            results["status"] = "AUDIT_FAILED"
            results["findings"].append("Keine PoPW-Citations im Angebot enthalten.")
            return results

        valid_citations = []
        for citation in popw_citations:
            results["citations_checked"] += 1
            cid = citation.get("hash") or citation.get("proof_id") or ""

            # Check 1: DKG existence
            dkg_record = self._fetch_dkg_record(cid)
            if not dkg_record:
                results["citations_invalid"] += 1
                results["invalid_citations"].append({
                    "citation_hash": cid[:20] + "...",
                    "reason": "Knoten nicht im DKG / on-chain auffindbar",
                })
                continue

            # Check 2: DID ownership match
            if bidder_did and not self._verify_did_match(bidder_did, dkg_record):
                results["citations_invalid"] += 1
                results["invalid_citations"].append({
                    "citation_hash": cid[:20] + "...",
                    "reason": f"DID-Inhaber ({dkg_record.get('owner_did', '?')[:30]}...) ≠ Bieter ({bidder_did[:30]}...)",
                })
                continue

            # Check 3: Temporal consistency
            if not self._check_temporal_consistency(dkg_record):
                results["citations_invalid"] += 1
                results["invalid_citations"].append({
                    "citation_hash": cid[:20] + "...",
                    "reason": "PoPW-Event liegt in der Zukunft",
                    "event_timestamp": dkg_record.get("timestamp"),
                })
                continue

            # Check 4: ZK-Proof on-chain verification
            zk_proof = citation.get("zk_proof")
            if zk_proof:
                if self._verify_zk_proof(zk_proof, dkg_record):
                    results["zk_proofs_verified"] += 1
                else:
                    results["zk_proofs_invalid"] += 1
                    results["citations_invalid"] += 1
                    results["invalid_citations"].append({
                        "citation_hash": cid[:20] + "...",
                        "reason": "ZK-Proof on-chain nicht verifizierbar",
                    })
                    continue
            else:
                results["findings"].append(
                    f"Kein ZK-Proof für Citation {cid[:10]}... angegeben.")

            # Check 5: Metric accuracy
            claimed_metrics = citation.get("metrics", {})
            if claimed_metrics and not self._compare_metrics(claimed_metrics,
                                                             dkg_record.get("metrics", {})):
                results["citations_invalid"] += 1
                results["invalid_citations"].append({
                    "citation_hash": cid[:20] + "...",
                    "reason": "Kennzahlen weichen > 0.5% von DKG-Daten ab",
                    "claimed": claimed_metrics,
                    "actual": dkg_record.get("metrics", {}),
                })
                continue

            # Check 6: Duplicate usage
            dup = self._check_duplicate(cid, tender_id)
            if dup:
                results["citations_invalid"] += 1
                results["invalid_citations"].append({
                    "citation_hash": cid[:20] + "...",
                    "reason": f"PoPW-Proof bereits in Tender {dup} verwendet",
                })
                continue

            results["citations_valid"] += 1
            valid_citations.append({**citation, "dkg_record": dkg_record})
            self._seen_hashes[cid].append(tender_id)

        # Calculate verified bonus
        if valid_citations:
            verified = self._calculate_verified_bonus(valid_citations)
            results["verified_bonus_percent"] = verified
            results["bonus_deviation_percent"] = round(
                abs(claimed_bonus_percent - verified), 1)
        else:
            results["verified_bonus_percent"] = 0.0
            results["bonus_deviation_percent"] = 100.0

        # Verdict
        if results["citations_invalid"] > 0:
            results["status"] = "AUDIT_FAILED"
            results["findings"].append(
                f"{results['citations_invalid']}/{results['citations_checked']} "
                f"Citations ungültig.")
        elif results["bonus_deviation_percent"] > 1.0:
            results["status"] = "AUDIT_WARNING"
            results["findings"].append(
                f"Bonuspunkte weichen um {results['bonus_deviation_percent']}% ab "
                f"(claimed={claimed_bonus_percent}%, verified={verified}%).")
        else:
            results["status"] = "AUDIT_PASSED"
            results["findings"].append(
                f"Alle {results['citations_valid']} PoPW-Citations valide. "
                f"Bonus korrekt: {claimed_bonus_percent}%.")

        logger.info(f"PoPW audit done: {results['status']} "
                     f"(valid={results['citations_valid']}, "
                     f"bonus Δ={results['bonus_deviation_percent']}%)")
        return results

    # ============================================================
    # Check implementations
    # ============================================================

    def _fetch_dkg_record(self, citation_hash: str) -> dict | None:
        """Query DKG (Neo4j) or chain for the PoPW node."""
        if self.dkg:
            try:
                return self.dkg.query_node(citation_hash)
            except Exception:
                pass
        # Mock fallback — production: Cypher MATCH on Neo4j
        return self._MOCK_DKG.get(citation_hash[:10])

    @staticmethod
    def _verify_did_match(bidder_did: str, dkg_record: dict) -> bool:
        """Check that the PoPW certificate owner DID matches the bidder DID."""
        owner_did = dkg_record.get("owner_did", "")
        return owner_did == bidder_did

    @staticmethod
    def _check_temporal_consistency(dkg_record: dict) -> bool:
        """Event must not be in the future."""
        ts = dkg_record.get("timestamp", "")
        if not ts:
            return False
        try:
            event_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return event_dt <= datetime.now(timezone.utc)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _compare_metrics(claimed: dict, actual: dict, tolerance: float = 0.5) -> bool:
        """Check claimed metrics match actual DKG data within tolerance (%)."""
        for key, claimed_value in claimed.items():
            actual_value = actual.get(key)
            if actual_value is None:
                return False
            if abs(float(claimed_value) - float(actual_value)) > tolerance:
                return False
        return True

    @staticmethod
    def _verify_zk_proof(zk_proof: dict, dkg_record: dict) -> bool:
        """Verify ZK-Proof on-chain. Mock: check proof_hash matches DKG record."""
        proof_hash = zk_proof.get("proof_hash", "")
        if not proof_hash:
            return False
        return proof_hash == dkg_record.get("zk_proof_hash", "")

    def _check_duplicate(self, citation_hash: str, tender_id: str) -> str | None:
        """Detect if the same PoPW proof was used in another tender."""
        previous = self._seen_hashes.get(citation_hash, [])
        if previous:
            return previous[0]  # Return the first tender_id that used this proof
        return None

    def _calculate_verified_bonus(self, valid_citations: list[dict]) -> float:
        """Recalculate PoPW bonus from verified DKG metrics."""
        total_termintreue = 0.0
        total_verschnitt = 0.0
        n = len(valid_citations)

        for c in valid_citations:
            m = c.get("dkg_record", {}).get("metrics", c.get("metrics", {}))
            total_termintreue += float(m.get("termintreue", 0))
            total_verschnitt += float(m.get("verschnitt", 0))

        if n == 0:
            return 0.0

        avg_termintreue = total_termintreue / n
        avg_verschnitt = total_verschnitt / n

        # PoPW bonus formula: termintreue (max +4%) + verschnitt bonus (max +2%)
        # Bonus capped at 10% (VOB/A §16d limits total deviation)
        bonus = min(10.0,
                    (avg_termintreue / 100.0 * 4.0) +
                    (1.0 - avg_verschnitt / 100.0) * 2.0)
        return round(bonus, 1)
