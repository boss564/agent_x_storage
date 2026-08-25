"""PM3 — CausalGraphPostMEVReconciler.

Append-only causal-graph amendments. Sealed Pre-Reg hashes are immutable;
mutation attempts → BLOCKED + PRE_REG_MUTATION_ATTEMPT.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from agents_b2g.diagnostic.post_mev.agents import make_response
from agents_b2g.diagnostic.post_mev.config import PostMEVConfig
from agents_b2g.diagnostic.post_mev.logging_utils import JSONLogger, _safe_call
from agents_b2g.diagnostic.post_mev.types import (
    GENESIS_AMENDMENT_PREV,
    AmendmentEntry,
    PostMEVBlockCause,
    ReconcileVerdict,
    sha256_hex,
    utc_now_iso,
)


# ---------------------------------------------------------------------------
# Subagents (9)
# ---------------------------------------------------------------------------


class PreRegHashLoader:
    name = "PreRegHashLoader"

    def run(self, sealed_hash: str, store_path: Path | None = None) -> dict[str, Any]:
        loaded = sealed_hash
        if store_path and store_path.is_file():
            data = json.loads(store_path.read_text(encoding="utf-8"))
            loaded = str(data.get("original_pre_reg_hash", sealed_hash))
        ok = len(loaded) == 64 and all(c in "0123456789abcdef" for c in loaded.lower())
        return {
            "original_pre_reg_hash": loaded,
            "ok": ok,
            "read_only": True,
            "path": str(store_path) if store_path else None,
        }


class PreRegMutationGuard:
    name = "PreRegMutationGuard"

    def run(
        self,
        *,
        sealed_hash: str,
        attempted_write: bool,
        attempted_overwrite_hash: str | None = None,
    ) -> dict[str, Any]:
        mutation = bool(attempted_write)
        if attempted_overwrite_hash and attempted_overwrite_hash != sealed_hash:
            mutation = True
        return {
            "allowed": not mutation,
            "blocked": mutation,
            "cause": PostMEVBlockCause.PRE_REG_MUTATION_ATTEMPT.value if mutation else None,
            "sealed_hash": sealed_hash,
        }


class CausalEdgeDiffBuilder:
    name = "CausalEdgeDiffBuilder"

    def run(
        self,
        expected_edges: list[Mapping[str, Any]],
        observed_edges: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        exp = {self._key(e): e for e in expected_edges}
        obs = {self._key(e): e for e in observed_edges}
        added = [obs[k] for k in obs if k not in exp]
        removed = [exp[k] for k in exp if k not in obs]
        return {
            "added": added,
            "removed": removed,
            "unchanged": len(exp) - len(removed),
            "has_diff": bool(added or removed),
        }

    @staticmethod
    def _key(edge: Mapping[str, Any]) -> str:
        return f"{edge.get('src')}→{edge.get('dst')}:{edge.get('rel', 'causes')}"


class NovelFactorAnnotator:
    name = "NovelFactorAnnotator"

    def run(self, factors: list[str], registered: list[str]) -> dict[str, Any]:
        reg = set(registered)
        novel = [f for f in factors if f not in reg]
        return {"novel_factors": novel, "annotation_only": True}


class AmendmentPayloadBuilder:
    name = "AmendmentPayloadBuilder"

    def run(
        self,
        *,
        edge_diff: Mapping[str, Any],
        novel_factors: list[str],
        distorted_ids: list[str],
        quarantined_ids: list[str],
    ) -> dict[str, Any]:
        payload = {
            "edge_diff": {
                "added": edge_diff.get("added", []),
                "removed": edge_diff.get("removed", []),
            },
            "novel_factors": list(novel_factors),
            "distorted_signal_ids": list(distorted_ids),
            "quarantined_ids": list(quarantined_ids),
            "kind": "POST_MEV_CAUSAL_AMENDMENT",
        }
        return {"payload": payload, "empty": not (
            edge_diff.get("has_diff") or novel_factors or distorted_ids or quarantined_ids
        )}


class AmendmentHasher:
    name = "AmendmentHasher"

    def run(
        self,
        *,
        amendment_id: str,
        original_pre_reg_hash: str,
        amendment_payload: Mapping[str, Any],
        prev_amendment_hash: str,
    ) -> dict[str, Any]:
        entry = AmendmentEntry.build(
            amendment_id=amendment_id,
            original_pre_reg_hash=original_pre_reg_hash,
            amendment_payload=dict(amendment_payload),
            prev_amendment_hash=prev_amendment_hash or GENESIS_AMENDMENT_PREV,
        )
        return {"entry": entry.to_dict(), "amendment_hash": entry.amendment_hash}


class AmendmentAppendWriter:
    name = "AmendmentAppendWriter"

    def run(self, path: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
        return {"path": str(path), "appended": 1, "append_only": True, "overwrote": False}


class GraphSnapshotExporter:
    name = "GraphSnapshotExporter"

    def run(self, path: Path, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write new snapshot file per job — never mutate sealed pre-reg store.
        path.write_text(json.dumps(snapshot, sort_keys=True, indent=2, default=str), encoding="utf-8")
        return {"path": str(path), "hash": sha256_hex(dict(snapshot))}


class ReconcileVerdictComposer:
    name = "ReconcileVerdictComposer"

    def run(
        self,
        *,
        mutation_blocked: bool,
        has_amendment: bool,
        cause: str | None = None,
    ) -> dict[str, Any]:
        if mutation_blocked:
            return {
                "verdict": ReconcileVerdict.BLOCKED.value,
                "cause": cause or PostMEVBlockCause.PRE_REG_MUTATION_ATTEMPT.value,
            }
        if has_amendment:
            return {"verdict": ReconcileVerdict.AMENDMENT_PROPOSED.value, "cause": None}
        return {"verdict": ReconcileVerdict.NO_AMENDMENT.value, "cause": None}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


@dataclass
class PM3Result:
    verdict: str
    amendments: list[AmendmentEntry] = field(default_factory=list)
    block_cause: str | None = None
    original_pre_reg_hash: str = ""
    subagent_results: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "amendments": [a.to_dict() for a in self.amendments],
            "block_cause": self.block_cause,
            "original_pre_reg_hash": self.original_pre_reg_hash,
            "subagents": self.subagent_results,
        }


class CausalGraphPostMEVReconciler:
    agent_name = "CausalGraphPostMEVReconciler"

    def __init__(self, user_id: str = "post_mev", config: PostMEVConfig | None = None):
        self.user_id = user_id
        self.config = config or PostMEVConfig.load()
        self.logger = JSONLogger(self.agent_name, user_id)
        self._tenant = self.config.tenant_root(user_id)
        self.loader = PreRegHashLoader()
        self.guard = PreRegMutationGuard()
        self.diff = CausalEdgeDiffBuilder()
        self.novel = NovelFactorAnnotator()
        self.builder = AmendmentPayloadBuilder()
        self.hasher = AmendmentHasher()
        self.writer = AmendmentAppendWriter()
        self.snapshot = GraphSnapshotExporter()
        self.composer = ReconcileVerdictComposer()

    def run(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        return _safe_call(self.logger, self.agent_name, self._run_inner, payload, job_id)

    def evaluate(self, payload: Mapping[str, Any], job_id: str = "pm3") -> PM3Result:
        return self._evaluate(payload, job_id)

    def _run_inner(self, payload: Mapping[str, Any], job_id: str) -> dict[str, Any]:
        result = self._evaluate(payload, job_id)
        status = "blocked" if result.verdict == ReconcileVerdict.BLOCKED.value else "completed"
        return make_response(
            status,  # type: ignore[arg-type]
            job_id,
            artifacts=[
                {
                    "type": "pm3_result",
                    "path": str(self._tenant / f"pm3_{job_id}.json"),
                    "metadata": result.to_dict(),
                }
            ],
            error=result.block_cause,
            logs=[f"verdict={result.verdict}"],
        )

    def _evaluate(self, payload: Mapping[str, Any], job_id: str) -> PM3Result:
        sealed = str(payload.get("original_pre_reg_hash", ""))
        store = payload.get("pre_reg_store_path")
        store_path = Path(store) if store else (self._tenant / "sealed_pre_reg.json")

        # Ensure sealed store exists as read-only reference (create once if missing).
        if sealed and not store_path.is_file():
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store_path.write_text(
                json.dumps({"original_pre_reg_hash": sealed, "sealed": True}, indent=2),
                encoding="utf-8",
            )

        load_r = self.loader.run(sealed or "0" * 64, store_path if store_path.is_file() else None)
        sealed_hash = str(load_r["original_pre_reg_hash"])

        attempted_write = bool(payload.get("mutate_pre_reg", False)) or bool(
            payload.get("overwrite_pre_reg_hash")
        )
        overwrite = payload.get("overwrite_pre_reg_hash")
        # Also block if caller tries to rewrite the sealed store file content.
        if bool(payload.get("rewrite_sealed_store")) and store_path.is_file():
            attempted_write = True

        guard_r = self.guard.run(
            sealed_hash=sealed_hash,
            attempted_write=attempted_write,
            attempted_overwrite_hash=str(overwrite) if overwrite else None,
        )

        if guard_r["blocked"]:
            # Forensic stamp append (GoBD-WORM style) — never mutate sealed hash file.
            stamp_path = self._tenant / "forensic_stamps.jsonl"
            stamp = {
                "job_id": job_id,
                "cause": guard_r["cause"],
                "sealed_hash": sealed_hash,
                "created_at": utc_now_iso(),
            }
            with stamp_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(stamp, sort_keys=True) + "\n")
            verd_r = self.composer.run(mutation_blocked=True, has_amendment=False, cause=guard_r["cause"])
            return PM3Result(
                verdict=verd_r["verdict"],
                amendments=[],
                block_cause=verd_r["cause"],
                original_pre_reg_hash=sealed_hash,
                subagent_results={
                    PreRegHashLoader.name: load_r,
                    PreRegMutationGuard.name: guard_r,
                    ReconcileVerdictComposer.name: verd_r,
                    "forensic_stamp": {"path": str(stamp_path), "appended": True},
                },
            )

        expected = list(payload.get("expected_edges", []))
        observed = list(payload.get("observed_edges", expected))
        factors = list(payload.get("signal_factors", []))
        registered = list(payload.get("registered_factors", factors))
        distorted = list(payload.get("distorted_signal_ids", []))
        quarantined = list(payload.get("quarantined_ids", []))

        diff_r = self.diff.run(expected, observed)
        novel_r = self.novel.run(factors, registered)
        build_r = self.builder.run(
            edge_diff=diff_r,
            novel_factors=novel_r["novel_factors"],
            distorted_ids=distorted,
            quarantined_ids=quarantined,
        )

        amendments: list[AmendmentEntry] = []
        hash_r: dict[str, Any] = {}
        write_r: dict[str, Any] = {"appended": 0}
        if not build_r["empty"]:
            prev = str(payload.get("prev_amendment_hash", GENESIS_AMENDMENT_PREV))
            amendment_id = f"amd-{job_id}"
            hash_r = self.hasher.run(
                amendment_id=amendment_id,
                original_pre_reg_hash=sealed_hash,
                amendment_payload=build_r["payload"],
                prev_amendment_hash=prev,
            )
            entry = AmendmentEntry(
                amendment_id=hash_r["entry"]["amendment_id"],
                original_pre_reg_hash=hash_r["entry"]["original_pre_reg_hash"],
                amendment_payload=hash_r["entry"]["amendment_payload"],
                prev_amendment_hash=hash_r["entry"]["prev_amendment_hash"],
                amendment_hash=hash_r["entry"]["amendment_hash"],
                created_at=hash_r["entry"]["created_at"],
            )
            write_r = self.writer.run(self._tenant / "amendments.jsonl", entry.to_dict())
            amendments.append(entry)

        snap_r = self.snapshot.run(
            self._tenant / f"graph_snapshot_{job_id}.json",
            {
                "job_id": job_id,
                "original_pre_reg_hash": sealed_hash,
                "expected_edges": expected,
                "observed_edges": observed,
                "novel_factors": novel_r["novel_factors"],
            },
        )
        verd_r = self.composer.run(
            mutation_blocked=False,
            has_amendment=bool(amendments),
        )

        return PM3Result(
            verdict=verd_r["verdict"],
            amendments=amendments,
            block_cause=None,
            original_pre_reg_hash=sealed_hash,
            subagent_results={
                PreRegHashLoader.name: load_r,
                PreRegMutationGuard.name: guard_r,
                CausalEdgeDiffBuilder.name: diff_r,
                NovelFactorAnnotator.name: novel_r,
                AmendmentPayloadBuilder.name: build_r,
                AmendmentHasher.name: {k: v for k, v in hash_r.items() if k != "entry"} if hash_r else {},
                AmendmentAppendWriter.name: write_r,
                GraphSnapshotExporter.name: snap_r,
                ReconcileVerdictComposer.name: verd_r,
            },
        )
