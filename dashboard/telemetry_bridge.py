#!/usr/bin/env python3
"""
Telemetry Bridge — status.json als alleinige Schnittstelle zum X-STORAGE Control Center.

Architektur (bewusst entkoppelt):

    telemetry_bridge.py  --schreibt-->  status.json  --liest-->  React/Vite-Dashboard
                                              ^
                                              |
                             dort als einziger Vertrag (2s-Poll)

Das Frontend ist damit austauschbar: React, Streamlit oder ein curl-Watcher lesen
denselben Vertrag. Die Bridge kennt kein Frontend.

Vertrag (Schema-Version 1):
    repos[]   {name, path, role, state, kind, head, branch, dirty, changed_files[], error}
    agents[]  {name, state, pid(s), uptime_seconds, uptime_human, cmdline, cwd}
    charter{} {diagnostic_only, live_execution, order_send, not_investment_advice}
    alerts[]  {severity, code, source, message}
    logs{}    {path, lines[], truncated, error}
    meta{}    {generated_at, generated_ts, schema_version, duration_ms, host, ...}

Repo-Zustaende (state):
    ok           Arbeitsbaum, HEAD gelesen
    bare         Bare-Repo, gesund (kein Worktree, dirty=None)
    bare_empty   Bare-Repo ohne Commits (HEAD ungeboren)
    nested       Unterordner eines anderen Repos (kein eigener Anker)
    not_found    Pfad existiert nicht (Modul nicht ausgegruendet)
    no_git       Verzeichnis ohne Git
    error        git-Aufruf fehlgeschlagen

Wahrheitsregel (SCHWARM_STATUS.md §1.1 — Claims-vs-Beleg):
    Ein nicht existierendes Repo wird als "not_found" gemeldet, niemals als
    "DIRTY"/"CLEAN". Ein Unterordner eines anderen Repos wird als "nested"
    gemeldet, damit kein blindes `git rev-parse` eine falsche Antwort liefert.
    Lieber eine sichtbare Lücke als eine erfundene Zahl.

Usage:
    # Dauerbetrieb: schreibt status.json alle 2s
    python3 dashboard/telemetry_bridge.py

    # Einmalig (fuer Tests / CI) + auf stdout
    python3 dashboard/telemetry_bridge.py --once --stdout

    # Zusaetzlich kleiner HTTP-Endpoint auf :8787
    python3 dashboard/telemetry_bridge.py --serve
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

T = TypeVar("T")

SCHEMA_VERSION = 1
DEFAULT_INTERVAL = 2.0

# Projektwurzel = eine Ebene ueber diesem Skript (dashboard/ liegt im Repo-Root).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Konfiguration — Pfadliste als Config, nicht als Code (Frage 2 / Option A).
# Neue Repos oder Pfadaenderungen = eine Zeile hier, kein Codeumbau.
# ---------------------------------------------------------------------------

# Basis-Verzeichnis fuer relative Pfade. Ueber Env uebersteuerbar.
BASE_DIR = Path(os.environ.get("AGENTX_TELEMETRY_BASE", PROJECT_ROOT))

# Repo-Eintraege als Dicts mit explizitem 'kind':
#   worktree (Default) — normales Repo mit Arbeitsbaum
#   bare               — Bare-Repo ohne Worktree (git --git-dir, kein status)
#   package            — erwartet 'nested' (Paket im Hub, kein eigener Anker)
#
# 'kind' ist NICHT Kosmetik: ein Bare ohne Flag wuerde 'error'/'no_git' melden,
# obwohl es gesund ist — ein falscher Fehlerzustand im Dashboard.
DEFAULT_REPO_REGISTRY: list[dict[str, Any]] = [
    {"name": "agent_x_storage", "path": ".", "role": "hub"},
    # newsagent/ ist ein eigenes, ausgegruendetes Repo (nested Git im Hub-Ordner).
    {"name": "newsagent", "path": "newsagent", "role": "satellite"},
    # order_execution_engine ist KEIN eigenes Repo, sondern ein Paket im Hub.
    # Erwarteter Zustand: "nested" — verhindert falsche Git-Abfragen.
    {"name": "order_execution_engine", "path": "order_execution_engine",
     "role": "package", "kind": "package"},
    # data_infrastructure / polysentinel / farcaster_app: geplant, noch ohne
    # git init — bewusst NICHT in der Registry. Telemetrie misst Ist-Zustand,
    # nicht Roadmap. Dauerhaftes NOT_FOUND stumpft den Alert-Strip ab.
    # Nach git init: auf dem passenden Host mit echtem Pfad eintragen
    # (polysentinel live: Hetzner /opt/polysentinel).
    # Das Control-Center-Projekt selbst (eigenes Repo seit 2026-09-21).
    # Absoluter Pfad, weil es ausserhalb von BASE_DIR liegt.
    {"name": "x-storage-control-center", "path": "~/repos/x-storage-control-center",
     "role": "dashboard"},
]

# Prozess-Registry. 'required=False' = taucht nicht als Fehler auf,
# wenn er fehlt (sondern als "not_running" — Information, kein Alarm).
DEFAULT_PROCESS_REGISTRY: list[dict[str, Any]] = [
    {"name": "polymarket_monitor", "pattern": "polymarket_monitor.py", "required": True},
    {"name": "polysentinel", "pattern": "polysentinel", "required": False},
]


def _load_registry_file(path_str: str | None) -> tuple[list[dict[str, Any]] | None,
                                                       list[dict[str, Any]] | None]:
    """
    Laedt eine Registry-JSON aus AGENTX_TELEMETRY_REGISTRY.

    Format: {"repos": [...], "processes": [...]} — beide Schluessel optional.
    Gibt (repos, processes) zurueck; None = Schluessel nicht gesetzt.

    WARUM EINE DATEI UND KEIN NEUER MECHANISMUS: Der Remote-Host braucht andere
    Repos und andere Prozesse als der Mac. Ein zweiter Code-Pfad waere die
    Gabelung, die auseinanderdriftet — stattdessen dieselbe Bridge, andere
    Registry-Datei.
    """
    if not path_str:
        return None, None
    path = Path(path_str).expanduser()
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    if not isinstance(data, dict):
        return None, None
    repos = data.get("repos") if isinstance(data.get("repos"), list) else None
    procs = data.get("processes") if isinstance(data.get("processes"), list) else None
    return repos, procs


_REGISTRY_PATH = os.environ.get("AGENTX_TELEMETRY_REGISTRY")
_REGISTRY_FILE_REPOS, _REGISTRY_FILE_PROCESSES = _load_registry_file(_REGISTRY_PATH)

# Datei schlaegt Default — aber nur wenn sie nicht leer ist (eine leere
# Registry waere ein stiller Ausfall, kein Wunsch).
#
# Der stille Rueckfall ist selbst eine Falle: Zeigt AGENTX_TELEMETRY_REGISTRY
# auf eine nicht existierende oder kaputte Datei, uebernimmt die Default-Liste
# — und die zeigt auf die FALSCHEN Repos, ohne dass irgendwo ein Fehler steht.
# Auf dem Mac faellt das nicht auf (dort IST der Default richtig); auf einem
# Remote-Host mit eigener Registry erzeugt es plausibel aussehende, aber
# falsche Daten. Ist die Variable gesetzt, ist ein Rueckfall ein Fehler.
if _REGISTRY_PATH and _REGISTRY_FILE_REPOS is None:
    sys.stderr.write(
        f"[bridge] WARNUNG: AGENTX_TELEMETRY_REGISTRY={_REGISTRY_PATH} konnte "
        "nicht geladen werden — es gilt die eingebaute Default-Registry, die "
        "auf einem Remote-Host NICHT die erwarteten Repos enthaelt.\n"
    )

REPO_REGISTRY: list[dict[str, Any]] = _REGISTRY_FILE_REPOS or DEFAULT_REPO_REGISTRY
PROCESS_REGISTRY: list[dict[str, Any]] = _REGISTRY_FILE_PROCESSES or DEFAULT_PROCESS_REGISTRY

LOG_PATH = Path(os.environ.get("AGENTX_TELEMETRY_LOG", "/tmp/ref_run.log"))
LOG_TAIL_LINES = 10

# Bind-Adresse fuer --serve (nur lokal, nie 0.0.0.0 ohne expliziten Wunsch).
SERVE_HOST = os.environ.get("AGENTX_TELEMETRY_HOST", "127.0.0.1")
SERVE_PORT = int(os.environ.get("AGENTX_TELEMETRY_PORT", "8787"))

# Host-Kennzeichnung fuer die Multi-Host-Ansicht.
# Warum ein Override: der Remote-Host hat einen generischen Namen (oder nur
# eine IP). Im Dashboard soll der Ort stehen, den ein Mensch wiedererkennt —
# "hetzner", nicht "Ubuntu-2404-nbg1-01". Leer = echter Hostname.
HOST_LABEL = os.environ.get("AGENTX_TELEMETRY_HOSTLABEL", "").strip()

# Charter ist bindend (SCHWARM_STATUS.md Kopf). Hier nur gespiegelt, nicht erfunden.
CHARTER: dict[str, Any] = {
    "diagnostic_only": True,
    "live_execution": False,
    "order_send": False,
    "not_investment_advice": True,
}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path | None = None, timeout: float = 5.0) -> tuple[int, str, str]:
    """Subprozess ohne Shell. Gibt (returncode, stdout, stderr) — nie eine Exception."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: {' '.join(cmd)}"
    except Exception as exc:  # pragma: no cover - defensiv
        return 1, "", f"{type(exc).__name__}: {exc}"


def _run_git(args: list[str], repo: Path | None = None,
             git_dir: Path | None = None,
             timeout: float = 5.0) -> tuple[int, str, str]:
    """
    Git-Aufruf mit expliziter safe.directory-Freigabe.

    WARUM DAS NOETIG IST (gemessen auf hetzner, 2026-09-21):
        Repos, die per rsync vom Mac kommen, tragen eine fremde UID
        (UNKNOWN:staff). Git verweigert dann mit "detected dubious ownership"
        und die Bridge meldet 'error' fuer ein vollkommen gesundes Repo.

        Die naheliegende Loesung — `git config --global --add safe.directory`
        — greift unter systemd NICHT zuverlaessig: Der Dienst hat ein anderes
        HOME, und ProtectHome kann ~/.gitconfig ausblenden. Die Konfiguration
        liegt dann an einem Ort, den der Dienst nie liest.

        Robuster: die Ausnahme pro Aufruf mitgeben (`-c safe.directory=...`).
        Damit haengt die Bridge nicht an einer Host-Konfiguration, die beim
        naechsten Deploy wieder fehlt — sie traegt ihre Voraussetzung selbst.

    Die Freigabe gilt nur fuer das jeweilige Repo, nicht global.
    """
    cmd = ["git", "-c", f"safe.directory={repo or git_dir or '*'}", *args]
    return _run(cmd, cwd=None if git_dir else repo, timeout=timeout)


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _humanize_seconds(seconds: float | None) -> str:
    """4470.0 -> '1h 14m 30s'."""
    if seconds is None:
        return "—"
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _parallel_map(fn: Callable[[Any], T], items: list[Any]) -> list[T]:
    """
    Fuehrt fn ueber items parallel aus. Subprozess-Starts (git, ps, lsof) sind
    I/O-gebunden und dominieren die Zykluszeit; bei einem 2s-Takt lohnt das.

    Ergebnisse behalten die Reihenfolge von items. Faellt bei Problemen auf
    serielle Ausfuehrung zurueck — lieber langsam als falsch.
    """
    if not items:
        return []
    if len(items) == 1:
        return [fn(items[0])]
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(items))) as pool:
            return list(pool.map(fn, items))
    except Exception:
        return [fn(item) for item in items]


# ---------------------------------------------------------------------------
# 1. Git-Status
# ---------------------------------------------------------------------------

@dataclass
class RepoStatus:
    name: str
    path: str
    role: str
    state: str                      # ok | bare | bare_empty | nested | not_found | no_git | error
    kind: str = "worktree"          # worktree | bare | package
    head: str | None = None
    branch: str | None = None
    dirty: bool | None = None
    changed_files: list[str] = field(default_factory=list)
    changed_count: int = 0
    health: str = "UNKNOWN"         # CLEAN | WARN | DIRTY | NOT FOUND | NESTED | BARE | EMPTY
    error: str | None = None


def _find_enclosing_repo(path: Path) -> Path | None:
    """Sucht das naechste uebergeordnete Verzeichnis mit .git."""
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _looks_bare(path: Path) -> bool:
    """
    Erkennt ein Bare-Repo an seinen eigenen Markern — nicht an der Endung.

    Ein Bare-Repo hat HEAD, objects/ und refs/ direkt im Ordner. Die
    '.git'-Endung ist Konvention, kein Kriterium: `/root/newsagent-bare.git`
    heisst so, aber ein Bare koennte auch anders heissen.

    Preis der Ehrlichkeit: Es gibt keine 100%-Erkennung ohne `git rev-parse
    --is-bare-repository`. Der Marker-Check ist die Vorbedingung, der
    abschliessende git-Aufruf in _inspect_bare ist der Beleg.
    """
    return ((path / "HEAD").is_file()
            and (path / "objects").is_dir()
            and (path / "refs").is_dir())


def _inspect_bare(status: RepoStatus, target: Path, declared: bool) -> RepoStatus:
    """
    Fragt ein Bare-Repo ausschliesslich per --git-dir ab.

    WARUM NICHT `cwd=target`: `git status` im Bare-Verzeichnis bricht mit
    "this operation must be run in a work tree" ab. Die Bridge wuerde 'error'
    melden — ein falscher Fehlerzustand fuer ein voellig gesundes Repo. Genau
    die Klasse "Fehlen als Rauschen statt Information", die wir vermeiden.

    Deshalb: kein `status`, kein `dirty`. Ein Bare hat keinen Arbeitsbaum und
    damit auch keinen Dirty-Zustand. `dirty=None` ist die korrekte Aussage —
    nicht `False` (das wuerde "sauber" behaupten, was hier bedeutungslos ist).
    """
    git_dir = f"--git-dir={target}"

    rc, out, err = _run_git([git_dir, "rev-parse", "--is-bare-repository"], git_dir=target)
    if rc != 0 or out.strip() != "true":
        # Marker sahen nach Bare aus, git widerspricht. Entweder ein
        # beschaedigtes Repo oder ein Verzeichnis, das zufaellig so aussieht.
        status.state = "error"
        status.health = "UNKNOWN"
        status.error = (err or "git --git-dir: kein Bare-Repo"
                        + ("" if declared else " (Marker sahen nach Bare aus)"))
        return status

    status.kind = "bare"

    # HEAD: Bei einem Bare ist der abgekuerzte Hash die einzige Anzeige-Groesse.
    rc, out, err = _run_git([git_dir, "rev-parse", "--short", "HEAD"], git_dir=target)
    if rc != 0:
        # Frisch initialisiertes Bare ohne einen einzigen Commit.
        # Das ist ein echter Zustand, kein Fehler.
        status.state = "bare_empty"
        status.health = "EMPTY"
        status.error = "Bare-Repo ohne Commits (HEAD ungeboren)"
        return status
    status.head = out.splitlines()[0].strip() if out else None

    # Branch: symbolischer Ref. In einem Bare ist "(detached)" bzw. der
    # Default-Branch (master/main) die Aussage — es gibt kein "current branch"
    # im Sinne eines Checkouts.
    rc, out, _ = _run_git([git_dir, "symbolic-ref", "--short", "HEAD"], git_dir=target)
    status.branch = out.splitlines()[0].strip() if rc == 0 and out else "(detached)"

    status.dirty = None
    status.health = "BARE"
    # state MUSS hier explizit gesetzt werden: der Dataclass-Default ist "ok",
    # und ein Bare mit HEAD traf bisher keinen der beiden state-Zweige
    # (nur der Fehlerfall oben setzt "bare_empty"). Folge war state="ok" bei
    # kind="bare"/health="BARE" — ein Widerspruch, der im Dashboard die
    # bare-Regeln umging und den Schema-Check leiser machte statt rot.
    status.state = "bare"
    return status


def inspect_repo(name: str, rel_path: str, role: str, base: Path,
                 kind: str = "worktree") -> RepoStatus:
    """
    Ermittelt Git-Zustand eines Repos — mit ehrlicher Zustandsaufloesung.

    Faellt bewusst NICHT auf ein uebergeordnetes Repo zurueck, wenn der Pfad
    selbst kein Repo ist: genau das wuerde 'order_execution_engine' faelschlich
    den Hub-HEAD andichten.

    kind="bare": Ein Bare-Repo hat keinen Arbeitsbaum. `git status` ist dort
    nicht definiert und `(target/'.git').exists()` ist False — die naive
    Pruefung wuerde "no_git" melden, obwohl das Repo gesund ist. Bare-Repos
    werden deshalb ueber ihre eigenen Marker erkannt (HEAD, objects/, refs/)
    und ausschliesslich mit `git --git-dir=...` abgefragt.
    """
    target = Path(rel_path).expanduser()
    if not target.is_absolute():
        target = base / rel_path
    target = target.expanduser().resolve()

    status = RepoStatus(name=name, path=str(target), role=role, state="ok")

    if not target.exists():
        status.state = "not_found"
        status.health = "NOT FOUND"
        status.error = "Pfad existiert nicht (Modul nicht ausgegruendet)"
        return status

    if not target.is_dir():
        status.state = "error"
        status.health = "UNKNOWN"
        status.error = "Pfad ist kein Verzeichnis"
        return status

    # --- Bare-Repo: eigener Zweig, noch vor der .git-Pruefung ---------------
    # Ein Bare-Repo hat nie ein .git-Verzeichnis (der Ordner IST das Repo).
    if kind == "bare" or _looks_bare(target):
        return _inspect_bare(status, target, declared=(kind == "bare"))

    is_repo = (target / ".git").exists()
    if not is_repo:
        # Ist es ein Unterordner eines anderen Repos? -> nested (kein eigener Anker)
        enclosing = _find_enclosing_repo(target)
        if enclosing is not None:
            status.state = "nested"
            status.health = "NESTED"
            status.error = f"kein eigenes Repo — Teil von {enclosing.name}"
            # Anker des umgebenden Repos mitliefern (als Information, klar benannt).
            rc, out, _ = _run_git(["rev-parse", "--short", "HEAD"], repo=enclosing)
            if rc == 0 and out:
                status.head = out.splitlines()[0].strip()
            return status
        status.state = "no_git"
        status.health = "UNKNOWN"
        status.error = "kein Git-Repository"
        return status

    rc, out, err = _run_git(["rev-parse", "--short", "HEAD"], repo=target)
    if rc != 0:
        status.state = "error"
        status.health = "UNKNOWN"
        status.error = err or "git rev-parse fehlgeschlagen"
        return status
    status.head = out.splitlines()[0].strip() if out else None

    rc, out, err = _run_git(["branch", "--show-current"], repo=target)
    if rc == 0:
        status.branch = out.splitlines()[0].strip() if out else None
        if not status.branch:
            status.branch = "(detached)"

    rc, out, err = _run_git(["status", "--porcelain"], repo=target)
    if rc != 0:
        status.state = "error"
        status.health = "UNKNOWN"
        status.error = err or "git status fehlgeschlagen"
        return status

    lines = [ln for ln in out.splitlines() if ln.strip()]
    status.changed_files = lines
    status.changed_count = len(lines)
    status.dirty = bool(lines)

    if not lines:
        status.health = "CLEAN"
    elif all(ln.startswith("??") for ln in lines):
        # Nur neue, unverfolgte Dateien -> noch kein Verlustrisiko, aber Hinweis.
        status.health = "WARN"
    else:
        status.health = "DIRTY"

    return status


def collect_repos(base: Path) -> list[RepoStatus]:
    """Alle Repos parallel pruefen (Reihenfolge bleibt Registry-Reihenfolge)."""
    return _parallel_map(
        lambda item: inspect_repo(
            item["name"],
            item.get("path", "."),
            item.get("role", "satellite"),
            base,
            item.get("kind", "worktree"),
        ),
        list(REPO_REGISTRY),
    )


# ---------------------------------------------------------------------------
# 2. Prozess-Health
# ---------------------------------------------------------------------------

@dataclass
class AgentStatus:
    name: str
    state: str                      # running | not_running | error
    required: bool = True
    pids: list[int] = field(default_factory=list)
    pid: int | None = None
    uptime_seconds: float | None = None
    uptime_human: str = "—"
    started_at: str | None = None
    cmdline: str | None = None
    cwd: str | None = None
    detected_by: str | None = None    # pgrep | systemd — wie wurde der Fund gemacht
    unit: str | None = None           # systemd-Unit-Name, falls konfiguriert
    unit_state: str | None = None     # Rohzustand von systemd (active/failed/...)
    error: str | None = None


def _pgrep(pattern: str) -> tuple[list[int], str | None]:
    """
    PID-Suche via pgrep. Faellt auf 'ps -ax -o pid=,command=' zurueck,
    falls pgrep fehlt. Gibt (pids, error) zurueck.
    """
    if shutil.which("pgrep"):
        rc, out, err = _run(["pgrep", "-f", pattern])
        if rc == 0 and out:
            pids = []
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
            return pids, None
        if rc == 1:
            return [], None  # kein Treffer — kein Fehler
        return [], err or "pgrep fehlgeschlagen"

    # Fallback ohne pgrep
    rc, out, err = _run(["ps", "-ax", "-o", "pid=,command="])
    if rc != 0:
        return [], err or "ps fehlgeschlagen"
    pids = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        head, _, rest = line.partition(" ")
        if head.isdigit() and pattern in rest:
            pids.append(int(head))
    return pids, None


def _process_start_time(pid: int) -> tuple[str | None, float | None]:
    """
    Startzeit via 'ps -o lstart='. Gibt (iso_string, uptime_seconds).
    Uptime ist berechnet, nicht geschaetzt; bei Parser-Fehler None.
    """
    rc, out, err = _run(["ps", "-p", str(pid), "-o", "lstart="])
    if rc != 0 or not out:
        return None, None
    raw = out.strip()
    # Format z.B.: "Sun Sep 20 14:35:58 2026"
    for fmt in ("%a %b %d %H:%M:%S %Y", "%a %b  %d %H:%M:%S %Y"):
        try:
            started = datetime.strptime(raw, fmt).astimezone()
            uptime = (datetime.now().astimezone() - started).total_seconds()
            return started.isoformat(timespec="seconds"), max(0.0, uptime)
        except ValueError:
            continue
    return raw, None


def _process_cmdline(pid: int) -> str | None:
    rc, out, _ = _run(["ps", "-p", str(pid), "-o", "command="])
    return out.strip() if rc == 0 and out else None


def _process_cwd(pid: int) -> str | None:
    if not shutil.which("lsof"):
        return None
    rc, out, _ = _run(["lsof", "-p", str(pid), "-a", "-d", "cwd", "-Fn"])
    if rc != 0:
        return None
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:].strip()
    return None


def _systemd_unit_state(unit: str) -> tuple[str | None, str | None]:
    """
    Fragt einen systemd-Unit-Zustand ab. Gibt (state, error).

    WARUM DIESER WEG NEBEN pgrep: Ein Unit-Name steht NICHT in der Kommandozeile
    des Prozesses. `pgrep -f newsagent-poll.service` findet nichts, obwohl der
    Dienst laeuft — ein falsches not_running. systemd ist die Autoritaet fuer
    seine eigenen Units, also fragen wir systemd.

    Rueckgabe-State ist der systemd-Wert (active, failed, inactive, ...) —
    NICHT das Bridge-Vokabular. Die Uebersetzung passiert im Aufrufer, damit
    die Rohform im Snapshot sichtbar bleibt.
    """
    if not shutil.which("systemctl"):
        return None, "systemctl nicht verfuegbar"
    rc, out, err = _run(["systemctl", "is-active", unit], timeout=8.0)
    # is-active gibt den Zustand auf stdout aus, auch bei RC != 0
    # (z.B. "failed" mit RC 3, "inactive" mit RC 3). RC 4 = Unit unbekannt.
    state = out.strip().splitlines()[0].strip() if out.strip() else ""
    if not state:
        return None, err or f"systemctl is-active {unit}: keine Ausgabe"
    return state, None


def inspect_process(spec: dict[str, Any]) -> AgentStatus:
    name = spec["name"]
    pattern = spec["pattern"]
    required = bool(spec.get("required", True))
    unit = spec.get("unit")

    st = AgentStatus(name=name, state="not_running", required=required)

    # --- a) pgrep: findet echte Prozesse (Mac wie Host) ----------------------
    pids, err = _pgrep(pattern)
    if err:
        st.state = "error"
        st.error = err
        return st

    # Eigene pgrep-Aufrufe nie als Treffer zaehlen (Selbsttreffer vermeiden).
    pids = [p for p in pids if p != os.getpid()]

    if pids:
        st.pids = sorted(pids)
        st.pid = st.pids[0]
        st.state = "running"
        st.detected_by = "pgrep"

        started_at, uptime = _process_start_time(st.pid)
        st.started_at = started_at
        st.uptime_seconds = round(uptime, 1) if uptime is not None else None
        st.uptime_human = _humanize_seconds(uptime)
        st.cmdline = _process_cmdline(st.pid)
        st.cwd = _process_cwd(st.pid)
        return st

    # --- b) systemd-Unit: greift, wenn pgrep nichts findet -------------------
    # Ein oneshot-/timer-getriebener Dienst hat zwischen zwei Laeufen keinen
    # Prozess. pgrep sagt "laeuft nicht", systemd sagt "active (waiting)".
    # Ohne diesen Zweig waeren alle Timer-Dienste dauerhaft rot.
    if unit:
        unit_state, unit_err = _systemd_unit_state(unit)
        st.unit = unit
        st.unit_state = unit_state
        if unit_state is not None:
            st.detected_by = "systemd"
            if unit_state == "active":
                st.state = "running"
                st.uptime_human = "— (systemd)"
            elif unit_state == "activating":
                st.state = "starting"
            elif unit_state == "failed":
                st.state = "failed"
                st.error = f"systemd-Unit {unit} ist failed"
            else:
                # inactive / deactivating / dead
                st.state = "not_running"
        elif unit_err:
            st.error = unit_err

    return st


def collect_agents() -> list[AgentStatus]:
    """Alle Prozesse parallel pruefen."""
    return _parallel_map(inspect_process, list(PROCESS_REGISTRY))


# ---------------------------------------------------------------------------
# 3. Log-Tail
# ---------------------------------------------------------------------------

def collect_log(path: Path = LOG_PATH, lines: int = LOG_TAIL_LINES) -> dict[str, Any]:
    """
    Liest die letzten N Zeilen. Liest die Datei von hinten in Blaettern,
    damit ein 100-MB-Log nicht komplett in den Speicher muss.
    """
    result: dict[str, Any] = {
        "path": str(path),
        "lines": [],
        "line_count": 0,
        "size_bytes": None,
        "modified_at": None,
        "error": None,
    }
    if not path.exists():
        result["error"] = "Logdatei existiert nicht"
        return result

    try:
        stat = path.stat()
        result["size_bytes"] = stat.st_size
        result["modified_at"] = datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(
            timespec="seconds"
        )
    except OSError as exc:
        result["error"] = f"stat fehlgeschlagen: {exc}"
        return result

    try:
        block = 8192
        chunks: list[bytes] = []
        newlines = 0
        start = 0
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
            # Rueckwaerts lesen, aber auf BYTES zaehlen und erst am Ende
            # dekodieren. Zwei Fehler waren hier uebereinander:
            #   1. `collected.count("\n")` zaehlte in einer Liste von bereits
            #      gesplitteten Zeilen — dort gibt es nie ein "\n"-Element,
            #      die Bedingung war immer wahr und die Schleife lief bis 0.
            #   2. `decode` + `splitlines` auf dem wachsenden Gesamtpuffer pro
            #      Block machten das vollstaendige Lesen quadratisch.
            # Abbruch bei lines + 1 Umbruechen: die erste der letzten N Zeilen
            # ist dann garantiert vollstaendig (nicht mitten im Block).
            while pos > 0 and newlines < lines + 1:
                step = min(block, pos)
                pos -= step
                fh.seek(pos)
                chunk = fh.read(step)
                chunks.append(chunk)
                newlines += chunk.count(b"\n")
            start = pos
        buffer = b"".join(reversed(chunks))
        collected = buffer.decode("utf-8", errors="replace").splitlines()
        # Bei Offset > 0 ist die erste Zeile angeschnitten (oder eine
        # UTF-8-Sequenz an der Blockgrenze) — sie gehoert nicht zum Tail.
        if start > 0 and collected:
            collected = collected[1:]
        tail = [ln.rstrip("\r") for ln in collected[-lines:]]
        result["lines"] = tail
        result["line_count"] = len(tail)
    except OSError as exc:
        result["error"] = f"Lesefehler: {exc}"

    return result


# ---------------------------------------------------------------------------
# 4. Alerts + Charter
# ---------------------------------------------------------------------------

def _porcelain_untracked_rel(line: str) -> str | None:
    """Extrahiert den Relativpfad aus einer ``?? path``-Porcelain-Zeile."""
    if not line.startswith("??"):
        return None
    rel = line[2:].lstrip().rstrip("/")
    return rel or None


def _untracked_entry_has_own_git(repo_root: Path, rel: str) -> bool:
    """
    True, wenn ``repo_root/rel`` ein eigenes Git-Anker (``.git``-Dir oder
    ``gitdir:``-Datei) ist — ohne Symlinks nach aussen zu folgen.

    ``?? X/`` in porcelain sieht fuer eingebettete Repos und normale Ordner
    gleich aus; nur diese Pruefung trennt REPO_NESTED von REPO_UNTRACKED.
    """
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return False
    root = Path(repo_root)
    candidate = root / rel
    # Symlink am Eintrag selbst: nicht folgen (sonst Z → /tmp/repo-mit-git).
    try:
        if candidate.is_symlink():
            return False
    except OSError:
        return False
    if not candidate.is_dir():
        return False
    # Unter Root halten (kein Escape ueber aufgeloeste Zwischenstuecke).
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (ValueError, OSError, RuntimeError):
        return False
    marker = candidate / ".git"
    # Ordner ODER Datei (Worktree/Submodul: ``gitdir: …``).
    try:
        return marker.is_dir() or marker.is_file()
    except OSError:
        return False


def _registered_nested_paths(repos: Iterable[RepoStatus]) -> set[Path]:
    """Absolute Pfade aller Registry-Eintraege mit state=nested."""
    out: set[Path] = set()
    for r in repos:
        if r.state != "nested":
            continue
        try:
            out.add(Path(r.path).resolve(strict=False))
        except (OSError, RuntimeError):
            out.add(Path(r.path))
    return out


def _append_untracked_nested_alerts(
    alerts: list[dict[str, Any]],
    repo: RepoStatus,
    nested_registered: set[Path],
    *,
    emit_plain_untracked: bool = False,
) -> None:
    """Klassifiziert ``??``-Zeilen: eigenes .git → REPO_NESTED, sonst optional UNTRACKED."""
    plain = 0
    root = Path(repo.path)
    for line in repo.changed_files:
        rel = _porcelain_untracked_rel(line)
        if rel is None:
            continue
        if _untracked_entry_has_own_git(root, rel):
            try:
                abs_nested = (root / rel).resolve(strict=False)
            except (OSError, RuntimeError):
                abs_nested = root / rel
            if abs_nested in nested_registered:
                continue
            alerts.append({
                "severity": "info",
                "code": "REPO_NESTED",
                "source": rel,
                "message": (
                    f"{rel}: unregistered nested Git "
                    f"(unter {repo.name})"
                ),
            })
        elif emit_plain_untracked:
            plain += 1
    if emit_plain_untracked and plain:
        alerts.append({
            "severity": "info",
            "code": "REPO_UNTRACKED",
            "source": repo.name,
            "message": f"{repo.name}: {plain} untracked Datei(en)",
        })


def build_alerts(repos: Iterable[RepoStatus], agents: Iterable[AgentStatus],
                 log: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Alerts sind aus dem Zustand abgeleitet — nicht erfunden.
    Fehlende, nicht ausgegruendete Module erzeugen INFO (Information),
    kein CRITICAL: eine Luecke ist kein Ausfall.
    """
    alerts: list[dict[str, Any]] = []
    repo_list = list(repos)
    nested_registered = _registered_nested_paths(repo_list)

    for repo in repo_list:
        if repo.state == "not_found":
            alerts.append({
                "severity": "info",
                "code": "REPO_NOT_FOUND",
                "source": repo.name,
                "message": f"{repo.name}: nicht ausgegruendet (Pfad fehlt)",
            })
        elif repo.state == "nested":
            alerts.append({
                "severity": "info",
                "code": "REPO_NESTED",
                "source": repo.name,
                "message": f"{repo.name}: kein eigenes Repo — Teil des Hubs",
            })
        elif repo.state == "error":
            alerts.append({
                "severity": "warn",
                "code": "REPO_ERROR",
                "source": repo.name,
                "message": f"{repo.name}: {repo.error}",
            })
        elif repo.state == "bare_empty":
            # Ein Bare ohne Commits ist ein echter Befund: Der Push-Pfad
            # existiert, hat aber noch nie etwas angenommen.
            alerts.append({
                "severity": "warn",
                "code": "REPO_BARE_EMPTY",
                "source": repo.name,
                "message": f"{repo.name}: Bare-Repo ohne Commits (HEAD ungeboren)",
            })
        elif repo.health == "DIRTY":
            alerts.append({
                "severity": "warn",
                "code": "REPO_DIRTY",
                "source": repo.name,
                "message": f"{repo.name}: {repo.changed_count} uncommitted Aenderung(en)",
            })
            # Auch bei DIRTY: eingebettete Repos unter ?? melden (sonst Blindheit
            # sobald parallel getrackte Dateien geaendert sind).
            _append_untracked_nested_alerts(alerts, repo, nested_registered)
        elif repo.health == "WARN":
            # WARN = nur ??-Eintraege. Eingebettete Repos (X/.git) sind NESTED,
            # keine UNTRACKED — sonst luegt der Alert-Typ (Befund 2026-10-01).
            _append_untracked_nested_alerts(alerts, repo, nested_registered,
                                           emit_plain_untracked=True)

    for agent in agents:
        if agent.state == "failed":
            alerts.append({
                "severity": "critical",
                "code": "PROCESS_FAILED",
                "source": agent.name,
                "message": f"{agent.name}: systemd-Unit {agent.unit} ist failed",
            })
        elif agent.state == "not_running" and agent.required:
            alerts.append({
                "severity": "critical",
                "code": "PROCESS_DOWN",
                "source": agent.name,
                "message": f"{agent.name} laeuft nicht (required)",
            })
        elif agent.state == "error":
            alerts.append({
                "severity": "warn",
                "code": "PROCESS_ERROR",
                "source": agent.name,
                "message": f"{agent.name}: {agent.error}",
            })

    if log.get("error"):
        alerts.append({
            "severity": "warn",
            "code": "LOG_UNAVAILABLE",
            "source": "log_tail",
            "message": f"{log['path']}: {log['error']}",
        })

    # Kritisch zuerst, dann warn, dann info.
    order = {"critical": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 9))
    return alerts


# ---------------------------------------------------------------------------
# 5. Snapshot + atomares Schreiben
# ---------------------------------------------------------------------------

def build_snapshot(base: Path = BASE_DIR, log_path: Path = LOG_PATH) -> dict[str, Any]:
    started = time.perf_counter()

    # Repos, Prozesse und Log sind unabhaengig -> parallel erfassen.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        f_repos = pool.submit(collect_repos, base)
        f_agents = pool.submit(collect_agents)
        f_log = pool.submit(collect_log, log_path)
        repos = f_repos.result()
        agents = f_agents.result()
        log = f_log.result()

    alerts = build_alerts(repos, agents, log)

    duration_ms = round((time.perf_counter() - started) * 1000, 1)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _iso_now(),
        # Numerischer Zwilling zu generated_at. Der Pull-Agent berechnet daraus
        # das Alter der Datei — ohne Dateisystem-mtime, die beim rsync auf die
        # Empfangszeit gesetzt wird und damit luegen wuerde.
        "generated_ts": round(time.time(), 3),
        "charter": dict(CHARTER),
        "repos": [asdict(r) for r in repos],
        "agents": [asdict(a) for a in agents],
        "alerts": alerts,
        "logs": log,
        "meta": {
            "host": HOST_LABEL or socket.gethostname(),
            "hostname_real": socket.gethostname(),
            "platform": f"{platform.system()} {platform.release()}",
            "base_dir": str(base),
            "duration_ms": duration_ms,
            "alert_counts": {
                sev: sum(1 for a in alerts if a["severity"] == sev)
                for sev in ("critical", "warn", "info")
            },
        },
    }


def write_snapshot(snapshot: dict[str, Any], out_path: Path,
                   mirrors: Iterable[Path] | None = None) -> list[Path]:
    """
    Atomares Schreiben: temp-Datei im Zielverzeichnis + os.replace.
    Damit sieht das pollende Frontend nie eine halb geschriebene JSON.

    'mirrors' erlaubt zusaetzliche Ziele (z. B. public/status.json im
    Vite-Projekt). Ein fehlgeschlagener Mirror bricht den Hauptpfad nicht ab,
    sondern wird als Warnung gemeldet — die Bridge darf nie sterben.
    """
    out_path = Path(out_path)
    payload = json.dumps(snapshot, indent=2, ensure_ascii=False)
    written: list[Path] = [out_path]

    targets = [out_path, *[Path(m) for m in (mirrors or [])]]
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(target.parent), prefix=".status.", suffix=".json.tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_name, target)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except Exception as exc:
            if target == out_path:
                raise
            print(f"[bridge] Mirror fehlgeschlagen ({target}): {type(exc).__name__}: {exc}",
                  file=sys.stderr, flush=True)

    return written


# ---------------------------------------------------------------------------
# 6. HTTP-Endpoint (optional)
# ---------------------------------------------------------------------------

def _make_handler(out_path: Path):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            route = self.path.split("?")[0]
            if route not in ("/", "/status.json", "/health"):
                self.send_error(404, "not found")
                return
            try:
                body = out_path.read_bytes()
            except OSError as exc:
                self.send_error(503, f"status.json nicht lesbar: {exc}")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: Any) -> None:  # ruhig bleiben
            return

    return Handler


def serve(out_path: Path) -> None:
    from http.server import ThreadingHTTPServer

    handler = _make_handler(out_path)
    httpd = ThreadingHTTPServer((SERVE_HOST, SERVE_PORT), handler)
    print(f"[bridge] HTTP-Endpoint: http://{SERVE_HOST}:{SERVE_PORT}/status.json", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


# ---------------------------------------------------------------------------
# 7. CLI
# ---------------------------------------------------------------------------

def _print_summary(snapshot: dict[str, Any]) -> None:
    print(f"[bridge] {snapshot['generated_at']}  ({snapshot['meta']['duration_ms']}ms)")
    for r in snapshot["repos"]:
        head = r["head"] or "—"
        print(f"  repo   {r['name']:<22} {r['health']:<10} {head:<10} {r['state']}")
    for a in snapshot["agents"]:
        print(f"  agent  {a['name']:<22} {a['state']:<12} pid={a['pid']} up={a['uptime_human']}")
    print(f"  log    {snapshot['logs']['path']} ({snapshot['logs']['line_count']} Zeilen)")
    counts = snapshot["meta"]["alert_counts"]
    print(f"  alerts critical={counts['critical']} warn={counts['warn']} info={counts['info']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Telemetry Bridge — schreibt status.json fuer das X-STORAGE Control Center."
    )
    parser.add_argument(
        "--out",
        default=os.environ.get("AGENTX_TELEMETRY_OUT", str(PROJECT_ROOT / "dashboard" / "status.json")),
        help="Zielpfad fuer status.json",
    )
    parser.add_argument(
        "--mirror",
        action="append",
        default=None,
        help="Zusaetzlicher Zielpfad (mehrfach angebbar), z. B. public/status.json "
             "des Vite-Projekts. Default aus AGENTX_TELEMETRY_MIRROR (os.pathsep-getrennt).",
    )
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                        help="Schreibintervall in Sekunden (default 2.0)")
    parser.add_argument("--once", action="store_true", help="einmalig schreiben und beenden")
    parser.add_argument("--stdout", action="store_true", help="Snapshot zusaetzlich auf stdout")
    parser.add_argument("--serve", action="store_true", help="HTTP-Endpoint bereitstellen")
    parser.add_argument("--base", default=str(BASE_DIR), help="Basisverzeichnis der Repo-Registry")
    args = parser.parse_args(argv)

    base = Path(args.base).resolve()
    out_path = Path(args.out).resolve()

    # Mirror-Ziele: CLI hat Vorrang, sonst Env (os.pathsep-getrennt).
    if args.mirror:
        mirrors = [Path(m).resolve() for m in args.mirror]
    else:
        env_mirror = os.environ.get("AGENTX_TELEMETRY_MIRROR", "")
        mirrors = [Path(m).resolve() for m in env_mirror.split(os.pathsep) if m.strip()]

    def emit(snapshot: dict[str, Any]) -> None:
        write_snapshot(snapshot, out_path, mirrors)

    if args.once:
        snapshot = build_snapshot(base=base)
        emit(snapshot)
        _print_summary(snapshot)
        print(f"[bridge] geschrieben: {out_path}")
        for m in mirrors:
            print(f"[bridge] gespiegelt: {m}")
        if args.stdout:
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        return 0

    if args.serve:
        import threading

        def loop() -> None:
            while True:
                try:
                    emit(build_snapshot(base=base))
                except Exception as exc:  # Bridge darf nie sterben
                    print(f"[bridge] Fehler: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                time.sleep(args.interval)

        threading.Thread(target=loop, daemon=True).start()
        print(f"[bridge] schreibe {out_path} alle {args.interval}s", flush=True)
        for m in mirrors:
            print(f"[bridge] spiegele nach {m}", flush=True)
        serve(out_path)
        return 0

    print(f"[bridge] schreibe {out_path} alle {args.interval}s — Strg-C beendet", flush=True)
    for m in mirrors:
        print(f"[bridge] spiegele nach {m}", flush=True)
    try:
        while True:
            cycle_start = time.perf_counter()
            try:
                snapshot = build_snapshot(base=base)
                emit(snapshot)
                if args.stdout:
                    print(json.dumps(snapshot, indent=2, ensure_ascii=False), flush=True)
                else:
                    _print_summary(snapshot)
            except Exception as exc:
                print(f"[bridge] Fehler: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            elapsed = time.perf_counter() - cycle_start
            time.sleep(max(0.0, args.interval - elapsed))
    except KeyboardInterrupt:
        print("\n[bridge] gestoppt.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
