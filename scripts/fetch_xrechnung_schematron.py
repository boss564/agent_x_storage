#!/usr/bin/env python3
"""
XRechnung 3.0 Schematron & XSD Fetcher.

Lädt die offiziellen XRechnung-Schematron-Dateien vom ITZBund GitHub Release
mit Cache-First-Fallback-Muster (GitHub → ITZBund-Server).

Die XRechnung (EN 16931 / CIUS-DE) ist das Pflichtformat für Rechnungen
an öffentliche Auftraggeber in Deutschland.

Usage:
    python3 scripts/fetch_xrechnung_schematron.py              # Download (cache-first)
    python3 scripts/fetch_xrechnung_schematron.py --force      # Force re-download
    python3 scripts/fetch_xrechnung_schematron.py --status     # Check local status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("XRechnungFetcher")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = PROJECT_ROOT / "archive_b2g" / "schemas" / "xrechnung_30"
TEST_DATA_DIR = PROJECT_ROOT / "archive_b2g" / "test_data" / "xrechnung"
MANIFEST_FILE = SCHEMA_DIR / "manifest.json"

# Offizielle Quellen
# Primary: KoSIT GitLab (official source per README)
GITLAB_RELEASE = "https://projekte.kosit.org/xrechnung/xrechnung-schematron/-/releases"
# GitHub mirror: itplr-kosit/xrechnung-schematron (latest: release-2.4.0)
GITHUB_RELEASE = "https://github.com/itplr-kosit/xrechnung-schematron/releases/download/release-2.4.0/xrechnung-3.0.2-schematron-2.4.0.zip"
# Validator configuration (XSD + Schematron bundles)
VALIDATOR_CONFIG = "https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/latest"


def fetch(force: bool = False) -> bool:
    """
    Download XRechnung 3.0 schematron + XSD files.
    Returns True if schemas are available locally after the call.
    """
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

    schematron_dir = SCHEMA_DIR / "schematron"
    if schematron_dir.exists() and not force:
        _load_manifest()
        logger.info(f"XRechnung Schematron bereits lokal ({schematron_dir}). "
                     "Nutze --force fuer erneuten Download.")
        return True

    logger.info("Lade XRechnung 3.0 Schematron + XSD...")
    zip_path = SCHEMA_DIR / "xrechnung_3.0.zip"

    # Try GitHub release (itplr-kosit mirror)
    if _try_download(GITHUB_RELEASE, zip_path, "GitHub Release"):
        return _extract_and_verify(zip_path)

    logger.error("GitHub-Download fehlgeschlagen.")
    logger.info("Manueller Download:")
    logger.info("  GitHub: https://github.com/itplr-kosit/xrechnung-schematron/releases")
    logger.info("  GitLab (official): https://projekte.kosit.org/xrechnung/xrechnung-schematron/-/releases")
    return False


def _try_download(url: str, dest: Path, label: str) -> bool:
    """Attempt to download from a URL. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentX-B2G-Pipeline/0.2"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
        logger.info(f"Download erfolgreich ({label}): {dest.stat().st_size:,} bytes")
        return True
    except Exception as exc:
        logger.warning(f"Download fehlgeschlagen ({label}): {exc}")
        return False


def _extract_and_verify(zip_path: Path) -> bool:
    """Extract ZIP and verify structure."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(SCHEMA_DIR)
        zip_path.unlink()
    except Exception as exc:
        logger.error(f"ZIP-Extraktion fehlgeschlagen: {exc}")
        return False

    # Write manifest
    _write_manifest()

    # Verify key files exist
    key_files = _find_key_files()
    if key_files:
        logger.info(f"XRechnung Schematron bereit: {len(key_files)} Dateien gefunden")
        for f in sorted(key_files)[:5]:
            logger.info(f"  - {f}")
        if len(key_files) > 5:
            logger.info(f"  ... und {len(key_files) - 5} weitere")
        return True

    logger.warning("Keine Schematron/XSD-Dateien nach Extraktion gefunden.")
    return False


def _find_key_files() -> list[str]:
    """Find schematron (.sch) and XSD files in the schema directory."""
    found = []
    for ext in (".sch", ".xsd", ".xml"):
        for f in SCHEMA_DIR.rglob(f"*{ext}"):
            found.append(str(f.relative_to(SCHEMA_DIR)))
    return found


def _write_manifest() -> None:
    manifest = {
        "source": "KoSIT / itplr-kosit: xrechnung-schematron",
        "version": "3.0.0",
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "schema_dir": str(SCHEMA_DIR),
        "files": _find_key_files(),
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, default=str))


def _load_manifest() -> dict | None:
    if not MANIFEST_FILE.exists():
        return None
    try:
        return json.loads(MANIFEST_FILE.read_text())
    except json.JSONDecodeError:
        return None


def status() -> dict:
    """Return current status of XRechnung schemas."""
    manifest = _load_manifest()
    files = _find_key_files()
    return {
        "available": len(files) > 0,
        "file_count": len(files),
        "manifest": manifest,
        "schema_dir": str(SCHEMA_DIR),
        "test_data_dir": str(TEST_DATA_DIR),
    }


# ============================================================
# CLI
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="XRechnung 3.0 Schematron Fetcher")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    parser.add_argument("--status", action="store_true", help="Check local status only")
    args = parser.parse_args()

    if args.status:
        s = status()
        print(json.dumps(s, indent=2, default=str))
        return

    print("=" * 60)
    print("  XRechnung 3.0 Schematron Fetcher")
    print(f"  Schema-Dir: {SCHEMA_DIR}")
    print(f"  Test-Data:  {TEST_DATA_DIR}")
    print("=" * 60)

    success = fetch(force=args.force)
    if success:
        s = status()
        print(f"\n  Status: {s['file_count']} Dateien lokal verfuegbar")
        if s["manifest"]:
            print(f"  Version: {s['manifest'].get('version', 'unknown')}")
            print(f"  Downloaded: {s['manifest'].get('downloaded_at', 'unknown')[:19]}")
    else:
        print("\n  XRechnung Schematron nicht verfuegbar.")
        print("  Manueller Download: "
              "https://github.com/it-dienstleistungszentrum-bund/xrechnung-schematron/releases")
        sys.exit(1)


if __name__ == "__main__":
    main()
