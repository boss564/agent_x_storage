#!/usr/bin/env python3
"""TIER 2 — partner-lokale Taktraten-Kopplung.

Gemeinsame Quelle fuer Demo und Adapter.
  kappa=0, epsilon=0      -> TIER-1-Baseline (kein Timing-Eingriff)
  kappa>0, epsilon=0      -> TIER 2a Rueckstau (inhibitorisch, Diskret-Ceiling)
  epsilon>0               -> exzitatorische Sonde (ins Ceiling)
  RelaxationOscillator    -> TIER 2b Puls-Kopplung (Mirollo–Strogatz, Speicher)
"""
from __future__ import annotations

import math
from typing import Any, Optional


INBOX_CAPACITY_DEFAULT = 8
EXCITATORY_FLOOR_DEFAULT = 0.5
TAU_TICKS_DEFAULT = 4.0


def partner_activity(
    t_now: float,
    partner_last_tx_time: Optional[float],
    tau_ticks: float = TAU_TICKS_DEFAULT,
) -> float:
    """1.0 right after partner transacted, decaying to 0. Phase-sensitive."""
    if partner_last_tx_time is None or tau_ticks <= 0:
        return 0.0
    dt = max(float(t_now) - float(partner_last_tx_time), 0.0)
    return math.exp(-dt / tau_ticks)


def coupling_factor(
    partner_inbox_len: float,
    inbox_capacity: float,
    kappa: float,
    partner_activity: float = 0.0,
    epsilon: float = 0.0,
    excitatory_floor: float = EXCITATORY_FLOOR_DEFAULT,
) -> float:
    """Backpressure (inhibitory) × excitation (positive feedback).

    kappa   : backpressure strength (TIER 2a).
    epsilon : excitatory strength. partner_activity in [0,1]
              measures how recently the partner transacted.
    excitatory_floor: cap to prevent runaway (interval -> 0).
    """
    load = (
        0.0
        if inbox_capacity <= 0
        else min(float(partner_inbox_len) / float(inbox_capacity), 1.5)
    )
    inhibitory = 1.0 + float(kappa) * load
    excitatory = max(
        1.0 - float(epsilon) * float(partner_activity),
        float(excitatory_floor),
    )
    return inhibitory * excitatory


def backpressure_factor(
    partner_inbox_len: float,
    inbox_capacity: float,
    kappa: float,
) -> float:
    """TIER-2a-compat: inhibitory-only factor (epsilon=0)."""
    if kappa == 0.0 or inbox_capacity <= 0:
        return 1.0
    return coupling_factor(partner_inbox_len, inbox_capacity, kappa)


def init_timing(
    agent: Any,
    *,
    base_interval: float = 1.0,
    run_seed: int = 0,
) -> None:
    """Attach discrete-time phase state (idempotent).

    Initial phase is spread by ``crc32(f"{agent_id}|{run_seed}")`` — Pre-Reg §5.1
    interval path. Independent of ``base_interval`` / fee heterogeneity (fee only
    scales the interval after coupling, not the hash input). Must run before
    warm-up so Sticky freeze sees seed-diverse trajectories.
    """
    import zlib

    if not hasattr(agent, "base_interval"):
        agent.base_interval = float(base_interval)
    if not hasattr(agent, "effective_interval"):
        agent.effective_interval = float(base_interval)
    if not hasattr(agent, "phase"):
        aid = str(getattr(agent, "id", "") or "")
        h = zlib.crc32(f"{aid}|{int(run_seed)}".encode()) & 0xFFFFFFFF
        agent.phase = (h % 1000) / 1000.0 * float(base_interval)
    if not hasattr(agent, "inbox_capacity"):
        agent.inbox_capacity = INBOX_CAPACITY_DEFAULT
    if not hasattr(agent, "last_transaction_time"):
        agent.last_transaction_time = None


def update_sender_interval(
    agent: Any,
    partner: Optional[Any],
    kappa: float,
    *,
    epsilon: float = 0.0,
    t_now: float = 0.0,
    tau_ticks: float = TAU_TICKS_DEFAULT,
    gas: Any = None,
    partner_s_honor: Optional[float] = None,
) -> float:
    """Set agent.effective_interval from partner-local signal.

    Returns the factor applied. Partner-local only — never a global signal.

    If ``partner_s_honor`` is not None (KOPPLUNG_REPUTATION_v1), use
    ``factor = 1 + κ · s(H_partner)`` (Pre-Reg §2.2). Otherwise legacy inbox path.
    """
    init_timing(agent)

    if partner_s_honor is not None:
        # Reputation Pre-Reg: missing partner → caller passes 0.0
        factor = 1.0 + float(kappa) * float(partner_s_honor)
        if gas is not None and kappa > 0.0:
            ok = gas.consume(1)
            if not ok:
                factor = max(factor, 10.0)
            elif gas.needs_refuel():
                gas.refuel(gas.initial_balance * 0.30)
        agent.effective_interval = agent.base_interval * factor
        return factor

    inbox_len = len(getattr(partner, "inbox", [])) if partner is not None else 0
    capacity = float(
        getattr(partner, "inbox_capacity", INBOX_CAPACITY_DEFAULT)
        if partner is not None
        else INBOX_CAPACITY_DEFAULT
    )
    last_tx = (
        getattr(partner, "last_transaction_time", None) if partner is not None else None
    )
    act = partner_activity(t_now, last_tx, tau_ticks=tau_ticks)
    factor = coupling_factor(
        inbox_len, capacity, kappa,
        partner_activity=act, epsilon=epsilon,
    )

    if gas is not None and kappa > 0.0:
        # Congestion burns extra gas locally (gas/ as substrate).
        extra = int(kappa * min(inbox_len / max(capacity, 1.0), 1.5))
        ok = gas.consume(1 + extra)
        if not ok:
            factor = max(factor, 10.0)
        elif gas.needs_refuel():
            gas.refuel(gas.initial_balance * 0.30)

    agent.effective_interval = agent.base_interval * factor
    return factor


def should_act_this_cycle(agent: Any) -> bool:
    """Advance phase; True when the agent may tick this global cycle."""
    init_timing(agent)
    agent.phase += 1.0
    if agent.phase + 1e-12 >= agent.effective_interval:
        agent.phase -= agent.effective_interval
        return True
    return False


# ── TIER 2b: pulse-coupled relaxation oscillator (Mirollo–Strogatz) ─────────


class RelaxationOscillator:
    """Integrate-and-fire with memory: charge accumulates across cycles.

    Pulse advance (kappa) shifts fire time by multiple cycles without
    exceeding 1 fire/cycle — bypasses the discrete tick ceiling of 2a/ε.
    """

    def __init__(self, base_rate: float, threshold: float = 1.0, charge: float = 0.0):
        self.base_rate = float(base_rate)
        self.threshold = float(threshold)
        self.charge = float(charge)

    def step(self, pulses_received: float, kappa: float) -> bool:
        # 1) Pulses from partners that fired in the previous cycle
        self.charge += float(kappa) * float(pulses_received)
        # 2) Pulse-induced fire (phase advance → synchronisation)
        if self.charge >= self.threshold:
            self.charge = 0.0
            return True
        # 3) Accumulate
        self.charge += self.base_rate
        # 4) Threshold fire
        if self.charge >= self.threshold:
            self.charge = 0.0
            return True
        return False


def oscillator_from_gas(
    gas: Any,
    *,
    agent_id: str = "",
    run_seed: int = 0,
    target_median_rate: float = 0.30,
    fee_ref: float = 0.8,
) -> RelaxationOscillator:
    """Map gas_profiles heterogeneity → (base_rate, threshold=1).

    fee_per_action → base_rate around target_median_rate so that
    kappa / median(base_rate) ∈ ~1–5 for the planned kappa sweep.
    Period ≈ threshold/base_rate ≈ 3–4 cycles — dense enough to keep
    TIER-1 message topology (density ~0.13), sparse enough to entrain.
    Initial charge is agent- and run_seed-dependent (Pre-Reg §5.1).
    """
    import zlib

    fee = float(getattr(gas, "fee_per_action", fee_ref) or fee_ref)
    base_rate = target_median_rate * (fee / fee_ref)
    base_rate = min(0.50, max(0.15, base_rate))
    threshold = 1.0
    # Spread initial phase across [0, threshold); run_seed diversifies replicates
    material = f"{agent_id}|{int(run_seed)}" if agent_id else f"osc|{int(run_seed)}"
    seed = zlib.crc32(material.encode()) & 0xFFFFFFFF
    charge = (seed % 1000) / 1000.0 * threshold * 0.99
    osc = RelaxationOscillator(base_rate=base_rate, threshold=threshold, charge=charge)
    # Heterogeneous lock trigger: slower agents (low base_rate) trigger slightly earlier
    # so they can open corridors; faster agents need to be closer to fire threshold.
    frac = 0.85 + 0.10 * ((base_rate - 0.15) / 0.35)  # ~0.85..0.95
    frac = min(0.95, max(0.85, frac))
    osc.lock_trigger = threshold * frac
    return osc
