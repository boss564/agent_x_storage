"""W39-A1-S1 — load bindend Pre-Reg documents; verify existence and status."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from agents_b2g.ethical_boundary.prereg_paths import PREREG_DOCUMENTS, PreRegDocumentSpec


@dataclass(frozen=True)
class LoadedPreRegDocument:
    key: str
    path: Path
    text: str
    bindend: bool


@dataclass(frozen=True)
class PreRegLoaderResult:
    documents: tuple[LoadedPreRegDocument, ...]
    missing: tuple[str, ...]
    not_bindend: tuple[str, ...]


class PreRegLoader:
    subagent_id = "W39-A1-S1"

    def run(self, project_root: Path) -> PreRegLoaderResult:
        documents: list[LoadedPreRegDocument] = []
        missing: list[str] = []
        not_bindend: list[str] = []

        for spec in PREREG_DOCUMENTS:
            path = spec.resolve(project_root)
            if not path.is_file():
                missing.append(spec.key)
                continue
            text = path.read_text(encoding="utf-8")
            bindend = self._is_bindend(text)
            if not bindend:
                not_bindend.append(spec.key)
            documents.append(
                LoadedPreRegDocument(
                    key=spec.key,
                    path=path,
                    text=text,
                    bindend=bindend,
                )
            )

        return PreRegLoaderResult(
            documents=tuple(documents),
            missing=tuple(missing),
            not_bindend=tuple(not_bindend),
        )

    @staticmethod
    def _is_bindend(text: str) -> bool:
        lowered = text.lower()
        return "bindend" in lowered

    @staticmethod
    def spec_for_key(key: str) -> PreRegDocumentSpec | None:
        for spec in PREREG_DOCUMENTS:
            if spec.key == key:
                return spec
        return None
