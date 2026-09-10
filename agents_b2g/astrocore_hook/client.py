"""Read-only Class-C liquidation hook client (Neo4j / WORM / synthetic)."""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agents_b2g.astrocore_hook.neo4j_reader import (
    Neo4jReaderConfig,
    compute_since_ts,
    fetch_liquidation_timestamps,
    preflight_liquidation_aggregate,
    resolve_neo4j_read_auth,
)
from agents_b2g.astrocore_hook.raas_ingest import parse_gap_logs
from agents_b2g.astrocore_hook.verdict import cap_verdict_for_provenance

DEFAULT_FUNDING_PERIOD_S = float(os.getenv("ASTROCORE_FUNDING_PERIOD_S", "28800.0"))
DEFAULT_STRICT = os.getenv("ASTROCORE_STRICT", "false").lower() in ("true", "1", "yes")
DEFAULT_DATA_SOURCE = os.getenv("ASTROCORE_DATA_SOURCE", "synthetic").lower()
DEFAULT_AUDIT_DIR = os.getenv("RAAS_AUDIT_DIR", "/data/audit")

_CHERRY_ASTRO = (
    Path(__file__).resolve().parents[2] / "imports" / "cherrystudio" / "astrocore"
)


def _cherry_imports() -> Tuple[Any, Any]:
    path = str(_CHERRY_ASTRO)
    if path not in sys.path:
        sys.path.insert(0, path)
    from test_liquidation_coupling import (  # noqa: WPS433
        analyze_liquidation_events,
        generate_synthetic_liquidations,
    )
    return analyze_liquidation_events, generate_synthetic_liquidations


def _raw_verdict_from_analysis(analysis: dict) -> str:
    if analysis.get("error"):
        return "INSUFFICIENT_N"
    interp = str(analysis.get("interpretation", ""))
    if "SIGNIFIKANT" in interp and "NICHT" not in interp:
        return "CLUSTER_DETECTED"
    return "UNIFORM"


@dataclass
class AstrocoreHookClient:
    """Read-only Class-C liquidation coupling hook (Neo4j / WORM / synthetic)."""

    data_source: str = field(default_factory=lambda: DEFAULT_DATA_SOURCE)
    audit_dir: str = field(default_factory=lambda: DEFAULT_AUDIT_DIR)
    neo4j_uri: Optional[str] = None
    neo4j_user: Optional[str] = None
    neo4j_password: Optional[str] = None
    lookback_days: int = field(
        default_factory=lambda: int(os.getenv("ASTROCORE_NEO4J_LOOKBACK_DAYS", "7"))
    )
    funding_period_s: float = DEFAULT_FUNDING_PERIOD_S
    strict: bool = DEFAULT_STRICT
    limit: int = field(
        default_factory=lambda: int(os.getenv("ASTROCORE_NEO4J_LIMIT", "10000"))
    )

    def _synthetic_timestamps(self) -> Tuple[np.ndarray, dict]:
        _, generate_synthetic_liquidations = _cherry_imports()
        events = generate_synthetic_liquidations(
            n_events=1000,
            funding_period=self.funding_period_s,
            cluster_strength=0.3,
        )
        meta = {
            "provenance": "synthetic",
            "warnings": ["Synthetic fallback: Neo4j not configured or unavailable."],
            "source": "generate_synthetic_liquidations()",
        }
        return events, meta

    def _neo4j_timestamps(self) -> Tuple[np.ndarray, dict]:
        auth = resolve_neo4j_read_auth(
            uri=self.neo4j_uri,
            user=self.neo4j_user,
            password=self.neo4j_password,
            strict=self.strict,
        )
        if not auth["uri"]:
            if self.strict:
                raise RuntimeError("neo4j_uri required when strict=True")
            return self._synthetic_timestamps()

        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            if self.strict:
                raise RuntimeError("neo4j driver not installed") from exc
            ts, meta = self._synthetic_timestamps()
            meta["warnings"].append(f"neo4j import failed: {exc}")
            return ts, meta

        since_ts = compute_since_ts(
            lookback_days=self.lookback_days,
            allow_extended_lookback=False,
        )
        driver = GraphDatabase.driver(
            auth["uri"], auth=(auth["user"], auth["password"])
        )
        try:
            pre = preflight_liquidation_aggregate(driver, since_ts)
            if pre["n"] == 0:
                if self.strict:
                    raise RuntimeError("no LiquidationEvent rows in lookback window")
                ts, meta = self._synthetic_timestamps()
                meta["warnings"].insert(0, f"Neo4j empty in {self.lookback_days}d window")
                meta["warnings"].extend(auth["warnings"])
                return ts, meta
            timestamps = np.array(
                fetch_liquidation_timestamps(driver, since_ts=since_ts, limit=self.limit),
                dtype=np.float64,
            )
            return timestamps, {
                "provenance": "neo4j",
                "warnings": list(auth["warnings"]),
                "source": auth["uri"],
                "preflight": pre,
                "dedicated_reader": auth["dedicated_reader"],
            }
        except Exception as exc:
            if self.strict:
                raise
            ts, meta = self._synthetic_timestamps()
            meta["warnings"].append(f"Neo4j read failed: {exc}")
            return ts, meta
        finally:
            driver.close()

    def _worm_timestamps(self) -> Tuple[np.ndarray, dict]:
        timestamps, meta = parse_gap_logs(
            Path(self.audit_dir),
            lookback_days=self.lookback_days,
            limit=self.limit,
            funding_period_s=self.funding_period_s,
        )
        if meta.get("provenance") == "gap_synthetic" and self.strict:
            raise RuntimeError(
                f"no worm audit events in {self.lookback_days}d under {self.audit_dir}"
            )
        return timestamps, meta

    def fetch_timestamps(self) -> Tuple[np.ndarray, dict]:
        source = (self.data_source or "synthetic").lower()
        if source == "neo4j":
            return self._neo4j_timestamps()
        if source == "worm":
            return self._worm_timestamps()
        return self._synthetic_timestamps()

    def analyze_liquidations(self) -> Dict[str, Any]:
        """Return AstroCoreHookEnvelope-compatible dict."""
        analyze_fn, _ = _cherry_imports()
        timestamps, meta = self.fetch_timestamps()
        analysis = analyze_fn(timestamps, funding_period=self.funding_period_s)
        provenance = meta.get("provenance", "unknown")
        raw_verdict = _raw_verdict_from_analysis(analysis)
        verdict = cap_verdict_for_provenance(raw_verdict, provenance)

        return {
            "schema": "astrocore_hook_envelope/v1",
            "hook": "astrocore_hook_client",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "diagnostic_only": True,
            "live_execution": False,
            "order_send": False,
            "not_investment_advice": True,
            "data_provenance": provenance,
            "warnings": meta.get("warnings", []),
            "funding_period_s": self.funding_period_s,
            "lookback_days": self.lookback_days,
            "stats": {
                "events_read": int(len(timestamps)),
                "data_source": self.data_source,
                "source": meta.get("source", "n/a"),
                "source_files": meta.get("source_files", []),
                "raw_verdict": raw_verdict,
            },
            "analysis": analysis,
            "verdict": verdict,
        }

    def to_evaluator_signal(self, envelope: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Map envelope → flat dict for emergence_adapter consumers."""
        env = envelope or self.analyze_liquidations()
        analysis = env.get("analysis") or {}
        ray = analysis.get("rayleigh") or {}
        sur = analysis.get("surrogate_test") or analysis.get("surrogate") or {}
        return {
            "R": float(ray.get("R", 0.0)),
            "rayleigh_p": float(ray.get("p", 1.0)),
            "surrogate_p": float(sur.get("p_surrogate", sur.get("p", 1.0))),
            "verdict": env.get("verdict", "UNAVAILABLE"),
            "data_provenance": env.get("data_provenance", "unknown"),
            "warnings": list(env.get("warnings") or []),
            "n_events": int(analysis.get("n_events", env.get("stats", {}).get("events_read", 0))),
        }


def hook_enabled_from_env() -> bool:
    return os.getenv("ASTROCORE_HOOK_ENABLED", "false").lower() in ("true", "1", "yes")
