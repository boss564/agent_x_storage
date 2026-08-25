"""Structural read-only enforcement for sealed Bridge reference artifacts (Wave 38).

Reference JSONs are loaded from a dedicated read path; live captures write only
under ``{data_root}/{user_id}/wave38/live/``. Mutations to registered reference
files are detected via content hash and hard-blocked on write.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


class ReferenceArtifactMutationError(PermissionError):
    """Raised when a sealed reference artifact changed or a write was attempted."""


class ReferenceWriteForbiddenError(PermissionError):
    """Raised when a write targets a registered reference artifact path."""


DEFAULT_REFERENCE_ARTIFACTS: tuple[str, ...] = (
    "bridge_stufe_a_v3_ergebnis.json",
    "bridge_stufe_a_v3_integrity_gate.json",
    "bridge_stufe_a_v3_coverage_gate.json",
    "bridge_diagnostic_ergebnis.json",
    "bridge_diagnostic_ablation.json",
    "bridge_diagnostic_permutation.json",
    "bridge_diagnostic_kfold.json",
    "bridge_diagnostic_informativity_gate.json",
)


def _sha3_file(path: Path) -> str:
    digest = hashlib.sha3_256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ReferenceArtifactGuard:
    """Tracks sealed Bridge artifacts by absolute path + content hash."""

    project_root: Path
    artifact_names: tuple[str, ...] = DEFAULT_REFERENCE_ARTIFACTS
    _paths: tuple[Path, ...] = field(init=False, default=())
    _hashes: dict[str, str] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        root = self.project_root.resolve()
        paths: list[Path] = []
        hashes: dict[str, str] = {}
        for name in self.artifact_names:
            candidate = (root / name).resolve()
            paths.append(candidate)
            if candidate.is_file():
                hashes[str(candidate)] = _sha3_file(candidate)
        self._paths = tuple(paths)
        self._hashes = hashes

    @property
    def registered_paths(self) -> tuple[Path, ...]:
        return self._paths

    def is_reference_path(self, path: Path | str) -> bool:
        resolved = Path(path).resolve()
        return any(resolved == ref.resolve() for ref in self._paths)

    def verify_unchanged(self) -> None:
        """Re-hash registered files; raise if any content drifted."""
        for path in self._paths:
            key = str(path.resolve())
            if not path.is_file():
                if key in self._hashes:
                    raise ReferenceArtifactMutationError(
                        f"Reference artifact removed: {path}"
                    )
                continue
            current = _sha3_file(path)
            if key in self._hashes and current != self._hashes[key]:
                raise ReferenceArtifactMutationError(
                    f"Reference artifact mutated: {path}"
                )

    def assert_write_allowed(self, path: Path | str) -> None:
        if self.is_reference_path(path):
            raise ReferenceWriteForbiddenError(
                f"Write blocked — sealed reference artifact: {path}"
            )

    def load_json(self, path: Path | str) -> dict[str, Any]:
        target = Path(path)
        self.assert_write_allowed(target)  # no-op for reads; guards mistaken paths
        if self.is_reference_path(target):
            self.verify_unchanged()
        with target.open(encoding="utf-8") as handle:
            return json.load(handle)

    def snapshot_hashes(self) -> dict[str, str]:
        return dict(self._hashes)

    def compute_hashes(self) -> dict[str, str]:
        """Fresh content hashes of registered files (for E2E mutation checks)."""
        out: dict[str, str] = {}
        for path in self._paths:
            if path.is_file():
                out[str(path.resolve())] = _sha3_file(path)
        return out


def resolve_live_root(data_root: Path, user_id: str) -> Path:
    return (data_root / user_id / "wave38" / "live").resolve()


def resolve_reference_root(data_root: Path, user_id: str) -> Path:
    return (data_root / user_id / "wave38" / "reference").resolve()


def ensure_live_directory(data_root: Path, user_id: str) -> Path:
    live = resolve_live_root(data_root, user_id)
    live.mkdir(parents=True, exist_ok=True)
    return live


def iter_reference_only(paths: Iterable[Path | str], guard: ReferenceArtifactGuard) -> list[Path]:
    return [Path(p).resolve() for p in paths if guard.is_reference_path(p)]
