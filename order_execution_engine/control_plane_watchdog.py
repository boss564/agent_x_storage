"""L2 Watchdog — read-only stuck-RUNNING detection (E-1-LA precursor).

Freeze rules (L2-d): code + tests only until E-1 — do **not** install launchd.
Never writes the lease/telemetry DB (L2-c). Failures of the watchdog itself are
reported as alarms (fail-closed alarm path) without touching the runner process
(fail-open vs runner).

T_max default = 2 × TTL_MAX_S (lease token ceiling). A RUNNING run older than
that is treated as hung — token TTL no longer applies after claim.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional, TextIO

from order_execution_engine.control_plane_lease import (
    TTL_MAX_S,
    connect_control_plane_ro,
)

# L2-a: justified multiple of lease TTL ceiling (TTL_MAX_S=900 → 1800s).
DEFAULT_T_MAX_S = 2 * TTL_MAX_S
ENV_T_MAX = "CONTROL_PLANE_WATCHDOG_T_MAX_S"

EXIT_OK = 0
EXIT_STUCK = 2  # hung RUNNING detected → alarm
EXIT_WATCHDOG_ERROR = 3  # watchdog itself failed (still emit alarm)


@dataclass(frozen=True)
class StuckRun:
    run_id: int
    started_at: float
    age_s: float


@dataclass(frozen=True)
class WatchdogReport:
    ok: bool
    action: str
    t_max_s: float
    checked_at: float
    running_count: int
    stuck: list[StuckRun]
    alarm: bool
    alarm_channel: str
    error: Optional[str] = None
    db_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stuck"] = [asdict(s) for s in self.stuck]
        return d


def resolve_t_max_s(override: Optional[float] = None) -> float:
    if override is not None:
        if override <= 0:
            raise ValueError(f"t_max_s must be > 0, got {override}")
        return float(override)
    raw = os.environ.get(ENV_T_MAX, "").strip()
    if raw:
        val = float(raw)
        if val <= 0:
            raise ValueError(f"{ENV_T_MAX} must be > 0, got {raw!r}")
        return val
    return float(DEFAULT_T_MAX_S)


def _emit_alarm(
    report: WatchdogReport,
    *,
    alarm_log: Optional[Path],
    stream: TextIO,
) -> None:
    """L2-b: alarm channel = JSON line on stream + optional append-only log file."""
    line = json.dumps(
        {"channel": "control_plane_watchdog", **report.to_dict()},
        sort_keys=True,
    )
    stream.write(line + "\n")
    stream.flush()
    if alarm_log is not None:
        alarm_log.parent.mkdir(parents=True, exist_ok=True)
        with alarm_log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def scan_stuck_running(
    conn: Any,
    *,
    t_max_s: float,
    now: Optional[float] = None,
) -> list[StuckRun]:
    """Pure read of telemetry_runs RUNNING rows older than t_max_s."""
    now_s = float(time.time() if now is None else now)
    rows = conn.execute(
        "SELECT run_id, started_at FROM telemetry_runs"
        " WHERE status='RUNNING' ORDER BY run_id"
    ).fetchall()
    stuck: list[StuckRun] = []
    for rr in rows:
        started = float(rr[1] or 0.0)
        age = max(0.0, now_s - started)
        if age > t_max_s:
            stuck.append(
                StuckRun(run_id=int(rr[0]), started_at=started, age_s=age)
            )
    return stuck


def check_running_leases(
    db_path: Path,
    *,
    t_max_s: Optional[float] = None,
    allow_live: bool = False,
    now: Optional[float] = None,
    alarm_log: Optional[Path] = None,
    alarm_stream: Optional[TextIO] = None,
    connect_ro: Callable[..., Any] = connect_control_plane_ro,
) -> WatchdogReport:
    """RO scan; emit alarm if stuck RUNNING found or watchdog errors."""
    stream = alarm_stream if alarm_stream is not None else sys.stderr
    checked_at = float(time.time() if now is None else now)
    try:
        tmax = resolve_t_max_s(t_max_s)
    except ValueError as exc:
        report = WatchdogReport(
            ok=False,
            action="watchdog-check",
            t_max_s=0.0,
            checked_at=checked_at,
            running_count=0,
            stuck=[],
            alarm=True,
            alarm_channel="stderr+optional_log",
            error=str(exc),
            db_path=str(db_path),
        )
        _emit_alarm(report, alarm_log=alarm_log, stream=stream)
        return report

    try:
        conn = connect_ro(Path(db_path), allow_live=allow_live)
    except Exception as exc:  # noqa: BLE001 — fail-open vs runner; alarm closed
        report = WatchdogReport(
            ok=False,
            action="watchdog-check",
            t_max_s=tmax,
            checked_at=checked_at,
            running_count=0,
            stuck=[],
            alarm=True,
            alarm_channel="stderr+optional_log",
            error=f"watchdog RO open failed: {exc}",
            db_path=str(db_path),
        )
        _emit_alarm(report, alarm_log=alarm_log, stream=stream)
        return report

    try:
        try:
            running_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM telemetry_runs WHERE status='RUNNING'"
                ).fetchone()[0]
            )
            stuck = scan_stuck_running(conn, t_max_s=tmax, now=checked_at)
        except Exception as exc:  # noqa: BLE001
            report = WatchdogReport(
                ok=False,
                action="watchdog-check",
                t_max_s=tmax,
                checked_at=checked_at,
                running_count=0,
                stuck=[],
                alarm=True,
                alarm_channel="stderr+optional_log",
                error=f"watchdog query failed: {exc}",
                db_path=str(db_path),
            )
            _emit_alarm(report, alarm_log=alarm_log, stream=stream)
            return report
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    alarm = bool(stuck)
    report = WatchdogReport(
        ok=not alarm,
        action="watchdog-check",
        t_max_s=tmax,
        checked_at=checked_at,
        running_count=running_count,
        stuck=stuck,
        alarm=alarm,
        alarm_channel="stderr+optional_log",
        error=None,
        db_path=str(db_path),
    )
    if alarm:
        _emit_alarm(report, alarm_log=alarm_log, stream=stream)
    return report


def report_exit_code(report: WatchdogReport) -> int:
    if report.error:
        return EXIT_WATCHDOG_ERROR
    if report.alarm:
        return EXIT_STUCK
    return EXIT_OK
