"""Derive news-agent scheduler cadence from installed schedule (crontab / launchd).

G1 ``interval_min`` must match the real fire rate — not an env var alone.
Pre-Reg: NEWS_24H_SCHEDULER_GATE.md §8.6 · Amendment A3 · A3.1.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

NEWS_AGENT_CRON_MARKER = "# AGENTX_NEWS_AGENT"
LAUNCHD_LABEL = "com.agentx.news-agent"
DEFAULT_SCHEDULER_INTERVAL_MIN = 60


def crontab_lines() -> List[str]:
    proc = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        err = (proc.stderr or "") + (proc.stdout or "")
        if "no crontab" in err.lower():
            return []
        return []
    return [ln.rstrip("\n") for ln in proc.stdout.splitlines()]


def news_agent_cron_line(lines: Optional[List[str]] = None) -> Optional[str]:
    rows = crontab_lines() if lines is None else lines
    matches = [ln for ln in rows if NEWS_AGENT_CRON_MARKER in ln]
    if not matches:
        return None
    return matches[0]


def parse_interval_minutes_from_cron_fields(minute: str, hour: str) -> Optional[int]:
    """
  Supported installer patterns:
    0 * * * *     → 60 (hourly :00)
    5 * * * *     → 60 (hourly :05 — not a 5-min cadence)
    */5 * * * *   → 5
    */15 * * * *  → 15
    """
    if minute.startswith("*/"):
        try:
            step = int(minute[2:])
        except ValueError:
            return None
        if step <= 0 or step > 59:
            return None
        if hour == "*":
            return step
        return None
    if hour == "*" and minute.isdigit():
        return 60
    if hour.startswith("*/") and minute == "0":
        try:
            hstep = int(hour[2:])
        except ValueError:
            return None
        if hstep <= 0:
            return None
        return hstep * 60
    return None


def interval_minutes_from_cron_line(line: str) -> Optional[int]:
    body = line.split(NEWS_AGENT_CRON_MARKER, 1)[0].strip()
    parts = body.split()
    if len(parts) < 5:
        return None
    return parse_interval_minutes_from_cron_fields(parts[0], parts[1])


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def interval_minutes_from_launchd_plist(plist: Optional[Path] = None) -> Optional[int]:
    path = launchd_plist_path() if plist is None else plist
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        data = plistlib.load(handle)
    cal = data.get("StartCalendarInterval")
    if not isinstance(cal, dict):
        return None
    minute = cal.get("Minute")
    hour = cal.get("Hour")
    if hour is None and minute is not None:
        return 60
    if minute is not None and hour is not None:
        return 60
    return None


def _env_interval(name: str) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    try:
        val = int(float(raw))
    except (TypeError, ValueError):
        return None
    return max(1, val)


def measure_scheduler_interval_minutes() -> Tuple[int, str]:
    """
    Return (interval_min, source).

    Priority: crontab → launchd (macOS) → NEWS_SCHEDULER_INTERVAL_MINUTES →
    WATCHDOG_CRON_INTERVAL_MINUTES → default 60.

    Env is fallback when schedule is unreadable — not a substitute for crontab.
    """
    line = news_agent_cron_line()
    if line is not None:
        parsed = interval_minutes_from_cron_line(line)
        if parsed is not None:
            return parsed, "crontab"

    if os.name != "nt":
        import sys

        if sys.platform == "darwin":
            launchd = interval_minutes_from_launchd_plist()
            if launchd is not None:
                return launchd, "launchd"

    for name in ("NEWS_SCHEDULER_INTERVAL_MINUTES", "WATCHDOG_CRON_INTERVAL_MINUTES"):
        env_val = _env_interval(name)
        if env_val is not None:
            return env_val, f"env:{name}"

    return DEFAULT_SCHEDULER_INTERVAL_MIN, "default"


def get_scheduler_interval_from_system() -> int:
    """Platform schedule interval for G1 (crontab → launchd → env → 60)."""
    interval, _source = measure_scheduler_interval_minutes()
    return interval


def scheduler_interval_env_mismatch(schedule_interval: int, schedule_source: str) -> Optional[str]:
    """If env is set but disagrees with measured schedule, return error text."""
    if schedule_source not in ("crontab", "launchd"):
        return None
    env_val = _env_interval("NEWS_SCHEDULER_INTERVAL_MINUTES")
    if env_val is None:
        return None
    if env_val != schedule_interval:
        return (
            f"NEWS_SCHEDULER_INTERVAL_MINUTES={env_val} != "
            f"schedule={schedule_interval} ({schedule_source})"
        )
    return None


def cron_schedule_summary(line: Optional[str] = None) -> str:
    """Human-readable minute/hour fields for status output."""
    if line is None:
        line = news_agent_cron_line()
    if line is None:
        return "none"
    body = line.split(NEWS_AGENT_CRON_MARKER, 1)[0].strip()
    parts = body.split()
    if len(parts) < 2:
        return body[:40]
    return f"{parts[0]} {parts[1]} * * *"
