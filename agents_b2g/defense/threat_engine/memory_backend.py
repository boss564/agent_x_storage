"""In-memory threat backend for DI/E2E tests without PostgreSQL.

Mirrors SQL discipline: dim check, BLOCKED+cause, S(τ)≤0, RAISED/CLEARED via adapters.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional, Sequence

from agents_b2g.defense.threat_engine.pseudonym import eoa_pseudonym as hash_eoa


class MemoryThreatBackend:
    """Drop-in for ThreatEngineSession used by adapters in tests."""

    def __init__(self):
        self.signatures: list[dict] = []
        self.embeddings: list[dict] = []
        self.incidents: list[dict] = []
        self.vault: dict[tuple[str, str], str] = {}
        self.watchlist: list[dict] = []
        self.relayer_health: list[dict] = []
        self.censorship_incidents: list[dict] = []
        self._sig_seq = 0
        self._emb_seq = 0
        self._inc_seq = 0
        self._watch_seq = 0
        self._health_seq = 0
        self._cens_seq = 0
        self._last: Any = None
        self._rows: list = []

    @property
    def cursor(self) -> "MemoryThreatBackend":
        return self

    def execute(self, query: str, params: Any = None) -> "MemoryThreatBackend":
        q = " ".join(query.split())
        p = params or ()
        self._rows = []
        self._last = None

        if "INSERT INTO wave28_eoa_raw_vault" in q:
            tenant, pseudo, raw = p[0], p[1], p[2]
            self.vault[(tenant, pseudo)] = raw
            return self

        if "SELECT eoa_address_raw FROM wave28_eoa_raw_vault" in q:
            key = (p[0], p[1])
            if key in self.vault:
                self._rows = [(self.vault[key],)]
            return self

        if "INSERT INTO wave28_threat_signatures" in q:
            self._sig_seq += 1
            now = datetime.now(timezone.utc)
            row = {
                "signature_id": self._sig_seq,
                "eoa_pseudonym": p[0],
                "chain": p[1],
                "window_start": p[2],
                "window_end": p[3],
                "latency_ms_p50": p[4],
                "latency_ms_p99": p[5],
                "gas_priority_gwei": p[6],
                "interaction_type": p[7],
                "tx_count": p[8],
                "peer_cluster_size": p[9],
                "entropy_score": p[10],
                "pattern_label": p[11],
                "observed_by_user_id": p[12],
                "is_active": True,
                "created_at": now,
            }
            self.signatures.append(row)
            # Trigger-equivalent SIGNATURE_OBSERVED
            self._inc_seq += 1
            self.incidents.append(
                {
                    "incident_id": self._inc_seq,
                    "signature_id": self._sig_seq,
                    "eoa_pseudonym": p[0],
                    "action_type": "SIGNATURE_OBSERVED",
                    "agent_x_signal_status": "RELEASED",
                    "block_cause": None,
                    "s_tau": None,
                    "kfold_sensitivity": None,
                    "gatekeeper_job_id": None,
                    "observed_by_user_id": p[12],
                    "created_at": now,
                }
            )
            self._rows = [(self._sig_seq, now)]
            return self

        if "FROM wave28_threat_signatures" in q and "SELECT signature_id" in q:
            rows = list(self.signatures)
            # crude filter: last params before limit
            limit = int(p[-1]) if p else 100
            self._rows = [
                (
                    r["signature_id"],
                    r["eoa_pseudonym"],
                    r["chain"],
                    r["window_start"],
                    r["window_end"],
                    r["interaction_type"],
                    r["tx_count"],
                    r["peer_cluster_size"],
                    r["pattern_label"],
                    r["observed_by_user_id"],
                    r["created_at"],
                )
                for r in reversed(rows)
            ][:limit]
            return self

        if "INSERT INTO wave28_behavior_embeddings" in q:
            lit = p[2]
            dim = int(p[4])
            vec = _parse_vector(lit)
            if len(vec) != dim:
                raise ValueError(f"vector length {len(vec)} != embedding_dim {dim}")
            self._emb_seq += 1
            now = datetime.now(timezone.utc)
            self.embeddings.append(
                {
                    "embedding_id": self._emb_seq,
                    "signature_id": p[0],
                    "eoa_pseudonym": p[1],
                    "vector": vec,
                    "embedding_model": p[3],
                    "embedding_dim": dim,
                    "cluster_id": p[5],
                    "similarity_ref": p[6],
                    "observed_by_user_id": p[7],
                    "is_active": True,
                    "created_at": now,
                }
            )
            self._rows = [(self._emb_seq, now)]
            return self

        if "cosine_similarity" in q or "<=>" in q:
            lit, model, dim, _lit2, top_k = p[0], p[1], int(p[2]), p[3], int(p[4])
            qv = _parse_vector(lit)
            scored = []
            for e in self.embeddings:
                if e["embedding_model"] != model or e["embedding_dim"] != dim:
                    continue
                if not e["is_active"]:
                    continue
                sim = _cosine(qv, e["vector"])
                scored.append((e, sim))
            scored.sort(key=lambda x: -x[1])
            self._rows = [
                (
                    e["embedding_id"],
                    e["signature_id"],
                    e["eoa_pseudonym"],
                    e["cluster_id"],
                    e["embedding_model"],
                    e["embedding_dim"],
                    sim,
                )
                for e, sim in scored[:top_k]
            ]
            return self

        if "GROUP BY cluster_id" in q:
            model = p[0]
            counts: dict[int, int] = {}
            for e in self.embeddings:
                if e["embedding_model"] != model or e["cluster_id"] is None:
                    continue
                counts[e["cluster_id"]] = counts.get(e["cluster_id"], 0) + 1
            self._rows = sorted(counts.items(), key=lambda x: -x[1])
            return self

        if "wave28_record_gate_coupling" in q:
            # Classifier path: 10 bound params
            # Radar record_action: 6 bound params
            #   (sid, pseudo, action, kfold, notes, observed)
            #   with RELEASED / NULL literals in SQL
            if len(p) == 6:
                signature_id, pseudo, action_type, kfold, notes, observed = p
                status = "RELEASED"
                block_cause = None
                s_tau = None
                job_id = None
            elif len(p) == 10:
                (
                    signature_id,
                    pseudo,
                    action_type,
                    status,
                    block_cause,
                    s_tau,
                    kfold,
                    job_id,
                    notes,
                    observed,
                ) = p
            else:
                raise ValueError(f"unexpected gate_coupling arity: {len(p)}")
            if status == "BLOCKED" and (not block_cause or not str(block_cause).strip()):
                raise Exception("BLOCKED requires block_cause (Wave-38 gate invariant)")
            if status == "BLOCKED" and s_tau is not None and s_tau > 0:
                raise Exception("BLOCKED with S(τ)>0 rejected")
            self._inc_seq += 1
            now = datetime.now(timezone.utc)
            self.incidents.append(
                {
                    "incident_id": self._inc_seq,
                    "signature_id": signature_id,
                    "eoa_pseudonym": str(pseudo).lower(),
                    "action_type": action_type,
                    "agent_x_signal_status": status,
                    "block_cause": block_cause,
                    "s_tau": s_tau,
                    "kfold_sensitivity": kfold,
                    "gatekeeper_job_id": job_id,
                    "observed_by_user_id": observed,
                    "notes": notes,
                    "created_at": now,
                }
            )
            self._rows = [(self._inc_seq,)]
            return self

        if "FROM wave28_causal_incidents" in q:
            limit = int(p[-1])
            rows = list(reversed(self.incidents))[:limit]
            self._rows = [
                (
                    r["incident_id"],
                    r["signature_id"],
                    r["eoa_pseudonym"],
                    r["action_type"],
                    r["agent_x_signal_status"],
                    r["block_cause"],
                    r["s_tau"],
                    r["kfold_sensitivity"],
                    r["gatekeeper_job_id"],
                    r.get("observed_by_user_id"),
                    r["created_at"],
                )
                for r in rows
            ]
            return self

        if "INSERT INTO wave28_censorship_watchlist" in q:
            self._watch_seq += 1
            now = datetime.now(timezone.utc)
            self.watchlist.append(
                {
                    "watch_id": self._watch_seq,
                    "address_pseudonym": p[0],
                    "source": p[1],
                    "list_version": p[2],
                    "confidence": float(p[3]),
                    "observed_by_user_id": p[4],
                    "is_active": True,
                    "created_at": now,
                }
            )
            self._rows = [(self._watch_seq, now)]
            return self

        if "FROM wave28_censorship_watchlist" in q:
            pseudo = p[0]
            hits = [
                w
                for w in self.watchlist
                if w["address_pseudonym"] == pseudo and w["is_active"]
            ]
            hits.sort(key=lambda w: -w["confidence"])
            self._rows = [
                (w["watch_id"], w["source"], w["list_version"], w["confidence"])
                for w in hits[:5]
            ]
            return self

        if "INSERT INTO wave28_relayer_health" in q:
            self._health_seq += 1
            now = datetime.now(timezone.utc)
            flagged = bool(p[5])
            self.relayer_health.append(
                {
                    "health_id": self._health_seq,
                    "relayer_name": p[0],
                    "chain_id": p[1],
                    "asset_symbol": p[2],
                    "throughput_rate": p[3],
                    "drop_rate": p[4],
                    "censorship_detected": flagged,
                    "observed_at": now,
                }
            )
            self._rows = [(self._health_seq, now, flagged)]
            return self

        if "FROM wave28_relayer_health" in q:
            limit = int(p[-1])
            flagged = [h for h in self.relayer_health if h["censorship_detected"]]
            flagged = list(reversed(flagged))[:limit]
            self._rows = [
                (
                    h["health_id"],
                    h["relayer_name"],
                    h["asset_symbol"],
                    h["drop_rate"],
                    h["throughput_rate"],
                    h["observed_at"],
                )
                for h in flagged
            ]
            return self

        if "INSERT INTO wave28_censorship_incidents" in q:
            status = p[3]
            block_cause = p[4]
            if status == "BLOCKED" and (not block_cause or not str(block_cause).strip()):
                raise Exception("BLOCKED requires block_cause")
            self._cens_seq += 1
            now = datetime.now(timezone.utc)
            self.censorship_incidents.append(
                {
                    "incident_id": self._cens_seq,
                    "watch_id": p[0],
                    "relayer_name": p[1],
                    "censorship_type": p[2],
                    "agent_x_signal_status": status,
                    "block_cause": block_cause,
                    "route_fallback": p[5],
                    "logged_at": now,
                }
            )
            self._rows = [(self._cens_seq, now)]
            return self

        raise NotImplementedError(f"MemoryThreatBackend: unhandled SQL: {q[:120]}")

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list:
        return list(self._rows)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass

    @contextmanager
    def transaction(self) -> Iterator["MemoryThreatBackend"]:
        yield self


def _parse_vector(lit: str) -> list[float]:
    s = lit.strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    if not s:
        return []
    return [float(x) for x in s.split(",")]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def make_memory_session() -> MemoryThreatBackend:
    return MemoryThreatBackend()


# re-export for tests that need hashing
__all__ = ["MemoryThreatBackend", "make_memory_session", "hash_eoa"]
