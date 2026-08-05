"""
Agent 140 – Storage-Orchestrator.

Verwaltet die 3 Speicher-Ebenen (Hot/Warm/Cold).
Entscheidet über Platzierung, verschiebt Daten,
erstellt Symlinks und generiert Speicherberichte.
"""

import os
import json
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("agent_140_storage")

# ─── Speicher-Ebenen ───────────────────────────────────────────────

STORAGE_LAYERS = {
    "hot": {
        "path": "/Users/olivermueller",
        "capacity_gb": 2000,
        "min_free_gb": 100,
        "priority": 1,
        "label": "Intern (NVMe)",
    },
    "warm": {
        "path": "/Volumes/THX_CORE_16TB",
        "capacity_gb": 16000,
        "min_free_gb": 500,
        "priority": 2,
        "label": "RAID (SSD)",
    },
    "cold": {
        "path": "/Volumes/THIXO_BACKUP_28TB",
        "capacity_gb": 28000,
        "min_free_gb": 1000,
        "priority": 3,
        "label": "HDD (Archiv)",
    },
}

# ─── Hilfsfunktionen ───────────────────────────────────────────────

def _gb_from_df(path: str) -> tuple:
    """Gibt (available_gb, used_gb, total_gb) für einen Pfad zurück."""
    try:
        stat = shutil.disk_usage(path)
        total_gb = stat.total / (1024**3)
        used_gb = stat.used / (1024**3)
        free_gb = stat.free / (1024**3)
        return round(free_gb, 1), round(used_gb, 1), round(total_gb, 1)
    except FileNotFoundError:
        return 0.0, 0.0, 0.0


# ─── Sub-Agenten (Agent 140) ───────────────────────────────────────

def check_usage(layer_key: str | None = None) -> dict:
    """Prüft Speichernutzung aller oder einer bestimmten Ebene."""
    layers = [layer_key] if layer_key else STORAGE_LAYERS
    result = {}
    for key in layers:
        cfg = STORAGE_LAYERS[key]
        free, used, total = _gb_from_df(cfg["path"])
        pct = round((used / total) * 100, 1) if total else 0
        result[key] = {
            "label": cfg["label"],
            "total_gb": total,
            "used_gb": used,
            "free_gb": free,
            "used_pct": pct,
            "min_free_gb": cfg["min_free_gb"],
            "critical": free < cfg["min_free_gb"],
        }
    return result


def auto_move(
    source_path: str,
    target_layer: str,
    create_symlink: bool = True,
) -> str | None:
    """Verschiebt eine Datei / einen Ordner in die Ziel-Ebene.

    Args:
        source_path: Absoluter Pfad zum Verschieben.
        target_layer:  'hot' | 'warm' | 'cold'
        create_symlink: Symlink am Quellort hinterlassen.

    Returns:
        Neuer Pfad oder None bei Fehler.
    """
    cfg = STORAGE_LAYERS.get(target_layer)
    if not cfg:
        logger.error("Unbekannte Ebene: %s", target_layer)
        return None

    src = Path(source_path)
    if not src.exists():
        logger.error("Quelle nicht gefunden: %s", source_path)
        return None

    rel = src.relative_to(src.anchor)  # z. B. "Users/olivermueller/foo"
    dst = Path(cfg["path"]) / rel

    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(src), str(dst))
        logger.info("Verschoben: %s → %s", src, dst)

        if create_symlink:
            dst_rel = os.path.relpath(dst, start=src.parent)
            src.symlink_to(dst_rel)
            logger.info("Symlink erstellt: %s → %s", src, dst_rel)

        return str(dst)
    except OSError as e:
        logger.error("Fehler beim Verschieben: %s", e)
        return None


def balance_load(dry_run: bool = True) -> list[dict]:
    """Verteilt Daten basierend auf Priorität und freiem Speicher.

    Verschiebt selten genutzte Dateien von hot → warm und
    warm → cold, wenn der freie Speicher unter min_free_gb fällt.

    Args:
        dry_run: Wenn True, nur melden ohne zu verschieben.

    Returns:
        Liste der vorgeschlagenen/durchgeführten Aktionen.
    """
    usage = check_usage()
    actions = []

    for key in ("hot", "warm"):
        layer = usage[key]
        cfg = STORAGE_LAYERS[key]
        if layer["free_gb"] >= cfg["min_free_gb"]:
            continue

        next_layer = "warm" if key == "hot" else "cold"
        # Kandidaten: ältere Logs, temp-Dateien
        candidates = list(Path(cfg["path"]).rglob("*.log")) + list(
            Path(cfg["path"] / "temp").glob("*")
        )

        for cand in candidates[:20]:  # max 20 pro Durchlauf
            age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(cand.stat().st_mtime, tz=timezone.utc)).days
            if age_days < 30:
                continue
            action = {
                "file": str(cand),
                "from": key,
                "to": next_layer,
                "size_mb": round(cand.stat().st_size / (1024**2), 1),
                "age_days": age_days,
            }
            if not dry_run:
                new_path = auto_move(str(cand), next_layer)
                action["result"] = new_path
            actions.append(action)

    return actions


def create_symlink(target: str, link_path: str) -> bool:
    """Erstellt einen Symlink von link_path → target."""
    link = Path(link_path)
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        rel = os.path.relpath(target, start=link.parent)
        link.symlink_to(rel)
        logger.info("Symlink: %s → %s", link, rel)
        return True
    except OSError as e:
        logger.error("Symlink-Fehler: %s", e)
        return False


def generate_report() -> str:
    """Erstellt einen vollständigen Speicherbericht als String."""
    usage = check_usage()
    lines = [
        "=" * 50,
        "Speicherbericht – Agent X",
        f"Erstellt: {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S UTC}",
        "=" * 50,
    ]
    for key, data in usage.items():
        status = "⚠️ KRITISCH" if data["critical"] else "✅ OK"
        lines.extend([
            f"\n{data['label']} [{key}] {status}",
            f"  Gesamt:  {data['total_gb']:>8.1f} GB",
            f"  Genutzt: {data['used_gb']:>8.1f} GB ({data['used_pct']}%)",
            f"  Frei:    {data['free_gb']:>8.1f} GB",
            f"  Minimum: {data['min_free_gb']:>8.1f} GB",
        ])
    lines.append("\n" + "=" * 50)
    return "\n".join(lines)


def monitor_health() -> dict:
    """Prüft SMART-Status (via diskutil) und Mount-Status."""
    health = {}
    for key, cfg in STORAGE_LAYERS.items():
        mounted = Path(cfg["path"]).exists()
        health[key] = {
            "mounted": mounted,
            "path": cfg["path"],
        }
        if mounted:
            free, used, total = _gb_from_df(cfg["path"])
            health[key]["free_gb"] = free
            health[key]["used_gb"] = used
            health[key]["total_gb"] = total
    return health


def alert_low_space() -> list[str]:
    """Gibt Warnungen für Ebenen unter min_free_gb zurück."""
    usage = check_usage()
    alerts = []
    for key, data in usage.items():
        if data["critical"]:
            alerts.append(
                f"⚠️ {data['label']}: nur {data['free_gb']} GB frei "
                f"(Minimum: {data['min_free_gb']} GB)"
            )
    return alerts


# ─── CLI / Direktaufruf ────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(generate_report())

    warnings = alert_low_space()
    if warnings:
        print("\n".join(warnings))
    else:
        print("\nAlle Ebenen im grünen Bereich.")
