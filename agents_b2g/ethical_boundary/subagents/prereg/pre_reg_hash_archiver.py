"""W39-A1-S2 — validate WORM SHA-256 hashes against registered baseline."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from agents_b2g.ethical_boundary.prereg_paths import PREREG_DOCUMENTS


@dataclass(frozen=True)
class PreRegHashMismatch:
    key: str
    expected: str
    actual: str
    path: str


@dataclass(frozen=True)
class PreRegHashArchiverResult:
    validated_hashes: dict[str, str]
    mismatches: tuple[PreRegHashMismatch, ...]
    missing_registry_keys: tuple[str, ...]
    registry_error: str | None


class PreRegHashArchiver:
    subagent_id = "W39-A1-S2"

    def run(
        self,
        project_root: Path,
        *,
        registry_path: Path,
    ) -> PreRegHashArchiverResult:
        try:
            registry = self._load_registry(registry_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return PreRegHashArchiverResult(
                validated_hashes={},
                mismatches=(),
                missing_registry_keys=tuple(spec.key for spec in PREREG_DOCUMENTS),
                registry_error=str(exc),
            )

        expected = self._expected_hashes(registry)
        mismatches: list[PreRegHashMismatch] = []
        missing_keys: list[str] = []
        validated: dict[str, str] = {}

        for spec in PREREG_DOCUMENTS:
            if spec.key not in expected:
                missing_keys.append(spec.key)
                continue
            path = spec.resolve(project_root)
            if not path.is_file():
                mismatches.append(
                    PreRegHashMismatch(
                        key=spec.key,
                        expected=expected[spec.key],
                        actual="",
                        path=str(path),
                    )
                )
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            worm = expected[spec.key]
            if actual != worm:
                mismatches.append(
                    PreRegHashMismatch(
                        key=spec.key,
                        expected=worm,
                        actual=actual,
                        path=spec.relative_path,
                    )
                )
            else:
                validated[spec.key] = worm

        return PreRegHashArchiverResult(
            validated_hashes=validated,
            mismatches=tuple(mismatches),
            missing_registry_keys=tuple(missing_keys),
            registry_error=None,
        )

    @staticmethod
    def _load_registry(registry_path: Path) -> Mapping[str, Any]:
        if not registry_path.is_file():
            raise FileNotFoundError(f"WORM registry missing: {registry_path}")
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("registry root must be object")
        return data

    @staticmethod
    def _expected_hashes(registry: Mapping[str, Any]) -> dict[str, str]:
        raw = registry.get("hashes")
        if not isinstance(raw, dict):
            raise ValueError("registry missing hashes object")
        out: dict[str, str] = {}
        for key, entry in raw.items():
            if isinstance(entry, str):
                out[str(key)] = entry
            elif isinstance(entry, dict) and "sha256" in entry:
                out[str(key)] = str(entry["sha256"])
            else:
                raise ValueError(f"invalid hash entry for {key!r}")
        return out

    @staticmethod
    def default_registry_path(project_root: Path) -> Path:
        return project_root / "config" / "ethical_boundary_prereg_hashes.json"

    @staticmethod
    def user_registry_path(data_root: Path, user_id: str) -> Path:
        return data_root / user_id / "ethical_boundary" / "prereg_hashes.json"
