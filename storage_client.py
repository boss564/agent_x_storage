#!/usr/bin/env python3
"""
Storage-Client für M1 (Orchestrator/Supervisor).
Redis-basierte Kommunikation mit Storage-Worker auf M3.

Import:
    from storage_client import storage
    path = storage.get_sakral('orgel:dorian_slow')
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    import redis
except ImportError:
    redis = None  # type: ignore


class StorageClient:
    """Asynchroner Redis-Client für Storage-Agenten auf M3."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        timeout: float = 5.0,
        queue: str = "storage:jobs",
        reply_queue: str = "storage:replies",
    ):
        if redis is None:
            raise ImportError("redis nicht installiert – pip install redis")

        self.pool = redis.ConnectionPool(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        self.redis = redis.Redis(connection_pool=self.pool)
        self.timeout = timeout
        self.queue = queue
        self.reply_queue = reply_queue

    def _send_job(
        self, agent_type: str, action: str, payload: dict
    ) -> dict:
        """Sendet Job an Redis-Queue und wartet auf Antwort."""
        job_id = str(uuid.uuid4())
        msg = {
            "job_id": job_id,
            "agent_type": agent_type,
            "action": action,
            "payload": payload,
            "timestamp": time.time(),
        }
        self.redis.lpush(self.queue, json.dumps(msg))

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            reply = self.redis.brpop(self.reply_queue, timeout=1)
            if not reply:
                continue
            _, data = reply
            result = json.loads(data)
            if result.get("job_id") == job_id:
                return result

        raise TimeoutError(
            f"Storage-Agent {agent_type}:{action} keine Antwort "
            f"nach {self.timeout}s"
        )

    # ─── Öffentliche API ───────────────────────────────────────

    def get_sakral(self, identifier: str) -> Optional[str]:
        """Sakralen Sound abrufen (z. B. orgel:dorian_slow)."""
        r = self._send_job("sakral", "get", {"identifier": identifier})
        return r.get("path") if r.get("status") == "success" else None

    def get_motorik(self, identifier: str) -> Optional[str]:
        """Drum-Sample / MIDI-Groove abrufen."""
        r = self._send_job("motorik", "get", {"identifier": identifier})
        return r.get("path") if r.get("status") == "success" else None

    def get_effekt_preset(
        self, effect_type: str, name: str
    ) -> Optional[dict]:
        """Effekt-Preset als JSON abrufen."""
        r = self._send_job(
            "effekte", "get_preset",
            {"effect_type": effect_type, "name": name},
        )
        return r.get("preset") if r.get("status") == "success" else None

    def get_master_target(self, genre: str = "sakral_motorik") -> dict:
        """Mastering-Zielwerte abrufen."""
        r = self._send_job("master", "get_target", {"genre": genre})
        if r.get("status") == "success":
            return r.get("target", {})
        return {
            "loudness_target_lufs": -16.0,
            "true_peak_dbtp": -1.5,
            "crest_factor_min": 12.0,
        }

    def list_resources(
        self, agent_type: str, category: Optional[str] = None
    ) -> list:
        """Ressourcen eines Storage-Typs auflisten."""
        payload = {}
        if category:
            payload["category"] = category
        r = self._send_job(agent_type, "list", payload)
        return r.get("resources", []) if r.get("status") == "success" else []


# Singleton
storage = StorageClient()
