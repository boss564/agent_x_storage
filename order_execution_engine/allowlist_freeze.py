"""Laden und Validieren des Gamma-Allowlist-Freeze (Messperiode).

Kein Netzwerk — nur Datei → Resolver-Map + config_json-Einträge.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

REQUIRED_FIELDS = (
    "asset",
    "market_question",
    "slug",
    "token_id",
    "market_id",
    "resolved_at",
    "source",
)


class FreezeError(ValueError):
    """Freeze-Datei ungültig oder unvollständig."""


def parse_market_end_date(raw: Any) -> Optional[datetime]:
    """Parse end_date to aware UTC; None if missing/unparseable (fail-closed input)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in ("none", "null"):
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ts.tzinfo is None:
        # Naive → treat as UTC (documented); never as local.
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def is_market_expired(
    end_date_raw: Any,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """C1: True when market must not dispatch.

    - NULL / unparseable → fail-closed (True)
    - end_date <= now(UTC) → expired (True)
    - end_date > now → live (False)

    Restored 2026-11-11 for G8 SP-1926 M-a suite green: function lived in
    stash@{0} while news_bridge still imported it (stash left HEAD unimportable).
    """
    end = parse_market_end_date(end_date_raw)
    if end is None:
        return True
    clock = now if now is not None else datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    else:
        clock = clock.astimezone(timezone.utc)
    return end <= clock


def load_freeze(path: Path) -> dict[str, Any]:
    """Lädt allowlist.freeze.json; fail-closed bei Schema-/Feldfehlern."""
    if not path.exists():
        raise FreezeError(f"freeze missing: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise FreezeError(f"freeze JSON invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise FreezeError("freeze root must be object")
    entries = data.get("entries")
    if not isinstance(entries, dict) or not entries:
        raise FreezeError("freeze.entries missing or empty")
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            raise FreezeError(f"entry {key!r} not an object")
        for field in REQUIRED_FIELDS:
            if not entry.get(field):
                raise FreezeError(f"entry {key!r} missing {field}")
        if str(entry["source"]).lower() != "gamma":
            raise FreezeError(f"entry {key!r} source must be gamma")
        asset = str(entry["asset"]).strip().upper()
        if asset != str(key).strip().upper():
            raise FreezeError(f"entry key {key!r} != asset {asset!r}")
    return data


def freeze_to_resolver_map(freeze: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Asset → {token_id, market_id} für MarketResolver."""
    out: dict[str, dict[str, str]] = {}
    for asset, entry in freeze["entries"].items():
        out[str(asset).upper()] = {
            "token_id": str(entry["token_id"]),
            "market_id": str(entry["market_id"]),
        }
    return out


def freeze_entries_for_config(freeze: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Volle Freeze-Einträge für telemetry_runs.config_json."""
    return {
        str(asset).upper(): dict(entry)
        for asset, entry in freeze["entries"].items()
    }


def token_ids_from_freeze(freeze: Mapping[str, Any]) -> list[str]:
    """Stabile Reihenfolge der WS-assets_ids."""
    return [
        str(freeze["entries"][k]["token_id"])
        for k in sorted(freeze["entries"].keys())
    ]


def load_allowlist_file(path: Path) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    """Erkennt Freeze-Schema vs. flache Allowlist-Map.

    Returns:
        (resolver_map, config_allowlist) — config trägt volle Metadaten wenn Freeze.
    """
    raw = json.loads(path.read_text())
    if isinstance(raw, dict) and raw.get("schema") == "allowlist.freeze/v1":
        freeze = load_freeze(path)
        return freeze_to_resolver_map(freeze), freeze_entries_for_config(freeze)
    if not isinstance(raw, dict) or not raw:
        raise FreezeError(f"empty allowlist: {path}")
    # Flache Map {ASSET: {token_id, market_id}}
    resolver: dict[str, dict[str, str]] = {}
    for asset, entry in raw.items():
        if not isinstance(entry, dict) or "token_id" not in entry or "market_id" not in entry:
            raise FreezeError(f"flat allowlist entry invalid: {asset}")
        resolver[str(asset).upper()] = {
            "token_id": str(entry["token_id"]),
            "market_id": str(entry["market_id"]),
        }
    return resolver, {k: dict(v) for k, v in resolver.items()}
