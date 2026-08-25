"""RadarThreatStoreAdapter — data layer for SwarmSignatureDatabase.

No decision logic. BLOCKED/cause rules live in SQL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from agents_b2g.defense.swarm_defense_orchestrator import JSONLogger, _safe_call
from agents_b2g.defense.threat_engine.pseudonym import eoa_pseudonym
from agents_b2g.defense.threat_engine.session import ThreatEngineSession

# Spec §2.1 allowlist — reject unknown types at the store boundary
INTERACTION_TYPES = frozenset(
    {
        "bridge_transfer",
        "oracle_update",
        "liquidation_call",
        "dex_swap",
        "intent_fill",
        "contract_create",
        "other_allowlisted",
    }
)

ACTION_TYPES = frozenset(
    {
        "SIGNATURE_OBSERVED",
        "SENSITIVITY_RAISED",
        "SENSITIVITY_CLEARED",
        "GATE_BLOCKED",
        "GATE_RELEASED",
    }
)


class RadarThreatStoreAdapter:
    """Thin store for SwarmDetectionRadar / SwarmSignatureDatabase."""

    def __init__(self, session: ThreatEngineSession, logger: Optional[JSONLogger] = None):
        self.session = session
        self.logger = logger or JSONLogger("RadarThreatStoreAdapter")

    def record_signature(
        self,
        *,
        eoa_address_or_pseudonym: str,
        chain: str,
        window_start: datetime,
        window_end: datetime,
        interaction_type: str,
        tx_count: int = 0,
        peer_cluster_size: int = 1,
        latency_ms_p50: Optional[float] = None,
        latency_ms_p99: Optional[float] = None,
        gas_priority_gwei: Optional[float] = None,
        entropy_score: Optional[float] = None,
        pattern_label: Optional[str] = None,
        observed_by_user_id: Optional[str] = None,
        already_pseudonym: bool = False,
    ) -> dict:
        return _safe_call(
            self.logger,
            "record_signature",
            self._record_signature,
            eoa_address_or_pseudonym,
            chain,
            window_start,
            window_end,
            interaction_type,
            tx_count,
            peer_cluster_size,
            latency_ms_p50,
            latency_ms_p99,
            gas_priority_gwei,
            entropy_score,
            pattern_label,
            observed_by_user_id,
            already_pseudonym,
        )

    def _record_signature(
        self,
        eoa_address_or_pseudonym: str,
        chain: str,
        window_start: datetime,
        window_end: datetime,
        interaction_type: str,
        tx_count: int,
        peer_cluster_size: int,
        latency_ms_p50: Optional[float],
        latency_ms_p99: Optional[float],
        gas_priority_gwei: Optional[float],
        entropy_score: Optional[float],
        pattern_label: Optional[str],
        observed_by_user_id: Optional[str],
        already_pseudonym: bool,
    ) -> dict:
        if interaction_type not in INTERACTION_TYPES:
            raise ValueError(f"interaction_type not allowlisted: {interaction_type}")
        pseudo = (
            eoa_address_or_pseudonym.lower()
            if already_pseudonym
            else eoa_pseudonym(eoa_address_or_pseudonym)
        )
        self.session.execute(
            """
            INSERT INTO wave28_threat_signatures (
                eoa_pseudonym, chain, window_start, window_end,
                latency_ms_p50, latency_ms_p99, gas_priority_gwei,
                interaction_type, tx_count, peer_cluster_size, entropy_score,
                pattern_label, observed_by_user_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING signature_id, created_at
            """,
            (
                pseudo,
                chain,
                window_start,
                window_end,
                latency_ms_p50,
                latency_ms_p99,
                gas_priority_gwei,
                interaction_type,
                tx_count,
                peer_cluster_size,
                entropy_score,
                pattern_label,
                observed_by_user_id,
            ),
        )
        row = self.session.cursor.fetchone()
        return {
            "status": "completed",
            "job_id": "record_signature",
            "artifacts": [
                {
                    "signature_id": int(row[0]),
                    "eoa_pseudonym": pseudo,
                    "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
                }
            ],
            "error": None,
            "logs": [],
        }

    def lookup_signatures(
        self,
        *,
        eoa_pseudonym: Optional[str] = None,
        chain: Optional[str] = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> dict:
        return _safe_call(
            self.logger,
            "lookup_signatures",
            self._lookup_signatures,
            eoa_pseudonym,
            chain,
            active_only,
            limit,
        )

    def _lookup_signatures(
        self,
        eoa_pseudonym: Optional[str],
        chain: Optional[str],
        active_only: bool,
        limit: int,
    ) -> dict:
        clauses = ["TRUE"]
        params: list[Any] = []
        if eoa_pseudonym:
            clauses.append("eoa_pseudonym = %s")
            params.append(eoa_pseudonym.lower())
        if chain:
            clauses.append("chain = %s")
            params.append(chain)
        if active_only:
            clauses.append("is_active = TRUE")
        params.append(limit)
        # Global swarm: no tenant filter (Spec §1.1)
        self.session.execute(
            f"""
            SELECT signature_id, eoa_pseudonym, chain, window_start, window_end,
                   interaction_type, tx_count, peer_cluster_size, pattern_label,
                   observed_by_user_id, created_at
              FROM wave28_threat_signatures
             WHERE {' AND '.join(clauses)}
             ORDER BY created_at DESC
             LIMIT %s
            """,
            tuple(params),
        )
        rows = self.session.cursor.fetchall()
        artifacts = [
            {
                "signature_id": int(r[0]),
                "eoa_pseudonym": r[1],
                "chain": r[2],
                "window_start": r[3].isoformat() if hasattr(r[3], "isoformat") else str(r[3]),
                "window_end": r[4].isoformat() if hasattr(r[4], "isoformat") else str(r[4]),
                "interaction_type": r[5],
                "tx_count": r[6],
                "peer_cluster_size": r[7],
                "pattern_label": r[8],
                "observed_by_user_id": r[9],
                "created_at": r[10].isoformat() if hasattr(r[10], "isoformat") else str(r[10]),
            }
            for r in rows
        ]
        return {
            "status": "completed",
            "job_id": "lookup_signatures",
            "artifacts": artifacts,
            "error": None,
            "logs": [],
        }

    def record_action(
        self,
        *,
        signature_id: int,
        eoa_pseudonym: str,
        action_type: str,
        kfold_sensitivity: Optional[float] = None,
        notes: Optional[str] = None,
        observed_by_user_id: Optional[str] = None,
    ) -> dict:
        """Audit SENSITIVITY_RAISED/CLEARED via SQL function (RELEASED path)."""
        return _safe_call(
            self.logger,
            "record_action",
            self._record_action,
            signature_id,
            eoa_pseudonym,
            action_type,
            kfold_sensitivity,
            notes,
            observed_by_user_id,
        )

    def _record_action(
        self,
        signature_id: int,
        eoa_pseudonym: str,
        action_type: str,
        kfold_sensitivity: Optional[float],
        notes: Optional[str],
        observed_by_user_id: Optional[str],
    ) -> dict:
        if action_type not in ACTION_TYPES:
            raise ValueError(f"unknown action_type: {action_type}")
        if action_type in ("GATE_BLOCKED", "GATE_RELEASED"):
            raise ValueError(
                "use ClassifierIncidentAdapter.record_gate_coupling for GATE_* actions"
            )
        # Discipline stays in SQL — RELEASED + optional sensitivity
        self.session.execute(
            """
            SELECT wave28_record_gate_coupling(
                %s, %s, %s::wave28_action_type, 'RELEASED'::agent_signal_status,
                NULL, NULL, %s, NULL, %s, %s
            )
            """,
            (
                signature_id,
                eoa_pseudonym.lower(),
                action_type,
                kfold_sensitivity,
                notes,
                observed_by_user_id,
            ),
        )
        incident_id = int(self.session.cursor.fetchone()[0])
        return {
            "status": "completed",
            "job_id": "record_action",
            "artifacts": [{"incident_id": incident_id, "action_type": action_type}],
            "error": None,
            "logs": [],
        }

    def record_signature_with_action(
        self,
        *,
        action_type: str = "SENSITIVITY_RAISED",
        kfold_sensitivity: Optional[float] = None,
        **signature_kwargs: Any,
    ) -> dict:
        """Atomic: INSERT signature (+ trigger audit) + optional sensitivity action."""
        with self.session.transaction():
            sig = self._record_signature(**_unpack_signature_kwargs(signature_kwargs))
            sid = sig["artifacts"][0]["signature_id"]
            pseudo = sig["artifacts"][0]["eoa_pseudonym"]
            if action_type and action_type != "SIGNATURE_OBSERVED":
                act = self._record_action(
                    sid,
                    pseudo,
                    action_type,
                    kfold_sensitivity,
                    signature_kwargs.get("notes"),
                    signature_kwargs.get("observed_by_user_id"),
                )
                sig["artifacts"].append(act["artifacts"][0])
            return sig


def _unpack_signature_kwargs(kw: dict) -> dict:
    """Map public kwargs of record_signature_with_action to _record_signature args."""
    return {
        "eoa_address_or_pseudonym": kw["eoa_address_or_pseudonym"],
        "chain": kw["chain"],
        "window_start": kw["window_start"],
        "window_end": kw["window_end"],
        "interaction_type": kw["interaction_type"],
        "tx_count": kw.get("tx_count", 0),
        "peer_cluster_size": kw.get("peer_cluster_size", 1),
        "latency_ms_p50": kw.get("latency_ms_p50"),
        "latency_ms_p99": kw.get("latency_ms_p99"),
        "gas_priority_gwei": kw.get("gas_priority_gwei"),
        "entropy_score": kw.get("entropy_score"),
        "pattern_label": kw.get("pattern_label"),
        "observed_by_user_id": kw.get("observed_by_user_id"),
        "already_pseudonym": kw.get("already_pseudonym", False),
    }
