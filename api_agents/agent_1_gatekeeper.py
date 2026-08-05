"""
Agent X — API Agent 1: Gatekeeper (Sicherheitsschicht).

Verantwortung: API-Key-Validierung, Tenant-Isolation, Rate-Limiting.

Sub-Agenten:
  1a: RateLimitSubAgent — Sliding Window Rate-Limit via Redis/In-Memory
  1b: TenantMapper — API-Key → Tenant-ID Mapping
  1c: IP-Blocklist — DDoS-Schutz (optional)
"""

import hashlib
import logging
import time
from typing import Optional

from core.context import RequestContext
from core.exceptions import AgentXException

logger = logging.getLogger("ApiGatekeeper")


# ─── Rate-Limit-Exception ────────────────────────────────────────────

class RateLimitExceededError(AgentXException):
    def __init__(self, retry_after_s: int = 60):
        super().__init__(f"Rate limit exceeded — retry after {retry_after_s}s", "RATE_LIMITED", 429)
        self.retry_after_s = retry_after_s


class InvalidApiKeyError(AgentXException):
    def __init__(self):
        super().__init__("Invalid or expired API key", "INVALID_API_KEY", 401)


class TenantNotFoundError(AgentXException):
    def __init__(self, api_key_hash: str):
        super().__init__(f"Tenant not found for key hash {api_key_hash[:8]}...", "TENANT_NOT_FOUND", 403)


# ─── Sub-Agent 1a: RateLimitSubAgent ──────────────────────────────────

class RateLimitSubAgent:
    """Sliding-Window Rate-Limiter.

    Redis (Produktion) oder In-Memory-Dict (Entwicklung).
    Speichert Request-Timestamps pro API-Key-Hash.
    """

    def __init__(self, redis_client=None, window_s: int = 60, max_requests: int = 100):
        self.window = window_s
        self.max_requests = max_requests
        self.redis = redis_client
        # In-Memory Fallback
        self._memory: dict[str, list[float]] = {}

    async def check(self, api_key: str) -> bool:
        """True wenn Request erlaubt, False wenn Limit erreicht."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]

        if self.redis:
            return await self._check_redis(key_hash)
        return self._check_memory(key_hash)

    async def _check_redis(self, key_hash: str) -> bool:
        redis_key = f"ratelimit:{key_hash}"
        now = time.time()
        window_start = now - self.window

        try:
            await self.redis.zremrangebyscore(redis_key, 0, window_start)
            count = await self.redis.zcard(redis_key)
            if count >= self.max_requests:
                return False
            await self.redis.zadd(redis_key, {str(now): now})
            await self.redis.expire(redis_key, self.window + 10)
            return True
        except Exception as e:
            logger.warning("Redis-RateLimit Fehler: %s — In-Memory-Fallback", e)
            return self._check_memory(key_hash)

    def _check_memory(self, key_hash: str) -> bool:
        now = time.time()
        window_start = now - self.window

        if key_hash not in self._memory:
            self._memory[key_hash] = []

        # Bereinige alte Einträge
        self._memory[key_hash] = [t for t in self._memory[key_hash] if t > window_start]

        if len(self._memory[key_hash]) >= self.max_requests:
            return False

        self._memory[key_hash].append(now)
        return True

    def stats(self) -> dict:
        return {
            "window_s": self.window,
            "max_requests": self.max_requests,
            "active_keys": len(self._memory),
            "backend": "redis" if self.redis else "memory",
        }


# ─── Sub-Agent 1b: TenantMapper ──────────────────────────────────────

class TenantMapper:
    """Mappt API-Key → Tenant-ID.

    Produktion: Redis/Datenbank.
    Entwicklung: Statische Map.
    """

    STATIC_MAP = {
        "sk_test_abc123": {"tenant": "tenant_alpha", "tier": "pro"},
        "sk_live_xyz789": {"tenant": "tenant_beta", "tier": "enterprise"},
        "sk_demo_000": {"tenant": "default", "tier": "free"},
    }

    @classmethod
    def lookup(cls, api_key: str) -> Optional[dict]:
        """Gibt {tenant, tier} oder None zurück."""
        return cls.STATIC_MAP.get(api_key)

    @classmethod
    def register(cls, api_key: str, tenant_id: str, tier: str = "free"):
        """Registriert neuen API-Key (Dev-Mode)."""
        cls.STATIC_MAP[api_key] = {"tenant": tenant_id, "tier": tier}


# ─── Sub-Agent 1c: IP-Blocklist (optional) ───────────────────────────

class IPBlocklist:
    """DDoS-Schutz: Blockiert bekannte Angreifer-IPs."""

    def __init__(self):
        self._blocked: set[str] = set()

    def block(self, ip: str):
        self._blocked.add(ip)

    def is_blocked(self, ip: str) -> bool:
        return ip in self._blocked

    @property
    def count(self) -> int:
        return len(self._blocked)


# ─── Agent 1: ApiGatekeeperAgent ─────────────────────────────────────

class ApiGatekeeperAgent:
    """Haupt-Gatekeeper: Authentifizierung + Rate-Limit + Tenant.

    Usage:
        gatekeeper = ApiGatekeeperAgent()
        ctx = await gatekeeper.authenticate("sk_test_abc123", "/v1/evaluate")
        # → RequestContext(tenant_id="tenant_alpha", ...)
    """

    def __init__(self, redis_url: str | None = None, rate_limit_per_minute: int = 100):
        redis_client = None
        if redis_url:
            try:
                import redis.asyncio as aioredis
                redis_client = aioredis.from_url(redis_url, decode_responses=True)
                redis_client.ping()
            except Exception:
                logger.warning("Redis nicht verfügbar — In-Memory-Rate-Limit")

        self.rate_limiter = RateLimitSubAgent(
            redis_client=redis_client, max_requests=rate_limit_per_minute,
        )
        self.tenant_mapper = TenantMapper()
        self.ip_blocklist = IPBlocklist()

    async def authenticate(self, api_key: str | None, path: str = "/",
                           client_ip: str | None = None) -> RequestContext:
        """Vollständige Gatekeeper-Prüfung.

        Args:
            api_key: X-API-Key Header (None = kein Key)
            path: Request-Pfad (für Logging)
            client_ip: Client-IP (für Blocklist)

        Returns:
            RequestContext mit tenant_id

        Raises:
            InvalidApiKeyError (401)
            TenantNotFoundError (403)
            RateLimitExceededError (429)
        """
        # 1. API-Key-Validierung
        if not api_key or len(api_key) < 10:
            raise InvalidApiKeyError()

        # 2. IP-Blocklist (optional)
        if client_ip and self.ip_blocklist.is_blocked(client_ip):
            raise AgentXException(f"IP {client_ip} is blocked", "IP_BLOCKED", 403)

        # 3. Tenant-Mapping
        tenant_info = self.tenant_mapper.lookup(api_key)
        if not tenant_info:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12]
            raise TenantNotFoundError(key_hash)

        # 4. Rate-Limiting
        allowed = await self.rate_limiter.check(api_key)
        if not allowed:
            raise RateLimitExceededError()

        # 5. Context bauen
        ctx = RequestContext(tenant_id=tenant_info["tenant"])
        logger.info("Gatekeeper OK: tenant=%s path=%s tier=%s [%s]",
                     ctx.tenant_id, path, tenant_info["tier"], ctx.correlation_id)

        return ctx

    def register_key(self, api_key: str, tenant_id: str, tier: str = "free"):
        """Dev-Mode: Registriert einen neuen API-Key."""
        self.tenant_mapper.register(api_key, tenant_id, tier)
        logger.info("API-Key registriert: %s → %s (tier=%s)", api_key[:12], tenant_id, tier)
