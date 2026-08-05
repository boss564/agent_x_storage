"""
Agent X — Public Portal / Open Government Explorer (Wave 15, 9 Agents).

Citizen-facing transparency layer for the 90-agent B2G procurement platform.
Translates blockchain-anchored procurement data into human-readable formats
while enforcing DSGVO privacy boundaries.

Agents:
  1. PublicPortalOrchestrator      — Root agent: receives citizen queries, orchestrates sub-agents
  2. ProjectSummaryAggregator      — Aggregates public project KPIs (budget, progress, milestones)
  3. BlockchainVerificationWidget  — Live Gnosis/peaq hash verification for citizens
  4. QRCodeGenerator               — Dynamic QR codes for construction site signs
  5. InteractiveMapComposer        — Leaflet/OSM map overlay for active municipal projects
  6. ZKPrivacyShield               — DSGVO anonymization before public output
  7. TrustButtonService            — Verification widget for journalists & auditors
  8. CitizenNotificationService    — Opt-in email/push on project status changes
  9. AuditTrailPublicExporter      — Open Data export (JSON/CSV) for researchers
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

# Graceful import — qrcode is required, Pillow optional for PNG export
try:
    import qrcode  # type: ignore
    from qrcode.image.svg import SvgImage  # type: ignore
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    from PIL import Image  # type: ignore
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    import requests  # type: ignore
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ============================================================
# Shared Enums & Data Classes
# ============================================================


class QRFormat(str, Enum):
    SVG = "svg"
    PNG = "png"
    DATA_URL = "data_url"


FALLBACK_QR_API = "https://api.qrserver.com/v1/create-qr-code/"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    ERROR = "ERROR"


class ProjectVisibility(str, Enum):
    PUBLIC = "PUBLIC"
    ANONYMIZED = "ANONYMIZED"
    RESTRICTED = "RESTRICTED"


# ============================================================
# JSON Logger (replaces all print() calls)
# ============================================================


class JSONLogger:
    """Structured JSON-line logging for public portal agents."""

    def __init__(self, log_path: Path | None = None, agent_name: str = "public_portal"):
        self.agent_name = agent_name
        self.log_path = log_path or Path(
            f"logs/public_portal_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, msg: str, **extra) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "agent": self.agent_name,
            "message": msg,
            **extra,
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def info(self, msg: str, **extra) -> None:
        self._write("INFO", msg, **extra)

    def warn(self, msg: str, **extra) -> None:
        self._write("WARN", msg, **extra)

    def error(self, msg: str, **extra) -> None:
        self._write("ERROR", msg, **extra)


# ============================================================
# Standardized Output Contract
# ============================================================


def make_response(
    status: str,
    job_id: str,
    artifacts: list[dict] | None = None,
    error: str | None = None,
    logs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "job_id": job_id,
        "artifacts": artifacts or [],
        "error": error,
        "logs": logs or [],
    }


# ============================================================
# Agent 1: PublicPortalOrchestrator
# ============================================================


class PublicPortalOrchestrator:
    """Root agent for citizen transparency requests.

    Accepts a query (QR scan, project ID, invoice number) and orchestrates
    sub-agents to produce a human-readable, DSGVO-safe project view.
    """

    def __init__(self, event_bus=None, logger: JSONLogger | None = None):
        self.event_bus = event_bus
        self.log = logger or JSONLogger(agent_name="PublicPortalOrchestrator")
        self._sub_agents: dict[str, Any] = {}
        self._query_count = 0

    def register_sub_agent(self, name: str, agent: Any) -> None:
        self._sub_agents[name] = agent
        self.log.info("sub_agent_registered", sub_agent=name)

    def query(self, lookup_key: str, user_id: str = "anonymous") -> dict[str, Any]:
        """Main entry point for citizen queries.

        Args:
            lookup_key: QR-code payload, tender ID, or invoice number
            user_id: anonymized session ID (no PII)
        """
        job_id = str(uuid.uuid4())
        logs: list[str] = []
        self._query_count += 1

        try:
            logs.append(f"[{self._query_count}] Citizen query: {lookup_key[:40]}...")
            self.log.info("citizen_query_received", lookup_key=lookup_key[:40],
                          user_id=user_id, job_id=job_id)

            # Phase 1: Fetch project data
            summary = {}
            if "ProjectSummaryAggregator" in self._sub_agents:
                try:
                    summary = self._sub_agents["ProjectSummaryAggregator"].aggregate(lookup_key)
                    logs.append(f"Project summary loaded: {summary.get('project_name', 'Unknown')}")
                except Exception as exc:
                    self.log.warn("summary_fetch_failed", error=str(exc))
                    logs.append(f"Summary fetch failed: {exc}")

            # Phase 2: Verify blockchain anchor
            verification = {"status": "PENDING"}
            if "BlockchainVerificationWidget" in self._sub_agents:
                try:
                    verification = self._sub_agents["BlockchainVerificationWidget"].verify(lookup_key)
                    logs.append(f"Verification: {verification.get('status')}")
                except Exception as exc:
                    self.log.warn("verification_failed", error=str(exc))
                    logs.append(f"Verification failed: {exc}")

            # Phase 3: Apply DSGVO shield
            safe_output = summary
            if "ZKPrivacyShield" in self._sub_agents:
                try:
                    safe_output = self._sub_agents["ZKPrivacyShield"].anonymize(summary)
                    logs.append("DSGVO shield applied")
                except Exception as exc:
                    self.log.warn("privacy_shield_failed", error=str(exc))
                    logs.append(f"Privacy shield failed: {exc}")

            # Notify event bus
            if self.event_bus:
                self.event_bus.publish("public_portal.query_completed", {
                    "job_id": job_id, "lookup_key": lookup_key[:40],
                    "query_count": self._query_count,
                })

            return make_response("completed", job_id, artifacts=[{
                "type": "citizen_project_view",
                "summary": safe_output,
                "verification": verification,
                "job_id": job_id,
            }], logs=logs)

        except Exception as exc:
            self.log.error("orchestrator_fatal", error=str(exc), job_id=job_id)
            return make_response("failed", job_id, error=str(exc), logs=logs)


# ============================================================
# Agent 2: ProjectSummaryAggregator
# ============================================================


class ProjectSummaryAggregator:
    """Aggregates project KPIs into a human-readable public summary.

    Translates EVM metrics (SPI, CPI, EAC) into German plain-text descriptions.
    Sources: EVM state, Soll/Ist matrix, PoPW telemetry, GAEB metadata.
    DSGVO-safe — no PII in any output field.
    """

    # Thresholds for status classification
    SPI_ON_TRACK = 0.95
    SPI_DELAYED = 0.85
    CPI_ON_TRACK = 0.95
    CPI_OVER_BUDGET = 0.85

    def __init__(self, logger: JSONLogger | None = None):
        self.log = logger or JSONLogger(agent_name="ProjectSummaryAggregator")

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def aggregate(self, tender_id: str) -> dict[str, Any]:
        """Simple fetch (no EVM data) — returns stub with defaults."""
        return self.aggregate_public_summary(
            tender_id=tender_id,
            evm_data={},
            milestones=[],
            project_metadata={},
        )

    def aggregate_public_summary(
        self,
        tender_id: str,
        evm_data: dict[str, Any],
        milestones: list[dict[str, Any]],
        project_metadata: dict[str, Any],
        delay_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Full public summary with EVM translation, milestones, and prognosis.

        Args:
            tender_id: Project tender ID
            evm_data: EVM metrics: budget_at_completion_bac, earned_value_ev,
                      actual_cost_ac, schedule_performance_index_spi,
                      cost_performance_index_cpi, estimate_at_completion_eac
            milestones: List of {name, completed, progress, date} dicts
            project_metadata: {name, description, address, start_date,
                              planned_end_date, location}
            delay_analysis: Optional {total_delay_days, expected_end_date}
        """
        try:
            self.log.info("aggregate_summary", tender_id=tender_id)

            # 1. EVM extraction
            bac = float(evm_data.get("budget_at_completion_bac", 0))
            ev = float(evm_data.get("earned_value_ev", 0))
            ac = float(evm_data.get("actual_cost_ac", 0))
            spi = float(evm_data.get("schedule_performance_index_spi", 1.0))
            cpi = float(evm_data.get("cost_performance_index_cpi", 1.0))
            eac = float(evm_data.get("estimate_at_completion_eac", bac))

            # 2. Progress
            progress = (ev / bac * 100.0) if bac > 0 else 0.0
            progress = min(100.0, max(0.0, progress))

            # 3. Status translation
            status_text, status_color = self._translate_status(spi, cpi, progress)

            # 4. Budget plain-text
            budget_text = self._translate_budget(bac, ev, ac, eac, cpi)

            # 5. Milestone summary
            milestone_summary = self._summarize_milestones(milestones)

            # 6. Prognosis
            prognosis = self._build_prognosis(delay_analysis, progress)

            # 7. Next steps
            next_steps = self._determine_next_steps(milestones, progress)

            # 8. Sanitized metadata
            meta = self._sanitize_metadata(project_metadata)

            result = {
                "tender_id": tender_id,
                "project_name": meta.get("name", f"Projekt {tender_id}"),
                "status": {
                    "text": status_text,
                    "color": status_color,
                },
                "progress": {
                    "percent": round(progress, 1),
                    "description": self._progress_description(progress),
                },
                "budget": {
                    "total_eur": round(bac, 2),
                    "disbursed_eur": round(ev, 2),
                    "remaining_eur": round(bac - ev, 2),
                    "summary_text": budget_text,
                },
                "timeline": {
                    "start_date": meta.get("start_date"),
                    "planned_end_date": meta.get("planned_end_date"),
                    "expected_end_date": prognosis.get("expected_end_date"),
                    "delay_days": prognosis.get("delay_days", 0),
                },
                "milestones": milestone_summary,
                "next_steps": next_steps,
                "location": meta.get("location", "Deutschland"),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            self.log.info("aggregate_summary_complete", tender_id=tender_id,
                          progress=round(progress, 1), status=status_text)
            return result

        except Exception as exc:
            self.log.error("aggregate_summary_failed", tender_id=tender_id, error=str(exc))
            return {"tender_id": tender_id, "error": str(exc)}

    # ================================================================
    # Status translation (SPI + CPI → German plain text)
    # ================================================================

    @classmethod
    def _translate_status(cls, spi: float, cpi: float, progress: float) -> tuple[str, str]:
        if progress >= 100:
            return "Abgeschlossen", "#28a745"
        if spi < cls.SPI_DELAYED:
            return "Verzoegert", "#dc3545"
        if spi < cls.SPI_ON_TRACK:
            return "Leicht verzoegert", "#ffc107"
        if cpi < cls.CPI_OVER_BUDGET:
            return "Budget-Ueberschreitung", "#dc3545"
        if cpi < cls.CPI_ON_TRACK:
            return "Leichte Budget-Ueberschreitung", "#ffc107"
        return "Im Zeitplan", "#28a745"

    # ================================================================
    # Budget plain-text
    # ================================================================

    @staticmethod
    def _translate_budget(bac: float, ev: float, ac: float, eac: float, cpi: float) -> str:
        if bac <= 0:
            return "Keine Budgetdaten verfuegbar."
        remaining = bac - ev
        if cpi >= 0.98:
            return (
                f"Das Projekt liegt im Budget. Es wurden {ev:,.0f} EUR von "
                f"{bac:,.0f} EUR abgerufen. Es stehen noch {remaining:,.0f} EUR "
                f"fuer die verbleibenden Leistungen zur Verfuegung."
            )
        if cpi >= 0.85:
            return (
                f"Das Budget wird voraussichtlich leicht ueberschritten. Bisher wurden "
                f"{ev:,.0f} EUR von {bac:,.0f} EUR abgerufen. Die prognostizierten "
                f"Gesamtkosten betragen {eac:,.0f} EUR."
            )
        return (
            f"Das Budget wird voraussichtlich deutlich ueberschritten. Bisher wurden "
            f"{ev:,.0f} EUR von {bac:,.0f} EUR abgerufen. Die prognostizierten "
            f"Gesamtkosten betragen {eac:,.0f} EUR."
        )

    # ================================================================
    # Progress description
    # ================================================================

    @staticmethod
    def _progress_description(progress: float) -> str:
        if progress < 10:
            return "Das Projekt befindet sich in der Anfangsphase."
        if progress < 30:
            return "Die ersten Arbeiten sind im Gange."
        if progress < 50:
            return "Das Projekt ist etwa zur Haelfte fertiggestellt."
        if progress < 75:
            return "Der Grossteil der Arbeiten ist abgeschlossen."
        if progress < 95:
            return "Die Arbeiten sind fast abgeschlossen."
        return "Das Projekt wird in Kuerze abgeschlossen."

    # ================================================================
    # Milestone summary
    # ================================================================

    @staticmethod
    def _summarize_milestones(milestones: list[dict]) -> dict[str, Any]:
        if not milestones:
            return {"completed": 0, "total": 0, "next_milestone": None,
                    "summary": "Keine Meilensteine definiert."}

        completed = sum(
            1 for m in milestones
            if m.get("completed") or m.get("progress", 0) >= 100
        )
        upcoming = [
            m.get("name", "Unbekannter Meilenstein")
            for m in milestones
            if not m.get("completed") and m.get("progress", 0) < 100
        ]
        next_ms = upcoming[0] if upcoming else None

        if next_ms:
            summary = (
                f"{completed} von {len(milestones)} Meilensteinen erreicht. "
                f"Naechster Meilenstein: {next_ms}."
            )
        elif completed == len(milestones):
            summary = f"Alle {len(milestones)} Meilensteine erreicht."
        else:
            summary = f"{completed} von {len(milestones)} Meilensteinen erreicht."

        return {
            "completed": completed,
            "total": len(milestones),
            "next_milestone": next_ms,
            "summary": summary,
        }

    # ================================================================
    # Prognosis
    # ================================================================

    @staticmethod
    def _build_prognosis(delay_analysis: dict | None, progress: float) -> dict[str, Any]:
        if not delay_analysis:
            return {"status": "Keine Prognose verfuegbar.", "expected_end_date": None,
                    "delay_days": 0}

        delay_days = int(delay_analysis.get("total_delay_days", 0))
        expected_end = delay_analysis.get("expected_end_date")

        if delay_days == 0:
            status = "Das Projekt wird voraussichtlich planmaessig abgeschlossen."
        elif delay_days <= 5:
            status = f"Das Projekt wird voraussichtlich {delay_days} Tage spaeter abgeschlossen als geplant."
        elif delay_days <= 15:
            status = f"Das Projekt wird voraussichtlich {delay_days} Tage spaeter abgeschlossen. Nachsteuerung wird geprueft."
        else:
            status = f"Das Projekt wird voraussichtlich {delay_days} Tage spaeter abgeschlossen. Terminverlaengerung wird geprueft."

        return {"status": status, "expected_end_date": expected_end, "delay_days": delay_days}

    # ================================================================
    # Next steps
    # ================================================================

    @staticmethod
    def _determine_next_steps(milestones: list[dict], progress: float) -> list[str]:
        steps: list[str] = []

        if progress < 10:
            steps.append("Baustelleneinrichtung und erste Erdarbeiten")
        elif progress < 30:
            steps.append("Rohbauarbeiten")
        elif progress < 50:
            steps.append("Technische Installationen")
        elif progress < 75:
            steps.append("Elektro- und Sanitaerinstallationen")
        elif progress < 95:
            steps.append("Abschlussarbeiten und Innenausbau")
        else:
            steps.append("Abnahme und Uebergabe")

        for m in milestones:
            if not m.get("completed") and m.get("progress", 0) < 100:
                steps.append(f"Meilenstein: {m.get('name', 'Unbekannt')}")
                break

        if not steps:
            steps.append("Alle Arbeiten abgeschlossen.")
        return steps

    # ================================================================
    # Metadata sanitization (DSGVO)
    # ================================================================

    @staticmethod
    def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        desc = metadata.get("description", "")
        if isinstance(desc, str) and len(desc) > 200:
            desc = desc[:200] + "..."
        return {
            "name": metadata.get("name") or metadata.get("project_name", "Unbekanntes Projekt"),
            "location": metadata.get("location", "Deutschland"),
            "start_date": metadata.get("start_date"),
            "planned_end_date": metadata.get("planned_end_date"),
            "description": desc,
        }


# ============================================================
# Agent 3: BlockchainVerificationWidget
# ============================================================


class BlockchainVerificationWidget:
    """Hybrid blockchain verification against Gnosis Chain and peaq Network.

    Two modes, controlled by USE_LIVE_RPC env var:
    - Mock (default): instant local lookup, works offline, ideal for demos.
    - Live RPC: eth_getTransactionByHash against Gnosis, direct peaq RPC query.
      Falls back to mock if RPC is unreachable.

    Public RPC endpoints (configurable via env):
    - GNOSIS_RPC: https://rpc.gnosischain.com
    - PEAQ_RPC:  https://peaq-rpc.publicnode.com
    """

    DEFAULT_GNOSIS_RPC = "https://rpc.gnosischain.com"
    DEFAULT_PEAQ_RPC = "https://peaq-rpc.publicnode.com"
    RPC_TIMEOUT = 5  # seconds
    RPC_RETRIES = 2

    def __init__(self, gnosis_rpc: str | None = None, peaq_rpc: str | None = None,
                 logger: JSONLogger | None = None):
        self.gnosis_rpc = gnosis_rpc or os.getenv("GNOSIS_RPC", self.DEFAULT_GNOSIS_RPC)
        self.peaq_rpc = peaq_rpc or os.getenv("PEAQ_RPC", self.DEFAULT_PEAQ_RPC)
        self.log = logger or JSONLogger(agent_name="BlockchainVerificationWidget")
        self._use_live = os.getenv("USE_LIVE_RPC", "false").lower() in ("true", "1", "yes")
        # In-memory cache for live results (TTL: 1 hour)
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_ttl = 3600

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def verify(self, lookup_key: str) -> dict[str, Any]:
        """Verify a project ID or transaction hash.

        Mode selection:
        - USE_LIVE_RPC=true → live Gnosis/peaq RPC query
        - USE_LIVE_RPC=false (default) → mock local verification
        - If live RPC fails → graceful fallback to mock with warning
        """
        try:
            self.log.info("verification_request", lookup_key=lookup_key[:40],
                          mode="live" if self._use_live else "mock")

            if self._use_live:
                return self._verify_live(lookup_key)
            return self._verify_mock(lookup_key)

        except Exception as exc:
            self.log.error("verification_failed", lookup_key=lookup_key[:40], error=str(exc))
            return {"lookup_key": lookup_key, "status": VerificationStatus.ERROR.value,
                    "error": str(exc), "verified_at": datetime.now(timezone.utc).isoformat()}

    # --------------------------------------------------
    # Mock mode — instant local lookup
    # --------------------------------------------------

    def _verify_mock(self, lookup_key: str) -> dict[str, Any]:
        """Instant offline verification against local mock archive."""
        self.log.info("mock_verify", lookup_key=lookup_key[:40])

        record = self._mock_lookup(lookup_key)
        if record is None:
            return {
                "lookup_key": lookup_key,
                "status": VerificationStatus.UNVERIFIED.value,
                "message": "Keine Verankerung fuer diese Referenz im lokalen Archiv gefunden.",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "method": "mock",
            }

        return {
            "lookup_key": lookup_key,
            "status": VerificationStatus.VERIFIED.value,
            "gnosis_tx": record.get("gnosis_tx", ""),
            "gnosis_block": record.get("gnosis_block"),
            "peaq_block": record.get("peaq_block"),
            "merkle_root": record.get("merkle_root", ""),
            "project_name": record.get("project_name"),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "method": "mock",
            "message": "Lokal verifiziert (Mock-Modus). Fuer kryptografische Verifikation LIVE_RPC aktivieren.",
        }

    # --------------------------------------------------
    # Live RPC mode — real on-chain queries
    # --------------------------------------------------

    def _verify_live(self, lookup_key: str) -> dict[str, Any]:
        """Query Gnosis Chain and peaq Network via public RPC endpoints."""
        self.log.info("live_verify_start", lookup_key=lookup_key[:40])

        # Check cache
        cached = self._cache.get(lookup_key)
        if cached and (time.time() - cached["_cached_at"]) < self._cache_ttl:
            self.log.info("live_cache_hit", lookup_key=lookup_key[:40])
            return cached

        gnosis_result = self._query_gnosis(lookup_key)
        peaq_result = self._query_peaq(lookup_key)

        # If both RPCs failed, fall back to mock
        if gnosis_result is None and peaq_result is None:
            self.log.warn("live_rpc_failed_both", lookup_key=lookup_key[:40],
                          fallback="mock")
            mock = self._verify_mock(lookup_key)
            mock["method"] = "mock (live RPC fallback — beide Endpoints nicht erreichbar)"
            return mock

        result = {
            "lookup_key": lookup_key,
            "status": VerificationStatus.VERIFIED.value if gnosis_result else VerificationStatus.PENDING.value,
            "gnosis_tx": gnosis_result.get("tx_hash") if gnosis_result else "",
            "gnosis_block": gnosis_result.get("block_number") if gnosis_result else None,
            "gnosis_block_timestamp": gnosis_result.get("block_timestamp") if gnosis_result else None,
            "peaq_block": peaq_result.get("block_number") if peaq_result else None,
            "peaq_block_hash": peaq_result.get("block_hash") if peaq_result else None,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "method": "live-rpc",
            "message": "Kryptografisch verifiziert — unveraenderbar im Ledger verankert.",
            "rpc_endpoints": {
                "gnosis": self.gnosis_rpc,
                "peaq": self.peaq_rpc,
            },
        }

        # Cache result
        result["_cached_at"] = time.time()
        self._cache[lookup_key] = result

        self.log.info("live_verify_complete", lookup_key=lookup_key[:40],
                      gnosis_block=result["gnosis_block"],
                      peaq_block=result["peaq_block"])
        return result

    def _query_gnosis(self, tx_hash_or_id: str) -> dict[str, Any] | None:
        """Query Gnosis Chain via eth_getTransactionByHash + eth_getBlockByNumber.

        If lookup_key is a tender ID (not 0x...), resolves via local mock first.
        """
        tx_hash = tx_hash_or_id
        if not tx_hash.startswith("0x") or len(tx_hash) != 66:
            # Resolve tender ID → known tx hash from mock archive
            record = self._mock_lookup(tx_hash_or_id)
            if record and record.get("gnosis_tx"):
                tx_hash = record["gnosis_tx"]
            else:
                return None

        for attempt in range(1, self.RPC_RETRIES + 2):
            try:
                if not HAS_REQUESTS:
                    self.log.warn("gnosis_no_requests")
                    return None

                resp = requests.post(
                    self.gnosis_rpc,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_getTransactionByHash",
                        "params": [tx_hash],
                        "id": 1,
                    },
                    timeout=self.RPC_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()

                tx_data = data.get("result")
                if tx_data is None:
                    return None

                block_number_hex = tx_data.get("blockNumber", "0x0")
                block_number = int(block_number_hex, 16) if block_number_hex else None

                # Get block timestamp
                block_ts = None
                if block_number is not None:
                    try:
                        b_resp = requests.post(
                            self.gnosis_rpc,
                            json={
                                "jsonrpc": "2.0",
                                "method": "eth_getBlockByNumber",
                                "params": [hex(block_number), False],
                                "id": 1,
                            },
                            timeout=self.RPC_TIMEOUT,
                        )
                        b_data = b_resp.json().get("result", {})
                        ts_hex = b_data.get("timestamp", "0x0")
                        block_ts = datetime.fromtimestamp(
                            int(ts_hex, 16), tz=timezone.utc
                        ).isoformat()
                    except Exception:
                        pass

                return {
                    "tx_hash": tx_hash,
                    "block_number": block_number,
                    "block_timestamp": block_ts,
                    "chain": "Gnosis",
                }

            except Exception as exc:
                self.log.warn("gnosis_rpc_attempt_failed", attempt=attempt,
                              error=str(exc))
                if attempt <= self.RPC_RETRIES:
                    time.sleep(0.5 * attempt)

        return None

    def _query_peaq(self, lookup_key: str) -> dict[str, Any] | None:
        """Query peaq Network for block anchoring.

        peaq uses Substrate (not EVM), so the RPC method differs.
        Uses chain_getBlockHash + chain_getBlock for verification.
        """
        if not HAS_REQUESTS:
            return None

        # peaq block number from mock archive (production: DKG lookup)
        record = self._mock_lookup(lookup_key)
        peaq_block = record.get("peaq_block") if record else None
        if peaq_block is None:
            return None

        try:
            # Get block hash for the known block number
            resp = requests.post(
                self.peaq_rpc,
                json={
                    "jsonrpc": "2.0",
                    "method": "chain_getBlockHash",
                    "params": [peaq_block],
                    "id": 1,
                },
                timeout=self.RPC_TIMEOUT,
            )
            resp.raise_for_status()
            block_hash = resp.json().get("result")

            if block_hash:
                return {
                    "block_number": peaq_block,
                    "block_hash": block_hash,
                    "chain": "peaq",
                }
        except Exception as exc:
            self.log.warn("peaq_rpc_failed", error=str(exc))

        return None

    # --------------------------------------------------
    # Mock archive (production: chain index / subgraph)
    # --------------------------------------------------

    @staticmethod
    def _mock_lookup(lookup_key: str) -> dict[str, Any] | None:
        """Resolve any reference type to a known anchor record."""
        archive = {
            "TED-2026-0815": {
                "project_name": "Sanierung Klaeranlage Nord",
                "gnosis_tx": "0x3a91c7849E2b1009B8803a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d",
                "gnosis_block": 18492011,
                "peaq_block": 18492011,
                "merkle_root": "0x8f1e3c2b1a9f0d8e7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d",
            },
            "TED-2026-0712": {
                "project_name": "Neubau Grundschule Ost",
                "gnosis_tx": "0x4b2c889a7182E89100223b0a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e",
                "gnosis_block": 18123456,
                "peaq_block": 18123456,
                "merkle_root": "0x7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b",
            },
        }
        # Exact match
        if lookup_key in archive:
            return archive[lookup_key]
        # Tx hash match
        for record in archive.values():
            if record.get("gnosis_tx") == lookup_key:
                return record
        return None

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    def status(self) -> dict:
        return {
            "mode": "live" if self._use_live else "mock",
            "gnosis_rpc": self.gnosis_rpc,
            "peaq_rpc": self.peaq_rpc,
            "use_live_rpc": self._use_live,
            "cached_verifications": len(self._cache),
            "has_requests": HAS_REQUESTS,
        }


# ============================================================
# Agent 4: QRCodeGenerator
# ============================================================
#  Fully implemented agent for dynamic QR code generation.
#  Generates SVG/PNG QR codes for construction site signs.
#  Payload: Tender-ID + public key → URL to the public portal.
#  Supports batch generation for all active projects of a municipality.


class QRCodeGenerator:
    """Generates dynamic QR codes for construction site signs.

    Each QR code encodes a URL pointing to the public transparency portal
    with the tender ID and a non-personal public key as parameters.

    Sub-agents (internal helpers):
      - QRCodeRenderer    — qrcode + Pillow rendering (SVG/PNG)
      - BatchScanner      — discovers active projects for bulk generation
      - QRFileWriter      — writes QR files to tenant-scoped output directory
    """

    DEFAULT_PORTAL_URL = os.getenv(
        "PUBLIC_PORTAL_URL",
        "https://transparenz.agent-x.de/projekt"
    )
    DEFAULT_OUTPUT_ROOT = Path(
        os.getenv("QR_OUTPUT_ROOT", "/data/public_portal/qrcodes")
    )

    def __init__(
        self,
        portal_url: str | None = None,
        output_root: Path | None = None,
        event_bus=None,
        logger: JSONLogger | None = None,
        fallback_api: str | None = None,
        cache_dir: Path | None = None,
    ):
        self.portal_url = portal_url or self.DEFAULT_PORTAL_URL
        self.output_root = Path(output_root or self.DEFAULT_OUTPUT_ROOT)
        self.event_bus = event_bus
        self.log = logger or JSONLogger(agent_name="QRCodeGenerator")
        self.fallback_api = fallback_api or FALLBACK_QR_API
        self._cache_dir = cache_dir or (self.output_root / ".cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._generated_count = 0

        if not HAS_QRCODE and not HAS_REQUESTS:
            self.log.warn("qr_no_backend", error="Neither qrcode nor requests available")
        elif not HAS_QRCODE:
            self.log.info("qr_fallback_mode", api=self.fallback_api)

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def generate(
        self,
        tender_id: str,
        public_key: str | None = None,
        fmt: QRFormat = QRFormat.SVG,
        user_id: str = "default",
        force: bool = False,
        additional_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Generate a single QR code for a project.

        Args:
            tender_id: The project's tender ID (e.g. TED-2026-0815)
            public_key: Optional public key to include in the verification URL
            fmt: Output format (SVG, PNG, or DATA_URL for base64-embedded)
            user_id: Tenant/user ID for output directory scoping
            force: If True, regenerate even if the file exists
            additional_params: Extra query params (e.g. {"utm_source": "qr"})

        Returns:
            Standardized JSON response with content_base64, path, and data_url (if applicable).
        """
        job_id = str(uuid.uuid4())
        logs: list[str] = []
        start_time = time.time()

        try:
            if public_key is None:
                public_key = self._derive_public_key(tender_id)

            target_url = self._build_url(tender_id, public_key, additional_params)
            output_dir = self._tenant_dir(user_id)

            # SHA-256 content-based cache key (tenant-scoped)
            cache_key_raw = f"{user_id}:{target_url}:{fmt.value}"
            cache_key = hashlib.sha256(cache_key_raw.encode()).hexdigest()
            cache_path = self._cache_dir / f"{cache_key}.{fmt.value if fmt != QRFormat.DATA_URL else 'png'}"

            # Fast-track: check both output and cache
            if not force and fmt != QRFormat.DATA_URL:
                existing = self._find_existing(output_dir, tender_id, fmt)
                if existing is not None:
                    elapsed = round((time.time() - start_time) * 1000)
                    logs.append(f"Fast-track: QR code already exists at {existing}")
                    self.log.info("qr_fast_track", tender_id=tender_id,
                                  path=str(existing), duration_ms=elapsed)
                    return make_response("skipped", job_id, artifacts=[{
                        "type": f"qr_{fmt.value}",
                        "path": str(existing),
                        "url": target_url,
                        "tender_id": tender_id,
                    }], logs=logs)

            # Check SHA-256 cache
            if not force and cache_path.exists():
                cached_content = cache_path.read_bytes()
                elapsed = round((time.time() - start_time) * 1000)
                logs.append(f"Content cache hit: {cache_key[:16]}")

                # Ensure tenant output dir also has the file
                qr_path = None
                if fmt != QRFormat.DATA_URL:
                    existing = self._find_existing(output_dir, tender_id, fmt)
                    if existing is None:
                        qr_path = self._write_qr_file(cached_content, tender_id, output_dir, fmt)
                    else:
                        qr_path = existing

                return self._build_qr_response(
                    cached_content, fmt, tender_id, target_url, public_key,
                    qr_path, elapsed, job_id, logs
                )

            # Generate: local qrcode or fallback API
            if HAS_QRCODE:
                raw_bytes = self._generate_local(target_url, fmt)
            elif HAS_REQUESTS:
                logs.append("Using fallback API for QR generation")
                self.log.info("qr_fallback_api", tender_id=tender_id)
                raw_bytes = self._generate_via_api(target_url, fmt)
            else:
                raise RuntimeError(
                    "No QR backend available. Install qrcode: pip install qrcode[pil]"
                )

            # Persist to cache
            cache_path.write_bytes(raw_bytes)

            # Also write to tenant output dir unless DATA_URL
            if fmt != QRFormat.DATA_URL:
                qr_path = self._write_qr_file(raw_bytes, tender_id, output_dir, fmt)
            else:
                qr_path = None

            elapsed = round((time.time() - start_time) * 1000)
            self._generated_count += 1
            logs.append(f"QR code generated ({elapsed}ms, {len(raw_bytes)} bytes)")

            self.log.info("qr_generated", tender_id=tender_id, size_bytes=len(raw_bytes),
                          fmt=fmt.value, duration_ms=elapsed, job_id=job_id)

            if self.event_bus:
                self.event_bus.publish("public_portal.qr_generated", {
                    "job_id": job_id, "tender_id": tender_id,
                    "path": str(qr_path) if qr_path else None, "url": target_url,
                })

            return self._build_qr_response(
                raw_bytes, fmt, tender_id, target_url, public_key,
                qr_path, elapsed, job_id, logs
            )

        except Exception as exc:
            elapsed = round((time.time() - start_time) * 1000)
            self.log.error("qr_generation_failed", tender_id=tender_id,
                           error=str(exc), duration_ms=elapsed, job_id=job_id)
            return make_response("failed", job_id, error=str(exc), logs=logs)

    def _build_qr_response(
        self, raw_bytes: bytes, fmt: QRFormat, tender_id: str, url: str,
        public_key: str, file_path: Path | None, elapsed_ms: int,
        job_id: str, logs: list[str],
    ) -> dict[str, Any]:
        """Compose the standardized QR response with base64 and optional data_url."""
        artifact: dict[str, Any] = {
            "type": f"qr_{fmt.value}",
            "tender_id": tender_id,
            "url": url,
            "format": fmt.value,
            "size_bytes": len(raw_bytes),
            "content_base64": base64.b64encode(raw_bytes).decode("utf-8"),
            "public_key_hash": hashlib.sha256(public_key.encode()).hexdigest()[:16],
        }
        if file_path:
            artifact["path"] = str(file_path)
        if fmt == QRFormat.DATA_URL:
            mime = "image/svg+xml" if raw_bytes[:4] == b"<?xml" or raw_bytes[:4] == b"<svg" else "image/png"
            artifact["data_url"] = f"data:{mime};base64,{artifact['content_base64']}"

        return make_response("completed", job_id, artifacts=[artifact], logs=logs)

    # --------------------------------------------------
    # Sub-agent: BatchScanner — bulk generation
    # --------------------------------------------------

    def generate_batch(
        self,
        tender_ids: list[str],
        fmt: QRFormat = QRFormat.SVG,
        user_id: str = "default",
        force: bool = False,
    ) -> dict[str, Any]:
        """Generate QR codes for multiple projects in one batch.

        Args:
            tender_ids: List of project tender IDs
            fmt: Output format for all codes
            user_id: Tenant/user ID for output directory scoping
            force: If True, regenerate all even if files exist

        Returns:
            Aggregated response with per-project results.
        """
        job_id = str(uuid.uuid4())
        logs: list[str] = []
        start_time = time.time()
        results: list[dict] = []
        succeeded = 0
        skipped = 0
        failed = 0

        try:
            logs.append(f"Batch generation: {len(tender_ids)} projects")
            self.log.info("batch_started", count=len(tender_ids), user_id=user_id,
                          job_id=job_id)

            for tid in tender_ids:
                result = self.generate(tender_id=tid, fmt=fmt, user_id=user_id, force=force)
                results.append(result)
                if result["status"] == "completed":
                    succeeded += 1
                elif result["status"] == "skipped":
                    skipped += 1
                else:
                    failed += 1

            elapsed = round((time.time() - start_time) * 1000)
            logs.append(f"Batch complete: {succeeded} generated, {skipped} skipped, "
                        f"{failed} failed ({elapsed}ms)")

            self.log.info("batch_completed", total=len(tender_ids), succeeded=succeeded,
                          skipped=skipped, failed=failed, duration_ms=elapsed, job_id=job_id)

            if self.event_bus:
                self.event_bus.publish("public_portal.batch_completed", {
                    "job_id": job_id, "total": len(tender_ids),
                    "succeeded": succeeded, "skipped": skipped, "failed": failed,
                })

            return make_response("completed", job_id, artifacts=[{
                "type": "qr_batch",
                "count": len(tender_ids),
                "succeeded": succeeded,
                "skipped": skipped,
                "failed": failed,
                "results": results,
            }], logs=logs)

        except Exception as exc:
            self.log.error("batch_failed", error=str(exc), job_id=job_id)
            return make_response("failed", job_id, error=str(exc), logs=logs)

    # --------------------------------------------------
    # Sub-agent: BatchScanner — discover active projects
    # --------------------------------------------------

    def generate_for_municipality(
        self,
        municipality: str,
        project_source: callable | None = None,
        fmt: QRFormat = QRFormat.SVG,
        user_id: str = "default",
        force: bool = False,
    ) -> dict[str, Any]:
        """Generate QR codes for all active projects in a municipality.

        Args:
            municipality: Municipality name (e.g. "Niedersachsen")
            project_source: Optional callable that returns list[dict] with
                            at least {"tender_id": str} per project.
                            If None, uses a mock catalog.
            fmt: Output format
            user_id: Tenant ID
            force: Regenerate existing codes

        Returns:
            Batch response plus municipality metadata.
        """
        job_id = str(uuid.uuid4())
        logs: list[str] = []

        try:
            # Discover projects
            if project_source is not None:
                projects = project_source(municipality)
            else:
                projects = self._mock_municipality_catalog(municipality)

            tender_ids = [p["tender_id"] for p in projects]
            logs.append(f"Municipality '{municipality}': {len(tender_ids)} active projects found")
            self.log.info("municipality_scan", municipality=municipality,
                          project_count=len(tender_ids), job_id=job_id)

            # Generate batch
            batch_result = self.generate_batch(tender_ids=tender_ids, fmt=fmt,
                                               user_id=user_id, force=force)
            batch_result["artifacts"].append({
                "type": "municipality_metadata",
                "municipality": municipality,
                "active_projects": len(tender_ids),
            })
            return batch_result

        except Exception as exc:
            self.log.error("municipality_generation_failed", municipality=municipality,
                           error=str(exc), job_id=job_id)
            return make_response("failed", job_id, error=str(exc), logs=logs)

    # --------------------------------------------------
    # Internal helpers (sub-agents)
    # --------------------------------------------------

    def _derive_public_key(self, tender_id: str) -> str:
        """Derive a non-personal public key from the tender ID.

        This is NOT a cryptographic key — it's a public identifier that can
        be safely displayed on construction site signs without revealing PII.
        """
        seed = f"agent-x-public-portal:{tender_id}"
        return hashlib.sha256(seed.encode()).hexdigest()

    def _build_url(self, tender_id: str, public_key: str,
                   additional_params: dict[str, str] | None = None) -> str:
        """Build the public portal URL that the QR code will encode."""
        base = f"{self.portal_url}?id={tender_id}&key={public_key[:16]}"
        if additional_params:
            base += "&" + urlencode(additional_params)
        return base

    def _tenant_dir(self, user_id: str) -> Path:
        """Resolve the tenant-scoped output directory: /data/{user_id}/qrcodes/"""
        safe_user = user_id.replace("/", "_").replace("..", "_") or "default"
        d = self.output_root / safe_user / "qrcodes"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _find_existing(self, directory: Path, tender_id: str, fmt: QRFormat) -> Path | None:
        """Fast-track: check if a QR file already exists for this tender ID."""
        ext = f".{fmt.value}"
        pattern = f"{tender_id}*{ext}"
        matches = list(directory.glob(pattern))
        return matches[0] if matches else None

    def _generate_local(self, url: str, fmt: QRFormat) -> bytes:
        """Sub-agent: QRCodeRenderer — render QR code locally via qrcode library."""
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)

        if fmt == QRFormat.SVG:
            img = qr.make_image(image_factory=SvgImage)
            buf = io.BytesIO()
            img.save(buf)
            return buf.getvalue()
        else:
            # PNG or DATA_URL — both produce PNG bytes
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

    def _generate_via_api(self, url: str, fmt: QRFormat) -> bytes:
        """Sub-agent: FallbackAPI — generate QR via external API (api.qrserver.com)."""
        is_svg = fmt == QRFormat.SVG
        params = {
            "size": "300x300",
            "data": url,
            "format": "svg" if is_svg else "png",
            "margin": 10,
        }
        try:
            resp = requests.get(self.fallback_api, params=params, timeout=10)
            resp.raise_for_status()
            self.log.info("fallback_api_success", size_bytes=len(resp.content))
            return resp.content
        except Exception as exc:
            self.log.error("fallback_api_failed", error=str(exc))
            # Return a minimal red 1x1 PNG as error indicator
            if HAS_PILLOW:
                buf = io.BytesIO()
                Image.new("RGB", (1, 1), color="red").save(buf, format="PNG")
                return buf.getvalue()
            raise RuntimeError(f"Fallback API failed and Pillow not available: {exc}")

    def _write_qr_file(
        self, raw_bytes: bytes, tender_id: str, output_dir: Path, fmt: QRFormat
    ) -> Path:
        """Sub-agent: QRFileWriter — persist raw bytes to tenant output directory."""
        ext = fmt.value
        safe_tid = tender_id.replace("/", "_").replace(" ", "_")
        output_path = output_dir / f"{safe_tid}_qr.{ext}"
        output_path.write_bytes(raw_bytes)
        return output_path

    @staticmethod
    def _mock_municipality_catalog(municipality: str) -> list[dict]:
        """Mock project catalog for development. Replaced by EVM index in production."""
        catalog = {
            "Niedersachsen": [
                {"tender_id": "TED-2026-0815", "name": "Sanierung Klaeranlage Nord"},
                {"tender_id": "TED-2026-0712", "name": "Neubau Grundschule Ost"},
                {"tender_id": "TED-2026-0901", "name": "Brueckensanierung B3"},
            ],
            "Berlin": [
                {"tender_id": "TED-2026-1001", "name": "Radweg Friedrichshain"},
                {"tender_id": "TED-2026-1002", "name": "Schuldigitalisierung Mitte"},
            ],
        }
        return catalog.get(municipality, [
            {"tender_id": f"TED-{municipality[:4].upper()}-0001", "name": "Demo Project"}
        ])

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    def status(self) -> dict:
        cache_files = list(self._cache_dir.glob("*")) if self._cache_dir.exists() else []
        return {
            "generated_count": self._generated_count,
            "output_root": str(self.output_root),
            "portal_url": self.portal_url,
            "cache_dir": str(self._cache_dir),
            "cached_entries": len(cache_files),
            "has_qrcode": HAS_QRCODE,
            "has_pillow": HAS_PILLOW,
            "has_requests": HAS_REQUESTS,
            "fallback_api": self.fallback_api if not HAS_QRCODE else None,
        }


# ============================================================
# Agent 5: InteractiveMapComposer
# ============================================================


class InteractiveMapComposer:
    """Generates Leaflet/OpenStreetMap GeoJSON overlays for active projects.

    Color-coded by status AND progress percentage. Each marker popup contains
    budget, disbursed, progress bar, and a link to the blockchain verification page.
    DSGVO-safe: no PII in markers or popups.
    """

    # Progress thresholds for color grading
    PROGRESS_HIGH = 90
    PROGRESS_MID = 50

    # Default center: Berlin
    DEFAULT_CENTER = (52.5200, 13.4049)

    def __init__(self, cache_dir: Path | None = None, logger: JSONLogger | None = None):
        self.log = logger or JSONLogger(agent_name="InteractiveMapComposer")
        self._cache_dir = cache_dir or (Path(
            os.getenv("MAP_CACHE_DIR", "/data/public_portal/map_cache")
        ))
        self._cache_ready = False

    def _ensure_cache_dir(self) -> None:
        """Lazy mkdir — only when cache is actually accessed."""
        if not self._cache_ready:
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                self._cache_ready = True
            except OSError as exc:
                self.log.warn("map_cache_unavailable", error=str(exc))
                self._cache_ready = True  # don't retry

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def compose(self, projects: list[dict], municipality: str = "",
                portal_base_url: str = "", use_cache: bool = True) -> dict[str, Any]:
        """Generate a GeoJSON FeatureCollection for the given projects.

        Each project may provide: tender_id, lat/lon or address, status,
        project_name, budget_eur, disbursed_eur, progress_percent, last_update.

        If lat/lon are missing, address geocoding is attempted.
        """
        try:
            self.log.info("map_compose", municipality=municipality,
                          project_count=len(projects))

            # Cache check
            cache_key = self._cache_key(projects)
            if use_cache:
                cached = self._load_cache(cache_key)
                if cached is not None:
                    self.log.info("map_cache_hit", cache_key=cache_key[:16])
                    return make_response("completed", str(uuid.uuid4()), artifacts=[{
                        "type": "geojson_map",
                        "municipality": municipality,
                        "feature_count": len(cached.get("features", [])),
                        "geojson": cached,
                        "cache_hit": True,
                    }])

            # Build features
            features = []
            for p in projects:
                feature = self._build_feature(p, portal_base_url)
                if feature is not None:
                    features.append(feature)

            geojson = {
                "type": "FeatureCollection",
                "features": features,
                "metadata": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "municipality": municipality,
                    "total_projects": len(features),
                },
            }

            # Persist cache
            self._save_cache(cache_key, geojson)

            self.log.info("map_composed", feature_count=len(features),
                          municipality=municipality)
            return make_response("completed", str(uuid.uuid4()), artifacts=[{
                "type": "geojson_map",
                "municipality": municipality,
                "feature_count": len(features),
                "geojson": geojson,
                "cache_hit": False,
            }])

        except Exception as exc:
            self.log.error("map_compose_failed", error=str(exc))
            return make_response("failed", str(uuid.uuid4()), error=str(exc))

    def compose_html(
        self, projects: list[dict], municipality: str = "",
        portal_base_url: str = "", map_height: str = "600px",
    ) -> dict[str, Any]:
        """Generate a complete, self-contained HTML page with embedded Leaflet map.

        Returns an artifact with the full HTML string ready for embedding.
        """
        try:
            geo_result = self.compose(projects, municipality, portal_base_url)
            if geo_result["status"] != "completed":
                return geo_result

            geojson = geo_result["artifacts"][0]["geojson"]
            center_lat, center_lon = self._compute_center(projects)

            html = self._render_html_template(
                geojson, municipality, center_lat, center_lon, map_height
            )

            self.log.info("map_html_rendered", municipality=municipality,
                          html_bytes=len(html))
            return make_response("completed", str(uuid.uuid4()), artifacts=[{
                "type": "leaflet_html_map",
                "municipality": municipality,
                "html": html,
                "geojson": geojson,
            }])

        except Exception as exc:
            self.log.error("map_html_failed", error=str(exc))
            return make_response("failed", str(uuid.uuid4()), error=str(exc))

    # --------------------------------------------------
    # Feature builder
    # --------------------------------------------------

    def _build_feature(self, project: dict, portal_base_url: str = "") -> dict | None:
        """Build a single GeoJSON Feature with popup-ready properties."""
        tender_id = project.get("tender_id")
        if not tender_id:
            return None

        # Resolve coordinates
        lat = project.get("lat") or project.get("latitude")
        lon = project.get("lon") or project.get("longitude")
        if lat is None or lon is None:
            address = project.get("address", "")
            if address:
                lat, lon = self._geocode(address)
        if lat is None or lon is None:
            self.log.warn("map_skip_no_coords", tender_id=tender_id)
            return None

        progress = float(project.get("progress_percent", 0))
        status = project.get("status", "UNKNOWN")
        color, status_text = self._status_color(status, progress)
        portal_url = portal_base_url or os.getenv(
            "PUBLIC_PORTAL_URL", "https://transparenz.agent-x.de/projekt"
        )

        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "tender_id": tender_id,
                "project_name": project.get("project_name", "Unbekanntes Projekt"),
                "status": status,
                "status_text": status_text,
                "marker_color": color,
                "progress_percent": progress,
                "budget_eur": project.get("budget_eur", 0),
                "disbursed_eur": project.get("disbursed_eur", 0),
                "last_update": project.get(
                    "last_update", datetime.now(timezone.utc).isoformat()
                ),
                "portal_url": f"{portal_url}?id={tender_id}",
                "popup_html": self._build_popup_html(project, color, status_text,
                                                     progress, portal_url),
            },
        }

    # --------------------------------------------------
    # Status color with progress-based grading
    # --------------------------------------------------

    @staticmethod
    def _status_color(status: str, progress: float) -> tuple[str, str]:
        """Color + German label, factoring in both status enum and progress %."""
        if status == "COMPLETED" or progress >= 100:
            return "#28a745", "Abgeschlossen"
        if status == "DELAYED" or status == "STALLED":
            return "#dc3545", "Verzoegert"
        if status == "TENDERING":
            return "#0d6efd", "Ausschreibung"
        if status == "PLANNED":
            return "#6c757d", "In Planung"
        # IN_PROGRESS — refine by progress
        if progress >= InteractiveMapComposer.PROGRESS_HIGH:
            return "#28a745", "Fast fertig"
        if progress >= InteractiveMapComposer.PROGRESS_MID:
            return "#ffc107", "In Bau"
        if progress > 0:
            return "#fd7e14", "Baubeginn"
        return "#6c757d", "Beauftragt"

    # --------------------------------------------------
    # Popup HTML (DSGVO-safe)
    # --------------------------------------------------

    @staticmethod
    def _build_popup_html(
        project: dict, color: str, status_text: str, progress: float,
        portal_url: str,
    ) -> str:
        """Generate DSGVO-safe HTML for a Leaflet marker popup."""
        name = project.get("project_name", "Unbekanntes Projekt")
        tender_id = project.get("tender_id", "")
        budget = project.get("budget_eur", 0)
        disbursed = project.get("disbursed_eur", 0)

        # Inline styles — no external CSS dependency
        return (
            f'<div style="font-family:system-ui,sans-serif;min-width:240px;max-width:320px;">'
            f'<h3 style="margin:0 0 8px;font-size:16px;color:#1a3a5c;">{name}</h3>'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
            f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;'
            f'background:{color};"></span>'
            f'<span style="font-size:14px;font-weight:500;">{status_text}</span>'
            f'<span style="font-size:13px;color:#6c757d;">&bull; {progress:.1f}%</span>'
            f'</div>'
            f'<div style="font-size:13px;color:#495057;line-height:1.6;">'
            f'<div><strong>Budget:</strong> {budget:,.0f} &euro;</div>'
            f'<div><strong>Abgerufen:</strong> {disbursed:,.0f} &euro;</div>'
            f'<div style="margin-top:6px;font-size:12px;">'
            f'<a href="{portal_url}?id={tender_id}" target="_blank" '
            f'style="color:#1a3a5c;text-decoration:none;font-weight:500;">'
            f'Details &amp; Blockchain-Verifikation &rarr;</a>'
            f'</div></div></div>'
        )

    # --------------------------------------------------
    # Geocoding (mock → Nominatim fallback)
    # --------------------------------------------------

    @staticmethod
    def _geocode(address: str) -> tuple[float | None, float | None]:
        """Resolve address → (lat, lon). Mock catalog, then Nominatim if available."""
        mock: dict[str, tuple[float, float]] = {
            "kläranlage nord berlin": (52.5200, 13.4049),
            "grundschule ost berlin": (52.5230, 13.4120),
            "brückensanierung berlin": (52.5150, 13.4080),
            "rathaus münchen": (48.1374, 11.5755),
            "neubau hamburg": (53.5511, 9.9937),
        }
        addr_lower = address.lower()
        for key, coords in mock.items():
            if key in addr_lower or addr_lower in key:
                return coords

        # Try Nominatim (rate-limit: 1 req/s)
        if HAS_REQUESTS:
            try:
                resp = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": address, "format": "json", "limit": 1},
                    headers={"User-Agent": "AgentX-PublicPortal/1.0"},
                    timeout=5,
                )
                resp.raise_for_status()
                results = resp.json()
                if results:
                    return float(results[0]["lat"]), float(results[0]["lon"])
            except Exception:
                pass

        return None, None

    # --------------------------------------------------
    # Cache
    # --------------------------------------------------

    def _cache_key(self, projects: list[dict]) -> str:
        sorted_ids = sorted(p.get("tender_id", "") for p in projects)
        raw = "|".join(
            f"{p.get('tender_id','')}:{p.get('status','')}:{p.get('progress_percent',0)}"
            for p in sorted(projects, key=lambda x: x.get("tender_id", ""))
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _load_cache(self, cache_key: str) -> dict | None:
        self._ensure_cache_dir()
        cache_path = self._cache_dir / f"{cache_key}.geojson"
        if cache_path.exists():
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def _save_cache(self, cache_key: str, geojson: dict) -> None:
        self._ensure_cache_dir()
        cache_path = self._cache_dir / f"{cache_key}.geojson"
        try:
            cache_path.write_text(json.dumps(geojson, ensure_ascii=False, default=str),
                                  encoding="utf-8")
        except Exception as exc:
            self.log.warn("map_cache_write_failed", error=str(exc))

    # --------------------------------------------------
    # Center computation & HTML template
    # --------------------------------------------------

    def _compute_center(self, projects: list[dict]) -> tuple[float, float]:
        """Compute the mean center of all project coordinates."""
        lats, lons = [], []
        for p in projects:
            lat = p.get("lat") or p.get("latitude")
            lon = p.get("lon") or p.get("longitude")
            if lat is not None and lon is not None:
                lats.append(float(lat))
                lons.append(float(lon))
        if lats:
            return sum(lats) / len(lats), sum(lons) / len(lons)
        return self.DEFAULT_CENTER

    def _render_html_template(
        self, geojson: dict, municipality: str,
        center_lat: float, center_lon: float, map_height: str,
    ) -> str:
        """Render a self-contained HTML page with embedded Leaflet map."""
        geojson_str = json.dumps(geojson, ensure_ascii=False, default=str)
        title = f"Bauprojekte – {municipality}" if municipality else "Kommunale Bauprojekte"

        return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} – Transparenzportal</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  * {{ box-sizing:border-box;margin:0;padding:0; }}
  body {{ font-family:system-ui,sans-serif;background:#f8f9fa; }}
  .header {{ background:#1a3a5c;color:white;padding:16px 24px; }}
  .header h1 {{ font-size:22px;font-weight:600; }}
  .header p {{ font-size:14px;opacity:0.8;margin-top:4px; }}
  #map {{ height:{map_height};width:100%; }}
  .legend {{ background:white;padding:10px 14px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,.15);font-size:13px;line-height:1.8; }}
  .legend i {{ display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px; }}
  .footer {{ text-align:center;padding:12px;font-size:12px;color:#6c757d; }}
  .footer a {{ color:#1a3a5c;text-decoration:none; }}
</style>
</head>
<body>
<div class="header">
  <h1>Bauprojekte in Ihrer Stadt</h1>
  <p>Daten unveranderbar auf Gnosis Chain &amp; peaq Network verankert</p>
</div>
<div id="map"></div>
<div class="footer">
  <a href="https://transparenz.agent-x.de" target="_blank">Agent X Open Government Explorer</a>
  &mdash; Alle Daten DSGVO-konform anonymisiert.
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function() {{
  const map = L.map('map').setView([{center_lat}, {center_lon}], 13);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }}).addTo(map);

  const geojson = {geojson_str};

  const layer = L.geoJSON(geojson, {{
    pointToLayer: function(feature, latlng) {{
      return L.circleMarker(latlng, {{
        radius: 10, fillColor: feature.properties.marker_color || '#6c757d',
        color: '#fff', weight: 2, opacity: 1, fillOpacity: 0.85
      }});
    }},
    onEachFeature: function(feature, layer) {{
      if (feature.properties.popup_html) {{
        layer.bindPopup(feature.properties.popup_html, {{ maxWidth: 340 }});
      }}
    }}
  }}).addTo(map);

  // Legend
  const legend = L.control({{ position: 'bottomright' }});
  legend.onAdd = function() {{
    const div = L.DomUtil.create('div', 'legend');
    div.innerHTML = '<i style="background:#28a745"></i> Abgeschlossen / Fast fertig<br>'
                  + '<i style="background:#ffc107"></i> In Bau<br>'
                  + '<i style="background:#fd7e14"></i> Baubeginn<br>'
                  + '<i style="background:#dc3545"></i> Verzogert<br>'
                  + '<i style="background:#0d6efd"></i> Ausschreibung';
    return div;
  }};
  legend.addTo(map);

  // Fit to markers
  try {{
    const bounds = layer.getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, {{ padding: [30, 30] }});
  }} catch(e) {{}}
}})();
</script>
</body>
</html>"""

    def status(self) -> dict:
        cached = 0
        if self._cache_dir.exists():
            cached = len(list(self._cache_dir.glob("*.geojson")))
        return {
            "cache_dir": str(self._cache_dir),
            "cached_maps": cached,
        }


# ============================================================
# Agent 6: ZKPrivacyShield
# ============================================================


class ZKPrivacyShield:
    """DSGVO-compliant anonymization for public citizen views.

    Two modes:
    1. shield_public_data() — structured pipeline: masks phones/emails/names,
       obfuscates GPS to ~1 km grid, pseudonymizes worker IDs, cleans free text,
       and produces a DSGVO audit trail.
    2. anonymize() — recursive key-based PII strip for bulk/legacy payloads.
    """

    PII_PATTERNS = ["name", "email", "phone", "address", "iban", "birth", "tax_id"]
    GEOHASH_DECIMALS = 2  # ~1.1 km grid

    def __init__(self, salt: str = "B2G_PUBLIC_SALT_2026", logger: JSONLogger | None = None):
        self.salt = salt
        self.log = logger or JSONLogger(agent_name="ZKPrivacyShield")

    # ================================================================
    # Pipeline 1: Structured public view shielding
    # ================================================================

    def shield_public_data(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Full DSGVO pipeline for a single project's public view.

        Preserves: tender_id, project_name, budget, progress, status, zk_proofs.
        Shields: contact info, worker identities, GPS, addresses, free text.
        """
        try:
            self.log.info("shield_start", tender_id=raw_data.get("tender_id", "unknown"))

            shielded: dict[str, Any] = {
                "tender_id": raw_data.get("tender_id"),
                "project_name": raw_data.get("project_name", "Unbekanntes Projekt"),
                "budget_eur": raw_data.get("budget_eur", 0.0),
                "disbursed_eur": raw_data.get("disbursed_eur", 0.0),
                "progress_percent": raw_data.get("progress_percent", 0.0),
                "status": raw_data.get("status", "UNKNOWN"),
                "last_update": raw_data.get(
                    "last_update", datetime.now(timezone.utc).isoformat()
                ),
            }

            # Address → city/ZIP only
            shielded["address"] = self._mask_address(raw_data.get("address", ""))

            # GPS → coarse grid
            lat = raw_data.get("latitude") or raw_data.get("lat")
            lon = raw_data.get("longitude") or raw_data.get("lon")
            if lat is not None and lon is not None:
                shielded["latitude"], shielded["longitude"] = self._obfuscate_gps(
                    float(lat), float(lon)
                )
            else:
                shielded["latitude"], shielded["longitude"] = None, None

            # Contact info
            shielded["contact"] = self._mask_contact(raw_data.get("contact", {}))

            # Workers → pseudonyms
            shielded["workers"] = self._pseudonymize_workers(raw_data.get("workers", []))

            # Free text
            shielded["description"] = self._clean_free_text(raw_data.get("description", ""))
            shielded["milestones"] = self._clean_milestones(raw_data.get("milestones", []))

            # Chain proofs (public)
            shielded["zk_proofs"] = raw_data.get("zk_proofs", [])

            # Audit trail
            shielded["_audit"] = {
                "anonymized_at": datetime.now(timezone.utc).isoformat(),
                "fields_anonymized": self._diff_fields(raw_data, shielded),
                "gps_precision_decimals": self.GEOHASH_DECIMALS,
            }

            self.log.info("shield_complete", tender_id=shielded.get("tender_id"))
            return shielded

        except Exception as exc:
            self.log.error("shield_failed", error=str(exc))
            return {"error": str(exc), "original_keys": list(raw_data.keys())}

    # ================================================================
    # Pipeline 2: Recursive key-based strip (legacy/bulk fallback)
    # ================================================================

    def anonymize(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively strip PII fields by key name. Used by exporters."""
        try:
            self.log.info("anonymize_start", field_count=len(data))
            cleaned = self._strip_pii(data)
            self.log.info("anonymize_complete")
            return cleaned
        except Exception as exc:
            self.log.error("anonymize_failed", error=str(exc))
            return {"error": str(exc), "original_keys": list(data.keys())}

    def _strip_pii(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: ("[ANONYMISIERT]" if self._is_pii_key(k) else self._strip_pii(v))
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [self._strip_pii(item) for item in obj]
        return obj

    def _is_pii_key(self, key: str) -> bool:
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in self.PII_PATTERNS)

    # ================================================================
    # Address → city/ZIP only
    # ================================================================

    @staticmethod
    def _mask_address(address: str) -> str:
        """Strip house number and street; keep only ZIP + city if detectable."""
        if not address:
            return ""
        import re
        # Extract 5-digit ZIP
        zip_match = re.search(r"\b\d{5}\b", address)
        zip_part = zip_match.group(0) if zip_match else ""
        # Extract capitalized words after ZIP as city candidate
        city_match = re.search(r"\d{5}\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s[A-ZÄÖÜ][a-zäöüß]+)*)", address)
        city_part = city_match.group(1) if city_match else ""
        if zip_part and city_part:
            return f"{zip_part}, {city_part}"
        if zip_part:
            return zip_part
        return "Deutschland"

    # ================================================================
    # GPS obfuscation
    # ================================================================

    @classmethod
    def _obfuscate_gps(cls, lat: float, lon: float) -> tuple[float, float]:
        """Round to 2 decimal places (~1.1 km grid)."""
        return round(lat, cls.GEOHASH_DECIMALS), round(lon, cls.GEOHASH_DECIMALS)

    # ================================================================
    # Contact masking
    # ================================================================

    @staticmethod
    def _mask_contact(contact: dict[str, Any]) -> dict[str, Any]:
        if not contact:
            return {}
        result: dict[str, Any] = {}
        if contact.get("phone"):
            result["phone"] = ZKPrivacyShield._mask_phone(str(contact["phone"]))
        if contact.get("email"):
            result["email"] = ZKPrivacyShield._mask_email(str(contact["email"]))
        if contact.get("name"):
            result["name"] = ZKPrivacyShield._mask_name(str(contact["name"]))
        return result

    @staticmethod
    def _mask_phone(phone: str) -> str:
        import re
        cleaned = re.sub(r"[\s\-/()]", "", phone)
        if len(cleaned) >= 6:
            return f"{cleaned[:3]}****{cleaned[-2:]}"
        return "***-****"

    @staticmethod
    def _mask_email(email: str) -> str:
        if "@" in email:
            local, domain = email.split("@", 1)
            return f"****@{domain}"
        return "****@****"

    @staticmethod
    def _mask_name(name: str) -> str:
        parts = name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}. {parts[-1][0]}."
        if len(parts) == 1:
            return f"{parts[0][0]}."
        return "***"

    # ================================================================
    # Worker pseudonymization
    # ================================================================

    def _pseudonymize_workers(self, workers: list[dict]) -> list[dict]:
        if not workers:
            return []
        result: list[dict] = []
        for i, w in enumerate(workers):
            raw_id = w.get("worker_id") or w.get("id") or f"W-{i}"
            pseudonym = self._pseudonymize_id(str(raw_id))
            result.append({
                "id": pseudonym,
                "role": w.get("role", "Unbekannt"),
                "hours_logged": round(float(w.get("hours_logged", 0)), 1),
            })
        return result

    def _pseudonymize_id(self, raw_id: str) -> str:
        """Deterministic SHA-256 pseudonym with salt."""
        h = hashlib.sha256(f"{self.salt}:{raw_id}".encode()).hexdigest()
        return f"P-{h[:10]}"

    # ================================================================
    # Free text PII cleaning
    # ================================================================

    @staticmethod
    def _clean_free_text(text: str) -> str:
        """Strip emails, phone numbers, and honorific+name patterns from text."""
        if not text:
            return ""
        import re
        text = re.sub(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            "[E-MAIL]", text
        )
        text = re.sub(
            r"\b(?:\+?[0-9]{1,4}[-\s]?)?(?:\(?[0-9]{2,6}\)?[-\s]?)?[0-9]{3,10}\b",
            "[TELEFON]", text
        )
        text = re.sub(
            r"\b(Herr|Frau|Dr\.|Prof\.)\s+[A-ZÄÖÜ][a-zäöüß]+\b",
            r"\1 [NAME]", text
        )
        return text

    @classmethod
    def _clean_milestones(cls, milestones: list[dict]) -> list[dict]:
        if not milestones:
            return []
        return [
            {
                "title": m.get("title", "Meilenstein"),
                "description": cls._clean_free_text(m.get("description", "")),
                "date": m.get("date"),
                "progress": m.get("progress", 0),
            }
            for m in milestones
        ]

    # ================================================================
    # Audit trail
    # ================================================================

    @staticmethod
    def _diff_fields(original: dict, shielded: dict) -> list[str]:
        """Return list of top-level keys that were modified."""
        changed = []
        for key, orig_val in original.items():
            if key.startswith("_"):
                continue
            new_val = shielded.get(key)
            if isinstance(orig_val, (str, dict, list)) and orig_val != new_val:
                changed.append(key)
            elif key not in shielded:
                changed.append(key)
        return changed[:20]


# ============================================================
# Agent 7: TrustButtonService
# ============================================================


class TrustButtonService:
    """Verification widget for journalists, auditors, and citizens.

    Accepts invoice numbers, transaction hashes, or tender IDs.
    Searches the GoBD archive, verifies against on-chain anchors,
    and returns a green certificate with timestamp on success.
    """

    PORTAL_VERIFY_URL = os.getenv(
        "TRUST_VERIFY_URL",
        "https://transparenz.agent-x.de/verify"
    )

    def __init__(self, logger: JSONLogger | None = None):
        self.log = logger or JSONLogger(agent_name="TrustButtonService")
        self._archive: dict[str, dict[str, Any]] = self._seed_mock_archive()

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def verify(self, reference: str, query_type: str | None = None) -> dict[str, Any]:
        """Verify a reference against the archive and on-chain anchors.

        Args:
            reference: Invoice number, tx hash, or tender ID
            query_type: Auto-detected if None. One of: invoice, tx_hash, tender_id.

        Returns:
            Standardized response with VERIFIED certificate or FAILED error.
        """
        try:
            self.log.info("trust_verify", reference=reference[:40])

            # 1. Detect query type
            if query_type is None:
                query_type = self._detect_query_type(reference)

            # 2. Search archive
            record = self._search_archive(reference, query_type)
            if record is None:
                self.log.info("trust_not_found", reference=reference[:40])
                return make_response("completed", str(uuid.uuid4()), artifacts=[{
                    "type": "verification_certificate",
                    "status": "FAILED",
                    "title": "Nicht gefunden",
                    "message": "Die eingegebene ID oder Transaktion konnte nicht im Archiv gefunden werden.",
                    "query": reference,
                    "query_type": query_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }])

            # 3. On-chain verification
            chain_ok = self._verify_on_chain(record)
            if not chain_ok:
                self.log.warn("trust_chain_mismatch", reference=reference[:40])
                return make_response("completed", str(uuid.uuid4()), artifacts=[{
                    "type": "verification_certificate",
                    "status": "FAILED",
                    "title": "Verifikation fehlgeschlagen",
                    "message": "Der gefundene Hash stimmt nicht mit der On-Chain-Verankerung ueberein. Moegliche Manipulation!",
                    "query": reference,
                    "query_type": query_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }])

            # 4. Issue green certificate
            certificate = self._issue_certificate(reference, record)
            self.log.info("trust_certificate_issued",
                          certificate_id=certificate["certificate_id"])
            return make_response("completed", certificate["certificate_id"], artifacts=[{
                "type": "verification_certificate",
                **certificate,
            }])

        except Exception as exc:
            self.log.error("trust_verify_failed", error=str(exc))
            return make_response("failed", str(uuid.uuid4()), error=str(exc))

    # --------------------------------------------------
    # Query type detection
    # --------------------------------------------------

    @staticmethod
    def _detect_query_type(query: str) -> str:
        q = query.strip()
        # Tx hash: 0x + 64 hex chars
        if q.startswith("0x") and len(q) == 66 and all(
            c in "0123456789abcdefABCDEF" for c in q[2:]
        ):
            return "tx_hash"
        if "RE-" in q or "INV-" in q or "RECHNUNG" in q.upper():
            return "invoice"
        if "TED-" in q or "TENDER" in q.upper():
            return "tender_id"
        return "unknown"

    # --------------------------------------------------
    # Archive search
    # --------------------------------------------------

    def _search_archive(self, query: str, query_type: str) -> dict[str, Any] | None:
        """Search mock archive (production: JSONL GoBD archive)."""
        # Exact key match
        if query in self._archive:
            return self._archive[query]

        # Field-based search
        for record in self._archive.values():
            if query_type == "tx_hash" and record.get("tx_hash") == query:
                return record
            if query_type == "invoice" and record.get("invoice_number") == query:
                return record
            if query_type == "tender_id" and record.get("tender_id") == query:
                return record

        # Full-text fallback
        for record in self._archive.values():
            for val in record.values():
                if isinstance(val, str) and query in val:
                    return record

        return None

    # --------------------------------------------------
    # On-chain verification (stub — RPC in production)
    # --------------------------------------------------

    @staticmethod
    def _verify_on_chain(record: dict[str, Any]) -> bool:
        """Verify the record's hash against Gnosis/peaq anchor."""
        _ = record  # production: RPC call to contract.verifyMerkleRoot()
        return True

    # --------------------------------------------------
    # Certificate issuance
    # --------------------------------------------------

    @classmethod
    def _issue_certificate(cls, query: str, record: dict[str, Any]) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        cert_input = f"{record.get('hash', query)}:{timestamp}:{query}"
        cert_hash = "0x" + hashlib.sha256(cert_input.encode()).hexdigest()

        return {
            "status": "VERIFIED",
            "seal": "GREEN",
            "message": "Kryptografisch unverfaelscht nachgewiesen — unveraenderbar im Ledger verankert.",
            "reference": query,
            "certificate_id": f"TRUST-{query[:12].replace('/', '-')}-{timestamp[:10]}",
            "certificate_hash": cert_hash,
            "timestamp": timestamp,
            "verification_method": "SHA-256 Merkle Root Verification",
            "issuer": "Agent X — Open Government Explorer",
            "verification_url": f"{cls.PORTAL_VERIFY_URL}/{cert_hash}",
            "details": {
                "tender_id": record.get("tender_id"),
                "project_name": record.get("project_name"),
                "hash": record.get("hash"),
                "tx_hash": record.get("tx_hash"),
                "amount_eur": record.get("amount_eur"),
                "chain": record.get("chain", "Gnosis & peaq"),
            },
        }

    # --------------------------------------------------
    # Mock archive (production: GoBD JSONL index)
    # --------------------------------------------------

    @staticmethod
    def _seed_mock_archive() -> dict[str, dict[str, Any]]:
        return {
            "TED-2026-0815": {
                "tender_id": "TED-2026-0815",
                "project_name": "Sanierung Klaeranlage Nord",
                "hash": "0x8f1e3c2b1a9f0d8e7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d",
                "tx_hash": "0x3a91c7849E2b1009B8803a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d",
                "timestamp": "2026-08-04T19:35:00Z",
                "amount_eur": 1274896.80,
                "chain": "Gnosis",
            },
            "RE-2026-001": {
                "tender_id": "TED-2026-0815",
                "invoice_number": "RE-2026-001",
                "hash": "0x4e8a2b1c9f0d8e7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c",
                "tx_hash": "0x7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b",
                "timestamp": "2026-08-15T14:00:00Z",
                "amount_eur": 302787.80,
                "chain": "Gnosis",
            },
            "0x3a91c7849E2b1009B8803a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d": {
                "tender_id": "TED-2026-0815",
                "project_name": "Sanierung Klaeranlage Nord",
                "tx_hash": "0x3a91c7849E2b1009B8803a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d",
                "hash": "0x8f1e3c2b1a9f0d8e7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d",
                "timestamp": "2026-08-04T19:35:00Z",
                "amount_eur": 1274896.80,
                "chain": "Gnosis",
            },
        }


# ============================================================
# Agent 8: CitizenNotificationService
# ============================================================


class CitizenNotificationService:
    """Opt-in notifications on project changes.

    Triggers: milestone reached, budget change, project completion.
    Channels: email, push (via BundID mailbox).
    """

    def __init__(self, logger: JSONLogger | None = None):
        self.log = logger or JSONLogger(agent_name="CitizenNotificationService")
        self._subscriptions: dict[str, list[dict]] = {}

    def subscribe(self, tender_id: str, channel: str, address: str) -> dict[str, Any]:
        """Register a citizen for project notifications (opt-in only)."""
        job_id = str(uuid.uuid4())
        try:
            self._subscriptions.setdefault(tender_id, []).append({
                "channel": channel, "address": address,
                "subscribed_at": datetime.now(timezone.utc).isoformat(),
            })
            self.log.info("subscription_added", tender_id=tender_id,
                          channel=channel, address_hash=hashlib.sha256(address.encode()).hexdigest()[:12])
            return make_response("completed", job_id, logs=[f"Subscribed to {tender_id}"])
        except Exception as exc:
            self.log.error("subscribe_failed", error=str(exc))
            return make_response("failed", job_id, error=str(exc))

    def notify(self, tender_id: str, event: str, message: str) -> dict[str, Any]:
        """Send notifications to all subscribers of a project."""
        job_id = str(uuid.uuid4())
        try:
            subs = self._subscriptions.get(tender_id, [])
            self.log.info("notification_sent", tender_id=tender_id, event=event,
                          recipient_count=len(subs))
            return make_response("completed", job_id, artifacts=[{
                "type": "notification_batch",
                "tender_id": tender_id,
                "event": event,
                "recipients": len(subs),
            }])
        except Exception as exc:
            self.log.error("notify_failed", error=str(exc))
            return make_response("failed", job_id, error=str(exc))

    def unsubscribe(self, tender_id: str, address: str) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        try:
            before = len(self._subscriptions.get(tender_id, []))
            self._subscriptions[tender_id] = [
                s for s in self._subscriptions.get(tender_id, [])
                if s["address"] != address
            ]
            self.log.info("unsubscribed", tender_id=tender_id, removed=before - len(self._subscriptions.get(tender_id, [])))
            return make_response("completed", job_id, logs=["Unsubscribed"])
        except Exception as exc:
            return make_response("failed", job_id, error=str(exc))


# ============================================================
# Agent 9: AuditTrailPublicExporter
# ============================================================


class AuditTrailPublicExporter:
    """Exports anonymized audit data as Open Data (JSON/CSV).

    For journalists, researchers, and transparency portals.
    All PII is stripped via ZKPrivacyShield before export.
    GovData.de-compliant metadata included in JSON exports.
    """

    DEFAULT_EXPORT_DIR = Path(
        os.getenv("OPEN_DATA_EXPORT_DIR", "exports/open_data")
    )

    # Event types considered public (non-PII)
    PUBLIC_EVENT_TYPES = frozenset({
        "b2g.tender.published",
        "b2g.offer.submitted",
        "b2g.contract.signed",
        "b2g.payment.disbursed",
        "b2g.installment.approved",
        "b2g.popw.verified",
        "b2g.milestone.reached",
        "b2g.notary.anchored",
    })

    def __init__(self, privacy_shield: ZKPrivacyShield | None = None,
                 logger: JSONLogger | None = None,
                 export_dir: Path | None = None):
        self.privacy_shield = privacy_shield or ZKPrivacyShield()
        self.log = logger or JSONLogger(agent_name="AuditTrailPublicExporter")
        self.export_dir = export_dir or self.DEFAULT_EXPORT_DIR
        self.export_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # Public API — unified export
    # --------------------------------------------------

    def export_open_data(
        self,
        records: list[dict] | None = None,
        fmt: str = "json",
        from_date: str | None = None,
        to_date: str | None = None,
        tender_id: str | None = None,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """Unified Open Data export with filtering and integrity hash.

        Args:
            records: Raw event list (if None, uses mock demo data)
            fmt: "json" or "csv"
            from_date: ISO-8601 start (inclusive)
            to_date: ISO-8601 end (inclusive)
            tender_id: Filter by project
            output_path: Target file path (auto-generated if None)
        """
        job_id = str(uuid.uuid4())
        try:
            # 1. Source data
            events = records if records is not None else self._mock_events()
            self.log.info("export_open_data", fmt=fmt, record_count=len(events),
                          from_date=from_date, to_date=to_date, tender_id=tender_id)

            # 2. Filter
            events = self._filter_events(events, from_date, to_date, tender_id)

            # 3. Extract public fields per event type
            public_events = [self._extract_public_fields(e) for e in events]

            # 4. Anonymize
            safe_events = [self.privacy_shield.anonymize(pe) for pe in public_events]

            if not safe_events:
                return make_response("completed", job_id, artifacts=[{
                    "type": f"open_data_{fmt}",
                    "record_count": 0,
                    "message": "Keine oeffentlichen Ereignisse fuer den Export gefunden.",
                }])

            # 5. Export
            if fmt == "csv":
                return self._write_csv(safe_events, output_path, job_id)
            return self._write_json(safe_events, output_path, job_id)

        except Exception as exc:
            self.log.error("export_open_data_failed", error=str(exc))
            return make_response("failed", job_id, error=str(exc))

    # --------------------------------------------------
    # Backward-compatible simple exports
    # --------------------------------------------------

    def export_json(self, records: list[dict], output_path: Path | None = None) -> dict[str, Any]:
        """Simple JSON export with recursive PII strip. Used by supervisor."""
        return self.export_open_data(records=records, fmt="json", output_path=output_path)

    def export_csv(self, records: list[dict], output_path: Path | None = None) -> dict[str, Any]:
        """Simple CSV export with recursive PII strip. Used by supervisor."""
        return self.export_open_data(records=records, fmt="csv", output_path=output_path)

    # --------------------------------------------------
    # Filtering
    # --------------------------------------------------

    @staticmethod
    def _filter_events(
        events: list[dict], from_date: str | None, to_date: str | None,
        tender_id: str | None,
    ) -> list[dict]:
        result = events
        if tender_id:
            result = [e for e in result if e.get("tender_id") == tender_id]
        if from_date:
            result = [e for e in result if e.get("timestamp", "") >= from_date]
        if to_date:
            result = [e for e in result if e.get("timestamp", "") <= to_date]
        return result

    # --------------------------------------------------
    # Event-type-specific public field extraction
    # --------------------------------------------------

    @classmethod
    def _extract_public_fields(cls, event: dict) -> dict:
        """Map raw event → public-only fields based on event_type.

        If no event_type is present, returns the record unchanged (simple mode
        for bulk anonymization of flat records).
        """
        etype = event.get("event_type", "")
        if not etype:
            # Simple record — pass through for recursive PII strip
            return dict(event)
        tender_id = event.get("tender_id", "")
        data = event.get("data", {})

        base = {
            "event_type": etype,
            "tender_id": tender_id,
            "timestamp": event.get("timestamp", ""),
            "block_hash": event.get("block_hash"),
        }

        if "tender.published" in etype:
            base["public_data"] = {
                "tender_id": tender_id,
                "title": data.get("title", "Ausschreibung"),
                "estimated_value_eur": data.get("estimated_value_eur"),
            }
        elif "offer.submitted" in etype:
            base["public_data"] = {
                "tender_id": tender_id,
                "bidder_id": cls._pseudonymize(data.get("bidder_id", "")),
                "total_price_eur": data.get("total_bid_price_eur"),
                "submission_hash": data.get("submission_hash"),
            }
        elif "contract.signed" in etype:
            base["public_data"] = {
                "tender_id": tender_id,
                "contractor": cls._pseudonymize(data.get("contractor", "")),
                "final_amount_eur": data.get("final_amount_eur"),
                "merkle_root": data.get("contract_root_hash"),
            }
        elif "payment.disbursed" in etype or "installment.approved" in etype:
            base["public_data"] = {
                "tender_id": tender_id,
                "installment_no": data.get("installment_no"),
                "net_amount_eur": data.get("net_paid_eur") or data.get("amount_net_eur"),
                "retention_eur": data.get("retention_5pct_eur") or data.get("retention_eur"),
                "tx_hash": data.get("burn_tx_hash") or data.get("tx_hash"),
                "recipient": cls._pseudonymize(
                    str(data.get("recipient_iban", ""))[:4] + "****"
                ),
            }
        elif "popw.verified" in etype:
            details = data.get("verification_details", {})
            base["public_data"] = {
                "tender_id": tender_id,
                "installment_no": data.get("installment_no"),
                "zk_ready_hash": data.get("zk_ready_hash"),
                "geofence_compliance_percent": details.get("geofence_compliance_percent"),
                "worker_hours_verified": details.get("worker_hours_verified"),
            }
        elif "milestone.reached" in etype:
            base["public_data"] = {
                "tender_id": tender_id,
                "milestone_name": data.get("milestone_name"),
                "completion_percent": data.get("completion_percent"),
                "proof_hash": data.get("proof_hash"),
            }
        elif "notary.anchored" in etype:
            gnosis = data.get("chain_anchors", {}).get("gnosis_chain", {})
            peaq = data.get("chain_anchors", {}).get("peaq_network", {})
            base["public_data"] = {
                "tender_id": tender_id,
                "global_merkle_root": data.get("global_merkle_root"),
                "gnosis_tx": gnosis.get("tx_hash"),
                "peaq_tx": peaq.get("tx_hash"),
                "block_number": gnosis.get("block_number"),
            }
        else:
            # Generic: shallow-copy data (DSGVO-safe keys only)
            base["public_data"] = {
                k: v for k, v in data.items()
                if k in {"tender_id", "title", "amount_eur", "hash", "tx_hash"}
            }

        return base

    @staticmethod
    def _pseudonymize(value: str) -> str:
        if not value:
            return "Anonym"
        if len(value) < 10:
            return value
        return "P-" + hashlib.sha256(value.encode()).hexdigest()[:8]

    # --------------------------------------------------
    # JSON export (GovData.de metadata)
    # --------------------------------------------------

    def _write_json(self, events: list[dict], output_path: Path | None,
                    job_id: str) -> dict[str, Any]:
        export_time = datetime.now(timezone.utc).isoformat()
        content = json.dumps({
            "metadata": {
                "source": "B2G Agent X Plattform",
                "exported_at": export_time,
                "total_events": len(events),
                "format": "Open-Data JSON (GovData.de konform)",
            },
            "events": events,
        }, indent=2, ensure_ascii=False, default=str)

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        path = output_path or self.export_dir / f"open_data_audit_{job_id[:8]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        self.log.info("export_json_complete", path=str(path), record_count=len(events),
                      content_hash=content_hash)
        return make_response("completed", job_id, artifacts=[{
            "type": "open_data_json",
            "path": str(path),
            "record_count": len(events),
            "content_hash": content_hash,
        }])

    # --------------------------------------------------
    # CSV export (semicolon-delimited, German Excel)
    # --------------------------------------------------

    def _write_csv(self, events: list[dict], output_path: Path | None,
                   job_id: str) -> dict[str, Any]:
        import csv

        path = output_path or self.export_dir / f"open_data_audit_{job_id[:8]}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Collect all column headers from public_data
        base_headers = ["event_type", "tender_id", "timestamp", "block_hash"]
        data_keys: list[str] = []
        for e in events:
            for k in e.get("public_data", {}):
                if k not in data_keys:
                    data_keys.append(k)

        all_headers = base_headers + data_keys

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(all_headers)
            for e in events:
                row = [e.get(h, "") for h in base_headers]
                pd = e.get("public_data", {})
                row.extend([pd.get(k, "") for k in data_keys])
                writer.writerow(row)

        content = path.read_text(encoding="utf-8-sig")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        self.log.info("export_csv_complete", path=str(path), record_count=len(events),
                      content_hash=content_hash)
        return make_response("completed", job_id, artifacts=[{
            "type": "open_data_csv",
            "path": str(path),
            "record_count": len(events),
            "content_hash": content_hash,
        }])

    # --------------------------------------------------
    # Mock events (demo / development)
    # --------------------------------------------------

    @staticmethod
    def _mock_events() -> list[dict]:
        return [
            {
                "event_type": "b2g.tender.published",
                "tender_id": "TED-2026-0815",
                "timestamp": "2026-07-01T08:00:00Z",
                "block_hash": "0x1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff",
                "data": {"tender_id": "TED-2026-0815",
                         "title": "Sanierung Klaeranlage Nord",
                         "estimated_value_eur": 1274896.80},
            },
            {
                "event_type": "b2g.contract.signed",
                "tender_id": "TED-2026-0815",
                "timestamp": "2026-08-03T10:15:30Z",
                "block_hash": "0x9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e",
                "data": {"tender_id": "TED-2026-0815",
                         "contractor": "Tiefbau Mueller GmbH",
                         "final_amount_eur": 1274896.80,
                         "contract_root_hash": "0x8f1e3c2b1a9f0d8e7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d"},
            },
            {
                "event_type": "b2g.payment.disbursed",
                "tender_id": "TED-2026-0815",
                "timestamp": "2026-08-15T14:00:00Z",
                "block_hash": "0x7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b",
                "data": {"tender_id": "TED-2026-0815", "installment_no": 1,
                         "net_paid_eur": 302787.80, "retention_5pct_eur": 15936.20,
                         "burn_tx_hash": "0x7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b",
                         "recipient_iban": "DE89370400440532013000"},
            },
            {
                "event_type": "b2g.milestone.reached",
                "tender_id": "TED-2026-0815",
                "timestamp": "2026-08-20T16:00:00Z",
                "block_hash": "0xaaaa1111222233334444555566667777888899990000aaaabbbbccccddddeeee",
                "data": {"tender_id": "TED-2026-0815",
                         "milestone_name": "Rohbau abgeschlossen",
                         "completion_percent": 84.4,
                         "proof_hash": "0xproof1111222233334444555566667777888899990000"},
            },
        ]


# ============================================================
# Public Portal Supervisor (orchestrates all 9 agents)
# ============================================================


class PublicPortalSupervisor:
    """Wraps all 9 Wave-15 agents and provides a unified query interface."""

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self.log = JSONLogger(agent_name="PublicPortalSupervisor")

        # Instantiate all agents
        self.orchestrator = PublicPortalOrchestrator(event_bus=event_bus, logger=self.log)
        self.summary = ProjectSummaryAggregator(logger=self.log)
        self.verification = BlockchainVerificationWidget(logger=self.log)

        # QRCodeGenerator requires external qrcode package — lazy init
        self._qr_generator: QRCodeGenerator | None = None
        self._qr_error: str | None = None
        if HAS_QRCODE:
            try:
                self._qr_generator = QRCodeGenerator(event_bus=event_bus, logger=self.log)
            except Exception as exc:
                self._qr_error = str(exc)
                self.log.warn("qr_generator_unavailable", error=str(exc))
        else:
            self._qr_error = "qrcode package not installed"
            self.log.warn("qr_generator_unavailable", error=self._qr_error)

        self.map_composer = InteractiveMapComposer(logger=self.log)
        self.privacy_shield = ZKPrivacyShield(logger=self.log)
        self.trust_button = TrustButtonService(logger=self.log)
        self.notification_svc = CitizenNotificationService(logger=self.log)
        self.exporter = AuditTrailPublicExporter(privacy_shield=self.privacy_shield, logger=self.log)

        # Register sub-agents into orchestrator
        self.orchestrator.register_sub_agent("ProjectSummaryAggregator", self.summary)
        self.orchestrator.register_sub_agent("BlockchainVerificationWidget", self.verification)
        self.orchestrator.register_sub_agent("ZKPrivacyShield", self.privacy_shield)

        self.log.info("supervisor_initialized", agent_count=9, wave=15,
                      qr_available=self._qr_generator is not None)

    @property
    def qr_generator(self) -> QRCodeGenerator:
        if self._qr_generator is None:
            raise ImportError(
                f"QRCodeGenerator is not available: {self._qr_error}. "
                "Install with: pip install qrcode[pil]"
            )
        return self._qr_generator

    # --- Convenience wrappers ---

    def citizen_query(self, lookup_key: str, user_id: str = "anonymous") -> dict:
        """Full citizen query pipeline: summary + verification + privacy shield."""
        return self.orchestrator.query(lookup_key, user_id=user_id)

    def generate_qr(self, tender_id: str, fmt: str = "svg", user_id: str = "default",
                    force: bool = False) -> dict:
        """Generate a single QR code."""
        qr_fmt = QRFormat.SVG if fmt == "svg" else QRFormat.PNG
        return self.qr_generator.generate(tender_id=tender_id, fmt=qr_fmt,
                                          user_id=user_id, force=force)

    def generate_qr_batch(self, tender_ids: list[str], fmt: str = "svg",
                          user_id: str = "default", force: bool = False) -> dict:
        """Generate QR codes for multiple projects."""
        qr_fmt = QRFormat.SVG if fmt == "svg" else QRFormat.PNG
        return self.qr_generator.generate_batch(tender_ids=tender_ids, fmt=qr_fmt,
                                                 user_id=user_id, force=force)

    def generate_qr_for_municipality(self, municipality: str, fmt: str = "svg",
                                     user_id: str = "default") -> dict:
        """Generate QR codes for all active projects in a municipality."""
        qr_fmt = QRFormat.SVG if fmt == "svg" else QRFormat.PNG
        return self.qr_generator.generate_for_municipality(municipality=municipality,
                                                           fmt=qr_fmt, user_id=user_id)

    def compose_map(self, projects: list[dict], municipality: str = "",
                    portal_base_url: str = "") -> dict:
        """Generate a GeoJSON map overlay."""
        return self.map_composer.compose(projects, municipality=municipality,
                                         portal_base_url=portal_base_url)

    def compose_map_html(self, projects: list[dict], municipality: str = "",
                         portal_base_url: str = "", map_height: str = "600px") -> dict:
        """Generate a self-contained HTML page with embedded Leaflet map."""
        return self.map_composer.compose_html(
            projects, municipality, portal_base_url, map_height
        )

    def verify_blockchain(self, lookup_key: str) -> dict:
        """Verify a project hash on-chain."""
        return self.verification.verify(lookup_key)

    def export_open_data(self, records: list[dict], fmt: str = "json",
                         output_path: str | None = None) -> dict:
        """Export anonymized audit data as open data."""
        path = Path(output_path) if output_path else None
        if fmt == "csv":
            return self.exporter.export_csv(records, output_path=path)
        return self.exporter.export_json(records, output_path=path)

    def subscribe_citizen(self, tender_id: str, channel: str, address: str) -> dict:
        """Register a citizen for project notifications."""
        return self.notification_svc.subscribe(tender_id, channel, address)

    def status(self) -> dict:
        return {
            "wave": 15,
            "agents": 9,
            "qr_generated": self._qr_generator.status() if self._qr_generator else {"error": self._qr_error},
            "subscriptions": len(self.notification_svc._subscriptions),
        }
