#!/usr/bin/env python3
"""Agent X — 3-Agenten-ABM-MVP (Archetypen: Provider, Evaluator, Economic).

Schritt 2+3 des ABM-Fahrplans: 3 Archetyp-Klassen, 100 Ticks im TickController.
Validiert den BaseAgent-Loop, Message-Passing und die SimChain-Integration.

  Provider  — erzeugt wirtschaftliche Transaktionen (Bau-Meilensteine)
  Evaluator — prüft BHO-Invarianz via Z3/SimChain (Δ = 0?)
  Economic  — führt Settlement durch und steuert Token-Flows

Jeder Agent erbt von BaseAgent, nutzt die StateMachine und loggt
seine Entscheidungen. Der TickController orchestriert 100 Zyklen.

Usage:
  python3 scripts/demo_producer_cluster.py
  python3 scripts/demo_producer_cluster.py --cycles 200
"""

import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents_b2g.emergence.partner_select import StickySelector

from agents_b2g.protocol import (
    AgentMessage, AgentState, BaseAgent, PayloadType, StateMachine, TickController,
    offer, bho_proof, alert,
)
from agents_b2g.finale import FinaleOrchestrator
from scripts.hebel1_evaluator_rules import EVALUATOR_RULES, rule_default


# ═══════════════════════════════════════════════════════════════════════════════
# Archetyp 1: Provider — Erzeugt wirtschaftliche Transaktionen
# ═══════════════════════════════════════════════════════════════════════════════

class ProviderAgent(BaseAgent):
    """Erzeugt Bau-Meilensteine mit variierenden Beträgen.

    Repräsentiert: Bauunternehmen, Material-Lieferanten, DePIN-Sensoren.
    Entscheidungsregel: Melde Meilenstein wenn Bedingungen erfüllt.
    """

    def __init__(self, agent_id: str = "provider"):
        super().__init__(agent_id)
        self.total_reported = 0.0
        self.milestone_count = 0
        self.failure_count = 0
        self.sector = "BAU"
        self.decision_bias = 0.20   # Wahrscheinlichkeit zu melden (0–1)
        self.amount_multiplier = 1.0
        self.risk_factor = 0.05      # Anteil manipulierter Meldungen (0–1)

    def decide(self) -> str:
        cycle = self.perception.get("cycle", 0)
        # Terminal RECEIPTs: drain (kein Folge-Traffic)
        self.inbox = [
            m for m in self.inbox
            if getattr(m, "payload_type", None) != PayloadType.RECEIPT
        ]
        # ACK settlement broadcasts (reziproke Kante Economic ↔ Provider)
        if any(
            getattr(m, "payload_type", None) == PayloadType.SETTLEMENT
            for m in self.inbox
        ):
            return "ack_settlement"
        # Melde-Entscheidung basierend auf decision_bias (pro Tick)
        threshold = int(1.0 / max(self.decision_bias, 0.01))
        if cycle % threshold == 0 and self.sm.can_transition(AgentState.NEGOTIATING):
            return "report_milestone"
        # Manipulierte Meldungen basierend auf risk_factor
        manip_threshold = int(1.0 / max(self.risk_factor, 0.01)) if self.risk_factor > 0 else 999
        if manip_threshold < 999 and cycle % manip_threshold == 0 and cycle > 0 \
           and self.sm.can_transition(AgentState.NEGOTIATING):
            return "report_inflated"
        return "idle"

    def act(self) -> List[AgentMessage]:
        decision = self.decision_log[-1]["decision"] if self.decision_log else "idle"
        cycle = self.perception.get("cycle", 0)
        msgs = []

        if decision == "ack_settlement":
            kept = []
            while self.inbox:
                msg = self.inbox.pop(0)
                if msg.payload_type != PayloadType.SETTLEMENT:
                    kept.append(msg)
                    continue
                msgs.append(AgentMessage(
                    sender=self.id,
                    receiver=msg.sender,
                    payload_type=PayloadType.RECEIPT,
                    content={
                        "ack_of": "SETTLEMENT",
                        "contract_id": msg.content.get("contract_id", "?"),
                        "signed_net": float(msg.content.get("volume", 0) or 0),
                    },
                ))
            self.inbox.extend(kept)
            return msgs

        if decision in ("report_milestone", "report_inflated"):
            self.sm.transition(AgentState.NEGOTIATING, triggered_by=f"cycle_{cycle}")
            self.sm.transition(AgentState.TRANSACTING, triggered_by="report")

            amount = (45_000.0 + cycle * 1_000.0) * self.amount_multiplier
            inflated = decision == "report_inflated"

            self.total_reported += amount
            self.milestone_count += 1

            if inflated:
                # Manipulierte Meldung: Netto überhöht, aber Brutto unverändert
                msgs.append(AgentMessage(
                    sender=self.id, receiver="evaluator",
                    payload_type=PayloadType.OFFER,
                    content={
                        "contract_id": f"{self.id}-{cycle:04d}",
                        "gross_amount": amount,
                        "net_amount": amount * 0.83,  # 3 % zu viel = BHO-Verletzung
                        "tax_amount": amount * 0.15,
                        "retention_amount": amount * 0.05,
                        "inflated": True,
                    },
                ))
            else:
                msgs.append(AgentMessage(
                    sender=self.id, receiver="evaluator",
                    payload_type=PayloadType.OFFER,
                    content={
                        "contract_id": f"{self.id}-{cycle:04d}",
                        "gross_amount": amount,
                        "net_amount": amount * 0.80,
                        "tax_amount": amount * 0.15,
                        "retention_amount": amount * 0.05,
                        "inflated": False,
                    },
                ))

            self.sm.transition(AgentState.COMMITTING, triggered_by="report_sent")
            self.sm.transition(AgentState.COMPLETED, triggered_by="report_done")

        return msgs

    def update_internal_state(self):
        if self.sm.current == AgentState.COMPLETED:
            self.sm.reset()


# ═══════════════════════════════════════════════════════════════════════════════
# Archetyp 2: Evaluator — Prüft BHO-Invarianten
# ═══════════════════════════════════════════════════════════════════════════════

class EvaluatorAgent(BaseAgent):
    """Prüft jede eingehende Transaktion auf BHO-Invarianz.

    Repräsentiert: Z3-Proof-Requestor, GoBD-Auditor, Compliance-Checker.
    Entscheidungsregel: Δ = 0 → approve, Δ ≠ 0 → reject + alert.
    """

    def __init__(self, agent_id: str = "evaluator", orch: FinaleOrchestrator = None):
        super().__init__(agent_id)
        self.orch = orch
        self.checks_performed = 0
        self.checks_passed = 0
        self.checks_failed = 0

    def decide(self) -> str:
        if self.inbox:
            return "verify_bho"
        return "idle"

    def act(self) -> List[AgentMessage]:
        msgs = []

        while self.inbox:
            msg = self.inbox.pop(0)
            if msg.payload_type != PayloadType.OFFER:
                continue

            content = msg.content
            gross = content["gross_amount"]
            net   = content["net_amount"]
            tax   = content["tax_amount"]
            ret   = content["retention_amount"]
            inflated = content.get("inflated", False)
            contract_id = content["contract_id"]
            delta = round(gross - (net + tax + ret), 10)
            # Hebel 1 Follow-up: differentiated rules by self.id (registry)
            rule = EVALUATOR_RULES.get(self.id, rule_default)
            holds = rule(net, tax, ret, gross, inflated, contract_id)

            self.sm.transition(AgentState.NEGOTIATING, triggered_by=msg.msg_id)
            self.sm.transition(AgentState.TRANSACTING, triggered_by="verify")

            self.checks_performed += 1
            if holds:
                self.checks_passed += 1
                self.sm.transition(AgentState.COMMITTING, triggered_by="bho_ok")
                self.sm.transition(AgentState.COMPLETED, triggered_by="verified")

                msgs.append(AgentMessage(
                    sender=self.id, receiver="economic",
                    payload_type=PayloadType.BHO_PROOF,
                    content={"contract_id": content["contract_id"],
                             "delta_eur": delta, "holds": True,
                             "inflated": content.get("inflated", False),
                             "gross_amount": gross, "net_amount": net},
                ))
                # Reziproke Kante: Evaluator → Provider (ACK auf OFFER)
                msgs.append(AgentMessage(
                    sender=self.id,
                    receiver=msg.sender,
                    payload_type=PayloadType.RECEIPT,
                    content={
                        "ack_of": "OFFER",
                        "contract_id": content["contract_id"],
                        "holds": True,
                        "signed_net": float(net),
                    },
                ))
            else:
                self.checks_failed += 1
                self.sm.transition(AgentState.FAILED, triggered_by="bho_violation")

                msgs.append(alert("CRITICAL", "bho",
                    f"BHO-Verletzung! {content['contract_id']}: Δ = {delta:.2f} € "
                    f"(inflated={content.get('inflated', False)})"))
                # Auch bei Reject: kurze Quittung (Rückkante), signed_net=0
                msgs.append(AgentMessage(
                    sender=self.id,
                    receiver=msg.sender,
                    payload_type=PayloadType.RECEIPT,
                    content={
                        "ack_of": "OFFER",
                        "contract_id": content["contract_id"],
                        "holds": False,
                        "signed_net": 0.0,
                    },
                ))

            self.sm.reset()

        return msgs


# ═══════════════════════════════════════════════════════════════════════════════
# Archetyp 3: Economic — Steuert Token-Flows
# ═══════════════════════════════════════════════════════════════════════════════

class EconomicAgent(BaseAgent):
    """Führt Settlement durch und steuert Fee/Burn/Staking.

    Repräsentiert: Staker, Burn-Executioner, Liquidity-Buffer.
    Entscheidungsregel: Nur ausführen wenn BHO geprüft und bestanden.
    """

    def __init__(self, agent_id: str = "economic", orch: FinaleOrchestrator = None):
        super().__init__(agent_id)
        self.orch = orch
        self.settlements = 0
        self.total_volume = 0.0
        self.total_fee_burned = 0.0
        self.fee_rate = 0.001  # 0.1 % Transaktionsgebühr

    def decide(self) -> str:
        if self.inbox:
            return "settle"
        return "idle"

    def act(self) -> List[AgentMessage]:
        msgs = []

        while self.inbox:
            msg = self.inbox.pop(0)
            if msg.payload_type != PayloadType.BHO_PROOF:
                continue

            content = msg.content
            if not content.get("holds"):
                continue  # BHO-Verletzung — kein Settlement!

            self.sm.transition(AgentState.NEGOTIATING, triggered_by=msg.msg_id)
            self.sm.transition(AgentState.TRANSACTING, triggered_by="settle")

            # Settlement in SimChain verbuchen
            if self.orch:
                gross = content.get("gross", 45000.0) if "gross" in content else 45000.0
                tx = {
                    "contract_id": content.get("contract_id", "ECON-UNKNOWN"),
                    "sector": "BAU",
                    "gross_amount": gross,
                    "net_amount": gross * 0.80,
                    "tax_amount": gross * 0.15,
                    "retention_amount": gross * 0.05,
                }
                self.orch.generate_full_audit_package(tx)

            # Fee-Berechnung und Burn
            volume = content.get("gross_amount", gross)
            fee = volume * self.fee_rate
            burn = fee * 0.30
            self.total_volume += volume
            self.total_fee_burned += burn
            self.settlements += 1

            self.sm.transition(AgentState.COMMITTING, triggered_by="settlement_done")
            self.sm.transition(AgentState.COMPLETED, triggered_by="settled")

            msgs.append(AgentMessage(
                sender=self.id, receiver="broadcast",
                payload_type=PayloadType.SETTLEMENT,
                content={
                    "contract_id": content.get("contract_id", "?"),
                    "volume": volume, "fee": round(fee, 2),
                    "burn": round(burn, 2), "settlements": self.settlements,
                },
            ))
            # Reziproke Kante: Economic → Evaluator (ACK auf BHO_PROOF)
            msgs.append(AgentMessage(
                sender=self.id,
                receiver=msg.sender,
                payload_type=PayloadType.RECEIPT,
                content={
                    "ack_of": "BHO_PROOF",
                    "contract_id": content.get("contract_id", "?"),
                    "signed_net": float(volume),
                },
            ))

            self.sm.reset()

        return msgs


# ═══════════════════════════════════════════════════════════════════════════════
# Parametrisierung: 9 Profile pro Archetyp → 27 Agenten (ABM Schritt 4)
# ═══════════════════════════════════════════════════════════════════════════════

# Profile: (id, sector, decision_bias, amount_multiplier, risk_factor)
PROVIDER_PROFILES = [
    # Bau & Infrastruktur
    ("P01-constructor",    "BAU",      0.20, 1.00, 0.05),
    ("P02-roofing",        "BAU",      0.15, 0.80, 0.08),
    ("P03-electrical",     "BAU",      0.12, 0.60, 0.10),
    # Energie & Wasser
    ("P04-solar",          "ENERGY",   0.25, 0.40, 0.03),
    ("P05-water",          "WATER",    0.22, 0.35, 0.04),
    ("P06-hydrogen",       "ENERGY",   0.10, 0.90, 0.12),
    # Rohstoffe & Logistik
    ("P07-grain",          "WHEAT",    0.18, 0.50, 0.06),
    ("P08-diesel",         "ENERGY",   0.16, 0.70, 0.07),
    ("P09-logistics",      "CUSTOMS",  0.14, 0.55, 0.09),
]

EVALUATOR_PROFILES = [
    ("E01-bho-checker",    "BAU",      1.00, 0.01, 0.00),
    ("E02-z3-prover",      "BAU",      1.00, 0.00, 0.00),
    ("E03-gobd-auditor",   "BAU",      0.80, 0.02, 0.01),
    ("E04-compliance",     "HEALTH",   0.90, 0.01, 0.01),
    ("E05-iot-verifier",   "ENERGY",   0.70, 0.00, 0.02),
    ("E06-qes-validator",  "BAU",      0.60, 0.00, 0.03),
    ("E07-geofence",       "CUSTOMS",  0.85, 0.00, 0.02),
    ("E08-fraud-detector", "BAU",      0.95, 0.00, 0.01),
    ("E09-tax-auditor",    "BAU",      0.75, 0.01, 0.01),
]

ECONOMIC_PROFILES = [
    ("C01-settlement",     "BAU",      1.00, 0.00, 0.00),
    ("C02-staking",        "BAU",      0.60, 0.00, 0.05),
    ("C03-burn-executor",  "BAU",      0.40, 0.00, 0.10),
    ("C04-liquidity",      "BAU",      0.50, 0.00, 0.08),
    ("C05-fee-distributor","BAU",      0.30, 0.00, 0.12),
    ("C06-gas-paymaster",  "ENERGY",   0.20, 0.00, 0.15),
    ("C07-retention",      "BAU",      0.70, 0.00, 0.03),
    ("C08-treasury",       "BAU",      0.55, 0.00, 0.06),
    ("C09-token-minter",   "BAU",      0.45, 0.00, 0.09),
]

def create_agent(profile: tuple, archetype: str, orch=None):
    """Factory: Erzeugt einen parametrisierten Agenten aus einem Profil.

    Jeder Agent erbt vom Archetyp und überschreibt nur die
    Parameter — keine neue Klasse pro Agent.
    """
    agent_id, sector, bias, amount_mult, risk = profile

    if archetype == "provider":
        class ParamProvider(ProviderAgent):
            pass
        a = ParamProvider(agent_id)
        a.sector = sector
        a.decision_bias = bias
        a.amount_multiplier = amount_mult
        a.risk_factor = risk
        return a

    elif archetype == "evaluator":
        class ParamEvaluator(EvaluatorAgent):
            pass
        a = ParamEvaluator(agent_id, orch)
        a.sector = sector
        a.decision_bias = bias
        a.amount_multiplier = amount_mult
        a.risk_factor = risk
        a.strictness = bias  # Höher = strengere Prüfung
        return a

    elif archetype == "economic":
        class ParamEconomic(EconomicAgent):
            pass
        a = ParamEconomic(agent_id, orch)
        a.sector = sector
        a.decision_bias = bias
        a.amount_multiplier = amount_mult
        a.risk_factor = risk
        return a

    raise ValueError(f"Unknown archetype: {archetype}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main: 100 Ticks im TickController
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="ABM: 3 oder 27 Agenten")
    parser.add_argument("--cycles", type=int, default=100,
                        help="Anzahl Ticks (default: 100)")
    parser.add_argument("--full", action="store_true",
                        help="Alle 27 Agenten (statt 3-Archetypen-MVP)")
    args = parser.parse_args()

    orch = FinaleOrchestrator(user_id="abm-mvp" if not args.full else "abm-full")

    if args.full:
        agents = []
        for p in PROVIDER_PROFILES:
            agents.append(create_agent(p, "provider", orch))
        for p in EVALUATOR_PROFILES:
            agents.append(create_agent(p, "evaluator", orch))
        for p in ECONOMIC_PROFILES:
            agents.append(create_agent(p, "economic", orch))
        mode = f"27 Agenten (9P + 9E + 9C)"
    else:
        agents = [
            ProviderAgent("provider"),
            EvaluatorAgent("evaluator", orch),
            EconomicAgent("economic", orch),
        ]
        mode = "3 Archetypen"

    tc = TickController(seed=1)
    for a in agents:
        tc.register(a)

    print(f"🏛️  ABM: {mode} — {args.cycles} Ticks")
    print(f"   {'Tick':<8} {'Provider':<20} {'Evaluator':<20} {'Economic':<20} {'Msgs':<8}")
    print(f"   {'─'*8} {'─'*20} {'─'*20} {'─'*20} {'─'*8}")

    providers  = [a for a in agents if isinstance(a, ProviderAgent)]
    evaluators = [a for a in agents if isinstance(a, EvaluatorAgent)]
    economics  = [a for a in agents if isinstance(a, EconomicAgent)]

    # TIER 1: kumulative Zustellungen = Last; StickySelector gegen Dichte-Inflation
    recv_load: Dict[str, int] = {a.id: 0 for a in agents}
    sticky = StickySelector(threshold=8)

    def _load(a):
        return recv_load.get(a.id, 0) + len(a.inbox)

    t_start = time.perf_counter()
    for _ in range(args.cycles):
        tc.cycle += 1
        env = {"cycle": tc.cycle, "agent_count": len(tc.agents)}
        tick_msgs = 0

        for agent in tc.agents:
            msgs = agent.tick(env)
            tick_msgs += len(msgs)

        # Message-Passing mit Archetyp-Routing (TIER 1: 1 Partner / Rolle, sticky)
        all_out = []
        for agent in tc.agents:
            all_out.extend(agent.outbox)
            agent.outbox.clear()
        for msg in all_out:
            if msg.receiver == "broadcast":
                # Settlement-Ankündigung: genau EIN Provider (nicht 27× fan-out)
                if not providers:
                    continue
                partner = sticky.select(
                    msg.sender, "broadcast→provider", providers, _load,
                )
                partner.receive(msg)
                recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            elif msg.receiver == "evaluator":
                if not evaluators:
                    continue
                partner = sticky.select(msg.sender, "evaluator", evaluators, _load)
                partner.receive(msg)
                recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            elif msg.receiver == "economic":
                if not economics:
                    continue
                # TIER-1 Sticky-Key: sender:contract_id (gemeinsam mit Adapter)
                partner = sticky.select(
                    f"{msg.sender}:{msg.content.get('contract_id', '')}",
                    "economic", economics, _load,
                )
                partner.receive(msg)
                recv_load[partner.id] = recv_load.get(partner.id, 0) + 1
            else:
                for agent in tc.agents:
                    if agent.id == msg.receiver:
                        agent.receive(msg)
                        recv_load[agent.id] = recv_load.get(agent.id, 0) + 1

        tc.total_messages += tick_msgs

        if tc.cycle % 10 == 0 or tc.cycle == 1:
            p_ms = sum(p.milestone_count for p in providers)
            p_vol = sum(p.total_reported for p in providers)
            e_ok = sum(e.checks_passed for e in evaluators)
            e_fail = sum(e.checks_failed for e in evaluators)
            c_tx = sum(c.settlements for c in economics)
            c_vol = sum(c.total_volume for c in economics)
            print(f"   {tc.cycle:<8} "
                  f"ms={p_ms} vol={p_vol:,.0f}      "
                  f"✓{e_ok}/✗{e_fail}               "
                  f"tx={c_tx} vol={c_vol:,.0f}      "
                  f"{tick_msgs:<8}")

    elapsed = time.perf_counter() - t_start

    p_ms = sum(p.milestone_count for p in providers)
    p_vol = sum(p.total_reported for p in providers)
    e_ok = sum(e.checks_passed for e in evaluators)
    e_fail = sum(e.checks_failed for e in evaluators)
    e_total = sum(e.checks_performed for e in evaluators)
    c_tx = sum(c.settlements for c in economics)
    c_vol = sum(c.total_volume for c in economics)
    c_burn = sum(c.total_fee_burned for c in economics)

    print(f"\n   {'─'*70}")
    print(f"   Ticks: {tc.cycle} | Dauer: {elapsed:.2f}s | "
          f"Nachrichten: {tc.total_messages}")

    print(f"\n   📦 Provider ({len(providers)}):  {p_ms} Meilensteine, {p_vol:,.0f} €")
    for p in providers:
        if p.milestone_count > 0:
            print(f"      {p.id}: {p.milestone_count} MS, {p.total_reported:,.0f} € [{p.sector}]")

    print(f"\n   🔍 Evaluator ({len(evaluators)}): {e_total} geprüft — ✅ {e_ok} / ❌ {e_fail}")
    for e in evaluators:
        if e.checks_performed > 0:
            print(f"      {e.id}: {e.checks_performed} checks [{e.sector}]")

    print(f"\n   💰 Economic ({len(economics)}): {c_tx} Settlements, {c_vol:,.0f} €, {c_burn:,.2f} € Burn")
    for c in economics:
        if c.settlements > 0:
            print(f"      {c.id}: {c.settlements} TXs, {c.total_volume:,.0f} € [{c.sector}]")

    stats = orch.audit.get_stats()
    chain = orch.audit.verify_chain()
    print(f"\n   🔗 SimChain:  {stats['total_entries']} Einträge, "
          f"Kette {'✅' if chain['artifacts'][0]['verified'] else '❌'}, "
          f"{stats['total_amount_eur']:,.0f} €")

    total_trans = sum(len(a.sm.history) for a in tc.agents)
    print(f"   🔄 Transitionen: {total_trans}")

    print()
    print("=" * 70)
    print(f"🏛️  ABM — {'27-AGENTEN' if args.full else '3-ARCHETYPEN'} VALIDIERUNG")
    print("=" * 70)
    # Settlement-Gate: Jede Settlement-TX muss BHO-geprüft sein
    # Die Anzahl gesettleder TXs darf die Anzahl bestandener BHO-Prüfungen nicht übersteigen
    # (pro Transaktion wird genau ein Evaluator-Check durchgeführt, Fan-out zählt nicht)
    settlement_ok = c_tx <= e_ok  # Jede Settlement-TX ist BHO-geprüft
    print(f"  Agenten:             {len(agents)} ({len(providers)}P + {len(evaluators)}E + {len(economics)}C)")
    print(f"  BHO-Erkennung:       {'✅' if e_fail > 0 else '⚠️  Keine Verletzungen'} "
          f"({e_fail} Verletzungen)")
    print(f"  Settlement-Gate:     {'✅' if settlement_ok else '❌'} "
          f"({c_tx} Settlements, {e_ok} BHO-bestanden — "
          f"keine ungeprüfte Zahlung)" if settlement_ok else
          f"({c_tx} Settlements > {e_ok} BHO-bestanden — Lücke!)")
    print(f"  SimChain intakt:     {'✅' if chain['artifacts'][0]['verified'] else '❌'}")
    print(f"  Message-Passing:     ✅ {tc.total_messages} Nachrichten")
    print(f"  Transitionen:        {total_trans}")
    print("=" * 70)

    sys.exit(0 if settlement_ok else 1)


if __name__ == "__main__":
    main()
