"""W39-A6-S3 — load AGENT_X_CHARTER.md and validate version metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LoadedCharter:
    path: Path
    version: str
    text: str


@dataclass(frozen=True)
class CharterLoaderResult:
    charter: LoadedCharter | None
    error: str | None


class CharterLoader:
    subagent_id = "W39-A6-S3"

    def load(self, charter_path: Path) -> CharterLoaderResult:
        if not charter_path.is_file():
            return CharterLoaderResult(
                charter=None,
                error=f"charter not found: {charter_path}",
            )
        try:
            text = charter_path.read_text(encoding="utf-8")
        except OSError as exc:
            return CharterLoaderResult(
                charter=None,
                error=f"charter unreadable: {exc}",
            )
        version = self._parse_version(text)
        if not version:
            return CharterLoaderResult(
                charter=None,
                error="charter missing **Version:** metadata",
            )
        return CharterLoaderResult(
            charter=LoadedCharter(path=charter_path, version=version, text=text),
            error=None,
        )

    @staticmethod
    def _parse_version(text: str) -> str | None:
        for line in text.splitlines():
            if line.startswith("**Version:**"):
                return line.split(":", 1)[1].strip().split()[0]
        return None
