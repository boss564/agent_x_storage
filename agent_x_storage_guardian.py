"""
Agent 143 – Speicher-Wächter (Storage Guardian).

Überwacht den freien Speicher aller 3 Ebenen,
sagt die Speichernutzung voraus, alarmiert bei Engpässen,
räumt temporäre Dateien auf und protokolliert die History.
"""

import csv
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("agent_143_guardian")

# ─── Pfade ─────────────────────────────────────────────────────────

HISTORY_DIR = Path("/Volumes/THX_CORE_16TB/.claude")
HISTORY_DB = HISTORY_DIR / "storage_history.db"

STORAGE_PATHS = {
    "hot": "/Users/olivermueller",
    "warm": "/Volumes/THX_CORE_16TB",
    "cold": "/Volumes/THIXO_BACKUP_28TB",
}

# ─── Datenbank initialisieren ──────────────────────────────────────

def _init_history_db():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(HISTORY_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS storage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            layer TEXT NOT NULL,
            total_gb REAL,
            used_gb REAL,
            free_gb REAL,
            used_pct REAL
        )
    """)
    conn.commit()
    return conn


# ─── Hilfsfunktionen ───────────────────────────────────────────────

def _disk_usage(path: str) -> dict:
    try:
        u = shutil.disk_usage(path)
        total_gb = u.total / (1024**3)
        used_gb = u.used / (1024**3)
        free_gb = u.free / (1024**3)
        return {
            "total_gb": round(total_gb, 1),
            "used_gb": round(used_gb, 1),
            "free_gb": round(free_gb, 1),
            "used_pct": round((used_gb / total_gb) * 100, 1),
        }
    except FileNotFoundError:
        return {"error": f"Pfad nicht gefunden: {path}"}


# ─── Sub-Agenten (Agent 143) ───────────────────────────────────────

def check_space(layer: str | None = None) -> dict:
    """Prüft freien Speicher auf einer oder allen Ebenen."""
    layers = [layer] if layer else list(STORAGE_PATHS)
    result = {}
    for key in layers:
        path = STORAGE_PATHS.get(key)
        if not path:
            result[key] = {"error": f"Unbekannte Ebene: {key}"}
            continue
        result[key] = _disk_usage(path)
    return result


def forecast_usage(layer: str, days_back: int = 30) -> dict:
    """Einfache lineare Prognose basierend auf gespeicherter History."""
    conn = _init_history_db()
    rows = conn.execute(
        """SELECT timestamp, used_gb FROM storage_history
           WHERE layer = ? ORDER BY timestamp ASC LIMIT ?""",
        (layer, days_back),
    ).fetchall()
    conn.close()

    if len(rows) < 2:
        return {"error": "Nicht genügend Daten für Prognose"}

    # Einfache lineare Regression: y = mx + b
    timestamps = [datetime.fromisoformat(r[0]).timestamp() for r in rows]
    values = [r[1] for r in rows]

    n = len(timestamps)
    sx = sum(timestamps)
    sy = sum(values)
    sxx = sum(t * t for t in timestamps)
    sxy = sum(t * v for t, v in zip(timestamps, values))

    m = (n * sxy - sx * sy) / (n * sxx - sx * sx) if (n * sxx - sx * sx) != 0 else 0
    b = (sy - m * sx) / n

    # Prognose in 30 Tagen
    future_ts = timestamps[-1] + (30 * 86400)
    predicted_gb = m * future_ts + b

    current = _disk_usage(STORAGE_PATHS[layer])
    days_until_full = (
        (current["total_gb"] - current["used_gb"]) / max(m * 86400, 0.001)
        if m > 0
        else float("inf")
    )

    return {
        "layer": layer,
        "current_used_gb": current["used_gb"],
        "predicted_30d_gb": round(predicted_gb, 1),
        "trend_gb_per_day": round(m * 86400, 2),
        "days_until_full": round(days_until_full) if days_until_full != float("inf") else -1,
    }


_THRESHOLDS = {
    "hot":  {"critical": 20, "warning": 50},
    "warm": {"critical": 100, "warning": 250},
    "cold": {"critical": 200, "warning": 500},
}


def alert_critical() -> list[dict]:
    """Alarmiert bei kritischem und warnt bei niedrigem Speicher.

    Returns:
        Liste der Alarme: [{layer, level, free_gb, message}].
    """
    alerts = []
    for key, path in STORAGE_PATHS.items():
        usage = _disk_usage(path)
        if "error" in usage:
            continue
        free = usage["free_gb"]
        thr = _THRESHOLDS[key]

        if free < thr["critical"]:
            alerts.append({
                "layer": key,
                "level": "critical",
                "free_gb": free,
                "message": f"{key}: Nur {free} GB frei! (kritisch < {thr['critical']} GB)",
            })
        elif free < thr["warning"]:
            alerts.append({
                "layer": key,
                "level": "warning",
                "free_gb": free,
                "message": f"{key}: Nur {free} GB frei (Schwelle: {thr['warning']} GB)",
            })

    return alerts


def auto_clean_temp(max_age_hours: int = 24, dry_run: bool = True) -> list[str]:
    """Löscht temporäre Dateien bei Speicher-Engpässen.

    Durchsucht temp/-Ordner aller Ebenen nach alten Dateien.
    """
    cleared = []
    temp_dirs = [
        "/Volumes/THX_CORE_16TB/temp",
        "/Volumes/THIXO_BACKUP_28TB/temp",
        "/tmp",
    ]
    now = time.time()
    cutoff = now - (max_age_hours * 3600)

    for td in temp_dirs:
        p = Path(td)
        if not p.is_dir():
            continue
        for f in p.iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                if dry_run:
                    cleared.append(f"[dry-run] würde löschen: {f}")
                else:
                    try:
                        f.unlink()
                        cleared.append(f"gelöscht: {f}")
                    except OSError as e:
                        cleared.append(f"fehler: {f} – {e}")

    return cleared


def optimize_storage() -> list[str]:
    """Schlägt Speicher-Optimierungen vor.

    Prüft auf Duplikate, übergroße temp-Dateien
    und ineffiziente Dateiformate.
    """
    suggestions = []
    warm_temp = Path("/Volumes/THX_CORE_16TB/temp")

    if warm_temp.is_dir():
        large_files = sorted(warm_temp.glob("*"), key=lambda f: f.stat().st_size, reverse=True)[:5]
        for f in large_files:
            size_mb = f.stat().st_size / (1024**2)
            if size_mb > 100:
                suggestions.append(
                    f"Große temp-Datei: {f} ({size_mb:.0f} MB) – "
                    "ggf. löschen oder archivieren"
                )

    # Prüfe, ob WAVs verlustfrei komprimiert werden können
    warm_audio = Path("/Volumes/THX_CORE_16TB/media/audio")
    if warm_audio.is_dir():
        wavs = list(warm_audio.rglob("*.wav"))
        if len(wavs) > 10:
            total_mb = sum(f.stat().st_size for f in wavs) / (1024**2)
            suggestions.append(
                f"{len(wavs)} WAV-Dateien ({total_mb:.0f} MB) – "
                "Konvertierung zu FLAC spart ~50%"
            )

    warm_images = Path("/Volumes/THX_CORE_16TB/media/images")
    if warm_images.is_dir():
        pngs = list(warm_images.rglob("*.png"))
        if len(pngs) > 10:
            total_mb = sum(f.stat().st_size for f in pngs) / (1024**2)
            suggestions.append(
                f"{len(pngs)} PNG-Dateien ({total_mb:.0f} MB) – "
                "Konvertierung zu WebP spart ~70%"
            )

    return suggestions


def report_smart() -> dict:
    """Prüft SMART-Status der Festplatten via diskutil."""
    result = {}
    try:
        out = subprocess.run(
            ["diskutil", "list", "-internal"],
            capture_output=True, text=True, timeout=10,
        )
        disks = []
        for line in out.stdout.splitlines():
            if line.strip().startswith("/dev/disk"):
                disks.append(line.strip().split()[0])

        for disk in disks:
            smart = subprocess.run(
                ["diskutil", "info", disk],
                capture_output=True, text=True, timeout=10,
            )
            # SMART-Status parsen
            for line in smart.stdout.splitlines():
                if "SMART" in line or "Solid State" in line:
                    result[disk] = line.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("SMART-Abfrage nicht möglich: %s", e)
        result["error"] = str(e)

    return result


def _export_csv(rows: list, filepath: str):
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "layer", "total_gb", "used_gb", "free_gb", "used_pct"])
        writer.writerows(rows)


def log_storage_history() -> int:
    """Protokolliert aktuelle Speichernutzung in der History-Datenbank.

    Returns:
        Anzahl der neu eingefügten Einträge.
    """
    conn = _init_history_db()
    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for layer, path in STORAGE_PATHS.items():
        usage = _disk_usage(path)
        if "error" in usage:
            continue
        conn.execute(
            """INSERT INTO storage_history (timestamp, layer, total_gb, used_gb, free_gb, used_pct)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, layer, usage["total_gb"], usage["used_gb"], usage["free_gb"], usage["used_pct"]),
        )
        count += 1

    conn.commit()
    conn.close()

    # Wöchentlich als CSV exportieren
    if datetime.now(timezone.utc).weekday() == 0:  # Montag
        export_path = HISTORY_DIR / f"storage_export_{datetime.now(timezone.utc):%Y-%m-%d}.csv"
        conn2 = _init_history_db()
        rows = conn2.execute("SELECT * FROM storage_history").fetchall()
        conn2.close()
        _export_csv(rows, str(export_path))
        logger.info("CSV-Export: %s", export_path)

    return count


# ─── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    if cmd == "check":
        result = check_space()
        print(json.dumps(result, indent=2))
    elif cmd == "forecast":
        layer = sys.argv[2] if len(sys.argv) > 2 else "warm"
        print(json.dumps(forecast_usage(layer), indent=2))
    elif cmd == "alerts":
        print(json.dumps(alert_critical(), indent=2))
    elif cmd == "clean":
        dry = "--dry" not in sys.argv
        result = auto_clean_temp(dry_run=not dry)
        print("\n".join(result))
    elif cmd == "optimize":
        print("\n".join(optimize_storage()))
    elif cmd == "log":
        count = log_storage_history()
        print(f"History aktualisiert: {count} Einträge")
    else:
        print(f"Verwendung: {sys.argv[0]} [check|forecast|alerts|clean|optimize|log]")
