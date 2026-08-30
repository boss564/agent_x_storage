#!/usr/bin/env python3
"""Kurz-Status: welche Schwarm-Logs/Agenten aktuell Daten schreiben.

Usage:
    python3 scripts/swarm_health.py
    python3 scripts/swarm_health.py --json
    python3 scripts/swarm_health.py --sync-inventory
    RAAS_DATA_ROOT=/data SWARM_DATA_ROOT=/data python3 scripts/swarm_health.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

RUNTIME_BEGIN = "<!-- SWARM_RUNTIME_BEGIN -->"
RUNTIME_END = "<!-- SWARM_RUNTIME_END -->"
INVENTORY_PATH = "docs/SWARM_INVENTORY.md"


# --- path resolution (mirrors daemon / paper_runner env) ---

def _swarm_root() -> Path:
    return Path(os.environ.get("SWARM_DATA_ROOT", os.environ.get("RAAS_DATA_ROOT", "data/raas")))


def _raas_root() -> Path:
    return Path(os.environ.get("RAAS_DATA_ROOT", "data/raas"))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _live_worm_dir() -> Path:
    env = os.environ.get("LIVE_FEED_WORM_DIR")
    if env:
        return Path(env)
    return _raas_root() / "worm" / "live"


def _paper_worm_candidates() -> List[Path]:
    roots = [
        _live_worm_dir(),
        _swarm_root() / "worm" / "live",
        _swarm_root() / "worm" / "paper_runs",
        _repo_root() / "logs" / "worm" / "live",
        _repo_root() / "logs" / "worm" / "paper_runs",
    ]
    out: List[Path] = []
    seen: set[str] = set()
    for d in roots:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("paper_trades.worm.jsonl")):
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


# --- log target registry ---

@dataclass(frozen=True)
class LogTarget:
    key: str
    name: str
    layer: str
    path_fn: Callable[[], Path]
    stale_s: float = 300.0
    optional: bool = False


@dataclass(frozen=True)
class RuntimeComponent:
    component_id: str
    label: str
    signal: str
    role: str
    layer: str


# Inventar-Zeilen → Health-Signal (Log-Frische). Mehrere Komponenten können dasselbe Signal teilen.
RUNTIME_COMPONENTS: Tuple[RuntimeComponent, ...] = (
    RuntimeComponent("LivePaperBridge", "LivePaperBridge", "paper_worm", "Shadow-Pfad", "P3"),
    RuntimeComponent("PaperTradingRunner", "PaperTradingRunner", "paper_worm", "Shadow-Pfad", "P3"),
    RuntimeComponent("FeedGapMonitor", "FeedGapMonitor", "feed_gap_writer", "Shadow-Pfad", "P1"),
    RuntimeComponent("CrossVenueMonitor", "CrossVenueMonitor", "cross_venue_gaps", "Opt-in (Env default off)", "P1"),
    RuntimeComponent("RegimeSwarmDaemon", "Regime Swarm Daemon", "regime_cycles", "Shadow-Pfad (primary)", "P5"),
    RuntimeComponent("A2DataIngestor", "A2 DataIngestor", "regime_cycles", "Shadow-Pfad", "P5"),
    RuntimeComponent("A3A9Drift", "A3–A9 Drift Agents", "regime_drift_audit", "Shadow-Pfad", "P5"),
    RuntimeComponent("A0CoreSanity", "A0 Core Sanity Gate", "regime_cycles", "Shadow-Pfad", "P6"),
    RuntimeComponent("A25Transport", "A2.5 Transport Gate", "regime_cycles", "Shadow-Pfad", "P6"),
    RuntimeComponent(
        "B0PositionSizing",
        "B0 Position Sizing",
        "position_sizing_audit",
        "Opt-in (Helm off, Strang B n<50)",
        "P5",
    ),
)


def _targets() -> List[LogTarget]:
    sr, rr = _swarm_root(), _raas_root()
    return [
        LogTarget("paper_worm", "Paper WORM (live)", "P3", lambda: _live_worm_dir() / "paper_trades.worm.jsonl", 120.0),
        LogTarget("feed_gaps", "Feed gaps (raw JSONL)", "P1", lambda: Path(os.environ.get("PAPER_FEED_GAPS_PATH", str(rr / "audit" / "feed_gaps.jsonl"))), 120.0),
        LogTarget("feed_gap_writer", "Feed gap writer", "P1", lambda: Path(os.environ.get("PAPER_FEED_GAPS_PATH", str(rr / "audit" / "feed_gaps.jsonl"))), 7200.0),
        LogTarget("cross_venue_gaps", "Cross-venue gaps", "P1", lambda: Path(os.environ.get("CROSS_VENUE_GAPS_PATH", str(rr / "audit" / "cross_venue_gaps.jsonl"))), 300.0, True),
        LogTarget("cross_venue_v1_writer", "Cross-venue V1 writer", "P1", lambda: Path(os.environ.get("CROSS_VENUE_GAPS_PATH", str(rr / "audit" / "cross_venue_gaps.jsonl"))), 7200.0, True),
        LogTarget("cross_venue_v2_writer", "Cross-venue V2 writer", "P1", lambda: Path(os.environ.get("CROSS_VENUE_GAPS_PATH", str(rr / "audit" / "cross_venue_gaps.jsonl"))), 7200.0, True),
        LogTarget("cross_venue_slots", "Cross-venue slots", "P1", lambda: Path(os.environ.get("CROSS_VENUE_SLOTS_PATH", str(rr / "audit" / "cross_venue_slots.jsonl"))), 300.0, True),
        LogTarget("regime_drift_audit", "Regime drift audit", "P5", lambda: Path(os.environ.get("REGIME_DRIFT_AUDIT_PATH", str(sr / "audit" / "regime_drift_audit.jsonl"))), 120.0),
        LogTarget("regime_cycles", "Regime swarm cycles", "P5", lambda: Path(os.environ.get("REGIME_SWARM_CYCLES_PATH", str(sr / "audit" / "regime_swarm_cycles.jsonl"))), 120.0),
        LogTarget("position_sizing_audit", "Position sizing audit", "P5", lambda: sr / "audit" / "position_sizing_audit.jsonl", 600.0, True),
        LogTarget("paper_edges", "Paper edges", "P3", lambda: Path(os.environ.get("PAPER_EDGES_PATH", str(rr / "audit" / "paper_edges.jsonl"))), 600.0, True),
        LogTarget("paper_position", "Paper position state", "P3", lambda: Path(os.environ.get("PAPER_POSITION_PATH", str(rr / "state" / "paper_position.json"))), 600.0, True),
        LogTarget("depth_snapshots", "Depth snapshots", "P1", lambda: Path(os.environ.get("RAAS_DEPTH_WORM_PATH", str(_repo_root() / "logs" / "worm" / "depth_snapshots.jsonl"))), 180.0, True),
        LogTarget("heartbeat", "Swarm heartbeat", "P5", lambda: Path(os.environ.get("SWARM_HEARTBEAT_PATH", "/tmp/swarm_heartbeat")), 90.0, True),
        LogTarget("cooling", "Cooling telemetry", "P5", lambda: sr / "state" / "regime_swarm_cooling.jsonl", 600.0, True),
        LogTarget("leader_snapshot", "Leader snapshot", "P5", lambda: sr / "state" / "leader_snapshot.json", 600.0, True),
    ]


def _target_by_key() -> Dict[str, LogTarget]:
    return {t.key: t for t in _targets()}


# --- helpers ---

def _fmt_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def _file_stats(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"exists": False}
    st = path.stat()
    age = time.time() - st.st_mtime
    size = st.st_size
    return {
        "exists": True,
        "size_bytes": size,
        "age_s": age,
        "mtime_iso": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
    }


def _classify(stats: Dict[str, Any], stale_s: float, optional: bool) -> str:
    if not stats.get("exists"):
        return "MISSING" if not optional else "OFF"
    age = stats.get("age_s", float("inf"))
    if age <= stale_s:
        return "ACTIVE"
    if age <= stale_s * 6:
        return "STALE"
    return "IDLE"


def _kubectl_pod() -> Optional[Dict[str, str]]:
    if not shutil.which("kubectl"):
        return None
    ns = os.environ.get("REGIME_SWARM_NAMESPACE", "trading")
    pod = os.environ.get("REGIME_SWARM_POD", "regime-swarm-0")
    try:
        proc = subprocess.run(
            ["kubectl", "get", "pod", pod, "-n", ns, "-o", "jsonpath={.status.phase}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        phase = proc.stdout.strip() or "?"
        ready_proc = subprocess.run(
            ["kubectl", "get", "pod", pod, "-n", ns, "-o", "jsonpath={.status.containerStatuses[0].ready}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ready = ready_proc.stdout.strip()
        return {"namespace": ns, "pod": pod, "phase": phase, "ready": ready}
    except (subprocess.TimeoutExpired, OSError):
        return None


def _pod_file_stats(pod_info: Dict[str, str], container_path: str) -> Dict[str, Any]:
    if pod_info.get("phase") != "Running" or pod_info.get("ready") != "true":
        return {"exists": False}
    ns, pod = pod_info["namespace"], pod_info["pod"]
    script = (
        "import os, time, json, sys\n"
        f"p = {container_path!r}\n"
        "if not os.path.isfile(p):\n"
        "    print(json.dumps({'exists': False})); sys.exit(0)\n"
        "st = os.stat(p)\n"
        "age = time.time() - st.st_mtime\n"
        "print(json.dumps({'exists': True, 'size_bytes': st.st_size, 'age_s': age}))\n"
    )
    try:
        proc = subprocess.run(
            ["kubectl", "exec", "-n", ns, pod, "--", "python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0:
            return {"exists": False}
        return json.loads(proc.stdout.strip() or "{}")
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return {"exists": False}


def _pod_find_best_worm(pod_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
    if pod_info.get("phase") != "Running":
        return None
    ns, pod = pod_info["namespace"], pod_info["pod"]
    script = (
        "import os, time, json\n"
        "root = '/data/worm'\n"
        "best = None\n"
        "if os.path.isdir(root):\n"
        "    for dp, _, files in os.walk(root):\n"
        "        if 'paper_trades.worm.jsonl' not in files:\n"
        "            continue\n"
        "        p = os.path.join(dp, 'paper_trades.worm.jsonl')\n"
        "        st = os.stat(p)\n"
        "        row = {'path': p, 'age_s': time.time() - st.st_mtime, 'size_bytes': st.st_size}\n"
        "        if best is None or row['age_s'] < best['age_s']:\n"
        "            best = row\n"
        "print(json.dumps(best or {}))\n"
    )
    try:
        proc = subprocess.run(
            ["kubectl", "exec", "-n", ns, pod, "--", "python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout.strip() or "{}")
        if not data:
            return None
        data["display_path"] = f"{pod}:{data['path']}"
        return data
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return None


def _resolve_feed_gap_writer_signal(target: LogTarget) -> Dict[str, Any]:
    """Writer liveness: heartbeat=quiet ACTIVE; no heartbeat + stale=defect."""
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from prototypes.raas_paper_trading.feed_gap import load_gaps, writer_liveness_status

    path = target.path_fn()
    gaps = load_gaps(path)
    live = writer_liveness_status(gaps=gaps)
    status = str(live.get("status") or "MISSING")
    age = live.get("age_s")
    mode = live.get("mode") or ""
    display = f"{path} ({mode})" if mode else str(path)
    return {
        "key": target.key,
        "name": target.name,
        "layer": target.layer,
        "status": status,
        "age_s": age,
        "age": _fmt_age(float(age)) if age is not None else "—",
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "path": display,
        "optional": False,
    }


def _resolve_cross_venue_writer_signal(target: LogTarget) -> Dict[str, Any]:
    """Per-venue heartbeat liveness (v1 / v2 separate observers)."""
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from prototypes.raas_paper_trading.cross_venue import load_jsonl, writer_liveness_status

    venue = "v1" if target.key == "cross_venue_v1_writer" else "v2"
    path = target.path_fn()
    gaps = load_jsonl(path)
    live = writer_liveness_status(gaps=gaps, venue=venue)
    status = str(live.get("status") or "MISSING")
    age = live.get("age_s")
    mode = live.get("mode") or ""
    display = f"{path} [{venue}] ({mode})" if mode else f"{path} [{venue}]"
    return {
        "key": target.key,
        "name": target.name,
        "layer": target.layer,
        "status": status if not target.optional or path.is_file() else "OFF",
        "age_s": age,
        "age": _fmt_age(float(age)) if age is not None else "—",
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "path": display,
        "optional": target.optional,
    }


def _resolve_signal(
    target: LogTarget,
    pod: Optional[Dict[str, str]],
    use_cluster: bool,
) -> Dict[str, Any]:
    path = target.path_fn()
    stats = _file_stats(path)
    display_path = str(path)

    if use_cluster and pod and not stats.get("exists"):
        rel = str(path)
        for prefix in (str(_swarm_root()), str(_raas_root()), str(_repo_root())):
            if rel.startswith(prefix):
                rel = rel[len(prefix):].lstrip("/")
                break
        cluster_path = f"/data/{rel}" if rel else ""
        if cluster_path:
            cstats = _pod_file_stats(pod, cluster_path)
            if cstats.get("exists"):
                stats = cstats
                display_path = f"{pod['pod']}:{cluster_path}"

    status = _classify(stats, target.stale_s, target.optional)
    return {
        "key": target.key,
        "name": target.name,
        "layer": target.layer,
        "status": status,
        "age_s": stats.get("age_s"),
        "age": _fmt_age(stats.get("age_s")) if stats.get("exists") else "—",
        "size_bytes": stats.get("size_bytes"),
        "path": display_path,
        "optional": target.optional,
    }


def _best_local_worm() -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    for worm in _paper_worm_candidates():
        stats = _file_stats(worm)
        if not stats.get("exists"):
            continue
        age = float(stats["age_s"])
        if best is None or age < float(best["age_s"]):
            best = {
                "path": str(worm),
                "age_s": age,
                "size_bytes": stats.get("size_bytes", 0),
                "display_path": str(worm),
            }
    return best


def collect_health_report() -> Dict[str, Any]:
    """Canonical runtime health — source of truth for inventory Laufzeit column."""
    pod = _kubectl_pod()
    cluster_reachable = bool(
        pod and pod.get("phase") == "Running" and pod.get("ready") == "true"
    )
    use_cluster = cluster_reachable or os.environ.get("SWARM_HEALTH_CLUSTER", "").lower() in (
        "1",
        "true",
        "yes",
    )

    signals: Dict[str, Dict[str, Any]] = {}
    for target in _targets():
        if target.key == "feed_gap_writer":
            signals[target.key] = _resolve_feed_gap_writer_signal(target)
            continue
        if target.key in ("cross_venue_v1_writer", "cross_venue_v2_writer"):
            signals[target.key] = _resolve_cross_venue_writer_signal(target)
            continue
        signals[target.key] = _resolve_signal(target, pod, use_cluster)

    # paper_worm: freshest cluster worm beats flat local path
    worm = None
    if use_cluster and pod:
        worm = _pod_find_best_worm(pod)
    if worm is None:
        worm = _best_local_worm()
    if worm:
        stale = 120.0
        age = float(worm["age_s"])
        status = "ACTIVE" if age <= stale else ("STALE" if age <= stale * 6 else "IDLE")
        signals["paper_worm"] = {
            "key": "paper_worm",
            "name": "Paper WORM (live)",
            "layer": "P3",
            "status": status,
            "age_s": age,
            "age": _fmt_age(age),
            "size_bytes": worm.get("size_bytes"),
            "path": worm.get("display_path", worm.get("path", "")),
            "optional": False,
        }
    elif signals["paper_worm"]["status"] == "MISSING":
        pass  # keep MISSING from flat path probe

    components: Dict[str, Dict[str, Any]] = {}
    for comp in RUNTIME_COMPONENTS:
        sig = signals.get(comp.signal, {})
        components[comp.component_id] = {
            "component_id": comp.component_id,
            "label": comp.label,
            "layer": comp.layer,
            "role": comp.role,
            "signal": comp.signal,
            "status": sig.get("status", "MISSING"),
            "age_s": sig.get("age_s"),
            "age": sig.get("age", "—"),
            "path": sig.get("path", "—"),
        }

    counts: Dict[str, int] = {}
    for sig in signals.values():
        st = sig["status"]
        counts[st] = counts.get(st, 0) + 1

    metrics = _curl_metrics(int(os.environ.get("SWARM_METRICS_PORT", "8080")))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cluster_reachable": cluster_reachable,
        "pod": pod,
        "metrics": metrics,
        "signals": signals,
        "components": components,
        "summary": counts,
    }


def _curl_metrics(port: int = 8080) -> Optional[Dict[str, Any]]:
    host = os.environ.get("SWARM_METRICS_HOST", "127.0.0.1")
    url = f"http://{host}:{port}/metrics"
    try:
        proc = subprocess.run(
            ["curl", "-sf", "--max-time", "2", url],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return None
        lines = proc.stdout.splitlines()
        interesting = {}
        for key in ("swarm_cycles_total", "swarm_drift_counter", "feed_gap_events_total", "feed_last_tick_age_s"):
            for ln in lines:
                if ln.startswith(key):
                    interesting[key] = ln.split()[1] if len(ln.split()) > 1 else ln
        return interesting or {"raw_lines": len(lines)}
    except OSError:
        return None


def render_runtime_markdown(report: Dict[str, Any]) -> str:
    """Markdown block for SWARM_INVENTORY.md (between BEGIN/END markers)."""
    lines = [
        RUNTIME_BEGIN,
        f"<!-- generated_at: {report['generated_at']} -->",
        "<!-- generator: scripts/swarm_health.py (--sync-inventory) -->",
        "",
        "_**Laufzeit** = Log-Frische (ACTIVE/STALE/IDLE/MISSING/OFF). "
        "**Rolle** = Architektur-Zugehörigkeit — kein Prozess-Nachweis. "
        "Sync: `make raas-swarm-inventory-sync`_",
        "",
        "| Komponente | Schicht | Laufzeit | Alter | Signal-Pfad | Rolle (Hand) |",
        "|------------|---------|----------|-------|-------------|--------------|",
    ]
    for comp in RUNTIME_COMPONENTS:
        row = report["components"][comp.component_id]
        path = str(row.get("path", "—"))
        if len(path) > 56:
            path = "…" + path[-53:]
        lines.append(
            f"| **{row['label']}** | {row['layer']} | **{row['status']}** | "
            f"{row.get('age', '—')} | `{path}` | {row['role']} |"
        )
    active = sum(1 for c in report["components"].values() if c["status"] == "ACTIVE")
    stale = sum(1 for c in report["components"].values() if c["status"] == "STALE")
    lines.extend([
        "",
        f"_Stand: {report['generated_at']} · "
        f"{active} ACTIVE · {stale} STALE (Laufzeit-Zeilen, nicht Rollen-Zeilen)_",
        "",
        RUNTIME_END,
    ])
    return "\n".join(lines)


def parse_runtime_block(text: str) -> Dict[str, str]:
    """component_id → Laufzeit status from committed inventory."""
    m = re.search(
        re.escape(RUNTIME_BEGIN) + r"(.*?)" + re.escape(RUNTIME_END),
        text,
        re.DOTALL,
    )
    if not m:
        return {}
    block = m.group(1)
    out: Dict[str, str] = {}
    for comp in RUNTIME_COMPONENTS:
        pat = rf"\|\s*\*\*{re.escape(comp.label)}\*\*\s*\|[^|]+\|\s*\*\*(\w+)\*\*"
        hit = re.search(pat, block)
        if hit:
            out[comp.component_id] = hit.group(1)
    return out


def sync_inventory_markdown(inventory_path: Optional[Path] = None) -> Tuple[str, Dict[str, Any]]:
    path = inventory_path or (_repo_root() / INVENTORY_PATH)
    report = collect_health_report()
    block = render_runtime_markdown(report)
    text = path.read_text(encoding="utf-8")
    if RUNTIME_BEGIN not in text or RUNTIME_END not in text:
        raise RuntimeError(f"{path}: {RUNTIME_BEGIN} … {RUNTIME_END} fehlt")
    new_text = re.sub(
        re.escape(RUNTIME_BEGIN) + r".*?" + re.escape(RUNTIME_END),
        block,
        text,
        count=1,
        flags=re.DOTALL,
    )
    path.write_text(new_text, encoding="utf-8")
    return new_text, report


def _print_table(rows: List[Tuple[str, str, str, str, str, str]]) -> None:
    headers = ("Status", "Layer", "Agent / Log", "Age", "Size", "Path")
    widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
    widths = [min(w, 48 if i == 2 else 72 if i == 5 else w) for i, w in enumerate(widths)]
    fmt = "  ".join(f"{{:{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*row))


def print_human_report(report: Dict[str, Any]) -> int:
    now = report["generated_at"]
    sr, rr = _swarm_root(), _raas_root()
    print(f"Agent X Schwarm Health — {now}")
    print(f"  SWARM_DATA_ROOT = {sr}")
    print(f"  RAAS_DATA_ROOT  = {rr}")
    print()

    pod = report.get("pod")
    if pod:
        print(f"K8s: {pod['pod']} @ {pod['namespace']} → phase={pod['phase']} ready={pod['ready']}")
    else:
        print("K8s: kubectl nicht verfügbar oder Pod nicht erreichbar")
    if report.get("metrics"):
        print(f"Prometheus :8080 → {report['metrics']}")
    else:
        print("Prometheus :8080 → nicht erreichbar (Daemon lokal nicht aktiv?)")
    print()

    rows: List[Tuple[str, str, str, str, str, str]] = []
    for sig in report["signals"].values():
        size = "—"
        if sig.get("size_bytes"):
            size = f"{sig['size_bytes'] / (1024 * 1024):.1f} MiB"
        rows.append(
            (sig["status"], sig["layer"], sig["name"], sig.get("age", "—"), size, str(sig.get("path", "—")))
        )
    _print_table(rows)
    print()

    print("Inventar-Laufzeit (Komponenten → Signal):")
    for comp in RUNTIME_COMPONENTS:
        row = report["components"][comp.component_id]
        print(f"  {row['label']:28} {row['status']:8} {row.get('age', '—'):>8}  ({row['signal']})")
    print()

    counts = report["summary"]
    active = counts.get("ACTIVE", 0)
    stale = counts.get("STALE", 0)
    comp_active = sum(1 for c in report["components"].values() if c["status"] == "ACTIVE")
    comp_stale = sum(1 for c in report["components"].values() if c["status"] == "STALE")
    print(
        f"Signale: {active} ACTIVE · {stale} STALE · "
        f"{counts.get('IDLE', 0)} IDLE · {counts.get('MISSING', 0)} MISSING · "
        f"{counts.get('OFF', 0)} OFF"
    )
    print(f"Inventar-Zeilen: {comp_active} ACTIVE · {comp_stale} STALE (geteilt via Signal-Mapping)")
    print()

    if active >= 2:
        print("→ Live-Pipeline schreibt vermutlich (WORM + Audit/Cycles).")
    elif active == 1:
        print("→ Teilweise aktiv — prüfe STALE/MISSING und Pod-Logs.")
    else:
        print("→ Keine frischen Logs — Daemon gestoppt oder falscher DATA_ROOT?")

    print()
    print(f"Vollständiges Inventar: {INVENTORY_PATH}")
    print("Sync Laufzeit-Spalte: make raas-swarm-inventory-sync")
    return 0 if active > 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Schwarm-Log-Frische und Inventar-Laufzeit")
    parser.add_argument("--json", action="store_true", help="Maschinenlesbarer Report (stdout)")
    parser.add_argument("--sync-inventory", action="store_true", help="SWARM_RUNTIME-Block in Inventar schreiben")
    args = parser.parse_args()

    if args.sync_inventory:
        _, report = sync_inventory_markdown()
        print(f"OK: {INVENTORY_PATH} Laufzeit-Block aktualisiert ({report['generated_at']})")
        return 0

    report = collect_health_report()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    return print_human_report(report)


if __name__ == "__main__":
    sys.exit(main())
