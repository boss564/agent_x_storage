"""
Agent X — API Agent 11: VaultStorageAgent (AES-256-Verschlüsselte Ablage).

Verantwortung: Verschlüsselt Fotos + PDFs pro Session mit AES-256-GCM.
Speichert die verschlüsselten Dateien auf dem lokalen Dateisystem oder S3.
NUR der AES-Key (+ IV + Auth-Tag) bleibt auf dem Server.

Sub-Agenten:
  11a: CryptoEngine — AES-256-GCM Verschlüsselung/Entschlüsselung
  11b: FileStore — Abstraktion über Dateisystem/S3/Seafile
  11c: KeyVault — Session-ID → {key, iv, tag, storage_path} Mapping

DSGVO: Kundendaten (Name, Adresse) werden NIE mit dem Protokoll-Hash
       verknüpft. Die session_id ist eine zufällige UUID ohne Personenbezug.
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("VaultStorage")

# ─── Konfiguration ───────────────────────────────────────────────────

VAULT_PATH = os.getenv("VAULT_PATH", "data/vault")
S3_BUCKET = os.getenv("S3_BUCKET", "")
MASTER_KEY_HEX = os.getenv("MASTER_KEY_HEX", "")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Sub-Agent 11a: CryptoEngine ─────────────────────────────────────

class CryptoEngine:
    """AES-256-GCM Verschlüsselung/Entschlüsselung.

    Verwendet die Python cryptography-Bibliothek.
    Fallback: Hash-basierte Simulation für Dev-Umgebungen ohne cryptography.
    """

    @staticmethod
    def encrypt(plaintext: bytes) -> dict:
        """Verschlüsselt Daten mit AES-256-GCM. Gibt {key, iv, tag, ciphertext}."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            import os as _os

            key = AESGCM.generate_key(bit_length=256)
            aesgcm = AESGCM(key)
            nonce = _os.urandom(12)  # 96-bit IV für GCM

            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            # Auth-Tag ist in den letzten 16 Bytes enthalten (GCM-Standard)
            tag = ciphertext[-16:]
            ct_without_tag = ciphertext[:-16]

            return {
                "key": key.hex(),
                "nonce": nonce.hex(),
                "tag": tag.hex(),
                "ciphertext": ct_without_tag.hex(),
            }
        except ImportError:
            # Fallback: XOR mit Key (nur für Dev!)
            key = hashlib.sha256(str(uuid.uuid4()).encode()).digest()
            nonce = hashlib.sha256(str(uuid.uuid4()).encode()).digest()[:12]
            ct = bytes(p ^ key[i % len(key)] for i, p in enumerate(plaintext))
            tag = hashlib.sha256(ct + key).digest()[:16]
            return {
                "key": key.hex(), "nonce": nonce.hex(),
                "tag": tag.hex(), "ciphertext": ct.hex(),
            }

    @staticmethod
    def decrypt(key_hex: str, nonce_hex: str, tag_hex: str,
                ciphertext_hex: str) -> bytes:
        """Entschlüsselt Daten. Wirft Exception bei falschem Key/Tag."""
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            key = bytes.fromhex(key_hex)
            nonce = bytes.fromhex(nonce_hex)
            tag = bytes.fromhex(tag_hex)
            ct = bytes.fromhex(ciphertext_hex)

            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ct + tag, None)
            return plaintext
        except ImportError:
            # Fallback-Decrypt
            key = bytes.fromhex(key_hex)
            ct = bytes.fromhex(ciphertext_hex)
            pt = bytes(c ^ key[i % len(key)] for i, c in enumerate(ct))
            # Verify tag
            expected_tag = hashlib.sha256(ct + key).digest()[:16]
            if expected_tag != bytes.fromhex(tag_hex):
                raise ValueError("Auth tag mismatch — data may be corrupted")
            return pt


# ─── Sub-Agent 11b: FileStore ────────────────────────────────────────

class FileStore:
    """Abstraktion über Dateisystem, S3, oder Seafile."""

    def __init__(self, base_path: str = VAULT_PATH):
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, session_id: str, encrypted_data: bytes) -> str:
        """Speichert verschlüsselte Daten. Gibt Pfad zurück."""
        path = self.base / f"{session_id}.enc"
        path.write_bytes(encrypted_data)
        logger.info("Vault saved: %s (%d bytes)", path.name, len(encrypted_data))
        return str(path)

    def load(self, session_id: str) -> bytes:
        """Lädt verschlüsselte Daten."""
        path = self.base / f"{session_id}.enc"
        if not path.exists():
            raise FileNotFoundError(f"Vault file not found: {path}")
        return path.read_bytes()

    def delete(self, session_id: str):
        """Löscht verschlüsselte Daten (DSGVO-Löschpflicht)."""
        path = self.base / f"{session_id}.enc"
        if path.exists():
            path.unlink()
            logger.info("Vault deleted: %s", path.name)

    def exists(self, session_id: str) -> bool:
        return (self.base / f"{session_id}.enc").exists()


# ─── Sub-Agent 11c: KeyVault ─────────────────────────────────────────

class KeyVault:
    """Session-ID → {key, nonce, tag, storage_path} Mapping.

    In-Memory für Dev, Redis/DB für Produktion.
    """

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self._memory: dict[str, dict] = {}

    def store(self, session_id: str, crypto_data: dict, storage_path: str):
        entry = {
            "key": crypto_data["key"],
            "nonce": crypto_data["nonce"],
            "tag": crypto_data["tag"],
            "storage_path": storage_path,
            "created_at": _now_iso(),
        }
        if self.redis:
            self.redis.hset(f"vault:key:{session_id}", mapping=entry)
        else:
            self._memory[session_id] = entry

    def get(self, session_id: str) -> Optional[dict]:
        if self.redis:
            data = self.redis.hgetall(f"vault:key:{session_id}")
            return data if data else None
        return self._memory.get(session_id)

    def delete(self, session_id: str):
        if self.redis:
            self.redis.delete(f"vault:key:{session_id}")
        else:
            self._memory.pop(session_id, None)


# ─── Agent 11: VaultStorageAgent ─────────────────────────────────────

class VaultStorageAgent:
    """Verschlüsselte Dateiablage mit Key-Management.

    Usage:
        vault = VaultStorageAgent()
        sid = vault.store(protocol_pdf_bytes, [photo1_bytes, photo2_bytes])
        # → Gibt session_id zurück
        files = vault.retrieve(sid)  # Nur mit korrektem Server-Key
    """

    def __init__(self):
        self.crypto = CryptoEngine()
        self.filestore = FileStore()
        self.keys = KeyVault()

    def store(self, protocol_pdf: bytes, photos: list[bytes],
              metadata: dict | None = None) -> dict:
        """Verschlüsselt und speichert Protokoll + Fotos.

        Returns:
            {"session_id": "...", "status": "stored", "size_bytes": N}
        """
        session_id = uuid.uuid4().hex[:24]

        # Bundle: Metadaten + Fotos + PDF
        bundle = {
            "session_id": session_id,
            "metadata": metadata or {},
            "photo_count": len(photos),
            "stored_at": _now_iso(),
        }
        bundle_bytes = json.dumps(bundle, ensure_ascii=False).encode()

        # Dateien in ein einfaches Container-Format packen
        container = bytearray()
        # Metadaten
        meta = json.dumps(bundle, ensure_ascii=False).encode()
        container.extend(len(meta).to_bytes(4, "big"))
        container.extend(meta)
        # PDF
        container.extend(len(protocol_pdf).to_bytes(4, "big"))
        container.extend(protocol_pdf)
        # Fotos
        container.extend(len(photos).to_bytes(2, "big"))
        for photo in photos:
            container.extend(len(photo).to_bytes(4, "big"))
            container.extend(photo)

        # Verschlüsseln
        crypto_data = self.crypto.encrypt(bytes(container))

        # Speichern
        storage_path = self.filestore.save(session_id, bytes.fromhex(crypto_data["ciphertext"]))
        self.keys.store(session_id, crypto_data, storage_path)

        logger.info("Vault stored: %s (%d bytes encrypted)", session_id, len(container))
        return {
            "session_id": session_id,
            "status": "stored",
            "original_size_bytes": len(container),
            "encrypted_size_bytes": len(crypto_data["ciphertext"]) // 2,
            "photo_count": len(photos),
        }

    def retrieve(self, session_id: str) -> dict | None:
        """Entschlüsselt und lädt Protokoll + Fotos."""
        key_data = self.keys.get(session_id)
        if not key_data:
            logger.warning("Key not found for session %s", session_id)
            return None

        encrypted = self.filestore.load(session_id)
        plaintext = self.crypto.decrypt(
            key_data["key"], key_data["nonce"],
            key_data["tag"], encrypted.hex(),
        )

        # Container parsen
        offset = 0
        meta_len = int.from_bytes(plaintext[offset:offset + 4], "big")
        offset += 4
        meta = json.loads(plaintext[offset:offset + meta_len].decode())
        offset += meta_len

        pdf_len = int.from_bytes(plaintext[offset:offset + 4], "big")
        offset += 4
        pdf = plaintext[offset:offset + pdf_len]
        offset += pdf_len

        photo_count = int.from_bytes(plaintext[offset:offset + 2], "big")
        offset += 2
        photos = []
        for _ in range(photo_count):
            p_len = int.from_bytes(plaintext[offset:offset + 4], "big")
            offset += 4
            photos.append(plaintext[offset:offset + p_len])
            offset += p_len

        return {
            "session_id": session_id,
            "metadata": meta,
            "protocol_pdf": pdf,
            "photos": photos,
        }

    def delete(self, session_id: str):
        """DSGVO-Löschung: Entfernt Key + Datei."""
        self.keys.delete(session_id)
        self.filestore.delete(session_id)
        logger.info("DSGVO-Delete: session %s", session_id)


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    vault = VaultStorageAgent()
    print("=== VaultStorageAgent Demo ===\n")

    # Store
    pdf = b"%PDF-1.4 Handover Protocol..." + b"X" * 1000
    photos = [b"JPEG_PHOTO_1" + b"Y" * 500, b"JPEG_PHOTO_2" + b"Z" * 500]
    result = vault.store(pdf, photos, {"project": "WP-2026-08", "inspector": "MM"})
    print(f"Stored: {json.dumps(result, indent=2)}")

    # Retrieve
    retrieved = vault.retrieve(result["session_id"])
    if retrieved:
        print(f"\nRetrieved: session={retrieved['session_id']}, "
              f"pdf={len(retrieved['protocol_pdf'])} bytes, "
              f"photos={len(retrieved['photos'])} files")
        print(f"  PDF preview: {retrieved['protocol_pdf'][:40]}...")
        print(f"  Photo 0: {retrieved['photos'][0][:20]}...")

    # Delete
    vault.delete(result["session_id"])
    print(f"\nDeleted. Exists: {vault.store.exists(result['session_id'])}")
