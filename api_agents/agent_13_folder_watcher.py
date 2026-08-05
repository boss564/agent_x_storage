"""
Agent X — API Agent 13: FolderWatcherAgent (Unsichtbare Auto-Ankerung).

Verantwortung: Überwacht Nextcloud/Seafile-Projektordner auf neue oder
geänderte Baupläne und verankert sie automatisch — der Handwerker muss
NICHTS tun. Die API sichert jeden Plan, der im Projektordner landet.

Sub-Agenten:
  13a: FolderScanner — Pollt Verzeichnisse auf neue PDFs
  13b: ChangeDetector — Hash-basierte Änderungserkennung
  13c: AutoAnchoringDispatcher — Feuert anchor_plan() bei jedem Fund

Konfiguration: WATCH_DIRS=/data/projekte/BAU-2026-081/plaene,...
               WATCH_INTERVAL_S=300  (alle 5 Minuten)
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("FolderWatcher")

WATCH_DIRS = os.getenv("WATCH_DIRS", "").split(",") if os.getenv("WATCH_DIRS") else []
WATCH_INTERVAL_S = int(os.getenv("WATCH_INTERVAL_S", "300"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Sub-Agent 13a: FolderScanner ────────────────────────────────────

class FolderScanner:
    """Scannt Verzeichnisse rekursiv nach PDFs."""

    def __init__(self, watch_dirs: list[str] | None = None):
        self.dirs = [Path(d) for d in (watch_dirs or WATCH_DIRS) if d.strip()]

    def scan(self) -> list[dict]:
        """Findet alle PDFs in den überwachten Verzeichnissen."""
        found = []
        for directory in self.dirs:
            if not directory.exists():
                logger.warning("Watch-Dir nicht gefunden: %s", directory)
                continue
            for pdf_path in directory.rglob("*.pdf"):
                if pdf_path.is_file():
                    stat = pdf_path.stat()
                    found.append({
                        "path": str(pdf_path),
                        "name": pdf_path.name,
                        "size_bytes": stat.st_size,
                        "modified_at": stat.st_mtime,
                        "directory": str(directory),
                    })
        return found


# ─── Sub-Agent 13b: ChangeDetector ───────────────────────────────────

class ChangeDetector:
    """Erkennt neue oder geänderte PDFs via Hash-Vergleich."""

    def __init__(self):
        self._known: dict[str, str] = {}  # path → hash

    def detect_changes(self, files: list[dict]) -> list[dict]:
        """Gibt nur neue oder geänderte Dateien zurück."""
        changed = []
        for f in files:
            path = f["path"]
            try:
                file_hash = self._hash_file(path)
            except Exception:
                continue

            if path not in self._known:
                self._known[path] = file_hash
                f["status"] = "new"
                changed.append(f)
            elif self._known[path] != file_hash:
                self._known[path] = file_hash
                f["status"] = "modified"
                changed.append(f)

        return changed

    @staticmethod
    def _hash_file(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @property
    def tracked_count(self) -> int:
        return len(self._known)


# ─── Sub-Agent 13c: AutoAnchoringDispatcher ──────────────────────────

class AutoAnchoringDispatcher:
    """Feuert anchor_plan() für jeden erkannten neuen/geänderten Plan."""

    def __init__(self, erp_adapter):
        self.adapter = erp_adapter
        self._processed = 0

    def dispatch(self, changed_files: list[dict], erp_token: str = "pds_token",
                 project_id: str = "AUTO") -> list[dict]:
        """Verankert alle geänderten Dateien."""
        results = []
        for f in changed_files:
            try:
                with open(f["path"], "rb") as fh:
                    pdf_bytes = fh.read()

                # Plan-Nummer aus Dateinamen ableiten
                name = f["name"].replace(".pdf", "")
                parts = name.split("_")
                plan_number = parts[0] if parts else name
                revision = parts[1] if len(parts) > 1 else "A"

                # Verzeichnis → Projekt-ID
                dir_name = Path(f["directory"]).name
                proj_id = project_id if project_id != "AUTO" else dir_name

                result = self.adapter.anchor_plan(
                    pdf_bytes=pdf_bytes,
                    erp_token=erp_token,
                    plan_number=plan_number,
                    revision=revision,
                    project_id=proj_id,
                    polier_id="AUTO-WATCHER",
                )
                self._processed += 1
                results.append({
                    "file": f["name"],
                    "status": result["status"],
                    "session_id": result["session_id"],
                })
                logger.info("Auto-anchored: %s → %s", f["name"], result["session_id"][:16])
            except Exception as e:
                logger.error("Auto-anchor failed for %s: %s", f["name"], e)
                results.append({"file": f["name"], "status": "error", "error": str(e)})

        return results

    @property
    def total_processed(self) -> int:
        return self._processed


# ─── Agent 13: FolderWatcherAgent ────────────────────────────────────

class FolderWatcherAgent:
    """Unsichtbare Auto-Ankerung: Überwacht Ordner und verankert neue Pläne.

    Usage:
        watcher = FolderWatcherAgent(adapter, ["/data/projekte/BAU-2026-081/plaene"])
        watcher.run_once()  # Einmaliger Scan + Anchor
        watcher.run_loop()  # Dauerhafte Überwachung

    Der Handwerker muss NICHTS tun — jeder Plan, der im Projektordner
    landet, wird automatisch per Triple-Lock gesichert.
    """

    def __init__(self, erp_adapter=None, watch_dirs: list[str] | None = None,
                 interval_s: int = WATCH_INTERVAL_S):
        if erp_adapter is None:
            from agent_12_erp_adapter import ERPAdapterAgent
            erp_adapter = ERPAdapterAgent()
        self.adapter = erp_adapter
        self.scanner = FolderScanner(watch_dirs)
        self.detector = ChangeDetector()
        self.dispatcher = AutoAnchoringDispatcher(erp_adapter)
        self.interval_s = interval_s
        self._running = False

    def run_once(self, erp_token: str = "pds_token",
                 project_id: str = "AUTO") -> dict:
        """Einmaliger Scan + Verankerung neuer Pläne."""
        files = self.scanner.scan()
        changed = self.detector.detect_changes(files)
        results = self.dispatcher.dispatch(changed, erp_token, project_id)

        # Batch auslösen wenn genug Docs gesammelt
        batch_result = self.adapter.run_batch_if_ready()

        return {
            "scanned": len(files),
            "changed": len(changed),
            "anchored": self.dispatcher.total_processed,
            "batch": batch_result["status"],
            "tracked_files": self.detector.tracked_count,
            "results": results,
        }

    def run_loop(self, erp_token: str = "pds_token", project_id: str = "AUTO"):
        """Dauerhafte Ordner-Überwachung."""
        self._running = True
        logger.info("FolderWatcher gestartet: %d Dirs, %ds Intervall",
                     len(self.scanner.dirs), self.interval_s)

        while self._running:
            try:
                result = self.run_once(erp_token, project_id)
                if result["changed"] > 0:
                    logger.info("Scan: %d Dateien, %d neu/geändert, %d verankert",
                                result["scanned"], result["changed"],
                                result["anchored"])
                time.sleep(self.interval_s)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error("Watcher-Fehler: %s", e)
                time.sleep(10)

    def stop(self):
        self._running = False

    @property
    def stats(self) -> dict:
        return {
            "watch_dirs": [str(d) for d in self.scanner.dirs],
            "interval_s": self.interval_s,
            "tracked_files": self.detector.tracked_count,
            "total_anchored": self.dispatcher.total_processed,
        }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Demo: Simuliere einen Projektordner
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # Erstelle 3 Test-PDFs
        for i in range(3):
            pdf_path = Path(tmpdir) / f"E-04-{12+i:02d}_C.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nPlan E-04-" + str(12+i).encode() + b"\n%%EOF")

        watcher = FolderWatcherAgent(watch_dirs=[tmpdir])
        result = watcher.run_once()

        print("=== FolderWatcher Demo ===")
        print(f"Scanned: {result['scanned']} files")
        print(f"Changed: {result['changed']} (new)")
        print(f"Anchored: {result['anchored']}")
        print(f"Tracked: {result['tracked_files']}")
        print(f"Batch: {result['batch']}")

        # Zweiter Scan: keine Änderungen
        result2 = watcher.run_once()
        print(f"\nRe-scan: {result2['changed']} changes (should be 0)")
        print(f"Stats: {json.dumps(watcher.stats, indent=2)}")
