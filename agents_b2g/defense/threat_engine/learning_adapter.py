"""LearningEmbeddingAdapter — data layer for FeatureExtractor / ModelVersionManager."""

from __future__ import annotations

from typing import Optional, Sequence

from agents_b2g.defense.swarm_defense_orchestrator import JSONLogger, _safe_call
from agents_b2g.defense.threat_engine.session import ThreatEngineSession

DEFAULT_MODEL = "all-MiniLM-L6-v2"
DEFAULT_DIM = 384


def _as_vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


class LearningEmbeddingAdapter:
    """Thin store for SwarmLearningAdapter. Dim check before INSERT."""

    def __init__(
        self,
        session: ThreatEngineSession,
        logger: Optional[JSONLogger] = None,
        *,
        default_model: str = DEFAULT_MODEL,
        default_dim: int = DEFAULT_DIM,
    ):
        self.session = session
        self.logger = logger or JSONLogger("LearningEmbeddingAdapter")
        self.default_model = default_model
        self.default_dim = default_dim

    def store_embedding(
        self,
        *,
        signature_id: int,
        eoa_pseudonym: str,
        vector: Sequence[float],
        embedding_model: Optional[str] = None,
        embedding_dim: Optional[int] = None,
        cluster_id: Optional[int] = None,
        similarity_ref: Optional[float] = None,
        observed_by_user_id: Optional[str] = None,
    ) -> dict:
        return _safe_call(
            self.logger,
            "store_embedding",
            self._store_embedding,
            signature_id,
            eoa_pseudonym,
            vector,
            embedding_model,
            embedding_dim,
            cluster_id,
            similarity_ref,
            observed_by_user_id,
        )

    def _store_embedding(
        self,
        signature_id: int,
        eoa_pseudonym: str,
        vector: Sequence[float],
        embedding_model: Optional[str],
        embedding_dim: Optional[int],
        cluster_id: Optional[int],
        similarity_ref: Optional[float],
        observed_by_user_id: Optional[str],
    ) -> dict:
        model = embedding_model or self.default_model
        dim = embedding_dim if embedding_dim is not None else self.default_dim
        if len(vector) != dim:
            raise ValueError(
                f"vector length {len(vector)} != embedding_dim {dim} (model={model})"
            )
        if dim != self.default_dim and model == self.default_model:
            raise ValueError(
                f"model {model} expects dim {self.default_dim}, got {dim}"
            )
        lit = _as_vector_literal(vector)
        self.session.execute(
            """
            INSERT INTO wave28_behavior_embeddings (
                signature_id, eoa_pseudonym, embedding,
                embedding_model, embedding_dim, cluster_id, similarity_ref,
                observed_by_user_id
            ) VALUES (
                %s, %s, %s::vector, %s, %s, %s, %s, %s
            )
            RETURNING embedding_id, created_at
            """,
            (
                signature_id,
                eoa_pseudonym.lower(),
                lit,
                model,
                dim,
                cluster_id,
                similarity_ref,
                observed_by_user_id,
            ),
        )
        row = self.session.cursor.fetchone()
        return {
            "status": "completed",
            "job_id": "store_embedding",
            "artifacts": [
                {
                    "embedding_id": int(row[0]),
                    "embedding_model": model,
                    "embedding_dim": dim,
                    "created_at": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
                }
            ],
            "error": None,
            "logs": [],
        }

    def query_similar(
        self,
        vector: Sequence[float],
        *,
        top_k: int = 10,
        embedding_model: Optional[str] = None,
        embedding_dim: Optional[int] = None,
        active_only: bool = True,
    ) -> dict:
        return _safe_call(
            self.logger,
            "query_similar",
            self._query_similar,
            vector,
            top_k,
            embedding_model,
            embedding_dim,
            active_only,
        )

    def _query_similar(
        self,
        vector: Sequence[float],
        top_k: int,
        embedding_model: Optional[str],
        embedding_dim: Optional[int],
        active_only: bool,
    ) -> dict:
        model = embedding_model or self.default_model
        dim = embedding_dim if embedding_dim is not None else self.default_dim
        if len(vector) != dim:
            raise ValueError(
                f"query vector length {len(vector)} != embedding_dim {dim}"
            )
        lit = _as_vector_literal(vector)
        active_clause = "AND is_active = TRUE" if active_only else ""
        # Cosine distance via <=> ; same model+dim only (Spec §6)
        self.session.execute(
            f"""
            SELECT embedding_id, signature_id, eoa_pseudonym, cluster_id,
                   embedding_model, embedding_dim,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
              FROM wave28_behavior_embeddings
             WHERE embedding_model = %s
               AND embedding_dim = %s
               {active_clause}
             ORDER BY embedding <=> %s::vector
             LIMIT %s
            """,
            (lit, model, dim, lit, top_k),
        )
        rows = self.session.cursor.fetchall()
        artifacts = [
            {
                "embedding_id": int(r[0]),
                "signature_id": int(r[1]),
                "eoa_pseudonym": r[2],
                "cluster_id": r[3],
                "embedding_model": r[4],
                "embedding_dim": int(r[5]),
                "cosine_similarity": float(r[6]) if r[6] is not None else None,
            }
            for r in rows
        ]
        return {
            "status": "completed",
            "job_id": "query_similar",
            "artifacts": artifacts,
            "error": None,
            "logs": [],
        }

    def get_cluster_labels(
        self,
        *,
        embedding_model: Optional[str] = None,
        active_only: bool = True,
    ) -> dict:
        return _safe_call(
            self.logger,
            "get_cluster_labels",
            self._get_cluster_labels,
            embedding_model,
            active_only,
        )

    def _get_cluster_labels(
        self,
        embedding_model: Optional[str],
        active_only: bool,
    ) -> dict:
        model = embedding_model or self.default_model
        active_clause = "AND is_active = TRUE" if active_only else ""
        self.session.execute(
            f"""
            SELECT cluster_id, COUNT(*) AS n
              FROM wave28_behavior_embeddings
             WHERE embedding_model = %s
               AND cluster_id IS NOT NULL
               {active_clause}
             GROUP BY cluster_id
             ORDER BY n DESC
            """,
            (model,),
        )
        rows = self.session.cursor.fetchall()
        return {
            "status": "completed",
            "job_id": "get_cluster_labels",
            "artifacts": [
                {"cluster_id": int(r[0]), "count": int(r[1]), "embedding_model": model}
                for r in rows
            ],
            "error": None,
            "logs": [],
        }
