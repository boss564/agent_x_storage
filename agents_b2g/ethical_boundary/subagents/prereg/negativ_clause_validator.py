"""W39-A1-S3 — hard §1.0.E negation clause validation on Pre-Reg + payload."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents_b2g.ethical_boundary.config import OFFENSIVE_MARKER_REGISTRY
from agents_b2g.ethical_boundary.subagents.prereg.pre_reg_loader import LoadedPreRegDocument


NEGATION_BYPASS_KEYS = frozenset(
    {
        "negation_clause_bypass",
        "allow_offensive_execution",
        "profit_extraction_enabled",
        "offensive_mode",
    }
)

NEGATION_SURFACE_KEYS = frozenset(
    {
        "purpose",
        "purposes",
        "intent",
        "declared_purpose",
        "execution_mode",
    }
)


@dataclass(frozen=True)
class NegativClauseHit:
    marker: str
    location: str
    charter_ref: str


@dataclass(frozen=True)
class NegativClauseValidatorResult:
    hits: tuple[NegativClauseHit, ...]
    not_bindend_keys: tuple[str, ...]
    bypass_flags: tuple[str, ...]


class NegativClauseValidator:
    subagent_id = "W39-A1-S3"

    def run(
        self,
        payload: Mapping[str, Any],
        *,
        documents: tuple[LoadedPreRegDocument, ...],
    ) -> NegativClauseValidatorResult:
        hits: list[NegativClauseHit] = []
        not_bindend = [doc.key for doc in documents if not doc.bindend]
        bypass_flags: list[str] = []

        for key in NEGATION_BYPASS_KEYS:
            if payload.get(key) is True:
                bypass_flags.append(key)

        for surface_key in NEGATION_SURFACE_KEYS:
            value = payload.get(surface_key)
            if value is None:
                continue
            for marker in self._markers_in_value(value):
                hits.append(
                    NegativClauseHit(
                        marker=marker,
                        location=f"payload.{surface_key}",
                        charter_ref=OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                            marker, "§1.0.E"
                        ),
                    )
                )

        receiver = payload.get("receiver_metadata")
        if isinstance(receiver, Mapping):
            for surface_key in ("purposes", "purpose", "intent"):
                value = receiver.get(surface_key)
                for marker in self._markers_in_value(value):
                    hits.append(
                        NegativClauseHit(
                            marker=marker,
                            location=f"payload.receiver_metadata.{surface_key}",
                            charter_ref=OFFENSIVE_MARKER_REGISTRY.charter_refs.get(
                                marker, "§1.0.E"
                            ),
                        )
                    )

        return NegativClauseValidatorResult(
            hits=tuple(hits),
            not_bindend_keys=tuple(not_bindend),
            bypass_flags=tuple(bypass_flags),
        )

    @staticmethod
    def _markers_in_value(value: Any) -> tuple[str, ...]:
        tokens: list[str] = []
        if isinstance(value, str):
            tokens = [value.upper()]
        elif isinstance(value, (list, tuple)):
            tokens = [str(item).upper() for item in value]
        found: list[str] = []
        for token in tokens:
            if token in OFFENSIVE_MARKER_REGISTRY.markers:
                found.append(token)
        return tuple(dict.fromkeys(found))
