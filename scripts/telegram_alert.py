#!/usr/bin/env python3
"""Local / Cron Telegram alerts for Regime-Swarm (STALE, pod down, RT fail).

Loads project `.env` (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID or ADMIN_TELEGRAM_USER_ID).
Stdlib only. Never prints credential values.

Usage:
    python3 scripts/telegram_alert.py "test message"
    python3 scripts/telegram_alert.py --from-health
    SWARM_HEALTH_ALERT=false python3 scripts/swarm_health.py   # skip notify
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.raas_alert import (  # noqa: E402
    send_alert,
    send_alert_dedup,
    send_telegram,
    telegram_chat_id,
)

# Health components that should page (not optional OFF/IDLE paper state).
CRITICAL_COMPONENTS = (
    "CrossVenueMonitor",
    "FeedGapMonitor",
    "RegimeSwarmDaemon",
)


def load_project_env(path: Optional[Path] = None) -> Path:
    """Fill os.environ from `.env` without overwriting already-set keys."""
    env_path = path or (_ROOT / ".env")
    if not env_path.is_file():
        return env_path
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    if not os.environ.get("TELEGRAM_CHAT_ID") and os.environ.get("ADMIN_TELEGRAM_USER_ID"):
        os.environ["TELEGRAM_CHAT_ID"] = os.environ["ADMIN_TELEGRAM_USER_ID"].strip()
    if not os.environ.get("RAAS_STATE_DIR"):
        os.environ["RAAS_STATE_DIR"] = str(_ROOT / "data" / "raas" / "state")
    return env_path


def credentials_ok() -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    return bool(token and telegram_chat_id())


def health_problems(report: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    pod = report.get("pod")
    if not pod:
        problems.append("pod=UNREACHABLE")
    else:
        phase = str(pod.get("phase") or "")
        ready = str(pod.get("ready") or "")
        if phase != "Running" or ready != "true":
            problems.append(f"pod={pod.get('pod', '?')} phase={phase} ready={ready}")

    components = report.get("components") or {}
    for cid in CRITICAL_COMPONENTS:
        row = components.get(cid) or {}
        st = str(row.get("status") or "MISSING")
        if st in ("STALE", "MISSING", "IDLE"):
            problems.append(f"{cid}={st} age={row.get('age', '—')}")

    ac = report.get("astrocore_hook") or {}
    if ac.get("status") == "FAIL":
        problems.append(f"astrocore_hook=FAIL {ac.get('reason', '')}".strip())
    return problems


def format_health_alert(report: Dict[str, Any], problems: Sequence[str]) -> str:
    ts = str(report.get("generated_at") or "")
    pod = report.get("pod") or {}
    lines = [
        "🚨 Regime-Swarm Health",
        f"ts={ts}",
        f"pod={pod.get('pod', '—')} ns={pod.get('namespace', '—')}",
        "problems:",
        *[f"  • {p}" for p in problems],
    ]
    return "\n".join(lines)


def maybe_alert_health(report: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    load_project_env()
    raw = os.environ.get("SWARM_HEALTH_ALERT", "true").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return [{"ok": False, "skipped": True, "reason": "SWARM_HEALTH_ALERT=false"}]
    if not credentials_ok():
        return [{"ok": False, "skipped": True, "reason": "missing Telegram credentials"}]
    os.environ.setdefault("RAAS_ALERT_ENABLED", "true")
    problems = health_problems(report)
    if not problems:
        return None
    return send_alert_dedup("swarm_health", format_health_alert(report, problems))


def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram ops alert (no token echo)")
    parser.add_argument("message", nargs="*", help="Text to send")
    parser.add_argument(
        "--from-health",
        action="store_true",
        help="Run swarm_health and alert on STALE / pod down",
    )
    parser.add_argument("--json", action="store_true", help="JSON result (no secrets)")
    args = parser.parse_args()
    load_project_env()
    os.environ.setdefault("RAAS_ALERT_ENABLED", "true")

    if args.from_health:
        from scripts.swarm_health import collect_health_report

        report = collect_health_report()
        results = maybe_alert_health(report)
        if args.json:
            print(json.dumps({"problems": health_problems(report), "alert": results}, default=str))
        elif results is None:
            print("health OK — no Telegram sent")
        elif results and results[0].get("skipped"):
            print(f"alert skipped: {results[0].get('reason')}")
        else:
            ok = any(r.get("ok") for r in (results or []))
            print("Telegram sent" if ok else "Telegram send failed")
        return 0 if (results is None or any(r.get("ok") or r.get("skipped") for r in (results or []))) else 1

    text = " ".join(args.message).strip()
    if not text:
        print("Usage: telegram_alert.py <message> | --from-health", file=sys.stderr)
        return 2
    if not credentials_ok():
        print("missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (or ADMIN_TELEGRAM_USER_ID)", file=sys.stderr)
        return 1
    results = send_alert(text)
    if args.json:
        safe = [{k: v for k, v in r.items() if k != "response"} for r in results]
        print(json.dumps(safe))
    else:
        ok = any(r.get("ok") for r in results)
        print("Telegram sent" if ok else f"Telegram failed: {results}")
    return 0 if any(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
