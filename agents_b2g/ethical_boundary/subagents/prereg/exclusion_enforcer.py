"""W39-A1-S4 — deep payload scan for OFFENSIVE_PURPOSE_MARKERS (Charter §1.0.E)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.config import OFFENSIVE_MARKER_REGISTRY


@dataclass(frozen=True)
class ExclusionHit:
    marker: str
    json_path: str
    charter_ref: str


@dataclass(frozen=True)
class ExclusionEnforcerResult:
    hits: tuple[ExclusionHit, ...]


class ExclusionEnforcer:
    subagent_id = "W39-A1-S4"

    def run(self, payload: Mapping[str, Any]) -> ExclusionEnforcerResult:
        hits: list[ExclusionHit] = []
        self._walk(payload, path="payload", hits=hits)
        return ExclusionEnforcerResult(hits=tuple(hits))

    def _walk(self, node: Any, *, path: str, hits: list[ExclusionHit]) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                child = f"{path}.{key}"
                self._check_token(str(key), child, hits)
                self._walk(value, path=child, hits=hits)
            return
        if isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                self._walk(item, path=f"{path}[{index}]", hits=hits)
            return
        if isinstance(node, str):
            self._check_token(node, path, hits)

    def _check_token(self, token: str, path: str, hits: list[ExclusionHit]) -> None:
        upper = token.upper()
        if upper in OFFENSIVE_MARKER_REGISTRY.markers:
            hits.append(
                ExclusionHit(
                    marker=upper,
                    json_path=path,
                    charter_ref=OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                        upper, "§1.0.E"
                    ),
                )
            )
            return
        for marker in OFFENSIVE_MARKER_REGISTRY.markers:
            if marker in upper and marker not in {hit.marker for hit in hits if hit.json_path == path}:
                hits.append(
                    ExclusionHit(
                        marker=marker,
                        json_path=path,
                        charter_ref=OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                            marker, "§1.0.E"
                        ),
                    )
                )
