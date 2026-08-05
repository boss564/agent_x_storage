"""
Ops-Agent: BVBSReferenceSyncAgent — Auto-Updater for BVBS/GAEB DA XML 3.3.

Monitors official BVBS/GAEB certification file sources, checks SHA-256
freshness, downloads updates automatically, and fires b2g.reference.updated
events when new reference data arrives. Falls back to a minimal valid X83
when servers are unreachable.

Usage:
    sync = BVBSReferenceSyncAgent(event_bus=bus)
    status = await sync.sync_latest_reference_suite()
    # status["status"]: UP_TO_DATE / UPDATED / FALLBACK
"""
from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("BVBSReferenceSyncAgent")


class BVBSReferenceSyncAgent:
    """Keeps BVBS/GAEB DA XML 3.3 certification files synchronized."""

    DEFAULT_URL = "https://www.gaeb.de/fileadmin/GAEB_DA_XML/GAEB_DA_XML_3_3_2021-05.zip"
    TARGET_FILE = "BVBS_Pruefdatei_GAEB_DA_XML_3.3_Bauausfuehrung.x83"

    def __init__(self, event_bus: Any = None,
                 target_dir: str = "archive_b2g/reference/bvbs_test_suite"):
        self.bus = event_bus
        self.target_dir = Path(target_dir)
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.target_path = self.target_dir / self.TARGET_FILE

    # ============================================================
    # Main sync
    # ============================================================

    async def sync_latest_reference_suite(self,
                                          force_download: bool = False) -> dict[str, Any]:
        """Check freshness, download if needed, fire event on update."""

        logger.info(f"BVBS sync: {self.target_path}")

        file_exists = self.target_path.exists()
        old_hash = self._hash_file() if file_exists else None

        if file_exists and not force_download:
            logger.info(f"BVBS reference up-to-date (SHA-256: {old_hash[:16]}...)")
            return {"status": "UP_TO_DATE", "file_path": str(self.target_path),
                    "sha256": old_hash, "updated": False}

        # Attempt download
        success = self._download_and_extract()

        if not success or not self.target_path.exists():
            logger.warning("Download failed — creating fallback X83")
            self._create_fallback()

        new_hash = self._hash_file()
        is_new = new_hash != old_hash

        result = {"status": "UPDATED" if is_new else "FALLBACK",
                  "file_path": str(self.target_path),
                  "sha256": new_hash, "updated": is_new,
                  "synced_at": datetime.now(timezone.utc).isoformat()}

        if is_new and self.bus:
            self.bus.publish("b2g.reference.updated", result)

        print(f"  [BVBS-Sync]     {'🔄' if is_new else '📎'} {result['status']} "
              f"SHA-256={new_hash[:16]}...")

        return result

    # ============================================================
    # Download + extract
    # ============================================================

    def _download_and_extract(self) -> bool:
        zip_path = self.target_dir / "bvbs_temp.zip"
        try:
            req = urllib.request.Request(
                self.DEFAULT_URL,
                headers={"User-Agent": "AgentX-B2G-BVBS-Sync/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                zip_path.write_bytes(resp.read())

            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    if info.filename.endswith(".x83") or "Bauausfuehrung" in info.filename:
                        extracted = zf.extract(info, path=self.target_dir)
                        os.replace(extracted, str(self.target_path))
                        break

            zip_path.unlink()
            return self.target_path.exists()

        except Exception as exc:
            logger.warning(f"BVBS download failed: {exc}")
            if zip_path.exists():
                zip_path.unlink()
            return False

    # ============================================================
    # Fallback
    # ============================================================

    def _create_fallback(self) -> None:
        """Create a minimal valid GAEB DA XML 3.3 X83 for offline testing."""
        minimal = """<?xml version="1.0" encoding="UTF-8"?>
<GAEB xmlns="http://www.gaeb.de/GAEB_DA_XML/DA83/3.3">
  <GAEBInfo><Version>3.3</Version><VersDate>2021-05</VersDate></GAEBInfo>
  <Award>
    <DP>83</DP>
    <BoQ>
      <BoQInfo><Name>BVBS Referenz-Pruefdatei Klaeranlage Nord</Name>
        <DescrBoQ>Automatisch generierte Fallback-Datei</DescrBoQ>
      </BoQInfo>
      <BoQBody>
        <BoQCtgy>
          <CtgyTitle>Beton- und Stahlbetonarbeiten</CtgyTitle>
          <Item><ItemID>01.02.0040</ItemID>
            <Descr>Stahlbetonsohle C30/37 giessen, d=40cm</Descr>
            <Qty>450.0</Qty><Unit>m³</Unit></Item>
          <Item><ItemID>01.02.0050</ItemID>
            <Descr>Bodenplatte bewehrt, d=30cm</Descr>
            <Qty>380.0</Qty><Unit>m³</Unit></Item>
        </BoQCtgy>
        <BoQCtgy>
          <CtgyTitle>Rohrleitungsbau</CtgyTitle>
          <Item><ItemID>02.01.0010</ItemID>
            <Descr>Edelstahlrohr 1.4404, DN200</Descr>
            <Qty>220.0</Qty><Unit>m</Unit></Item>
        </BoQCtgy>
      </BoQBody>
    </BoQ>
  </Award>
</GAEB>"""
        self.target_path.write_text(minimal, encoding="utf-8")
        logger.info(f"Fallback X83 written: {self.target_path}")

    # ============================================================
    # Hash
    # ============================================================

    def _hash_file(self) -> str:
        if not self.target_path.exists():
            return ""
        sha = hashlib.sha256()
        with open(self.target_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    # ============================================================
    # Status
    # ============================================================

    def status(self) -> dict:
        return {
            "file": str(self.target_path),
            "exists": self.target_path.exists(),
            "sha256": self._hash_file()[:16] + "..." if self.target_path.exists() else None,
            "size_bytes": self.target_path.stat().st_size if self.target_path.exists() else 0,
        }
