"""
Agent X — API Agent 2: Validation (Schema-Validierung & Sanitization).

Verantwortung: Pydantic-Schema-Validierung, Deep-Payload-Sanitization,
Transformation in interne DTOs.

Sub-Agenten:
  2a: Schema-Validator — Pydantic-Modelle gegen JSON-Payload
  2b: Deep-Sanitizer — Entfernt Injection-Vektoren aus String-Feldern
  2c: DTO-Transformer — Konvertiert API-DTOs in Orchestrator-Dicts
"""

import logging
import re
from typing import Any

from pydantic import ValidationError

from core.exceptions import SnapshotValidationError, MissingRequiredFieldError
from core.schemas.api_schemas import SnapshotRequestDTO, PositionDTO, TimelockDTO

logger = logging.getLogger("RequestValidation")


# ─── Sub-Agent 2a: Schema-Validator ──────────────────────────────────

class SchemaValidator:
    """Validiert JSON-Payload gegen Pydantic-Schemata.

    Konvertiert und validiert in einem Schritt.
    Bei Fehler: Detaillierte Feld-für-Feld-Fehlerliste.
    """

    def validate_snapshot(self, raw: dict[str, Any]) -> SnapshotRequestDTO:
        try:
            return SnapshotRequestDTO(**raw)
        except ValidationError as e:
            errors = e.errors()
            formatted = []
            for err in errors:
                loc = " → ".join(str(l) for l in err["loc"])
                formatted.append(f"{loc}: {err['msg']}")
            detail = "; ".join(formatted)
            logger.warning("Schema-Validierung fehlgeschlagen: %s", detail)
            raise SnapshotValidationError(detail)

    def validate_batch(self, raw_list: list[dict]) -> list[SnapshotRequestDTO]:
        results = []
        errors = []
        for i, item in enumerate(raw_list):
            try:
                results.append(self.validate_snapshot(item))
            except SnapshotValidationError as e:
                errors.append({"index": i, "error": str(e)})
        if errors and not results:
            raise SnapshotValidationError(f"Batch: {len(errors)}/{len(raw_list)} failed")
        return results


# ─── Sub-Agent 2b: Deep-Sanitizer ────────────────────────────────────

class DeepSanitizer:
    """Entfernt potenziell gefährliche Inhalte aus String-Feldern.

    Schützt gegen:
      - SQL-Injection (entfernt ', ", ;)
      - XSS (entfernt <script>, <img onerror>)
      - Prototype-Pollution (entfernt __proto__, constructor)
    """

    def sanitize(self, data: Any) -> Any:
        if isinstance(data, str):
            return self._sanitize_string(data)
        elif isinstance(data, dict):
            return {k: self.sanitize(v) for k, v in data.items()
                    if not self._is_dangerous_key(k)}
        elif isinstance(data, list):
            return [self.sanitize(item) for item in data]
        return data

    def _sanitize_string(self, s: str) -> str:
        s = s.replace("'", "")
        s = s.replace('"', "")
        s = s.replace(";", "")
        s = re.sub(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "", s, flags=re.IGNORECASE)
        s = re.sub(r"<\s*img[^>]*onerror\s*=", "", s, flags=re.IGNORECASE)
        s = s.replace("__proto__", "").replace("constructor", "")
        s = s.replace("${", "").replace("$(", "")  # Shell-Injection
        return s.strip()

    def _is_dangerous_key(self, key: str) -> bool:
        danger = ["__proto__", "constructor", "prototype", "$where", "$gt", "$regex"]
        return any(d in key.lower() for d in danger)


# ─── Sub-Agent 2c: DTO-Transformer ───────────────────────────────────

class DTOTransformer:
    """Konvertiert API-DTOs in Orchestrator-kompatible Dicts.

    Der Orchestrator arbeitet mit dict-basierten Schnittstellen.
    Diese Schicht übersetzt die streng typisierten API-DTOs.
    """

    def snapshot_to_dict(self, dto: SnapshotRequestDTO) -> dict:
        """SnapshotRequestDTO → Orchestrator-kompatibles Dict."""
        collateral_usd = sum(
            p.amount * p.price_usd for p in dto.positions if p.is_collateral
        )
        debt_usd = sum(
            p.amount * p.price_usd for p in dto.positions if not p.is_collateral
        )
        avg_threshold = (
            sum(p.liquidation_threshold * p.amount * p.price_usd
                for p in dto.positions if p.is_collateral)
            / max(1, collateral_usd)
        ) if collateral_usd > 0 else 0.80
        hf = round((collateral_usd * avg_threshold) / max(1, debt_usd), 4) if debt_usd > 0 else float("inf")

        return {
            "user_address": dto.user_address,
            "positions": [p.model_dump() for p in dto.positions],
            "health_factors": [{
                "user_address": dto.user_address or "0x0000000000000000000000000000000000000001",
                "health_factor": hf if hf != float("inf") else 999.0,
                "total_collateral_usd": collateral_usd,
                "total_debt_usd": debt_usd,
                "liquidation_threshold": avg_threshold,
            }],
            "gas_pressure": dto.gas_pressure,
            "mev_pressure": dto.mev_pressure,
            "consensus_health": dto.consensus_health,
            "mempool_bots": dto.mempool_bots,
            "oracle_update_in_s": dto.oracle_update_in_s,
            "leader_utilization": dto.leader_utilization,
            "expected_profit_usd": dto.expected_profit_usd,
            "pending_timelocks": [
                {"action": t.action, "hours_until_executable": t.hours_until_executable,
                 "impact_score": t.impact_score}
                for t in (dto.pending_timelocks or [])
            ],
        }


# ─── Agent 2: RequestValidationAgent ─────────────────────────────────

class RequestValidationAgent:
    """Validiert + saniert + transformiert API-Requests.

    Usage:
        validator = RequestValidationAgent()
        dto = validator.validate_snapshot_payload(raw_json)
        internal = validator.to_internal(dto)
    """

    def __init__(self):
        self.schema_validator = SchemaValidator()
        self.sanitizer = DeepSanitizer()
        self.transformer = DTOTransformer()

    def validate_snapshot_payload(self, raw: dict[str, Any]) -> SnapshotRequestDTO:
        """Vollständiger Validierungs-Durchlauf für einen Snapshot."""
        # 1. Deep-Sanitize
        clean = self.sanitizer.sanitize(raw)
        # 2. Schema-Validierung
        return self.schema_validator.validate_snapshot(clean)

    def to_internal(self, dto: SnapshotRequestDTO) -> dict:
        """Transformiert ein validiertes DTO in Orchestrator-Dict."""
        return self.transformer.snapshot_to_dict(dto)

    def validate_and_transform(self, raw: dict[str, Any]) -> dict:
        """All-in-One: Sanitize → Validate → Transform."""
        dto = self.validate_snapshot_payload(raw)
        return self.to_internal(dto)
