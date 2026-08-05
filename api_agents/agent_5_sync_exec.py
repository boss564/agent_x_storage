"""
Agent X — API Agent 5: SyncExecutionAgent (Fast-Path < 40ms).

Verantwortung: Synchrone, latenzkritische Ausführung von Risk-Checks
mit Timeout-Überwachung und Circuit Breaker.

Sub-Agenten:
  5a: FastPathGuardSubAgent — Timeout + Circuit Breaker
  5b: Response Enricher — Metadaten (execution_time_ms, path)
"""

import asyncio
import logging
import time
from typing import Any, Optional

from core.exceptions import AgentXException

logger = logging.getLogger("SyncExecutionAgent")


# ─── Timeout-Exception ───────────────────────────────────────────────

class TimeoutException(AgentXException):
    def __init__(self, detail: str, code: str = "SYNC_TIMEOUT", status_code: int = 504):
        super().__init__(detail, code, status_code)


class CircuitBreakerOpenError(AgentXException):
    def __init__(self):
        super().__init__("Circuit breaker open — core temporarily unavailable",
                         "CIRCUIT_OPEN", 503)


# ─── Sub-Agent 5a: FastPathGuardSubAgent ─────────────────────────────

class FastPathGuardSubAgent:
    """Timeout-Überwachung + Circuit Breaker für Sync-Pfad.

    Circuit Breaker: Öffnet nach N aufeinanderfolgenden Fehlern.
    Halb-Offen nach 30s — erster erfolgreicher Request schließt ihn wieder.
    """

    def __init__(self, default_timeout_ms: float = 40.0, failure_threshold: int = 5):
        self.default_timeout_s = default_timeout_ms / 1000.0
        self.failure_threshold = failure_threshold
        self._failure_count = 0
        self._circuit_open = False
        self._last_failure_time = 0.0
        self._total_executed = 0
        self._total_timeouts = 0

    def check_circuit(self):
        """Wirft Exception wenn Circuit offen ist."""
        if self._circuit_open:
            if time.time() - self._last_failure_time > 30.0:
                self._circuit_open = False
                self._failure_count = 0
                logger.warning("Circuit Breaker: HALF-OPEN → CLOSED (30s elapsed)")
            else:
                raise CircuitBreakerOpenError()

    async def execute(self, coro, timeout_ms: Optional[float] = None) -> Any:
        """Führt Coroutine mit Timeout aus. Zählt Erfolge/Fehler."""
        self.check_circuit()
        timeout_s = (timeout_ms or self.default_timeout_s * 1000) / 1000.0
        self._total_executed += 1

        try:
            result = await asyncio.wait_for(coro, timeout=timeout_s)
            self._failure_count = max(0, self._failure_count - 1)
            return result
        except asyncio.TimeoutError:
            self._total_timeouts += 1
            self._record_failure()
            raise TimeoutException(f"Core response exceeded {timeout_s*1000:.0f}ms timeout")
        except AgentXException:
            raise
        except Exception as e:
            self._record_failure()
            logger.error("Core error in sync path: %s", e)
            raise

    def _record_failure(self):
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._circuit_open = True
            self._last_failure_time = time.time()
            logger.critical("Circuit Breaker OPEN after %d failures", self.failure_threshold)

    @property
    def stats(self) -> dict:
        return {
            "circuit_open": self._circuit_open,
            "failure_count": self._failure_count,
            "total_executed": self._total_executed,
            "total_timeouts": self._total_timeouts,
            "default_timeout_ms": self.default_timeout_s * 1000,
        }


# ─── Agent 5: SyncExecutionAgent ─────────────────────────────────────

class SyncExecutionAgent:
    """Führt synchrone, latenzkritische Anfragen aus.

    Usage:
        sync_exec = SyncExecutionAgent(orchestrator)
        result = await sync_exec.execute(internal_dict, context)
    """

    def __init__(self, default_timeout_ms: float = 40.0):
        self.guard = FastPathGuardSubAgent(default_timeout_ms)
        self._orchestrator = None

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            from agent_x_orchestrator import SymbolicsAgent
            self._orchestrator = SymbolicsAgent()
        return self._orchestrator

    async def execute(self, internal: dict, context) -> dict:
        """Fast-Path: Synchrone Evaluation mit Timeout-Schutz."""
        t0 = time.time()
        logger.info("SyncExecution start [%s]", context.correlation_id)

        async def _call():
            # Orchestrator im Sync-Mode (Thread-safe, keine async-Interna)
            return self.orchestrator.evaluate(
                consensus_health_index=internal.get("consensus_health") or 94.0,
                gas_pressure_index=internal.get("gas_pressure") or 50.0,
                mev_pressure_index=internal.get("mev_pressure") or 50.0,
                health_factors=internal.get("health_factors"),
                mempool_bots_count=internal.get("mempool_bots") or 0,
                pending_timelocks=internal.get("pending_timelocks") or None,
                leader_utilization_pct=internal.get("leader_utilization") or 50.0,
                oracle_update_in_s=internal.get("oracle_update_in_s") or 999.0,
                expected_profit_usd=internal.get("expected_profit_usd") or 0,
            )

        result = await self.guard.execute(_call())

        elapsed_ms = round((time.time() - t0) * 1000)
        result["execution_time_ms"] = elapsed_ms
        result["execution_path"] = "SYNC_FAST_PATH"
        result["circuit_breaker"] = self.guard.stats

        logger.info("SyncExecution complete: %dms [%s]", elapsed_ms, context.correlation_id)
        return result
