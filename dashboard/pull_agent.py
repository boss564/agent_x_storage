#!/usr/bin/env python3
"""
Remote Pull-Agent — holt die status.json eines Remote-Hosts auf den Mac.

Architektur (bewusst schmal):

    Remote:  telemetry_bridge.py --schreibt--> /var/lib/agent-x-telemetry/status.json
                                                          |
    Mac:     pull_agent.py --rsync holt ---------------> public/status-<host>.json
                                                          |
                                                          +-- Stale-Erkennung
                                                          +-- Transport-Metadaten

Warum ein eigener Agent und nicht rsync in einer Cron-Zeile: Der Agent muss
mehr tun als kopieren — er muss *sagen*, ob der Transport geklappt hat.
Ein reines rsync laesst bei Netzausfall die alte Datei stehen, und das
Dashboard zeigt sie als aktuell. Genau dieses stille Alter-Werden ist die
Luege, die wir vermeiden.

Vertrag (Schema ergaenzt, nichts ersetzt):
    Die Remote-JSON wird unveraendert uebernommen und um einen Block
    `transport` erweitert:
        transport {
            fetched_at, fetched_ts,   wann der Mac sie geholt hat
            source_host,              SSH-Ziel
            remote_path,              Pfad auf dem Host
            age_seconds,              Alter der Remote-Daten (generated_ts)
            stale,                    age > stale_after
            stale_after_seconds,      Schwelle
            ok,                       Transport erfolgreich
            error                     Fehlertext, falls nicht
        }

Wahrheitsregel: Bei fehlgeschlagenem Transport wird die letzte bekannte Datei
NICHT ueberschrieben — aber `ok: false` und der Fehler werden geschrieben.
Eine veraltete Datei mit ehrlichem Stempel ist besser als eine frische Datei,
die es nicht gibt.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SSH_HOST = os.environ.get("AGENTX_PULL_SSH_HOST", "hetzner")
DEFAULT_REMOTE_PATH = os.environ.get(
    "AGENTX_PULL_REMOTE_PATH", "/var/lib/agent-x-telemetry/status.json"
)
DEFAULT_INTERVAL = float(os.environ.get("AGENTX_PULL_INTERVAL", "15"))
DEFAULT_STALE_AFTER = float(os.environ.get("AGENTX_PULL_STALE_AFTER", "60"))
DEFAULT_TIMEOUT = float(os.environ.get("AGENTX_PULL_TIMEOUT", "15"))

# Zielt auf den public/-Ordner des Vite-Projekts: dort liegt auch die lokale
# status.json. Das Frontend unterscheidet die Quellen nur am Dateinamen.
DEFAULT_OUT = os.environ.get(
    "AGENTX_PULL_OUT",
    str(Path.home() / "repos" / "x-storage-control-center" / "public"
        / "status-hetzner.json"),
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_atomic(snapshot: dict[str, Any], out_path: Path) -> None:
    """Atomar: temp-Datei im Zielverzeichnis + os.replace. Kein halber Zustand."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out_path)


def fetch_remote(ssh_host: str, remote_path: str, timeout: float) -> tuple[str | None, str | None]:
    """
    Holt den Dateiinhalt per SSH. Gibt (inhalt, error).

    `cat` statt rsync: Wir wollen genau EINE Datei, atomar geschrieben auf der
    Gegenseite (os.replace), also ist ein read-only `cat` ausreichend und
    billiger als ein rsync-Prozess mit Connection-Reuse-Verhandlung. Bei
    mehreren Dateien (Logs, Metriken) waere rsync richtig — hier nicht.

    BatchMode=yes: kein Passwort-Prompt. Ein haengender SSH-Prozess in einem
    LaunchAgent ist schlimmer als ein Fehler.
    """
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=accept-new",
        ssh_host,
        f"cat {remote_path}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"SSH-Timeout nach {timeout}s"
    except FileNotFoundError:
        return None, "ssh nicht gefunden"
    except Exception as exc:  # pragma: no cover
        return None, f"{type(exc).__name__}: {exc}"

    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        return None, err[-1] if err else f"ssh exit {proc.returncode}"
    if not proc.stdout.strip():
        return None, "Remote-Datei ist leer"
    return proc.stdout, None


def build_pulled_snapshot(payload: dict[str, Any], ssh_host: str, remote_path: str,
                          stale_after: float, error: str | None) -> dict[str, Any]:
    """
    Baut den Snapshot fuer die Ausgabe. Bei Fehler wird der letzte bekannte
    Inhalt NICHT ueberschrieben (der Aufrufer entscheidet), sondern nur der
    Transport-Stempel gesetzt.
    """
    now = time.time()
    generated_ts = payload.get("generated_ts")
    age = round(now - generated_ts, 1) if isinstance(generated_ts, (int, float)) else None

    out = dict(payload)
    out["transport"] = {
        "fetched_at": _iso_now(),
        "fetched_ts": round(now, 3),
        "source_host": ssh_host,
        "remote_path": remote_path,
        "age_seconds": age,
        "stale": (age is not None and age > stale_after),
        "stale_after_seconds": stale_after,
        "ok": error is None,
        "error": error,
    }

    # Alerts des Remote-Snapshots um den Transport-Befund ergaenzen.
    alerts = list(out.get("alerts") or [])
    if error is not None:
        alerts.insert(0, {
            "severity": "warn",
            "code": "PULL_FAILED",
            "source": ssh_host,
            "message": f"Remote-Status nicht abrufbar: {error}",
        })
    elif age is not None and age > stale_after:
        alerts.insert(0, {
            "severity": "warn",
            "code": "REMOTE_STALE",
            "source": ssh_host,
            "message": (f"{ssh_host}: Daten sind {int(age)}s alt "
                        f"(Schwelle {int(stale_after)}s) — Remote-Bridge pruefen"),
        })
    out["alerts"] = alerts
    return out


def load_previous(out_path: Path) -> dict[str, Any] | None:
    if not out_path.is_file():
        return None
    try:
        return json.loads(out_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def pull_once(ssh_host: str, remote_path: str, out_path: Path,
              stale_after: float, timeout: float) -> dict[str, Any]:
    """Ein Pull-Zyklus. Gibt den geschriebenen Snapshot zurueck."""
    raw, error = fetch_remote(ssh_host, remote_path, timeout)

    payload: dict[str, Any] | None = None
    if raw is not None:
        try:
            candidate = json.loads(raw)
            if isinstance(candidate, dict) and "repos" in candidate:
                payload = candidate
            else:
                error = "Remote-JSON hat kein 'repos' — falsche Datei oder fremdes Schema"
        except json.JSONDecodeError as exc:
            error = f"Remote-JSON nicht lesbar: {exc}"

    if payload is None:
        # Transport oder Inhalt kaputt: letzten Stand bewahren, aber stempeln.
        previous = load_previous(out_path)
        if previous is None:
            # Noch nie etwas geholt — ein leerer Rumpf mit ehrlichem Fehler.
            payload = {"schema_version": 1, "repos": [], "agents": [],
                       "alerts": [], "charter": {},
                       "meta": {"host": ssh_host}}
        else:
            payload = previous

    snapshot = build_pulled_snapshot(payload, ssh_host, remote_path, stale_after, error)
    _write_atomic(snapshot, out_path)
    return snapshot


def _summary(snapshot: dict[str, Any], out_path: Path) -> str:
    t = snapshot.get("transport", {})
    age = t.get("age_seconds")
    parts = [
        f"[pull] {out_path.name}",
        f"ok={t.get('ok')}",
        f"alter={age:.0f}s" if isinstance(age, (int, float)) else "alter=—",
        f"stale={t.get('stale')}",
        f"repos={len(snapshot.get('repos') or [])}",
        f"alerts={len(snapshot.get('alerts') or [])}",
    ]
    if t.get("error"):
        parts.append(f"fehler={t['error']}")
    return "  ".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Holt die status.json eines Remote-Hosts (Pull-Modell, kein offener Port).",
    )
    ap.add_argument("--ssh-host", default=DEFAULT_SSH_HOST,
                    help=f"SSH-Alias oder user@host (Default: {DEFAULT_SSH_HOST})")
    ap.add_argument("--remote-path", default=DEFAULT_REMOTE_PATH,
                    help=f"Pfad zur status.json auf dem Host (Default: {DEFAULT_REMOTE_PATH})")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="Lokales Ziel (public/-Ordner des Dashboards)")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                    help=f"Sekunden zwischen Pulls (Default: {DEFAULT_INTERVAL})")
    ap.add_argument("--stale-after", type=float, default=DEFAULT_STALE_AFTER,
                    help=f"Alter in s, ab dem die Daten als veraltet gelten (Default: {DEFAULT_STALE_AFTER})")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help=f"SSH-Timeout in s (Default: {DEFAULT_TIMEOUT})")
    ap.add_argument("--once", action="store_true", help="Einmal holen und beenden")
    ap.add_argument("--quiet", action="store_true", help="Keine Statuszeilen")
    args = ap.parse_args(argv)

    out_path = Path(args.out).expanduser()
    verbose = not args.quiet

    if args.once:
        snap = pull_once(args.ssh_host, args.remote_path, out_path,
                         args.stale_after, args.timeout)
        if verbose:
            print(_summary(snap, out_path))
        return 0 if snap.get("transport", {}).get("ok") else 1

    if verbose:
        print(f"[pull] {args.ssh_host}:{args.remote_path} -> {out_path} "
              f"alle {args.interval}s (stale nach {args.stale_after}s)")
    try:
        while True:
            started = time.monotonic()
            snap = pull_once(args.ssh_host, args.remote_path, out_path,
                             args.stale_after, args.timeout)
            if verbose:
                print(_summary(snap, out_path), flush=True)
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, args.interval - elapsed))
    except KeyboardInterrupt:
        if verbose:
            print("\n[pull] beendet")
        return 0


if __name__ == "__main__":
    sys.exit(main())
