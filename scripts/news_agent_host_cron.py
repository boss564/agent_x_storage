#!/usr/bin/env python3
"""Install exactly one Host-Cron line for the multi-scraper news agent.

Identity is the trailing comment `# AGENTX_NEWS_AGENT`, not path or argv.
Entity-gap daily job uses `# AGENTX_NEWS_GAP`.
Price-gap hourly job uses `# AGENTX_PRICE_GAP` at :05 (after news :00).
News-sentiment PhaseSource uses `# AGENTX_NEWS_PHASE` at :06 (after news JSONL, not :05).
Price-gap PhaseSource uses `# AGENTX_GAP_PHASE` at :07 (after detector :05; not a prefix of PRICE_GAP).
"""
from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
from pathlib import Path

# Canonical ownership tag — filter enable/disable/status on this only.
MARKER = "# AGENTX_NEWS_AGENT"
GAP_MARKER = "# AGENTX_NEWS_GAP"
PRICE_GAP_MARKER = "# AGENTX_PRICE_GAP"
PHASE_MARKER = "# AGENTX_NEWS_PHASE"
GAP_PHASE_MARKER = "# AGENTX_GAP_PHASE"
LAUNCHD_LABEL = "com.agentx.news-agent"
# One-time migration: previous installer used this comment.
LEGACY_MARKERS = ("# agent_x_news_agent_host",)
LOCK_PATH = Path("/tmp/agent_x_news_agent_crontab.lock")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def news_python(root: Path) -> Path:
    """Absolute interpreter for cron/launchd (PATH is /usr/bin:/bin only)."""
    py = venv_python(root)
    if py.is_file():
        return py
    return Path(sys.executable).resolve()


def job_line(root: Path) -> str:
    r = str(root.absolute())
    log = str((root / "logs" / "audit" / "news_cron.log").absolute())
    py = str(news_python(root).absolute())
    return (
        f"0 * * * * cd \"{r}\" && PYTHONPATH=. \"{py}\" -m services.news_agent.runner "
        f"--once >> \"{log}\" 2>&1  {MARKER}"
    )


def gap_job_line(root: Path) -> str:
    r = str(root)
    log = root / "logs" / "audit" / "gap_detector.log"
    out = root / "exports" / "reports" / "gap_analysis.json"
    return (
        f"0 0 * * * cd \"{r}\" && PYTHONPATH=. python3 -m services.news_agent.gap_detector "
        f"--output \"{out}\" >> \"{log}\" 2>&1  {GAP_MARKER}"
    )


def venv_python(root: Path) -> Path:
    return root / ".venv" / "bin" / "python"


def ensure_price_gap_venv(root: Path) -> Path:
    """Local .venv with ccxt — cron must not use system python3 (PEP 668)."""
    py = venv_python(root)
    venv_dir = root / ".venv"
    if not py.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, timeout=60)
    subprocess.run(
        [str(py), "-m", "pip", "install", "-q", "ccxt>=4.4.0"],
        check=True,
        timeout=180,
    )
    return py


def price_gap_job_line(root: Path) -> str:
    """Hourly :05 — after news :00 so news_scores.jsonl is fresh.

    Cron cwd is typically $HOME. Always cd + absolute interpreter and script.
    """
    r = str(root.absolute())
    log = str((root / "logs" / "audit" / "price_gap_cron.log").absolute())
    py = str(venv_python(root).absolute())
    script = str((root / "scripts" / "run_gap_detector.py").absolute())
    return (
        f"5 * * * * cd \"{r}\" && PYTHONPATH=. \"{py}\" \"{script}\" "
        f"--once >> \"{log}\" 2>&1  {PRICE_GAP_MARKER}"
    )


def ensure_venv(root: Path) -> Path:
    py = venv_python(root)
    if not py.is_file():
        subprocess.run(
            [sys.executable, "-m", "venv", str(root / ".venv")],
            check=True,
            timeout=60,
        )
    return py


def phase_job_line(root: Path) -> str:
    """Hourly :06 — after news :00 and price-gap :05. Cron cwd is $HOME."""
    r = str(root.absolute())
    log = str((root / "logs" / "audit" / "phase_source_cron.log").absolute())
    py = str(venv_python(root).absolute())
    out = str((root / "data" / "phase_signals" / "news_sentiment.jsonl").absolute())
    return (
        f"6 * * * * cd \"{r}\" && PYTHONPATH=. \"{py}\" -m astrocore.sources.news_sentiment_source "
        f"--output-jsonl \"{out}\" --lookback-hours 24 >> \"{log}\" 2>&1  {PHASE_MARKER}"
    )


def gap_phase_job_line(root: Path) -> str:
    """Hourly :07 — after price-gap detector :05 and news-phase :06."""
    r = str(root.absolute())
    log = str((root / "logs" / "audit" / "gap_phase_cron.log").absolute())
    py = str(venv_python(root).absolute())
    out = str((root / "data" / "phase_signals" / "price_gap.jsonl").absolute())
    return (
        f"7 * * * * cd \"{r}\" && PYTHONPATH=. \"{py}\" -m astrocore.sources.price_gap_source "
        f"--output-jsonl \"{out}\" --lookback-hours 24 >> \"{log}\" 2>&1  {GAP_PHASE_MARKER}"
    )


def crontab_list() -> list[str]:
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
        raise RuntimeError(f"crontab -l failed: {err.strip() or proc.returncode}")
    return [ln.rstrip("\n") for ln in proc.stdout.splitlines()]


def is_managed_line(line: str) -> bool:
    """True iff this crontab row is the hourly news job (current or legacy marker)."""
    if MARKER in line:
        return True
    return any(legacy in line for legacy in LEGACY_MARKERS)


def is_gap_line(line: str) -> bool:
    return GAP_MARKER in line


def is_price_gap_line(line: str) -> bool:
    return PRICE_GAP_MARKER in line


def is_phase_line(line: str) -> bool:
    return PHASE_MARKER in line


def is_gap_phase_line(line: str) -> bool:
    return GAP_PHASE_MARKER in line


def _dedupe_keep(lines: list[str], drop) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if drop(line):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def keep_other(lines: list[str]) -> list[str]:
    return _dedupe_keep(lines, is_managed_line)


def keep_other_gap(lines: list[str]) -> list[str]:
    return _dedupe_keep(lines, is_gap_line)


def keep_other_price_gap(lines: list[str]) -> list[str]:
    return _dedupe_keep(lines, is_price_gap_line)


def keep_other_phase(lines: list[str]) -> list[str]:
    return _dedupe_keep(lines, is_phase_line)


def keep_other_gap_phase(lines: list[str]) -> list[str]:
    return _dedupe_keep(lines, is_gap_phase_line)


def crontab_install(lines: list[str]) -> None:
    body = "\n".join(lines).rstrip() + "\n"
    tmp = Path("/tmp/agent_x_news_agent_crontab.txt")
    tmp.write_text(body, encoding="utf-8")
    try:
        subprocess.run(["crontab", str(tmp)], check=True, timeout=20)
    except subprocess.TimeoutExpired:
        print(
            f"crontab hung (macOS/Agent). Im Terminal: crontab {tmp}",
            file=sys.stderr,
        )
        raise


def with_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK_PATH, "a+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def render_launchd_plist(root: Path) -> str:
    r = str(root.absolute())
    py = str(news_python(root).absolute())
    log = str((root / "logs" / "audit" / "news_cron.log").absolute())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LAUNCHD_LABEL}</string>
  <key>WorkingDirectory</key>
  <string>{r}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{py}</string>
    <string>-m</string>
    <string>services.news_agent.runner</string>
    <string>--once</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>.</string>
  </dict>
  <key>StandardOutPath</key>
  <string>{log}</string>
  <key>StandardErrorPath</key>
  <string>{log}</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
</dict>
</plist>
"""


def launchd_loaded() -> bool:
    proc = subprocess.run(
        ["launchctl", "print", f"{launchd_domain()}/{LAUNCHD_LABEL}"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    return proc.returncode == 0


def launchd_bootstrap(plist: Path) -> None:
    domain = launchd_domain()
    subprocess.run(
        ["launchctl", "bootout", domain, str(plist)],
        capture_output=True,
        timeout=20,
    )
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist)],
        check=True,
        timeout=30,
    )


def launchd_bootout(plist: Path) -> None:
    subprocess.run(
        ["launchctl", "bootout", launchd_domain(), str(plist)],
        capture_output=True,
        timeout=20,
    )


def _remove_news_cron_line() -> None:
    lock = with_lock()
    try:
        kept = keep_other(crontab_list())
        if not kept:
            subprocess.run(["crontab", "-r"], timeout=20, check=False)
        else:
            crontab_install(kept)
    finally:
        lock.close()


def cmd_launchd_enable(root: Path) -> int:
    (root / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    plist = launchd_plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(render_launchd_plist(root), encoding="utf-8")
    launchd_bootstrap(plist)
    print(
        f"News-Agent LaunchAgent: stündlich :00 → {root / 'data' / 'news_scores.jsonl'} "
        f"({LAUNCHD_LABEL})"
    )
    return cmd_status()


def cmd_enable(root: Path) -> int:
    (root / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        # macOS cron skips :00 while asleep; one LaunchAgent avoids duplicate runs.
        _remove_news_cron_line()
        return cmd_launchd_enable(root)
    lock = with_lock()
    try:
        kept = keep_other(crontab_list())
        kept.append(job_line(root))
        crontab_install(kept)
    finally:
        lock.close()
    print("News-Agent Host-Cron: Multi-Scraper stündlich :00 → data/news_scores.jsonl")
    return cmd_status()


def cmd_disable() -> int:
    if sys.platform == "darwin":
        plist = launchd_plist_path()
        if plist.is_file():
            launchd_bootout(plist)
            plist.unlink(missing_ok=True)
        print("News-Agent LaunchAgent entfernt.")
        return 0
    lock = with_lock()
    try:
        kept = keep_other(crontab_list())
        if not kept:
            subprocess.run(["crontab", "-r"], timeout=20, check=False)
        else:
            crontab_install(kept)
    finally:
        lock.close()
    print("News-Agent Host-Cron entfernt.")
    return 0


def cmd_status() -> int:
    if sys.platform == "darwin":
        plist = launchd_plist_path()
        loaded = launchd_loaded()
        print(f"scheduler=launchd label={LAUNCHD_LABEL} loaded={loaded} plist={plist}")
        if plist.is_file():
            print(f"python={news_python(repo_root())}")
    all_lines = crontab_list()
    current = [ln for ln in all_lines if MARKER in ln]
    legacy = [
        ln for ln in all_lines if any(m in ln for m in LEGACY_MARKERS) and MARKER not in ln
    ]
    n = len(current)
    unique = len(set(current))
    if n == 0 and not legacy and sys.platform != "darwin":
        print("No news-agent cron job found.")
        return 0
    if n == 0 and not legacy and sys.platform == "darwin" and not launchd_loaded():
        print("No news-agent scheduler found (LaunchAgent not loaded).")
        return 0
    for ln in current:
        print(ln)
    for ln in legacy:
        print(f"LEGACY {ln}")
    print(f"count={n} unique={unique}")
    rc = 0
    if legacy:
        print("WARN: Legacy-Marker — einmal: make news-agent-cron-enable")
        rc = 1
    if n > 1:
        print("WARN: count>1 — Duplikat oder mehrere Jobs. Einmal: make news-agent-cron-enable")
        rc = 1
    if sys.platform == "darwin" and n > 0:
        print("WARN: cron-Zeile auf macOS — einmal: make news-agent-cron-enable (LaunchAgent only)")
        rc = 1
    if sys.platform == "darwin" and not launchd_loaded() and n == 0:
        print("FAIL: LaunchAgent nicht geladen")
        rc = 1
    # Same instrument as feed-gap: mark age is a fault when the cron line exists.
    try:
        from services.news_agent.liveness import run_marker_freshness
        from services.news_agent.runner import jsonl_path

        live = run_marker_freshness(jsonl_path())
        print(
            f"marker_liveness={live.get('status')} age_s={live.get('age_s')} "
            f"max_age_s={live.get('max_age_s')} last_ts={live.get('last_ts')}"
        )
        st = live.get("status")
        if st in ("STALE", "UNPARSEABLE"):
            print("FAIL: news run_marker stale — agent did not write within NEWS_MARKER_MAX_AGE_H")
            rc = 1
        elif st == "MISSING":
            print("WARN: no run_marker yet — waiting for first hourly run")
    except Exception as exc:
        print(f"WARN: marker_liveness check failed: {exc}")
        rc = 1
    return rc


def cmd_gap_enable(root: Path) -> int:
    (root / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    (root / "exports" / "reports").mkdir(parents=True, exist_ok=True)
    lock = with_lock()
    try:
        kept = keep_other_gap(crontab_list())
        kept.append(gap_job_line(root))
        crontab_install(kept)
    finally:
        lock.close()
    print("Gap-Detector Host-Cron: täglich 00:00 → exports/reports/gap_analysis.json")
    return cmd_gap_status()


def cmd_gap_disable() -> int:
    lock = with_lock()
    try:
        kept = keep_other_gap(crontab_list())
        if not kept:
            subprocess.run(["crontab", "-r"], timeout=20, check=False)
        else:
            crontab_install(kept)
    finally:
        lock.close()
    print("Gap-Detector Host-Cron entfernt.")
    return 0


def cmd_gap_status() -> int:
    current = [ln for ln in crontab_list() if GAP_MARKER in ln]
    n = len(current)
    unique = len(set(current))
    if n == 0:
        print("No news-agent gap-detector cron job found.")
        return 0
    for ln in current:
        print(ln)
    print(f"count={n} unique={unique}")
    if n > 1:
        print("WARN: count>1 — einmal: make news-agent-gap-cron-enable")
        return 1
    return 0


def cmd_price_gap_status() -> int:
    current = [ln for ln in crontab_list() if PRICE_GAP_MARKER in ln]
    n = len(current)
    unique = len(set(current))
    if n == 0:
        print("No price-gap cron job found.")
        return 0
    for ln in current:
        print(ln)
    print(f"count={n} unique={unique}")
    if n > 1:
        print("WARN: count>1 — einmal: make gap-detector-cron-enable")
        return 1
    return 0


def cmd_price_gap_enable(root: Path) -> int:
    (root / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    ensure_price_gap_venv(root)
    lock = with_lock()
    try:
        kept = keep_other_price_gap(crontab_list())
        kept.append(price_gap_job_line(root))
        crontab_install(kept)
    finally:
        lock.close()
    print("Price-Gap Host-Cron: stündlich :05 → data/gap_reports.jsonl + docs/SWARM_GAP_ANALYSIS.md")
    return cmd_price_gap_status()


def cmd_price_gap_disable() -> int:
    lock = with_lock()
    try:
        kept = keep_other_price_gap(crontab_list())
        if not kept:
            subprocess.run(["crontab", "-r"], timeout=20, check=False)
        else:
            crontab_install(kept)
    finally:
        lock.close()
    print("Price-Gap Host-Cron entfernt.")
    return 0


def cmd_satellites_enable(root: Path) -> int:
    """Hourly news :00 + price-gap :05. Leaves entity-gap daily and cluster jobs."""
    (root / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    ensure_price_gap_venv(root)
    lock = with_lock()
    try:
        kept = keep_other(crontab_list())
        kept = keep_other_price_gap(kept)
        kept.append(job_line(root))
        kept.append(price_gap_job_line(root))
        crontab_install(kept)
    finally:
        lock.close()
    print("Satelliten Host-Cron: News :00 + Price-Gap :05 (Cluster unberührt)")
    news_rc = cmd_status()
    price_rc = cmd_price_gap_status()
    return 1 if news_rc or price_rc else 0


def cmd_phase_status() -> int:
    current = [ln for ln in crontab_list() if PHASE_MARKER in ln]
    n = len(current)
    unique = len(set(current))
    if n == 0:
        print("No news-sentiment phase cron job found.")
        return 0
    for ln in current:
        print(ln)
    print(f"count={n} unique={unique}")
    if n > 1:
        print("WARN: count>1 — einmal: make news-sentiment-phase-cron-enable")
        return 1
    return 0


def cmd_phase_enable(root: Path) -> int:
    (root / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    (root / "data" / "phase_signals").mkdir(parents=True, exist_ok=True)
    ensure_venv(root)
    lock = with_lock()
    try:
        kept = keep_other_phase(crontab_list())
        kept.append(phase_job_line(root))
        crontab_install(kept)
    finally:
        lock.close()
    print("News-Sentiment PhaseSource Host-Cron: stündlich :06 → data/phase_signals/news_sentiment.jsonl")
    return cmd_phase_status()


def cmd_phase_disable() -> int:
    lock = with_lock()
    try:
        kept = keep_other_phase(crontab_list())
        if not kept:
            subprocess.run(["crontab", "-r"], timeout=20, check=False)
        else:
            crontab_install(kept)
    finally:
        lock.close()
    print("News-Sentiment PhaseSource Host-Cron entfernt.")
    return 0


def cmd_gap_phase_status() -> int:
    current = [ln for ln in crontab_list() if GAP_PHASE_MARKER in ln]
    n = len(current)
    unique = len(set(current))
    if n == 0:
        print("No price-gap phase cron job found.")
        return 0
    for ln in current:
        print(ln)
    print(f"count={n} unique={unique}")
    if n > 1:
        print("WARN: count>1 — einmal: make price-gap-phase-cron-enable")
        return 1
    return 0


def cmd_gap_phase_enable(root: Path) -> int:
    (root / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    (root / "data" / "phase_signals").mkdir(parents=True, exist_ok=True)
    ensure_venv(root)
    lock = with_lock()
    try:
        kept = keep_other_gap_phase(crontab_list())
        kept.append(gap_phase_job_line(root))
        crontab_install(kept)
    finally:
        lock.close()
    print("Price-Gap PhaseSource Host-Cron: stündlich :07 → data/phase_signals/price_gap.jsonl")
    return cmd_gap_phase_status()


def cmd_gap_phase_disable() -> int:
    lock = with_lock()
    try:
        kept = keep_other_gap_phase(crontab_list())
        if not kept:
            subprocess.run(["crontab", "-r"], timeout=20, check=False)
        else:
            crontab_install(kept)
    finally:
        lock.close()
    print("Price-Gap PhaseSource Host-Cron entfernt.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "enable",
            "disable",
            "status",
            "gap-enable",
            "gap-disable",
            "gap-status",
            "price-gap-enable",
            "price-gap-disable",
            "price-gap-status",
            "satellites-enable",
            "phase-enable",
            "phase-disable",
            "phase-status",
            "gap-phase-enable",
            "gap-phase-disable",
            "gap-phase-status",
        ),
    )
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    root = Path(args.root) if args.root else repo_root()
    os.chdir(root)
    if args.action == "enable":
        return cmd_enable(root)
    if args.action == "disable":
        return cmd_disable()
    if args.action == "status":
        return cmd_status()
    if args.action == "gap-enable":
        return cmd_gap_enable(root)
    if args.action == "gap-disable":
        return cmd_gap_disable()
    if args.action == "gap-status":
        return cmd_gap_status()
    if args.action == "price-gap-enable":
        return cmd_price_gap_enable(root)
    if args.action == "price-gap-disable":
        return cmd_price_gap_disable()
    if args.action == "price-gap-status":
        return cmd_price_gap_status()
    if args.action == "phase-enable":
        return cmd_phase_enable(root)
    if args.action == "phase-disable":
        return cmd_phase_disable()
    if args.action == "phase-status":
        return cmd_phase_status()
    if args.action == "gap-phase-enable":
        return cmd_gap_phase_enable(root)
    if args.action == "gap-phase-disable":
        return cmd_gap_phase_disable()
    if args.action == "gap-phase-status":
        return cmd_gap_phase_status()
    return cmd_satellites_enable(root)


if __name__ == "__main__":
    raise SystemExit(main())
