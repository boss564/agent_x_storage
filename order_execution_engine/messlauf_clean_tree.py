"""M-W4 Clean-Tree check for Messlauf measurement paths (Bauplan §7 / Boss start).

Clean Tree (Operator-Definition):
  - ``git status --porcelain`` lines touching mess paths must be empty
  - no untracked *or* ignored files under mess paths

Ephemeral bytecode (``__pycache__/``, ``*.pyc``, ``.pytest_cache/``) is excluded
from the ignored-fail set — it is not measurement contamination (contrast:
foreign trees like ``var/wt64`` under a mess prefix *do* fail).

Non-mess-path untracked (e.g. historical report ZIPs under newsagent/reports/,
or Pre-Flight ``phase_c_a_prime_replay.py`` until P-0/P-1) are reported but do
not fail the gate — they are outside the M-W4 measurement tree.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

# Paths relative to repo root. Prefix-matched against porcelain paths.
# AX: source/ops/tests only — not historical local hub_*.zip archives at package root
# (those are gitignored local artefacts; foreign trees like var/wt64 still fail if
# they land under these prefixes).
AX_MESS_PREFIXES: tuple[str, ...] = (
    "order_execution_engine/messlauf_",
    "order_execution_engine/ops/",
    "order_execution_engine/tests/",
    "order_execution_engine/scripts/",
    # Top-level engine modules: matched specially in _is_mess_ax.
    "order_execution_engine/*.py",
)

# M-W4 / suite / messlauf orchestration — not Pre-Flight A′-Replay (P-0/P-1).
NA_MESS_PREFIXES: tuple[str, ...] = (
    "scripts/night_probe.sh",
    "scripts/run_10h_absence.sh",
    "scripts/run_engine_suite_pipefail.sh",
    "scripts/n4_classify_resolve.py",
    "scripts/forward_test_status.py",
    "scripts/absence_10h_synthesize.py",
    "scripts/phase_c_monitor.py",
    "scripts/vacuity_",
    "scripts/write_messlauf_manifest.py",
    "scripts/vacuity_m_w4_",
)

# Ignored paths that are never measurement contamination.
_EPHEMERAL_IGNORED_MARKERS: tuple[str, ...] = (
    "/__pycache__/",
    "__pycache__/",
    ".pyc",
    ".pytest_cache/",
)


@dataclass
class CleanTreeResult:
    repo: str
    root: Path
    ok: bool
    porcelain_all: List[str] = field(default_factory=list)
    porcelain_mess: List[str] = field(default_factory=list)
    ignored_mess: List[str] = field(default_factory=list)
    non_mess_untracked_n: int = 0
    detail: str = ""


def _run_git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode not in (0, 1):
        raise RuntimeError(
            f"git {' '.join(args)} rc={out.returncode}: {out.stderr.strip()}"
        )
    return out.stdout


def _porcelain_path(line: str) -> str:
    # "XY path" or "XY orig -> path" — take last token after optional rename.
    body = line[3:] if len(line) > 3 else line
    if " -> " in body:
        body = body.split(" -> ", 1)[1]
    return body.strip().strip('"')


def _is_mess(path: str, prefixes: Sequence[str]) -> bool:
    for p in prefixes:
        if p.endswith("*.py"):
            # order_execution_engine/*.py — exactly one path segment after dir.
            root = p[: -len("*.py")]
            if not path.startswith(root):
                continue
            rest = path[len(root) :]
            if rest.endswith(".py") and "/" not in rest:
                return True
            continue
        if path == p.rstrip("/") or path.startswith(p):
            return True
    return False


def _is_ephemeral_ignored(path: str) -> bool:
    if path.endswith(".pyc"):
        return True
    for m in _EPHEMERAL_IGNORED_MARKERS:
        if m in path or path.startswith(m.lstrip("/")):
            return True
    return False


def check_clean_tree(
    root: Path,
    *,
    repo: str,
    prefixes: Sequence[str],
) -> CleanTreeResult:
    """Return Clean-Tree verdict for one repo."""
    root = root.resolve()
    porcelain = [
        ln for ln in _run_git(root, "status", "--porcelain").splitlines() if ln.strip()
    ]
    mess_hits = [ln for ln in porcelain if _is_mess(_porcelain_path(ln), prefixes)]
    non_mess = [
        ln
        for ln in porcelain
        if ln.startswith("??") and not _is_mess(_porcelain_path(ln), prefixes)
    ]

    # Ignored files under mess prefixes (Boss: no ignored in mess paths),
    # minus ephemeral bytecode.
    ignored_raw = _run_git(
        root, "ls-files", "--others", "--ignored", "--exclude-standard"
    )
    ignored_mess = [
        p
        for p in ignored_raw.splitlines()
        if p.strip() and _is_mess(p, prefixes) and not _is_ephemeral_ignored(p)
    ]

    ok = not mess_hits and not ignored_mess
    detail = (
        f"mess_porcelain={len(mess_hits)} ignored_mess={len(ignored_mess)} "
        f"non_mess_untracked={len(non_mess)}"
    )
    return CleanTreeResult(
        repo=repo,
        root=root,
        ok=ok,
        porcelain_all=porcelain,
        porcelain_mess=mess_hits,
        ignored_mess=ignored_mess,
        non_mess_untracked_n=len(non_mess),
        detail=detail,
    )


def assert_clean_or_raise(results: Iterable[CleanTreeResult]) -> None:
    bad = [r for r in results if not r.ok]
    if not bad:
        return
    parts = []
    for r in bad:
        parts.append(
            f"{r.repo}: {r.detail}\n"
            f"  porcelain_mess={r.porcelain_mess!r}\n"
            f"  ignored_mess={r.ignored_mess!r}"
        )
    raise AssertionError("Clean-Tree FAIL\n" + "\n".join(parts))
