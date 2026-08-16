#!/usr/bin/env python3
"""Deterministische Partner-Selektion fuer ABM-Rollen-Routing (TIER 1).

Gemeinsame Quelle fuer ``demo_producer_cluster.py`` und
``emergence/adapter_agentx.py`` — keine Duplikation, sonst driftet die
Messung vom Verhalten.

Selektion: Least-Loaded mit sender-abhaengigem crc32-Tie-Break
(konsistent mit TIER-0-Reproduzierbarkeit). Sticky/Hysterese haelt den
Partner ueber Ticks, damit der aggregierte Graph nicht wieder dicht wird.
"""
from __future__ import annotations

import zlib
from typing import Callable, Dict, Sequence, Tuple, TypeVar

T = TypeVar("T")


def select_partner(
    sender_id: str,
    candidates: Sequence[T],
    load_of: Callable[[T], float | int],
    *,
    id_of: Callable[[T], str] | None = None,
) -> T:
    """Waehlt genau einen Partner aus der Ziel-Rolle (Least-Loaded + crc32)."""
    if not candidates:
        raise ValueError("select_partner: leere Kandidatenliste")

    def _id(c: T) -> str:
        if id_of is not None:
            return id_of(c)
        return getattr(c, "id", str(c))

    def key(c: T):
        tiebreak = zlib.crc32(f"{sender_id}:{_id(c)}".encode()) & 0xFFFFFFFF
        return (load_of(c), tiebreak)

    return min(candidates, key=key)


class StickySelector:
    """Partnerwahl mit Hysterese: Sender behält Partner, bis die Last klar
    abweicht. Senkt die aggregierte Graph-Dichte über lange Läufe."""

    def __init__(self, threshold: int = 8):
        self.threshold = threshold
        self._last: Dict[Tuple[str, str], str] = {}

    def select(
        self,
        sender_id: str,
        role_key: str,
        candidates: Sequence[T],
        load_of: Callable[[T], float | int],
        *,
        id_of: Callable[[T], str] | None = None,
    ) -> T:
        def _id(c: T) -> str:
            if id_of is not None:
                return id_of(c)
            return getattr(c, "id", str(c))

        best = select_partner(sender_id, candidates, load_of, id_of=id_of)
        key = (sender_id, role_key)
        cur_id = self._last.get(key)
        if cur_id is not None:
            current = next((c for c in candidates if _id(c) == cur_id), None)
            if current is not None:
                if load_of(current) <= load_of(best) + self.threshold:
                    return current
        self._last[key] = _id(best)
        return best

    def last_partner_id(self, sender_id: str, role_key: str) -> str | None:
        """Sticky partner for (sender, role), if already established."""
        return self._last.get((sender_id, role_key))
