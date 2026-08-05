"""Agent X — StateStore Interface (Redis/In-Memory/Neo4j)."""

from abc import ABC, abstractmethod
from typing import Optional


class StateStore(ABC):
    """Abstrakte Speicherschicht für Agent-X-Zustände.

    Produktion: Redis/Neo4j-Backend.
    Entwicklung: InMemoryStateStore (keine externen Abhängigkeiten).
    """

    @abstractmethod
    def get_hf(self, user_address: str, tenant: str = "default") -> Optional[float]:
        """Health-Factor eines Users abrufen."""
        ...

    @abstractmethod
    def set_hf(self, user_address: str, hf: float, tenant: str = "default") -> None:
        """Health-Factor speichern."""
        ...

    @abstractmethod
    def get_positions(self, user_address: str, tenant: str = "default") -> list[dict]:
        """Positionen eines Users abrufen."""
        ...

    @abstractmethod
    def set_positions(self, user_address: str, positions: list[dict], tenant: str = "default") -> None:
        """Positionen speichern."""
        ...

    @abstractmethod
    def get_global_state(self, tenant: str = "default") -> dict:
        """Global-State des Orchestrators abrufen."""
        ...

    @abstractmethod
    def set_global_state(self, state: dict, tenant: str = "default") -> None:
        """Global-State speichern."""
        ...

    @abstractmethod
    def get_timelocks(self, tenant: str = "default") -> list[dict]:
        """Pending Timelock-Actions abrufen."""
        ...


class InMemoryStateStore(StateStore):
    """In-Memory-Implementierung für Entwicklung und Tests.

    Keine externen Abhängigkeiten. Daten gehen bei Prozess-Neustart verloren.
    """

    def __init__(self):
        self._hf: dict[str, dict[str, float]] = {}        # tenant → user → hf
        self._positions: dict[str, dict[str, list]] = {}   # tenant → user → positions
        self._global_state: dict[str, dict] = {}            # tenant → state
        self._timelocks: dict[str, list] = {}               # tenant → timelocks

    def _key(self, user: str, tenant: str) -> str:
        return f"{tenant}:{user}"

    def get_hf(self, user_address: str, tenant: str = "default") -> Optional[float]:
        return self._hf.get(tenant, {}).get(user_address)

    def set_hf(self, user_address: str, hf: float, tenant: str = "default") -> None:
        self._hf.setdefault(tenant, {})[user_address] = hf

    def get_positions(self, user_address: str, tenant: str = "default") -> list[dict]:
        return self._positions.get(tenant, {}).get(user_address, [])

    def set_positions(self, user_address: str, positions: list[dict], tenant: str = "default") -> None:
        self._positions.setdefault(tenant, {})[user_address] = positions

    def get_global_state(self, tenant: str = "default") -> dict:
        return self._global_state.get(tenant, {"score": 100, "state": "healthy"})

    def set_global_state(self, state: dict, tenant: str = "default") -> None:
        self._global_state[tenant] = state

    def get_timelocks(self, tenant: str = "default") -> list[dict]:
        return self._timelocks.get(tenant, [])


class RedisStateStore(StateStore):
    """Redis-basierte Implementierung für Produktion.

    Keys: agent_x:{tenant}:hf:{user}, agent_x:{tenant}:positions:{user}, etc.
    Benötigt: pip install redis
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        try:
            import redis
            self._redis = redis.from_url(redis_url)
            self._redis.ping()
        except ImportError:
            raise ModuleNotFoundError("redis not installed — pip install redis")
        except Exception as e:
            raise ConnectionError(f"Redis connection failed: {e}")

    def _key(self, tenant: str, prefix: str, user: str = "") -> str:
        base = f"agent_x:{tenant}:{prefix}"
        return f"{base}:{user}" if user else base

    def get_hf(self, user_address: str, tenant: str = "default") -> Optional[float]:
        val = self._redis.get(self._key(tenant, "hf", user_address))
        return float(val) if val else None

    def set_hf(self, user_address: str, hf: float, tenant: str = "default") -> None:
        self._redis.set(self._key(tenant, "hf", user_address), str(hf), ex=3600)

    def get_positions(self, user_address: str, tenant: str = "default") -> list[dict]:
        import json
        val = self._redis.get(self._key(tenant, "positions", user_address))
        return json.loads(val) if val else []

    def set_positions(self, user_address: str, positions: list[dict], tenant: str = "default") -> None:
        import json
        self._redis.set(self._key(tenant, "positions", user_address), json.dumps(positions), ex=3600)

    def get_global_state(self, tenant: str = "default") -> dict:
        import json
        val = self._redis.get(self._key(tenant, "global_state"))
        return json.loads(val) if val else {"score": 100, "state": "healthy"}

    def set_global_state(self, state: dict, tenant: str = "default") -> None:
        import json
        self._redis.set(self._key(tenant, "global_state"), json.dumps(state))

    def get_timelocks(self, tenant: str = "default") -> list[dict]:
        import json
        val = self._redis.get(self._key(tenant, "timelocks"))
        return json.loads(val) if val else []
