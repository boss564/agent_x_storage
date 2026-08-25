"""Sanctions / poisoning / relayer / bypass adapters — data layer only."""

from __future__ import annotations

import re
from typing import Optional, Sequence

from agents_b2g.defense.swarm_defense_orchestrator import JSONLogger, _safe_call
from agents_b2g.defense.threat_engine.pseudonym import eoa_pseudonym
from agents_b2g.defense.threat_engine.session import ThreatEngineSession

_HEX = re.compile(r"^0x[0-9a-fA-F]{40}$")

BLOCK_CAUSE_CENSORSHIP = "CENSORSHIP_DETECTED"

ASSET_FALLBACKS = {
    "USDC": "ETH_NATIVE",
    "USDT": "ETH_NATIVE",
    "EURe": "xDAI_NATIVE",
}


def detect_address_poisoning(
    candidate: str,
    targets: Sequence[str],
    *,
    min_match: int = 4,
) -> dict:
    """Objective vanity overlap: ≥4 leading or trailing hex vs a target, not equal."""
    if not _HEX.match(candidate or ""):
        return {"poisoning_suspected": False, "reason": "invalid_candidate"}
    c = candidate.lower()[2:]
    hits = []
    for t in targets:
        if not _HEX.match(t or ""):
            continue
        th = t.lower()[2:]
        if c == th:
            continue
        lead = c[:min_match] == th[:min_match]
        trail = c[-min_match:] == th[-min_match:]
        if lead or trail:
            hits.append(
                {
                    "target": t.lower(),
                    "leading_match": lead,
                    "trailing_match": trail,
                    "min_match": min_match,
                }
            )
    return {
        "poisoning_suspected": len(hits) > 0,
        "hits": hits,
        "reason": "VANITY_OVERLAP" if hits else "OK",
    }


class SanctionsScreeningAdapter:
    """OFAC/EU/Treasury watchlist + poisoning — Perimeter / ReputationScoreLookup."""

    def __init__(self, session: ThreatEngineSession, logger: Optional[JSONLogger] = None):
        self.session = session
        self.logger = logger or JSONLogger("SanctionsScreeningAdapter")

    def upsert_watch(
        self,
        *,
        address: str,
        source: str,
        list_version: str,
        confidence: float,
        observed_by_user_id: Optional[str] = None,
        already_pseudonym: bool = False,
    ) -> dict:
        return _safe_call(
            self.logger,
            "upsert_watch",
            self._upsert_watch,
            address,
            source,
            list_version,
            confidence,
            observed_by_user_id,
            already_pseudonym,
        )

    def _upsert_watch(
        self,
        address: str,
        source: str,
        list_version: str,
        confidence: float,
        observed_by_user_id: Optional[str],
        already_pseudonym: bool,
    ) -> dict:
        pseudo = address.lower() if already_pseudonym else eoa_pseudonym(address)
        self.session.execute(
            """
            INSERT INTO wave28_censorship_watchlist (
                address_pseudonym, source, list_version, confidence, observed_by_user_id
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING watch_id, created_at
            """,
            (pseudo, source, list_version, confidence, observed_by_user_id),
        )
        row = self.session.cursor.fetchone()
        return {
            "status": "completed",
            "job_id": "upsert_watch",
            "artifacts": [
                {
                    "watch_id": int(row[0]),
                    "address_pseudonym": pseudo,
                    "source": source,
                    "created_at": row[1].isoformat()
                    if hasattr(row[1], "isoformat")
                    else str(row[1]),
                }
            ],
            "error": None,
            "logs": [],
        }

    def screen_address(
        self,
        address: str,
        *,
        poisoning_targets: Optional[Sequence[str]] = None,
    ) -> dict:
        return _safe_call(
            self.logger,
            "screen_address",
            self._screen_address,
            address,
            poisoning_targets,
        )

    def _screen_address(
        self,
        address: str,
        poisoning_targets: Optional[Sequence[str]],
    ) -> dict:
        pseudo = eoa_pseudonym(address)
        self.session.execute(
            """
            SELECT watch_id, source, list_version, confidence
              FROM wave28_censorship_watchlist
             WHERE address_pseudonym = %s AND is_active = TRUE
             ORDER BY confidence DESC
             LIMIT 5
            """,
            (pseudo,),
        )
        hits = [
            {
                "watch_id": int(r[0]),
                "source": r[1],
                "list_version": r[2],
                "confidence": float(r[3]),
            }
            for r in self.session.cursor.fetchall()
        ]
        poison = detect_address_poisoning(address, poisoning_targets or [])
        sanctioned = len(hits) > 0
        risk = 100 if sanctioned else (80 if poison["poisoning_suspected"] else 0)
        return {
            "status": "completed",
            "job_id": "screen_address",
            "artifacts": [
                {
                    "address_pseudonym": pseudo,
                    "sanctioned": sanctioned,
                    "watch_hits": hits,
                    "poisoning": poison,
                    "risk_score": risk,
                    "category": "HIGH_RISK"
                    if risk >= 70
                    else "LOW_RISK",
                }
            ],
            "error": None,
            "logs": [],
        }


class RelayerHealthAdapter:
    """Bridge relayer throughput/drop — FeatureExtractor / Learning."""

    def __init__(self, session: ThreatEngineSession, logger: Optional[JSONLogger] = None):
        self.session = session
        self.logger = logger or JSONLogger("RelayerHealthAdapter")

    def record_health(
        self,
        *,
        relayer_name: str,
        chain_id: int,
        asset_symbol: str,
        throughput_rate: float,
        drop_rate: float,
        censorship_detected: bool = False,
        observed_by_user_id: Optional[str] = None,
    ) -> dict:
        return _safe_call(
            self.logger,
            "record_health",
            self._record_health,
            relayer_name,
            chain_id,
            asset_symbol,
            throughput_rate,
            drop_rate,
            censorship_detected,
            observed_by_user_id,
        )

    def _record_health(
        self,
        relayer_name: str,
        chain_id: int,
        asset_symbol: str,
        throughput_rate: float,
        drop_rate: float,
        censorship_detected: bool,
        observed_by_user_id: Optional[str],
    ) -> dict:
        # Heuristic: drop dominates throughput → flag
        if drop_rate > 0 and drop_rate >= max(throughput_rate, 0.01) * 0.5:
            censorship_detected = True
        self.session.execute(
            """
            INSERT INTO wave28_relayer_health (
                relayer_name, chain_id, asset_symbol,
                throughput_rate, drop_rate, censorship_detected, observed_by_user_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING health_id, observed_at, censorship_detected
            """,
            (
                relayer_name,
                chain_id,
                asset_symbol,
                throughput_rate,
                drop_rate,
                censorship_detected,
                observed_by_user_id,
            ),
        )
        row = self.session.cursor.fetchone()
        return {
            "status": "completed",
            "job_id": "record_health",
            "artifacts": [
                {
                    "health_id": int(row[0]),
                    "observed_at": row[1].isoformat()
                    if hasattr(row[1], "isoformat")
                    else str(row[1]),
                    "censorship_detected": bool(row[2]),
                    "relayer_name": relayer_name,
                    "asset_symbol": asset_symbol,
                }
            ],
            "error": None,
            "logs": [],
        }

    def latest_flags(self, *, limit: int = 20) -> dict:
        return _safe_call(self.logger, "latest_flags", self._latest_flags, limit)

    def _latest_flags(self, limit: int) -> dict:
        self.session.execute(
            """
            SELECT health_id, relayer_name, asset_symbol, drop_rate, throughput_rate, observed_at
              FROM wave28_relayer_health
             WHERE censorship_detected = TRUE
             ORDER BY observed_at DESC
             LIMIT %s
            """,
            (limit,),
        )
        rows = self.session.cursor.fetchall()
        return {
            "status": "completed",
            "job_id": "latest_flags",
            "artifacts": [
                {
                    "health_id": int(r[0]),
                    "relayer_name": r[1],
                    "asset_symbol": r[2],
                    "drop_rate": float(r[3] or 0),
                    "throughput_rate": float(r[4] or 0),
                    "observed_at": r[5].isoformat()
                    if hasattr(r[5], "isoformat")
                    else str(r[5]),
                }
                for r in rows
            ],
            "error": None,
            "logs": [],
        }


class CensorshipBypassAdapter:
    """Routing + incident log — ActiveResponseCoordinator / CensorshipBypassRouter."""

    def __init__(self, session: ThreatEngineSession, logger: Optional[JSONLogger] = None):
        self.session = session
        self.logger = logger or JSONLogger("CensorshipBypassAdapter")

    def recommend_route(
        self,
        *,
        censorship_type: str,
        asset_symbol: Optional[str] = None,
        preferred_relayer: Optional[str] = None,
    ) -> dict:
        fallback_asset = ASSET_FALLBACKS.get((asset_symbol or "").upper())
        route = {
            "censorship_type": censorship_type,
            "rpc_fallback": "private_or_self_hosted"
            if censorship_type in ("RPC_BLOCK", "BUILDER_FILTER")
            else None,
            "builder_fallback": "non_ofac_restrictive"
            if censorship_type == "BUILDER_FILTER"
            else None,
            "relayer_fallback": "alternate_attester"
            if censorship_type == "RELAYER_DROP"
            else preferred_relayer,
            "asset_fallback": fallback_asset
            if censorship_type == "STABLECOIN_FREEZE"
            else None,
            "defensive_only": True,
        }
        return {
            "status": "completed",
            "job_id": "recommend_route",
            "artifacts": [route],
            "error": None,
            "logs": [],
        }

    def record_incident(
        self,
        *,
        censorship_type: str,
        agent_x_signal_status: str,
        block_cause: Optional[str] = None,
        watch_id: Optional[int] = None,
        relayer_name: Optional[str] = None,
        route_fallback: Optional[str] = None,
        gatekeeper_job_id: Optional[str] = None,
        observed_by_user_id: Optional[str] = None,
    ) -> dict:
        return _safe_call(
            self.logger,
            "record_incident",
            self._record_incident,
            censorship_type,
            agent_x_signal_status,
            block_cause,
            watch_id,
            relayer_name,
            route_fallback,
            gatekeeper_job_id,
            observed_by_user_id,
        )

    def _record_incident(
        self,
        censorship_type: str,
        agent_x_signal_status: str,
        block_cause: Optional[str],
        watch_id: Optional[int],
        relayer_name: Optional[str],
        route_fallback: Optional[str],
        gatekeeper_job_id: Optional[str],
        observed_by_user_id: Optional[str],
    ) -> dict:
        if agent_x_signal_status == "BLOCKED":
            block_cause = block_cause or BLOCK_CAUSE_CENSORSHIP
            if not str(block_cause).strip():
                raise ValueError("BLOCKED requires block_cause")
        self.session.execute(
            """
            INSERT INTO wave28_censorship_incidents (
                watch_id, relayer_name, censorship_type,
                agent_x_signal_status, block_cause, route_fallback,
                gatekeeper_job_id, observed_by_user_id
            ) VALUES (%s, %s, %s, %s::agent_signal_status, %s, %s, %s, %s)
            RETURNING incident_id, logged_at
            """,
            (
                watch_id,
                relayer_name,
                censorship_type,
                agent_x_signal_status,
                block_cause,
                route_fallback,
                gatekeeper_job_id,
                observed_by_user_id,
            ),
        )
        row = self.session.cursor.fetchone()
        return {
            "status": "completed",
            "job_id": "record_incident",
            "artifacts": [
                {
                    "incident_id": int(row[0]),
                    "block_cause": block_cause,
                    "agent_x_signal_status": agent_x_signal_status,
                    "logged_at": row[1].isoformat()
                    if hasattr(row[1], "isoformat")
                    else str(row[1]),
                }
            ],
            "error": None,
            "logs": [],
        }
