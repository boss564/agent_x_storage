"""Cross-chain impact from config/cross_chain_map.json.

Diagnostic only. Does not send orders or touch the cluster.
affected_chains come from correlation_matrix (+ corridor destinations),
not from dumping every peer on a matching bridge (that would hide the
solana→ethereum/avalanche/arbitrum example behind polygon/optimism).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_MAP_PATH = _REPO / "config" / "cross_chain_map.json"
REQUIRED_KEYS = (
    "version",
    "bridges",
    "protocols",
    "liquidity_corridors",
    "correlation_matrix",
)


def empty_cross_chain_impact() -> Dict[str, Any]:
    return {"bridges": [], "affected_chains": [], "impact_score": 0.0}


def map_path() -> Path:
    override = os.environ.get("CROSS_CHAIN_MAP", "").strip()
    return Path(override) if override else DEFAULT_MAP_PATH


def _factor(row: Mapping[str, Any]) -> float:
    try:
        value = float(row.get("impact_factor", 0.0))
    except (TypeError, ValueError):
        return 0.0
    if value < 0.0 or value > 1.0:
        return 0.0
    return value


def validate_map(data: Mapping[str, Any]) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"cross_chain_map missing keys: {missing}")
    for group in ("bridges", "protocols"):
        rows = data.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"cross_chain_map.{group} must be a non-empty list")
        names: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"cross_chain_map.{group} entries must be objects")
            name = str(row.get("name") or "").strip()
            if not name:
                raise ValueError(f"cross_chain_map.{group} entry missing name")
            if name in names:
                raise ValueError(f"duplicate {group} name: {name}")
            names.append(name)
            chains = row.get("chains")
            if not isinstance(chains, list) or not chains:
                raise ValueError(f"{group} {name}: chains must be a non-empty list")
            factor = row.get("impact_factor")
            if not isinstance(factor, (int, float)) or factor < 0 or factor > 1:
                raise ValueError(f"{group} {name}: impact_factor must be in [0, 1]")
    corridors = data.get("liquidity_corridors")
    if not isinstance(corridors, list):
        raise ValueError("liquidity_corridors must be a list")
    matrix = data.get("correlation_matrix")
    if not isinstance(matrix, dict) or not matrix:
        raise ValueError("correlation_matrix must be a non-empty object")


@lru_cache(maxsize=4)
def load_map(path: Optional[str] = None) -> Dict[str, Any]:
    resolved = Path(path) if path else map_path()
    data = json.loads(resolved.read_text(encoding="utf-8"))
    validate_map(data)
    return data


def validate_default_map() -> Dict[str, Any]:
    load_map.cache_clear()
    return load_map()


def _matching_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    tagged_names: Iterable[str],
    tagged_chains: Iterable[str],
) -> List[Mapping[str, Any]]:
    names = {n for n in tagged_names if n}
    chains = {c for c in tagged_chains if c}
    matched: List[Mapping[str, Any]] = []
    for row in rows:
        name = str(row.get("name") or "")
        row_chains = {str(c) for c in (row.get("chains") or [])}
        if name in names or (chains and chains & row_chains):
            matched.append(row)
    return matched


def _extend_unique(dest: List[str], seen: set, values: Iterable[str], *, skip: set) -> None:
    for value in values:
        if not value or value in skip or value in seen:
            continue
        seen.add(value)
        dest.append(value)


def compute_cross_chain_impact(
    entities: Mapping[str, Any],
    mapping: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return bridges + correlated peers + max structural impact_factor."""
    data = mapping if mapping is not None else load_map()
    tagged_chains = [str(c) for c in (entities.get("chains") or []) if c]
    tagged_bridges = [str(b) for b in (entities.get("bridges") or []) if b]
    tagged_protocols = [str(p) for p in (entities.get("protocols") or []) if p]
    skip = set(tagged_chains)

    if not tagged_chains and not tagged_bridges and not tagged_protocols:
        return empty_cross_chain_impact()

    bridges = _matching_rows(
        list(data.get("bridges") or []),
        tagged_names=tagged_bridges,
        tagged_chains=tagged_chains,
    )
    protocols = _matching_rows(
        list(data.get("protocols") or []),
        tagged_names=tagged_protocols,
        tagged_chains=tagged_chains,
    )

    affected: List[str] = []
    seen: set = set()
    matrix = data.get("correlation_matrix") or {}
    for chain in tagged_chains:
        neighbors = matrix.get(chain) or {}
        if isinstance(neighbors, dict):
            _extend_unique(affected, seen, neighbors.keys(), skip=skip)

    for corridor in data.get("liquidity_corridors") or []:
        if str(corridor.get("from") or "") in skip:
            _extend_unique(affected, seen, (str(c) for c in (corridor.get("to") or [])), skip=skip)

    if not tagged_chains:
        for row in bridges:
            _extend_unique(affected, seen, (str(c) for c in (row.get("chains") or [])), skip=skip)

    scores = [_factor(row) for row in bridges] + [_factor(row) for row in protocols]
    for corridor in data.get("liquidity_corridors") or []:
        if str(corridor.get("from") or "") in skip:
            scores.append(_factor(corridor))

    impact = round(max(scores) if scores else 0.0, 4)
    return {
        "bridges": [str(row.get("name")) for row in bridges],
        "affected_chains": affected,
        "impact_score": impact,
    }
