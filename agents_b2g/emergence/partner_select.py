#!/usr/bin/env python3
"""Deterministische Partner-Selektion fuer ABM-Rollen-Routing (TIER 1).

Gemeinsame Quelle fuer ``demo_producer_cluster.py`` und
``emergence/adapter_agentx.py`` — keine Duplikation, sonst driftet die
Messung vom Verhalten.

Selektion: Least-Loaded mit sender-abhaengigem crc32-Tie-Break
(konsistent mit TIER-0-Reproduzierbarkeit). Sticky/Hysterese haelt den
Partner ueber Ticks, damit der aggregierte Graph nicht wieder dicht wird.

Pre-Reg Kopplung (docs/EMERGENZ_KOPPLUNG_PREREG.md §2.2): nach Warm-up
``freeze()`` — Least-Loaded-Umschaltung deaktiviert; Map fest.
"""
from __future__ import annotations

import random
import zlib
from collections import defaultdict
from typing import Callable, Dict, List, Mapping, Sequence, Tuple, TypeVar

T = TypeVar("T")

StickyMap = Dict[Tuple[str, str], str]


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
    abweicht. Senkt die aggregierte Graph-Dichte über lange Läufe.

    Nach ``freeze()`` ist die Map unveränderlich — Load-Umschaltung aus.
    """

    def __init__(self, threshold: int = 8):
        self.threshold = threshold
        self._last: StickyMap = {}
        self._frozen: bool = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def freeze(self) -> StickyMap:
        """Freeze current sticky map. Subsequent select() ignores load hysteresis.

        Returns a copy of the frozen map for Arm-C shuffle / audit.
        """
        self._frozen = True
        return dict(self._last)

    def unfreeze(self) -> None:
        """Re-enable Least-Loaded switching (tests / teardown only)."""
        self._frozen = False

    def snapshot(self) -> StickyMap:
        """Copy of current (sender, role) → partner_id map."""
        return dict(self._last)

    def load_map(self, mapping: Mapping[Tuple[str, str], str], *, freeze: bool = True) -> None:
        """Replace sticky map (e.g. Arm-C shuffled). Optionally freeze immediately."""
        self._last = dict(mapping)
        self._frozen = bool(freeze)

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

        key = (sender_id, role_key)

        if self._frozen:
            cur_id = self._last.get(key)
            if cur_id is None:
                # Novel (sender, role) after freeze: pin first choice, never switch.
                best = select_partner(sender_id, candidates, load_of, id_of=id_of)
                self._last[key] = _id(best)
                return best
            current = next((c for c in candidates if _id(c) == cur_id), None)
            if current is None:
                raise RuntimeError(
                    f"StickySelector frozen: partner {cur_id!r} not in candidates"
                )
            return current

        best = select_partner(sender_id, candidates, load_of, id_of=id_of)
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


def permute_sticky_map(
    frozen: Mapping[Tuple[str, str], str],
    *,
    seed: int,
    max_redraw: int = 64,
) -> StickyMap:
    """Degree-preserving, role-segment-internal bijection of partner assignments.

    For each ``role_key`` independently: keep the multiset of partner IDs
    (in-degrees preserved) and reassign them to the same senders via a
    permutation. Out-degree stays 1 per (sender, role).

    Pre-Reg §2.3 Arm C. Uses ``random.Random(seed)`` — never ``hash()``.
    Redraws if the permutation is a fixed point of the original (when a
    non-identity permutation exists).
    """
    by_role: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for (sender, role), partner in frozen.items():
        by_role[role].append((sender, partner))

    out: StickyMap = {}
    for role_idx, (role, edges) in enumerate(sorted(by_role.items())):
        senders = [s for s, _ in edges]
        partners = [p for _, p in edges]
        rng = random.Random(int(seed) + 100 * role_idx)
        shuffled = list(partners)
        if len(set(partners)) <= 1:
            # Cannot destroy identity — still degree-preserving (trivial).
            for s, p in zip(senders, partners):
                out[(s, role)] = p
            continue
        for _ in range(max_redraw):
            rng.shuffle(shuffled)
            if shuffled != partners:
                break
        else:
            # Exhausted redraws: force a transposition of two distinct partners.
            i = next(i for i, p in enumerate(partners) if p != partners[0])
            shuffled = list(partners)
            shuffled[0], shuffled[i] = shuffled[i], shuffled[0]
        for s, p in zip(senders, shuffled):
            out[(s, role)] = p
    return out


def assert_degree_preserving(
    original: Mapping[Tuple[str, str], str],
    shuffled: Mapping[Tuple[str, str], str],
) -> None:
    """Raise AssertionError if Arm-C invariants are violated."""
    if set(original) != set(shuffled):
        raise AssertionError("shuffle changed edge keys (sender, role)")
    by_role_o: Dict[str, List[str]] = defaultdict(list)
    by_role_s: Dict[str, List[str]] = defaultdict(list)
    for (sender, role), partner in original.items():
        by_role_o[role].append(partner)
        if shuffled[(sender, role)] is None:
            raise AssertionError("missing shuffled partner")
        by_role_s[role].append(shuffled[(sender, role)])
    for role in by_role_o:
        if sorted(by_role_o[role]) != sorted(by_role_s[role]):
            raise AssertionError(
                f"role {role!r}: partner multiset changed (not degree-preserving)"
            )
        # Role-segment internal: every shuffled partner must appear in original
        # partner set for that role (already implied by multiset equality).
