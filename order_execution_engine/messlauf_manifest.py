"""M-W4 Messlauf Manifest — Freeze-Pin + Clean-Tree + Charter + Quarantäne.

Hash-Zusammenhang (ein Satz):
  ``5adab542…`` = SHA-256 der kanonischen ``allowlist.freeze.json`` (Markt-Freeze-
  Inhalt, committed unter ``07a06d1c``); ``487b3547…`` = ``stash@{0}``-Objekt mit
  konfligierendem Freeze/Feed-Dirty (Quarantäne, do-not-drop); ``43445de8…`` =
  SHA-256 des Stash-Patches (Integritätswächter). Der neue Code-Freeze-Pin ist der
  Git-SHA des letzten Code-Commits nach M-W4 und bindet, *welcher Code* gegen den
  unveränderten Allowlist-Freeze ``5adab542…`` laufen darf — Tip danach nur
  docs/reports, belegt per Diff Pin..Tip.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from order_execution_engine.fill_simulator import FillSimConfig
from order_execution_engine.messlauf_clean_tree import (
    AX_MESS_PREFIXES,
    NA_MESS_PREFIXES,
    CleanTreeResult,
    check_clean_tree,
)

# Historical allowlist.freeze.json content pin (unchanged; history only for M-W4).
ALLOWLIST_FREEZE_SHA_HISTORICAL = (
    "5adab54278462f16eac4538b75e75f027fb3b41411e2da7bfe1a73d4826b7379"
)
STASH_REV_QUARANTINE = "487b354709c7dbb682f7f66bbcaaf5bf5348b146"
STASH_PATCH_SHA_QUARANTINE = (
    "43445de8b58fdd6cd2aae4c0c03c8d1ebfd33e8991556086e6f1a2fbca1b2bdd"
)
HASH_RELATION_DE = (
    "5adab542… = SHA-256 von allowlist.freeze.json (Markt-Freeze-Inhalt); "
    "487b3547… = stash@{0}-Rev mit konfligierendem Freeze/Feed-Dirty (Quarantäne); "
    "43445de8… = SHA-256 des Stash-Patches; "
    "code_freeze_pin = Git-SHA des letzten M-W4-Code-Commits (welcher Code gegen "
    "5adab542… laufen darf) — Tip danach nur docs/reports."
)


@dataclass
class MesslaufManifest:
    utc: str
    wave: str
    code_freeze_pin_ax: str
    code_freeze_pin_na: str
    tip_ax: str
    tip_na: str
    allowlist_freeze_sha: str
    allowlist_freeze_sha_historical: str
    stash_rev: str
    stash_patch_sha: str
    hash_relation: str
    clean_tree_ax: Dict[str, Any]
    clean_tree_na: Dict[str, Any]
    charter: Dict[str, Any]
    suite: Dict[str, Any]
    pin_to_tip_ax_docs_only: bool
    pin_to_tip_na_docs_only: bool
    pin_to_tip_ax_paths: List[str] = field(default_factory=list)
    pin_to_tip_na_paths: List[str] = field(default_factory=list)
    kein_lauf: bool = True
    push: str = "held"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(
            f"git -C {root} {' '.join(args)} rc={out.returncode}: {out.stderr.strip()}"
        )
    return out.stdout.strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def measure_stash_quarantine(ax_root: Path) -> tuple[str, str]:
    """Return (stash_rev, patch_sha) for stash@{0}; must match quarantine pins."""
    rev = _git(ax_root, "rev-parse", "stash@{0}")
    patch = subprocess.run(
        ["git", "-C", str(ax_root), "stash", "show", "-p", "stash@{0}"],
        capture_output=True,
        check=True,
    ).stdout
    patch_sha = hashlib.sha256(patch).hexdigest()
    return rev, patch_sha


def paths_changed(root: Path, a: str, b: str) -> List[str]:
    if a == b:
        return []
    out = _git(root, "diff", "--name-only", f"{a}..{b}")
    return [ln for ln in out.splitlines() if ln.strip()]


def _is_docs_only(paths: List[str]) -> bool:
    if not paths:
        return True
    for p in paths:
        if p.startswith("docs/") or p.startswith("reports/"):
            continue
        return False
    return True


def charter_snapshot() -> Dict[str, Any]:
    cfg = FillSimConfig()
    # Default lives on FillSimConfig — no literal year/ms copy in this module.
    default_ms = int(FillSimConfig.model_fields["max_book_age_ms"].default)
    return {
        "order_send": False,
        "diagnostic_only": True,
        "max_book_age_ms": int(cfg.max_book_age_ms),
        "max_book_age_ms_default": default_ms,
        "max_book_age_ms_ok": int(cfg.max_book_age_ms) == default_ms,
    }


def build_manifest(
    *,
    ax_root: Path,
    na_root: Path,
    code_freeze_pin_ax: str,
    code_freeze_pin_na: str,
    suite: Optional[Dict[str, Any]] = None,
    allow_dirty_for_test: bool = False,
) -> MesslaufManifest:
    ax_root = ax_root.resolve()
    na_root = na_root.resolve()
    freeze_path = ax_root / "order_execution_engine" / "ops" / "allowlist.freeze.json"
    freeze_sha = sha256_file(freeze_path)
    if freeze_sha != ALLOWLIST_FREEZE_SHA_HISTORICAL:
        raise AssertionError(
            f"allowlist.freeze.json sha changed: {freeze_sha} != "
            f"{ALLOWLIST_FREEZE_SHA_HISTORICAL}"
        )

    stash_rev, stash_patch = measure_stash_quarantine(ax_root)
    if stash_rev != STASH_REV_QUARANTINE:
        raise AssertionError(
            f"stash@{{0}} rev drift: {stash_rev} != {STASH_REV_QUARANTINE}"
        )
    if stash_patch != STASH_PATCH_SHA_QUARANTINE:
        raise AssertionError(
            f"stash patch-sha drift: {stash_patch} != {STASH_PATCH_SHA_QUARANTINE}"
        )

    ct_ax = check_clean_tree(ax_root, repo="agent_x", prefixes=AX_MESS_PREFIXES)
    ct_na = check_clean_tree(na_root, repo="newsagent", prefixes=NA_MESS_PREFIXES)
    if not allow_dirty_for_test:
        if not ct_ax.ok or not ct_na.ok:
            raise AssertionError(
                f"Clean-Tree FAIL ax={ct_ax.detail} na={ct_na.detail} "
                f"ax_mess={ct_ax.porcelain_mess} na_mess={ct_na.porcelain_mess}"
            )

    tip_ax = _git(ax_root, "rev-parse", "HEAD")
    tip_na = _git(na_root, "rev-parse", "HEAD")
    ax_paths = paths_changed(ax_root, code_freeze_pin_ax, tip_ax)
    na_paths = paths_changed(na_root, code_freeze_pin_na, tip_na)

    return MesslaufManifest(
        utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        wave="M-W4",
        code_freeze_pin_ax=code_freeze_pin_ax,
        code_freeze_pin_na=code_freeze_pin_na,
        tip_ax=tip_ax,
        tip_na=tip_na,
        allowlist_freeze_sha=freeze_sha,
        allowlist_freeze_sha_historical=ALLOWLIST_FREEZE_SHA_HISTORICAL,
        stash_rev=stash_rev,
        stash_patch_sha=stash_patch,
        hash_relation=HASH_RELATION_DE,
        clean_tree_ax={
            "ok": ct_ax.ok,
            "detail": ct_ax.detail,
            "porcelain_mess": ct_ax.porcelain_mess,
            "ignored_mess": ct_ax.ignored_mess,
            "non_mess_untracked_n": ct_ax.non_mess_untracked_n,
            "cmd": "git status --porcelain (mess-path prefixes)",
        },
        clean_tree_na={
            "ok": ct_na.ok,
            "detail": ct_na.detail,
            "porcelain_mess": ct_na.porcelain_mess,
            "ignored_mess": ct_na.ignored_mess,
            "non_mess_untracked_n": ct_na.non_mess_untracked_n,
            "cmd": "git status --porcelain (mess-path prefixes)",
        },
        charter=charter_snapshot(),
        suite=suite or {"status": "pending"},
        pin_to_tip_ax_docs_only=_is_docs_only(ax_paths),
        pin_to_tip_na_docs_only=_is_docs_only(na_paths),
        pin_to_tip_ax_paths=ax_paths,
        pin_to_tip_na_paths=na_paths,
        kein_lauf=True,
        push="held",
        notes=[
            "allowlist.freeze.json content pin unchanged (historical 5adab542…)",
            "code_freeze_pin = last M-W4 code commit; tip may advance docs/reports only",
            "S2-W4 N-2 xfail stub not in scope (M-W5)",
        ],
    )


def write_manifest(manifest: MesslaufManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clean_tree_result_to_public(r: CleanTreeResult) -> Dict[str, Any]:
    return {
        "repo": r.repo,
        "ok": r.ok,
        "detail": r.detail,
        "porcelain_mess": r.porcelain_mess,
        "ignored_mess": r.ignored_mess,
        "non_mess_untracked_n": r.non_mess_untracked_n,
    }
