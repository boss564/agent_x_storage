"""
Agent 141 – Seafile-Connector.

Verbindet Agent X mit der lokalen Seafile-Instanz
(Docker auf THX_CORE_16TB).
Ermöglicht Upload, Download, Suche und Sync
mit Seafile-Bibliotheken.
"""

import os
import json
import logging
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("agent_141_seafile")

SEAFILE_DEFAULT_URL = "http://localhost:8082"
SEAFILE_DATA_DIR = "/Volumes/THX_CORE_16TB/seafile"
SEAFILE_TOKEN_FILE = str(Path(SEAFILE_DATA_DIR) / "auth_token.txt")


class SeafileBridge:
    """Wrapper um die Seafile Web API v2."""

    def __init__(
        self,
        server_url: str = SEAFILE_DEFAULT_URL,
        username: str | None = None,
        password: str | None = None,
    ):
        self.server_url = server_url.rstrip("/")
        self.token: str | None = None

        # Token aus Datei laden oder per Login holen
        token = self._load_token()
        if token:
            self.token = token
            logger.info("Seafile-Token aus Datei geladen")
        elif username and password:
            self.login(username, password)

    # ─── Auth ───────────────────────────────────────────────────────

    def _load_token(self) -> str | None:
        try:
            with open(SEAFILE_TOKEN_FILE) as f:
                return f.read().strip()
        except FileNotFoundError:
            return None

    def _save_token(self, token: str) -> None:
        Path(SEAFILE_TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(SEAFILE_TOKEN_FILE, "w") as f:
            f.write(token)

    def login(self, username: str, password: str) -> bool:
        """Login und Token speichern."""
        try:
            resp = requests.post(
                f"{self.server_url}/api2/auth-token/",
                data={"username": username, "password": password},
                timeout=10,
            )
            if resp.status_code == 200:
                self.token = resp.json()["token"]
                self._save_token(self.token)
                logger.info("Seafile-Login erfolgreich")
                return True
            logger.warning("Seafile-Login fehlgeschlagen: %s", resp.status_code)
            return False
        except requests.RequestException as e:
            logger.error("Seafile-Verbindungsfehler: %s", e)
            return False

    def _headers(self) -> dict:
        if not self.token:
            raise PermissionError("Nicht authentifiziert – bitte login() aufrufen")
        return {"Authorization": f"Token {self.token}"}

    # ─── Sub-Agenten (Agent 141) ────────────────────────────────────

    def _get_upload_url(self, library_id: str) -> str | None:
        """Holt den Upload-Endpoint (Seafile 11.x: /api2/repos/{id}/upload-link/)."""
        try:
            url = f"{self.server_url}/api2/repos/{library_id}/upload-link/"
            resp = requests.get(url, headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                return resp.json() if isinstance(resp.json(), str) else resp.text.strip('"')
            logger.warning("upload-link fehlgeschlagen: %s", resp.status_code)
            return None
        except requests.RequestException as e:
            logger.error("upload-link-Fehler: %s", e)
            return None

    def upload_file(
        self,
        library_id: str,
        local_path: str,
        remote_dir: str = "/",
    ) -> bool:
        """Lädt eine Datei in eine Seafile-Bibliothek hoch (Seafile 11.x)."""
        try:
            upload_url = self._get_upload_url(library_id)
            if not upload_url:
                return False

            with open(local_path, "rb") as f:
                files = {"file": (os.path.basename(local_path), f)}
                data = {"parent_dir": remote_dir}
                resp = requests.post(
                    upload_url, files=files, data=data, timeout=120
                )
            ok = resp.status_code == 200
            logger.info("Upload %s: %s", local_path, "OK" if ok else f"FAIL ({resp.status_code})")
            return ok
        except (OSError, requests.RequestException) as e:
            logger.error("Upload-Fehler: %s", e)
            return False

    def download_file(
        self,
        library_id: str,
        remote_path: str,
        local_path: str,
    ) -> bool:
        """Lädt eine Datei aus Seafile herunter (Seafile 11.x)."""
        try:
            url = f"{self.server_url}/api2/repos/{library_id}/file/"
            params = {"p": remote_path}
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=30
            )
            if resp.status_code != 200:
                logger.warning("Download fehlgeschlagen: %s", resp.status_code)
                return False

            # Seafile 11.x: Antwort ist JSON-String mit Download-URL
            file_url = resp.json()
            if not isinstance(file_url, str) or not file_url.startswith("http"):
                # Direkter Datei-Inhalt
                content = resp.content
            else:
                file_resp = requests.get(file_url, timeout=120)
                if file_resp.status_code != 200:
                    logger.warning("Download fehlgeschlagen: %s", file_resp.status_code)
                    return False
                content = file_resp.content

            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content)
            logger.info("Download OK: %s → %s", remote_path, local_path)
            return True
        except (OSError, requests.RequestException, ValueError) as e:
            logger.error("Download-Fehler: %s", e)
            return False

    def search_files(self, library_id: str, query: str) -> list[dict]:
        """Durchsucht eine Bibliothek nach Dateien."""
        try:
            url = f"{self.server_url}/api2/repos/{library_id}/search/"
            params = {"q": query}
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=30
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
            return []
        except requests.RequestException as e:
            logger.error("Suche fehlgeschlagen: %s", e)
            return []

    def create_library(self, name: str, desc: str = "") -> dict | None:
        """Erstellt eine neue Seafile-Bibliothek."""
        try:
            url = f"{self.server_url}/api2/repos/"
            data = {"name": name, "desc": desc}
            resp = requests.post(
                url, headers=self._headers(), data=data, timeout=30
            )
            if resp.status_code in (200, 201):
                lib = resp.json()
                logger.info("Bibliothek erstellt: %s (ID: %s)", name, lib.get("repo_id"))
                return lib
            logger.warning("Bibliothek-Erstellung fehlgeschlagen: %s", resp.status_code)
            return None
        except requests.RequestException as e:
            logger.error("Fehler bei Bibliothek-Erstellung: %s", e)
            return None

    def sync_folder(self, library_id: str, local_folder: str, remote_dir: str = "/") -> bool:
        """Synchronisiert einen lokalen Ordner mit einer Seafile-Bibliothek.

        Lädt alle Dateien aus dem lokalen Ordner hoch,
        die nicht bereits auf dem Server existieren.
        """
        local = Path(local_folder)
        if not local.is_dir():
            logger.error("Kein gültiger Ordner: %s", local_folder)
            return False

        # Bestehende Remote-Dateien abrufen
        existing = self.list_files(library_id, remote_dir)
        existing_names = {e.get("name") for e in existing if e.get("type") == "file"}

        ok = True
        for f in local.glob("*"):
            if f.is_file() and f.name not in existing_names:
                if not self.upload_file(library_id, str(f), remote_dir):
                    ok = False
        return ok

    def get_file_info(self, library_id: str, remote_path: str) -> dict | None:
        """Holt Metadaten einer Datei."""
        try:
            url = f"{self.server_url}/api2/repos/{library_id}/file/detail/"
            params = {"p": remote_path}
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=30
            )
            return resp.json() if resp.status_code == 200 else None
        except requests.RequestException as e:
            logger.error("Fehler bei file_info: %s", e)
            return None

    def delete_file(self, library_id: str, remote_path: str) -> bool:
        """Löscht eine Datei aus Seafile."""
        try:
            url = f"{self.server_url}/api2/repos/{library_id}/file/"
            params = {"p": remote_path}
            resp = requests.delete(
                url, headers=self._headers(), params=params, timeout=30
            )
            ok = resp.status_code in (200, 204)
            logger.info("Löschen %s: %s", remote_path, "OK" if ok else f"FAIL ({resp.status_code})")
            return ok
        except requests.RequestException as e:
            logger.error("Fehler beim Löschen: %s", e)
            return False

    def share_link(self, library_id: str, remote_path: str) -> str | None:
        """Erstellt einen öffentlichen Teilen-Link."""
        try:
            url = f"{self.server_url}/api2/repos/{library_id}/file/shared-link/"
            data = {"p": remote_path}
            resp = requests.post(
                url, headers=self._headers(), data=data, timeout=30
            )
            if resp.status_code == 200:
                link = resp.json().get("link", "")
                logger.info("Share-Link erstellt: %s", link)
                return link
            logger.warning("Share-Link fehlgeschlagen: %s", resp.status_code)
            return None
        except requests.RequestException as e:
            logger.error("Fehler bei Share-Link: %s", e)
            return None

    def list_libraries(self) -> list[dict]:
        """Listet alle Bibliotheken auf."""
        try:
            url = f"{self.server_url}/api2/repos/"
            resp = requests.get(url, headers=self._headers(), timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                return data.get("repos", [])
            return []
        except requests.RequestException as e:
            logger.error("Fehler beim Auflisten der Bibliotheken: %s", e)
            return []

    def list_files(self, library_id: str, directory: str = "/") -> list[dict]:
        """Listet Dateien in einem Verzeichnis einer Bibliothek."""
        try:
            url = f"{self.server_url}/api2/repos/{library_id}/dir/"
            params = {"p": directory}
            resp = requests.get(
                url, headers=self._headers(), params=params, timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                return data.get("direntries", [])
            return []
        except requests.RequestException as e:
            logger.error("Fehler beim Auflisten: %s", e)
            return []


# ─── CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = SeafileBridge()
    libs = bridge.list_libraries()
    print(f"Gefundene Bibliotheken: {len(libs)}")
    for lib in libs:
        print(f"  - {lib.get('name', '?')} (ID: {lib.get('id', '?')})")
