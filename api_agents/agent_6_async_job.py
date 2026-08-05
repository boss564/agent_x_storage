"""
Agent X — API Agent 6: AsyncJobAgent (Hintergrund-Jobs).

Verantwortung: Langlaufende Aufgaben (Backtests, Mining) asynchron
in Worker-Prozessen ausführen mit Status-Tracking.

Sub-Agenten:
  6a: JobStatusSubAgent — Redis-basiertes Job-Tracking (PENDING→RUNNING→DONE)
  6b: WorkerPool — Konfigurierbare Anzahl Worker-Tasks
"""

import asyncio
import json
import logging
import time
import uuid
from enum import Enum
from typing import Any, Optional

from core.exceptions import AgentXException

logger = logging.getLogger("AsyncJobAgent")


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobNotFoundError(AgentXException):
    def __init__(self, job_id: str):
        super().__init__(f"Job {job_id} not found", "JOB_NOT_FOUND", 404)


# ─── Sub-Agent 6a: JobStatusSubAgent ─────────────────────────────────

class JobStatusSubAgent:
    """Verwaltet Job-Zustände. Redis (Produktion) oder In-Memory (Dev)."""

    def __init__(self, redis_client=None, job_ttl_s: int = 86400):
        self.redis = redis_client
        self.ttl = job_ttl_s
        self._memory: dict[str, dict] = {}

    async def create(self, tenant_id: str, job_type: str, correlation_id: str) -> str:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        data = {
            "job_id": job_id, "type": job_type,
            "status": JobStatus.PENDING.value,
            "tenant_id": tenant_id, "correlation_id": correlation_id,
            "created_at": str(time.time()), "progress": 0,
            "result": "null", "error": "null",
        }
        if self.redis:
            await self.redis.hset(f"job:{job_id}", mapping=data)
            await self.redis.expire(f"job:{job_id}", self.ttl)
        else:
            self._memory[job_id] = data
        return job_id

    async def update(self, job_id: str, status: JobStatus, progress: float = 0):
        data = self._get(job_id)
        if isinstance(data, dict):
            data["status"] = status.value
            data["progress"] = str(progress)
            if self.redis:
                await self.redis.hset(f"job:{job_id}", mapping={
                    "status": status.value, "progress": str(progress),
                })

    async def set_result(self, job_id: str, result: dict):
        data = self._get(job_id)
        if isinstance(data, dict):
            data["status"] = JobStatus.COMPLETED.value
            data["result"] = json.dumps(result)
            data["progress"] = "100"
            if self.redis:
                await self.redis.hset(f"job:{job_id}", mapping={
                    "status": JobStatus.COMPLETED.value,
                    "result": json.dumps(result), "progress": "100",
                })

    async def set_error(self, job_id: str, error: str):
        data = self._get(job_id)
        if isinstance(data, dict):
            data["status"] = JobStatus.FAILED.value
            data["error"] = error
            if self.redis:
                await self.redis.hset(f"job:{job_id}", mapping={
                    "status": JobStatus.FAILED.value, "error": error,
                })

    async def get(self, job_id: str) -> dict:
        data = self._get(job_id)
        if isinstance(data, dict):
            d = dict(data)
            if d.get("result") and d["result"] != "null":
                try:
                    d["result"] = json.loads(d["result"])
                except json.JSONDecodeError:
                    pass
            return d
        raise JobNotFoundError(job_id)

    def _get(self, job_id: str):
        if self.redis:
            # Synchroner Fallback für In-Memory-Pfad
            return self._memory.get(job_id, {"status": "UNKNOWN"})
        return self._memory.get(job_id)


# ─── Agent 6: AsyncJobAgent ──────────────────────────────────────────

class AsyncJobAgent:
    """Verwaltet langlaufende Hintergrundaufgaben mit Status-Tracking.

    Usage:
        async_job = AsyncJobAgent(worker_count=4)
        await async_job.start()
        job_id = await async_job.submit(internal_dict, ctx, "BACKTEST")
        status = await async_job.get_status(job_id)
    """

    def __init__(self, worker_count: int = 2):
        self.status_agent = JobStatusSubAgent()
        self.worker_count = worker_count
        self._queue: asyncio.Queue = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def submit(self, internal: dict, context, job_type: str = "BACKTEST") -> str:
        """Nimmt neuen Job an, gibt Job-ID zurück."""
        job_id = await self.status_agent.create(
            context.tenant_id, job_type, context.correlation_id,
        )
        await self._queue.put({"job_id": job_id, "internal": internal, "context": context})
        logger.info("Job %s queued [%s]", job_id, context.correlation_id)
        return job_id

    async def get_status(self, job_id: str) -> dict:
        return await self.status_agent.get(job_id)

    async def start(self):
        """Startet Worker-Pool."""
        self._running = True
        self._workers = [
            asyncio.create_task(self._worker_loop(i))
            for i in range(self.worker_count)
        ]
        logger.info("AsyncJobAgent: %d workers started", self.worker_count)

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def _worker_loop(self, worker_id: int):
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

            job_id = task["job_id"]
            internal = task["internal"]
            logger.info("Worker %d processing %s", worker_id, job_id)

            await self.status_agent.update(job_id, JobStatus.RUNNING, 10)
            try:
                # Simulierter Backtest (in Produktion: echter Run)
                await asyncio.sleep(0.5)  # Simulierte Arbeit
                result = {
                    "status": "completed",
                    "scenarios_run": 8,
                    "overall_grade": "B",
                    "overall_score": 88.0,
                    "job_id": job_id,
                }
                await self.status_agent.set_result(job_id, result)
                logger.info("Job %s completed", job_id)
            except Exception as e:
                await self.status_agent.set_error(job_id, str(e))
                logger.error("Job %s failed: %s", job_id, e)
            finally:
                self._queue.task_done()
