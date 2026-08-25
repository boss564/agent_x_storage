"""ClassifierIncidentAdapter — delegates gate coupling to SQL (single source of truth)."""

from __future__ import annotations

from typing import Optional

from agents_b2g.defense.swarm_defense_orchestrator import JSONLogger, _safe_call
from agents_b2g.defense.threat_engine.session import ThreatEngineSession


class ClassifierIncidentAdapter:
    """Thin store for ThreatClassifierEngine / MEVArbitrageClassifier."""

    def __init__(self, session: ThreatEngineSession, logger: Optional[JSONLogger] = None):
        self.session = session
        self.logger = logger or JSONLogger("ClassifierIncidentAdapter")

    def record_gate_coupling(
        self,
        *,
        signature_id: Optional[int],
        eoa_pseudonym: str,
        action_type: str,
        agent_x_signal_status: str,
        block_cause: Optional[str] = None,
        s_tau: Optional[float] = None,
        kfold_sensitivity: Optional[float] = None,
        gatekeeper_job_id: Optional[str] = None,
        notes: Optional[str] = None,
        observed_by_user_id: Optional[str] = None,
    ) -> dict:
        """Call wave28_record_gate_coupling — do not re-implement BLOCKED rules."""
        return _safe_call(
            self.logger,
            "record_gate_coupling",
            self._record_gate_coupling,
            signature_id,
            eoa_pseudonym,
            action_type,
            agent_x_signal_status,
            block_cause,
            s_tau,
            kfold_sensitivity,
            gatekeeper_job_id,
            notes,
            observed_by_user_id,
        )

    def _record_gate_coupling(
        self,
        signature_id: Optional[int],
        eoa_pseudonym: str,
        action_type: str,
        agent_x_signal_status: str,
        block_cause: Optional[str],
        s_tau: Optional[float],
        kfold_sensitivity: Optional[float],
        gatekeeper_job_id: Optional[str],
        notes: Optional[str],
        observed_by_user_id: Optional[str],
    ) -> dict:
        self.session.execute(
            """
            SELECT wave28_record_gate_coupling(
                %s, %s, %s::wave28_action_type, %s::agent_signal_status,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                signature_id,
                eoa_pseudonym.lower(),
                action_type,
                agent_x_signal_status,
                block_cause,
                s_tau,
                kfold_sensitivity,
                gatekeeper_job_id,
                notes,
                observed_by_user_id,
            ),
        )
        incident_id = int(self.session.cursor.fetchone()[0])
        return {
            "status": "completed",
            "job_id": "record_gate_coupling",
            "artifacts": [
                {
                    "incident_id": incident_id,
                    "action_type": action_type,
                    "agent_x_signal_status": agent_x_signal_status,
                }
            ],
            "error": None,
            "logs": [],
        }

    def query_incidents(
        self,
        *,
        eoa_pseudonym: Optional[str] = None,
        action_type: Optional[str] = None,
        signal_status: Optional[str] = None,
        limit: int = 100,
    ) -> dict:
        return _safe_call(
            self.logger,
            "query_incidents",
            self._query_incidents,
            eoa_pseudonym,
            action_type,
            signal_status,
            limit,
        )

    def _query_incidents(
        self,
        eoa_pseudonym: Optional[str],
        action_type: Optional[str],
        signal_status: Optional[str],
        limit: int,
    ) -> dict:
        clauses = ["TRUE"]
        params: list = []
        if eoa_pseudonym:
            clauses.append("eoa_pseudonym = %s")
            params.append(eoa_pseudonym.lower())
        if action_type:
            clauses.append("action_type = %s::wave28_action_type")
            params.append(action_type)
        if signal_status:
            clauses.append("agent_x_signal_status = %s::agent_signal_status")
            params.append(signal_status)
        params.append(limit)
        self.session.execute(
            f"""
            SELECT incident_id, signature_id, eoa_pseudonym, action_type,
                   agent_x_signal_status, block_cause, s_tau, kfold_sensitivity,
                   gatekeeper_job_id, observed_by_user_id, created_at
              FROM wave28_causal_incidents
             WHERE {' AND '.join(clauses)}
             ORDER BY created_at DESC
             LIMIT %s
            """,
            tuple(params),
        )
        rows = self.session.cursor.fetchall()
        artifacts = [
            {
                "incident_id": int(r[0]),
                "signature_id": int(r[1]) if r[1] is not None else None,
                "eoa_pseudonym": r[2],
                "action_type": str(r[3]),
                "agent_x_signal_status": str(r[4]),
                "block_cause": r[5],
                "s_tau": float(r[6]) if r[6] is not None else None,
                "kfold_sensitivity": float(r[7]) if r[7] is not None else None,
                "gatekeeper_job_id": r[8],
                "observed_by_user_id": r[9],
                "created_at": r[10].isoformat() if hasattr(r[10], "isoformat") else str(r[10]),
            }
            for r in rows
        ]
        return {
            "status": "completed",
            "job_id": "query_incidents",
            "artifacts": artifacts,
            "error": None,
            "logs": [],
        }
