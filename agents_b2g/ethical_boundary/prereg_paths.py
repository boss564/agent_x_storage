"""Pre-Reg document registry — paths relative to project root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class PreRegDocumentSpec:
    """One bindend Pre-Reg file tracked by Agent 1."""

    key: str
    relative_path: str

    def resolve(self, project_root: Path) -> Path:
        return project_root / self.relative_path


PREREG_DOCUMENTS: tuple[PreRegDocumentSpec, ...] = (
    PreRegDocumentSpec("bridge_stufe_a_v3", "docs/BRIDGE_STUFE_A_V3_PREREG.md"),
    PreRegDocumentSpec("bridge_diagnostic", "docs/BRIDGE_DIAGNOSTIC_PREREG.md"),
    PreRegDocumentSpec("wave38_live", "docs/WAVE38_LIVE_PREREG.md"),
)

PREREG_DOCUMENTS_BY_KEY: Mapping[str, PreRegDocumentSpec] = {
    spec.key: spec for spec in PREREG_DOCUMENTS
}
