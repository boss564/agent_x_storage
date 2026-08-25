"""Wave 39 configuration — fail-closed; no disable path.

Methodische Schwellen und Marker-Registry sind hier registriert (auditierbar),
nicht stillschweigend in types.py hardcodiert. Änderungen erfordern Charter-Amendment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

StrictMode = Literal["true", "strict"]

# Bindender Blocking-Schwellenwert — Charter §9.1 / WAVE39 Spec §2
ETHICAL_BLOCKING_SEVERITY_THRESHOLD: int = int(
    os.getenv("ETHICAL_BLOCKING_SEVERITY_THRESHOLD", "50")
)


class EthicalBoundaryConfigError(RuntimeError):
    """Raised when ethical boundary config is missing or attempts bypass."""


@dataclass(frozen=True)
class OffensiveMarkerRegistry:
    """Versionierte Heuristik-Liste — Charter §1.0.E Abdeckung."""

    version: str
    markers: frozenset[str]
    charter_refs: Mapping[str, str]

    def covers_charter_negation(self) -> frozenset[str]:
        return frozenset(self.charter_refs.values())


# Charter §1.0.E — fünf Negativ-Kategorien vollständig abgedeckt
OFFENSIVE_MARKER_REGISTRY = OffensiveMarkerRegistry(
    version="1.0",
    markers=frozenset(
        {
            "MEV_EXTRACTION",  # §1.0.E(a): aktive MEV-Extraktion
            "FRONTRUNNING",  # §1.0.E(b): Frontrunning
            "BACKRUNNING",  # §1.0.E(b): Backrunning zur Gewinnmaximierung
            "SANDWICH_ATTACK",  # §1.0.E(c): Sandwiching
            "OFFENSIVE_LIQUIDATION",  # §1.0.E(d): offensive Liquidationen
            "PROFIT_EXTRACTION",  # §1.0.E(e): Gewinn-Umleitung
            "GAIN_ROUTING",  # §1.0.E(e): automatisierte Gewinn-Umleitung
        }
    ),
    charter_refs={
        "MEV_EXTRACTION": "§1.0.E(a)",
        "FRONTRUNNING": "§1.0.E(b)",
        "BACKRUNNING": "§1.0.E(b)",
        "SANDWICH_ATTACK": "§1.0.E(c)",
        "OFFENSIVE_LIQUIDATION": "§1.0.E(d)",
        "PROFIT_EXTRACTION": "§1.0.E(e)",
        "GAIN_ROUTING": "§1.0.E(e)",
    },
)

OFFENSIVE_PURPOSE_MARKERS: frozenset[str] = OFFENSIVE_MARKER_REGISTRY.markers

CHARTER_PROFIT_SYSTEM_MARKERS: frozenset[str] = frozenset(
    {
        "titan-vault",  # Charter §5
        "titan_vault",
        "profit-optimizer",
        "offensive-searcher",
        "gain-routing-stack",
    }
)


def _parse_strict_mode(name: str, default: StrictMode = "true") -> StrictMode:
    raw = os.getenv(name, default).strip().lower()
    if raw not in ("true", "strict"):
        raise EthicalBoundaryConfigError(
            f"{name} must be 'true' or 'strict' (no disable path); got {raw!r}"
        )
    return raw  # type: ignore[return-value]


@dataclass(frozen=True)
class EthicalBoundaryConfig:
    """Immutable runtime config for Wave 39."""

    project_root: Path
    data_root: Path
    log_dir: Path
    charter_path: Path
    ethical_boundary_mandatory: StrictMode
    ethical_assertion_enabled: StrictMode
    defensive_scope_mandatory: StrictMode
    blocking_severity_threshold: int
    offensive_marker_version: str
    max_retries: int
    pipeline_timeout_s: float

    @classmethod
    def load(cls, project_root: Path | None = None) -> EthicalBoundaryConfig:
        root = project_root or Path(__file__).resolve().parent.parent.parent
        charter = Path(
            os.getenv("AGENT_X_CHARTER_PATH", str(root / "docs" / "AGENT_X_CHARTER.md"))
        )
        if not charter.is_file():
            raise EthicalBoundaryConfigError(
                f"Charter not found at {charter}; orchestrator refuses start"
            )

        threshold = int(os.getenv("ETHICAL_BLOCKING_SEVERITY_THRESHOLD", "50"))
        if not 0 <= threshold <= 100:
            raise EthicalBoundaryConfigError(
                f"ETHICAL_BLOCKING_SEVERITY_THRESHOLD must be in [0, 100]; got {threshold}"
            )

        return cls(
            project_root=root,
            data_root=Path(os.getenv("ETHICAL_BOUNDARY_DATA_ROOT", "data")),
            log_dir=Path(os.getenv("ETHICAL_BOUNDARY_LOG_DIR", "logs")),
            charter_path=charter,
            ethical_boundary_mandatory=_parse_strict_mode("ETHICAL_BOUNDARY_MANDATORY"),
            ethical_assertion_enabled=_parse_strict_mode("ETHICAL_ASSERTION_ENABLED"),
            defensive_scope_mandatory=_parse_strict_mode("DEFENSIVE_SCOPE_MANDATORY"),
            blocking_severity_threshold=threshold,
            offensive_marker_version=OFFENSIVE_MARKER_REGISTRY.version,
            max_retries=int(os.getenv("ETHICAL_BOUNDARY_MAX_RETRIES", "3")),
            pipeline_timeout_s=float(os.getenv("ETHICAL_BOUNDARY_TIMEOUT_S", "30")),
        )

    def ethical_root(self, user_id: str) -> Path:
        return self.data_root / user_id / "ethical_boundary"
