#!/usr/bin/env python3
"""Valhalla — ZK Honor Protocol.

Core concepts:
  - ZK-Proof: anonymous group membership ("I am authorized, donʼt ask who I am")
  - Nullifier: per-stamp pseudonym, not traceable to identity
  - Honor score: H = α·SAT + β·TPS − γ·UNSAT + δ·perfect_bonus
  - Valhalla Ledger: public, immutable ranking by honor (identities hidden)
  - Privileges: top stamps earn gas discounts, priority routing, auto-refuel
  - Reputation: 3 failures → blacklisted; high score → premium status

Usage: python3 -m agents_b2g.valhalla.valhalla
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ─── Core Data ──────────────────────────────────────────────────────────────

class StampStatus(Enum):
    ACTIVE = "ACTIVE"
    BLACKLISTED = "BLACKLISTED"
    LEGENDARY = "LEGENDARY"


class Title(Enum):
    LEGENDE = ("Legende", 1000)
    FLOTTENADMIRAL = ("Flottenadmiral", 700)
    KÜSTENWÄCHTER = ("Küstenwächter", 400)
    Z3_ARCHITEKT = ("Z3-Architekt", 250)
    SCHNELLBOOT_KAPITÄN = ("Schnellboot-Kapitän", 120)
    EHRENHAFTER_REITER = ("Ehrenhafter Reiter", 50)
    WÜRDIGER_KRIEGER = ("Würdiger Krieger", 0)

    @classmethod
    def for_score(cls, score: float) -> "Title":
        for t in cls:
            if score >= t.value[1]:
                return t
        return cls.WÜRDIGER_KRIEGER


@dataclass
class ValhallaEntry:
    nullifier: str
    honor: float = 0.0
    actions: int = 0
    sat_count: int = 0
    unsat_count: int = 0
    status: StampStatus = StampStatus.ACTIVE
    rank: int = 0
    title: str = ""
    last_seen: float = 0.0
    privileges: Dict = field(default_factory=dict)


# ─── Krypto-Engines ─────────────────────────────────────────────────────────

class ZKProofEngine:
    """Simulated ZK-SNARK: proves group membership without revealing identity."""

    VALID_GROUPS = {"AUTHORIZED", "CONTRACTOR", "INSPECTOR", "SENSOR", "TREASURY"}

    @staticmethod
    def generate(group: str, secret: str) -> Dict:
        proof_hash = hashlib.sha256(f"ZK_{group}_{secret}".encode()).hexdigest()
        return {"group": group, "proof": proof_hash, "valid": group in ZKProofEngine.VALID_GROUPS}

    @staticmethod
    def verify(proof: Dict) -> Tuple[bool, str]:
        if not proof.get("valid"):
            return False, "INVALID_GROUP"
        if proof["group"] not in ZKProofEngine.VALID_GROUPS:
            return False, f"UNKNOWN_GROUP:{proof['group']}"
        return True, "ZK_OK"


class NullifierManager:
    """Generates anonymous per-stamp pseudonyms. Not linkable to identity."""

    _SALT = "VALHALLA_SALT_2026"

    @staticmethod
    def generate(secret: str) -> str:
        return hashlib.sha256(f"{secret}{NullifierManager._SALT}{time.time()}".encode()).hexdigest()


class HonorCalculator:
    """H = α·SAT + β·TPS − γ·UNSAT + δ·perfect_bonus"""

    ALPHA = 50.0    # Points per Z3_SAT
    BETA = 0.1      # Points per TPS
    GAMMA = 100.0   # Penalty per UNSAT
    DELTA = 20.0    # Bonus if 100% success rate

    @classmethod
    def calc(cls, z3_sat: bool, tps: float, unsat_attempts: int) -> Dict:
        sat_pts = cls.ALPHA if z3_sat else 0
        tps_pts = cls.BETA * tps
        penalty = cls.GAMMA * unsat_attempts
        perfect = cls.DELTA if (z3_sat and unsat_attempts == 0) else 0
        score = max(0, sat_pts + tps_pts - penalty + perfect)
        return {
            "score": round(score, 2), "sat_pts": sat_pts,
            "tps_pts": round(tps_pts, 2), "penalty": penalty,
            "perfect_bonus": perfect,
        }


class PrivilegeManager:
    """Grants system privileges based on honor score."""

    @staticmethod
    def grant(score: float) -> Dict:
        p = {"priority": False, "gas_discount_pct": 0, "auto_refuel": False, "z3_premium": False}
        if score >= 1000:
            p.update(priority=True, gas_discount_pct=30, auto_refuel=True, z3_premium=True)
        elif score >= 500:
            p.update(priority=True, gas_discount_pct=20, auto_refuel=True)
        elif score >= 250:
            p.update(priority=True, gas_discount_pct=10)
        elif score >= 100:
            p["gas_discount_pct"] = 5
        return p


class ValhallaLedger:
    """Public, immutable ranking of stamps by honor. Identities hidden."""

    def __init__(self):
        self.entries: Dict[str, ValhallaEntry] = {}
        self._ranking_order: List[str] = []

    def register(self, nullifier: str, honor_result: Dict) -> ValhallaEntry:
        if nullifier not in self.entries:
            self.entries[nullifier] = ValhallaEntry(nullifier=nullifier)

        e = self.entries[nullifier]
        e.honor = round(e.honor + honor_result["score"], 2)
        e.actions += 1
        if honor_result["sat_pts"] > 0:
            e.sat_count += 1
        if honor_result["penalty"] > 0:
            e.unsat_count += 1
        e.last_seen = time.time()

        # Blacklist after 3 UNSAT attempts
        if e.unsat_count >= 3:
            e.status = StampStatus.BLACKLISTED
        elif e.honor >= 1000:
            e.status = StampStatus.LEGENDARY

        # Ranking
        active = {k: v for k, v in self.entries.items() if v.status != StampStatus.BLACKLISTED}
        self._ranking_order = sorted(active, key=lambda k: active[k].honor, reverse=True)

        if nullifier in self._ranking_order:
            e.rank = self._ranking_order.index(nullifier) + 1
        title = Title.for_score(e.honor)
        e.title = title.value[0]
        e.privileges = PrivilegeManager.grant(e.honor)

        return e

    def top(self, n: int = 10) -> List[Dict]:
        result = []
        for nullifier in self._ranking_order[:n]:
            e = self.entries[nullifier]
            result.append({
                "rank": e.rank, "nullifier": f"{nullifier[:12]}...",
                "title": e.title, "honor": e.honor,
                "actions": e.actions, "sat/unsat": f"{e.sat_count}/{e.unsat_count}",
                "status": e.status.value, "gas_discount": f"{e.privileges.get('gas_discount_pct', 0)}%",
            })
        return result

    def find(self, nullifier: str) -> Optional[ValhallaEntry]:
        return self.entries.get(nullifier)


# ─── Orchestrator ───────────────────────────────────────────────────────────

class ValhallaOrchestrator:
    """Coordinates the ZK honor protocol: proof → nullifier → score → ledger → privileges."""

    def __init__(self):
        self.zk = ZKProofEngine()
        self.nullifier_mgr = NullifierManager()
        self.honor_calc = HonorCalculator()
        self.ledger = ValhallaLedger()
        self.privilege_mgr = PrivilegeManager()

    def process_stamp(self, group: str, secret: str, z3_sat: bool,
                      tps: float = 1000, unsat: int = 0) -> Dict[str, Any]:
        """
        Process one crypto stamp through the Valhalla protocol.

        1. ZK-Proof: prove group membership anonymously
        2. Nullifier: generate per-stamp pseudonym
        3. Honor: calculate score from performance
        4. Ledger: record in Valhalla, get ranking
        5. Privileges: grant based on score
        """
        # 1. ZK-Proof
        proof = self.zk.generate(group, secret)
        ok, reason = self.zk.verify(proof)
        if not ok:
            return {"status": "REJECTED", "reason": reason}

        # 2. Nullifier (anonymous stamp ID)
        nullifier = self.nullifier_mgr.generate(secret)

        # 3. Honor score
        honor = self.honor_calc.calc(z3_sat, tps, unsat)

        # 4. Valhalla Ledger
        entry = self.ledger.register(nullifier, honor)

        # 5. Privileges
        privs = self.privilege_mgr.grant(entry.honor)

        return {
            "status": "PROCESSED",
            "nullifier": f"{nullifier[:16]}...",
            "honor_score": honor["score"],
            "rank": entry.rank,
            "title": entry.title,
            "privileges": privs,
            "breakdown": honor,
        }


# ─── Demo ───────────────────────────────────────────────────────────────────

def demo_valhalla():
    """Show the Valhalla protocol: anonymous stamps earn public reputation."""
    W = 72
    print("\n" + "█" * W)
    print("█" + " " * (W - 2) + "█")
    print("█" + "  🏛️  VALHALLA — ZK Honor Protocol".center(W - 2) + "█")
    print("█" + "  Ruhm der Marke, Schutz dem Schöpfer".center(W - 2) + "█")
    print("█" + " " * (W - 2) + "█")
    print("█" * W)

    orch = ValhallaOrchestrator()

    # Demos: different stamps with different performance
    stamps = [
        ("CONTRACTOR", "sec_1", True, 1500, 0),
        ("CONTRACTOR", "sec_2", True, 800, 0),
        ("INSPECTOR", "sec_3", False, 200, 2),
        ("CONTRACTOR", "sec_4", True, 1200, 0),
        ("TREASURY", "sec_5", True, 1000, 0),
        ("SENSOR", "sec_6", True, 2400, 0),
        ("INSPECTOR", "sec_3", False, 100, 1),  # 3rd UNSAT → blacklisted
    ]

    print(f"\n  {'#':<3} {'Group':<14} {'Z3':<6} {'TPS':<8} {'UNSAT':<7} {'Nullifier':<18} {'Score':>8} {'Rank':>5} {'Title':<22}")
    print(f"  {'─'*3} {'─'*14} {'─'*6} {'─'*8} {'─'*7} {'─'*18} {'─'*8} {'─'*5} {'─'*22}")

    for i, (group, secret, sat, tps, unsat) in enumerate(stamps, 1):
        r = orch.process_stamp(group, secret, sat, tps, unsat)
        if r["status"] == "PROCESSED":
            print(f"  {i:<3} {group:<14} {'SAT' if sat else 'UNSAT':<6} {tps:<8} {unsat:<7} "
                  f"{r['nullifier']:<18} {r['honor_score']:>8.1f} {r['rank']:>5} {r['title']:<22}")
        else:
            print(f"  {i:<3} {group:<14} {'—':<6} {'—':<8} {'—':<7} {'—':<18} {'—':>8} {'—':>5} REJECTED: {r['reason']}")

    # Valhalla Top 5
    print(f"\n  🏅 VALHALLA HALL OF FAME (Top 5):")
    print(f"  {'Rank':<5} {'Nullifier':<18} {'Honor':>8} {'Title':<22} {'SAT/UNSAT':<10} {'Gas':>5} {'Status':<12}")
    print(f"  {'─'*5} {'─'*18} {'─'*8} {'─'*22} {'─'*10} {'─'*5} {'─'*12}")
    for e in orch.ledger.top(5):
        print(f"  {e['rank']:<5} {e['nullifier']:<18} {e['honor']:>8.1f} {e['title']:<22} "
              f"{e['sat/unsat']:<10} {e['gas_discount']:>5} {e['status']:<12}")

    # Privilege summary
    print(f"\n  ⚡ PRIVILEGES AWARDED:")
    shown = set()
    for nullifier, entry in orch.ledger.entries.items():
        if entry.rank > 0 and entry.privileges.get("priority") and entry.title not in shown:
            shown.add(entry.title)
            print(f"     #{entry.rank} {entry.title}: priority routing, "
                  f"{entry.privileges['gas_discount_pct']}% gas discount, "
                  f"auto-refuel: {entry.privileges['auto_refuel']}")

    # Pitch
    print(f"\n{'█' * W}")
    print(f"  🎯 PITCH:")
    print(f"     »Jede Briefmarke ist anonym — ZK-Proof + Nullifier.«")
    print(f"     »Ruhm entsteht durch mathematische Perfektion: H = α·SAT + β·TPS − γ·UNSAT«")
    print(f"     »Top-Stamps erhalten Privilegien ohne Identitätspreisgabe.«")
    print(f"     »3 UNSAT = Blacklist. Kein Einspruch, kein Appell.«")
    print(f"{'█' * W}\n")


if __name__ == "__main__":
    demo_valhalla()
