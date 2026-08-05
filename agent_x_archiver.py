"""
Agent 142 – Medien-Archivar.

Archiviert alte Dateien auf die 28 TB HDD,
komprimiert vor dem Archivieren, prüft Integrität,
erstellt einen Index und kann Dateien zurückholen.
"""

import gzip
import hashlib
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger("agent_142_archiver")

# ─── Pfade ─────────────────────────────────────────────────────────

ARCHIVE_BASE = Path("/Volumes/THIXO_BACKUP_28TB/archive")
BACKUP_BASE = Path("/Volumes/THIXO_BACKUP_28TB/backups")
INDEX_DIR = Path("/Volumes/THIXO_BACKUP_28TB/index")
INDEX_DB = INDEX_DIR / "archive_index.db"
INDEX_JSON = INDEX_DIR / "archive_index.json"

# ─── Datenbank (Index) ─────────────────────────────────────────────

def _init_db():
    """Stellt sicher, dass die SQLite-Index-Datenbank existiert."""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(INDEX_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS archive_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_path TEXT NOT NULL,
            archive_path TEXT NOT NULL,
            size_bytes INTEGER,
            compressed_size_bytes INTEGER,
            sha256 TEXT,
            archived_at TEXT NOT NULL,
            category TEXT NOT NULL,
            restored_at TEXT
        )
    """)
    conn.commit()
    return conn


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ─── Sub-Agenten (Agent 142) ───────────────────────────────────────

def _archive_files(
    source_dir: Path,
    archive_subdir: str,
    age_days: int,
    pattern: str = "*",
    compress: bool = True,
    dry_run: bool = False,
) -> list[dict]:
    """Allgemeine Archivierungsfunktion.

    Args:
        source_dir: Quellverzeichnis.
        archive_subdir: Unterordner in ARCHIVE_BASE.
        age_days: Dateien älter als dieses Alter archivieren.
        pattern: Glob-Muster (z. B. "*.log", "*.wav").
        compress: gzip-komprimieren.
        dry_run: Nur melden, nichts verschieben.

    Returns:
        Liste der archivierten Einträge.
    """
    target_dir = ARCHIVE_BASE / archive_subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    archived: list[dict] = []
    conn = _init_db()

    for f in sorted(source_dir.rglob(pattern)):
        if not f.is_file():
            continue

        age = (now - datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)).days
        if age < age_days:
            continue

        entry = {
            "original_path": str(f),
            "size_bytes": f.stat().st_size,
            "age_days": age,
        }

        if dry_run:
            entry["action"] = "would_archive"
            archived.append(entry)
            continue

        # Komprimieren
        if compress and f.suffix not in (".gz", ".zip", ".mp3", ".flac", ".wav", ".jpg", ".png"):
            compressed = target_dir / f"{f.name}.gz"
            try:
                with open(f, "rb") as src, gzip.open(compressed, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                entry["archive_path"] = str(compressed)
                entry["compressed_size_bytes"] = compressed.stat().st_size
                entry["sha256"] = _sha256(compressed)
                f.unlink()
                logger.info("Archiviert (gz): %s → %s", f.name, compressed)
            except OSError as e:
                logger.error("Fehler bei %s: %s", f.name, e)
                continue
        else:
            # Direkt verschieben für bereits komprimierte Formate
            dest = target_dir / f.name
            try:
                shutil.move(str(f), str(dest))
                entry["archive_path"] = str(dest)
                entry["compressed_size_bytes"] = dest.stat().st_size
                entry["sha256"] = _sha256(dest)
                logger.info("Archiviert: %s → %s", f.name, dest)
            except OSError as e:
                logger.error("Fehler bei %s: %s", f.name, e)
                continue

        entry["category"] = archive_subdir
        entry["archived_at"] = now.isoformat()
        entry["restored_at"] = None

        conn.execute(
            """INSERT INTO archive_index (original_path, archive_path, size_bytes,
               compressed_size_bytes, sha256, archived_at, category)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["original_path"],
                entry["archive_path"],
                entry["size_bytes"],
                entry["compressed_size_bytes"],
                entry["sha256"],
                entry["archived_at"],
                entry["category"],
            ),
        )
        archived.append(entry)

    conn.commit()
    conn.close()
    return archived


# ─── Spezialisierte Archivierungs-Funktionen ────────────────────────

def archive_old_logs(
    log_dir: str = "/Users/olivermueller/LangGraph/logs",
    age_days: int = 30,
    dry_run: bool = False,
) -> list[dict]:
    """Verschiebt Logs > 30 Tage auf HDD."""
    return _archive_files(
        Path(log_dir), "logs", age_days=age_days, pattern="*.log", dry_run=dry_run
    )


def archive_old_samples(
    sample_dir: str = "/Volumes/THX_CORE_16TB/media/audio/samples",
    age_days: int = 180,
    dry_run: bool = False,
) -> list[dict]:
    """Verschiebt Samples > 6 Monate auf HDD."""
    return _archive_files(
        Path(sample_dir), "samples", age_days=age_days, dry_run=dry_run
    )


def archive_pdfs(
    pdf_dir: str = "/Volumes/THX_CORE_16TB/data/pdfs",
    age_days: int = 0,  # Alle PDFs archivieren
    dry_run: bool = False,
) -> list[dict]:
    """Verschiebt PDFs auf HDD."""
    return _archive_files(
        Path(pdf_dir), "pdfs", age_days=age_days, pattern="*.pdf", compress=False, dry_run=dry_run
    )


def archive_backups(
    backup_dir: str = "/Volumes/THX_CORE_16TB/data/neo4j",
    age_days: int = 0,
    dry_run: bool = False,
) -> list[dict]:
    """Verschiebt Neo4j-Backups auf HDD."""
    return _archive_files(
        Path(backup_dir), "backups", age_days=age_days, compress=True, dry_run=dry_run
    )


# ─── Index & Wiederherstellung ─────────────────────────────────────

def create_index() -> dict:
    """Erstellt einen JSON-Index aller archivierten Dateien."""
    conn = _init_db()
    rows = conn.execute("SELECT * FROM archive_index ORDER BY archived_at DESC").fetchall()
    conn.close()

    index = []
    for row in rows:
        index.append({
            "id": row[0],
            "original_path": row[1],
            "archive_path": row[2],
            "size_bytes": row[3],
            "compressed_size_bytes": row[4],
            "sha256": row[5],
            "archived_at": row[6],
            "category": row[7],
            "restored_at": row[8],
        })

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX_JSON, "w") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    logger.info("Index aktualisiert: %d Einträge", len(index))
    return {"total_entries": len(index), "file": str(INDEX_JSON)}


def verify_archive() -> list[dict]:
    """Prüft Integrität aller archivierten Dateien via SHA-256."""
    conn = _init_db()
    rows = conn.execute(
        "SELECT id, archive_path, sha256 FROM archive_index WHERE restored_at IS NULL"
    ).fetchall()
    conn.close()

    results = []
    for row_id, path, expected_hash in rows:
        p = Path(path)
        if not p.exists():
            results.append({"id": row_id, "path": path, "status": "missing"})
            logger.warning("Fehlt: %s", path)
            continue
        actual = _sha256(p)
        if actual == expected_hash:
            results.append({"id": row_id, "path": path, "status": "ok"})
        else:
            results.append({"id": row_id, "path": path, "status": "corrupt"})
            logger.error("Integritätsfehler: %s", path)

    return results


def restore_from_archive(
    entry_id: int | None = None,
    original_path: str | None = None,
    decompress: bool = True,
) -> bool:
    """Stellt eine archivierte Datei zurück an den Originalort.

    Args:
        entry_id: ID im Index.
        original_path: Alternativ den Originalpfad angeben.
        decompress: .gz-Endung entfernen.
    """
    conn = _init_db()
    if entry_id:
        row = conn.execute(
            "SELECT * FROM archive_index WHERE id = ?", (entry_id,)
        ).fetchone()
    elif original_path:
        row = conn.execute(
            "SELECT * FROM archive_index WHERE original_path = ? ORDER BY archived_at DESC LIMIT 1",
            (original_path,),
        ).fetchone()
    else:
        conn.close()
        logger.error("Keine ID oder Pfad angegeben")
        return False

    if not row:
        conn.close()
        logger.error("Nicht im Index gefunden")
        return False

    archive_path = Path(row[2])
    orig_path = Path(row[1])

    if not archive_path.exists():
        conn.close()
        logger.error("Archivdatei nicht gefunden: %s", archive_path)
        return False

    try:
        orig_path.parent.mkdir(parents=True, exist_ok=True)

        if decompress and archive_path.suffix == ".gz":
            with gzip.open(archive_path, "rb") as src, open(orig_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            archive_path.unlink()
        else:
            shutil.move(str(archive_path), str(orig_path))

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE archive_index SET restored_at = ? WHERE id = ?",
            (now, row[0]),
        )
        conn.commit()
        conn.close()
        logger.info("Wiederhergestellt: %s", orig_path)
        return True

    except OSError as e:
        conn.close()
        logger.error("Fehler bei Wiederherstellung: %s", e)
        return False


# ─── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "archive_logs":
        archive_old_logs(dry_run="--dry" in sys.argv)
    elif cmd == "archive_samples":
        archive_old_samples(dry_run="--dry" in sys.argv)
    elif cmd == "archive_pdfs":
        archive_pdfs(dry_run="--dry" in sys.argv)
    elif cmd == "verify":
        print(json.dumps(verify_archive(), indent=2))
    elif cmd == "index":
        print(json.dumps(create_index(), indent=2))
    else:
        print(f"Verwendung: {sys.argv[0]} [archive_logs|archive_samples|archive_pdfs|verify|index] [--dry]")
