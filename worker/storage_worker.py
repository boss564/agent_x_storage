#!/usr/bin/env python3
"""
Storage-Worker – Redis-Daemon für M3 (Storage-Server).
Lauscht auf storage:jobs, dispatched an Agent 140-143 via redis_bridge.

Start:
    python3 storage_worker.py
    # oder:  ./start_worker.sh
"""

import json
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import redis as redis_mod
except ImportError:
    redis_mod = None  # type: ignore

from worker.redis_bridge import dispatch

# ─── Logging mit Rotation (5 MB x 5 Backups) ─────────────────
# Pfad deterministisch aus __file__ (unabhängig vom Start-CWD).
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "storage_worker.log"

_root = logging.getLogger()
if not any(isinstance(h, RotatingFileHandler) for h in _root.handlers):
    _fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")
    _fh = RotatingFileHandler(_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    _fh.setFormatter(_fmt)
    _root.addHandler(_fh)
    if sys.stdout.isatty():  # im Terminal zusätzlich auf die Konsole (kein Doppel-Log unter nohup)
        _sh = logging.StreamHandler()
        _sh.setFormatter(_fmt)
        _root.addHandler(_sh)
    _root.setLevel(logging.INFO)

logger = logging.getLogger("storage_worker")

# ─── Konfiguration ───────────────────────────────────────────

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")  # M3 lokal (Docker-Redis); früher M1 192.168.178.27
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)
QUEUE = "storage:jobs"
REPLY_QUEUE = "storage:replies"
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "5"))


class StorageWorker:
    """Redis-basierter Worker für Storage-Jobs."""

    def __init__(self):
        if redis_mod is None:
            raise ImportError("redis nicht installiert – pip install redis")

        self.redis = redis_mod.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=3,
        )
        # Verbindung testen
        self.redis.ping()
        logger.info("✅ Verbunden mit Redis auf %s:%s", REDIS_HOST, REDIS_PORT)

    def run(self):
        logger.info("Warte auf Jobs in '%s' (Poll %ss)...", QUEUE, POLL_INTERVAL)
        while True:
            try:
                job_data = self.redis.brpop(QUEUE, timeout=POLL_INTERVAL)
                if not job_data:
                    continue

                _, job_str = job_data
                job = json.loads(job_str)
                job_id = job.get("job_id")
                agent_type = job.get("agent_type")
                action = job.get("action")
                payload = job.get("payload", {})

                logger.info("Job %s: %s.%s", job_id[:8], agent_type, action)

                result = dispatch(agent_type, action, payload)
                result["job_id"] = job_id

                self.redis.lpush(REPLY_QUEUE, json.dumps(result))
                logger.info("Antwort %s: %s", job_id[:8], result.get("status"))

            except redis_mod.ConnectionError:
                logger.warning("Redis-Verbindung verloren – versuche erneut in %ss...", POLL_INTERVAL)
                time.sleep(POLL_INTERVAL)
            except json.JSONDecodeError as e:
                logger.error("Ungültiges Job-JSON: %s", e)
            except KeyboardInterrupt:
                logger.info("Worker beendet.")
                break
            except Exception as e:
                logger.error("Fehler: %s", e)
                time.sleep(1)


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Storage-Worker gestartet")
    logger.info("Redis: %s:%s", REDIS_HOST, REDIS_PORT)
    logger.info("Queue: %s → %s", QUEUE, REPLY_QUEUE)
    logger.info("=" * 50)

    try:
        worker = StorageWorker()
        worker.run()
    except ImportError as e:
        logger.fatal("❌ %s", e)
        sys.exit(1)
    except redis_mod.ConnectionError:
        logger.fatal(
            "❌ Keine Verbindung zu Redis %s:%s\n"
            "   Stelle sicher, dass Redis lokal läuft (Docker-Container 'redis').",
            REDIS_HOST, REDIS_PORT,
        )
        sys.exit(1)
