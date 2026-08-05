"""Agent X — Standardisierte Exception-Hierarchie."""


class AgentXException(Exception):
    """Basis-Exception für alle Agent-X-Fehler.

    Jede Exception trägt einen machine-readable code und HTTP-Statuscode.
    """

    def __init__(self, message: str, code: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": str(self), "status": self.status_code}}


# ─── Request-Validierung ─────────────────────────────────────────────

class SnapshotValidationError(AgentXException):
    """Snapshot-Daten entsprechen nicht dem Schema."""

    def __init__(self, details: str):
        super().__init__(f"Snapshot validation failed: {details}", "SNAPSHOT_INVALID", 422)


class MissingRequiredFieldError(SnapshotValidationError):
    def __init__(self, field: str):
        super().__init__(f"Required field missing: {field}")


class InvalidAddressError(SnapshotValidationError):
    def __init__(self, address: str):
        super().__init__(f"Invalid Ethereum address: {address}")


# ─── Externe Abhängigkeiten ──────────────────────────────────────────

class OracleUnavailableError(AgentXException):
    """Oracle (Chainlink/Pyth) nicht erreichbar."""

    def __init__(self, provider: str = "chainlink"):
        super().__init__(f"Oracle unavailable: {provider}", "ORACLE_UNAVAILABLE", 503)


class RPCConnectionError(AgentXException):
    """RPC-Endpoint nicht erreichbar."""

    def __init__(self, chain: str = "ethereum"):
        super().__init__(f"RPC connection failed for {chain}", "RPC_CONNECTION_ERROR", 503)


class RateLimitError(AgentXException):
    """API-Rate-Limit überschritten."""

    def __init__(self, retry_after_s: int = 60):
        super().__init__(f"Rate limit exceeded — retry after {retry_after_s}s", "RATE_LIMITED", 429)
        self.retry_after_s = retry_after_s


# ─── Interne Fehler ──────────────────────────────────────────────────

class ModuleNotAvailableError(AgentXException):
    """Fach-Modul konnte nicht geladen werden."""

    def __init__(self, module_name: str):
        super().__init__(f"Module not available: {module_name}", "MODULE_UNAVAILABLE", 500)


class InconsistentStateError(AgentXException):
    """Inkonsistenz zwischen Modul und Orchestrator (Wächter-Alarm)."""

    def __init__(self, module: str, inline_val, module_val):
        super().__init__(
            f"Inconsistent state in {module}: inline={inline_val}, module={module_val}",
            "STATE_INCONSISTENT", 500,
        )


class CircuitBreakerTrippedError(AgentXException):
    """Circuit-Breaker hat Transaktion blockiert (Fee > X% vom Profit)."""

    def __init__(self, fee_usd: float, profit_usd: float, threshold_pct: float):
        super().__init__(
            f"Circuit breaker tripped: fee ${fee_usd:.2f} = {fee_usd/profit_usd*100:.1f}% "
            f"of profit ${profit_usd:.2f} (threshold: {threshold_pct}%)",
            "CIRCUIT_BREAKER_TRIPPED", 422,
        )
