#!/usr/bin/env python3
"""OS-isolation screen for Sub-Swarm Dockerfiles (D2 consolidation).

Static checks (always):
  - USER is non-root (redteam / numeric uid ≠ 0)
  - Runtime intent documents --read-only and --cap-drop ALL
  - No core/worm/gateway volume mounts in Dockerfile comments/COPY
  - Both MEV and Oracle plugins covered

Optional live check (if docker available + OS_ISOLATION_LIVE=1):
  - docker run --read-only --cap-drop ALL --user … whoami / id

Does not start Stage-2. Charter: live_execution=false

Usage:
  PYTHONPATH=. python3 scripts/test_os_isolation_subswarms.py
  make raas-os-isolation
  OS_ISOLATION_LIVE=1 make raas-os-isolation
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_ROOT = Path(__file__).resolve().parents[1]

DOCKERFILES = [
    _ROOT / "plugins" / "mev_latency_redteam" / "Dockerfile",
    _ROOT / "plugins" / "oracle_anomaly_swarm" / "Dockerfile",
]

_FORBIDDEN_MOUNT_HINTS = (
    "worm",
    "trusted_gateway",
    "supranode_facade",
    "raas_portal",
    "/data/raas/worm",
)


def _ok(name: str) -> None:
    print(f"  PASS  {name}")


def _fail(name: str) -> None:
    print(f"  FAIL  {name}")


def _parse_user(text: str) -> str | None:
    users = re.findall(r"(?m)^\s*USER\s+(\S+)", text)
    return users[-1] if users else None


def check_dockerfile(path: Path) -> Tuple[int, List[str]]:
    failed = 0
    notes: List[str] = []
    label = path.parent.name
    if not path.is_file():
        _fail(f"{label}: Dockerfile missing")
        return 1, [f"missing:{path}"]

    text = path.read_text(encoding="utf-8")
    user = _parse_user(text)
    if user is None:
        _fail(f"{label}: no USER directive")
        failed += 1
    elif user in ("root", "0", "0:0"):
        _fail(f"{label}: USER is root ({user})")
        failed += 1
    else:
        _ok(f"{label}: USER={user} (non-root)")
        notes.append(f"user={user}")

    if "--read-only" in text:
        _ok(f"{label}: documents --read-only")
    else:
        _fail(f"{label}: missing --read-only runtime intent")
        failed += 1

    if "cap-drop ALL" in text or "--cap-drop ALL" in text:
        _ok(f"{label}: documents --cap-drop ALL")
    else:
        _fail(f"{label}: missing --cap-drop ALL runtime intent")
        failed += 1

    if "Does NOT mount" in text or "Does NOT mount core" in text:
        _ok(f"{label}: documents no core/worm mount")
    else:
        # soft: still fail if COPY clearly pulls worm/core
        _fail(f"{label}: missing 'Does NOT mount' isolation note")
        failed += 1

    lower = text.lower()
    # COPY of plugin itself is fine; forbid mounting worm/core paths as volumes
    bad = []
    for hint in _FORBIDDEN_MOUNT_HINTS:
        if hint in ("worm",) and "does not mount" in lower:
            continue
        # volume-style hints
        if f"-v " in lower and hint in lower:
            bad.append(hint)
        if f"volume" in lower and "worm" in hint and "/data/raas/worm" in lower:
            bad.append(hint)
    if bad:
        _fail(f"{label}: forbidden mount hints {bad}")
        failed += 1
    else:
        _ok(f"{label}: no forbidden volume mounts in Dockerfile")

    if "nats-py" in text or "nats" in lower:
        notes.append("nats_worker")

    return failed, notes


def optional_live_docker() -> Tuple[int, str]:
    """Best-effort: verify docker CLI accepts isolation flags (no image build required)."""
    if os.environ.get("OS_ISOLATION_LIVE", "0") not in ("1", "true", "TRUE"):
        return 0, "skipped (set OS_ISOLATION_LIVE=1 for live)"

    if shutil.which("docker") is None:
        print("  SKIP  docker CLI not found")
        return 0, "skipped_no_docker"

    # Use alpine to validate flags without building plugin images
    cmd = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "10001:10001",
        "alpine:3.20",
        "id",
        "-u",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except Exception as exc:
        _fail(f"live docker run: {exc}")
        return 1, str(exc)

    if proc.returncode != 0:
        _fail(f"live docker isolation run failed: {proc.stderr.strip()[:200]}")
        return 1, proc.stderr.strip()[:200]

    uid = proc.stdout.strip()
    if uid == "10001":
        _ok("live docker: --read-only --cap-drop ALL --user 10001 works")
        return 0, f"uid={uid}"
    _fail(f"live docker: unexpected uid {uid!r}")
    return 1, uid


def main() -> int:
    print("OS isolation — Sub-Swarm Dockerfiles (D2 consolidation)")
    print("=" * 60)
    failed = 0
    details: Dict[str, Any] = {"dockerfiles": {}}

    for path in DOCKERFILES:
        f, notes = check_dockerfile(path)
        failed += f
        details["dockerfiles"][path.parent.name] = {
            "path": str(path.relative_to(_ROOT)),
            "failed": f,
            "notes": notes,
        }

    live_failed, live_note = optional_live_docker()
    failed += live_failed
    details["live"] = live_note

    verdict = "OS_ISOLATION_PASS" if failed == 0 else "OS_ISOLATION_FAIL"
    print("=" * 60)
    print(f"VERDICT: {verdict}")

    out = _ROOT / "data" / "raas" / "os_isolation_last.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({"verdict": verdict, "failed": failed, **details}, indent=2),
            encoding="utf-8",
        )
        print(f"artifact: {out}")
    except OSError as exc:
        print(f"artifact: skipped ({exc})")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
