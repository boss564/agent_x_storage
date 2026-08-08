#!/usr/bin/env python3
"""
PhilatelyCollectorVault — 1 Master Agent + 8 Subagenten.

Isoliertes, spezialisiertes Agenten-Cluster fuer das sichere Sammeln,
Verifizieren, Handeln und Zertifizieren von Crypto-Briefmarken (ERC-1155).

3 Schutz-Saeulen:
  🛡️ Security:   IssuerVerification → QuarantineManager → BurnAgent
  🔄 Trading:    AtomicSwapExecutor → OfferAgent → TradeMonitor
  🔍 Provenance: ProvenanceTracker → GradingAgent → CertificateGenerator

Usage:
    from agents_b2g.philately.collector_vault import VaultCoordinator
    vault = VaultCoordinator(owner_address='kaemmerer.muenchen.b2g')
    result = vault.receive_incoming_stamp(stamp_nft)
"""
from __future__ import annotations

import hashlib, json, os, sys, time, uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ============================================================
# Configuration
# ============================================================


class VaultConfig:
    """Konfiguration fuer PhilatelyCollectorVault."""
    DATA_ROOT: Path = Path(os.getenv("VAULT_DATA_ROOT", "data"))
    LOG_DIR: Path = Path(os.getenv("VAULT_LOG_DIR", "logs"))
    WHITELIST: set = {"0xOFFICIAL_POST_AUTHORITY", "0xB2G_GOV_ISSUER", "0xAGENT_X_MINT"}
    BLOCKLIST: set = {"0xPHISHING_SCAMMER", "0xDUST_ATTACKER", "0xFAKE_ISSUER"}
    PHISHING_PATTERNS: List[str] = ["phishing", "fake", "scam", "claim_reward", "free_mint", "airdrop_claim"]
    GRADING_THRESHOLDS: dict = {"MINT": 95, "EXCELLENT": 80, "GOOD": 60, "FAIR": 40}
    CERTIFICATE_VALIDITY_YEARS: int = 1
    MAX_RETRIES: int = 3


# ============================================================
# Logger
# ============================================================


class JSONLogger:
    def __init__(self, agent_name: str = "vault", user_id: str = "default"):
        self.agent_name, self.user_id = agent_name, user_id
        self.log_path = VaultConfig.LOG_DIR / f"vault_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    def _write(self, level: str, msg: str, **extra) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": level,
                 "agent": self.agent_name, "user_id": self.user_id, "message": msg, **extra}
        with open(self.log_path, "a") as f: f.write(json.dumps(entry, default=str) + "\n")
    def info(self, m, **kw): self._write("INFO", m, **kw)
    def warn(self, m, **kw): self._write("WARN", m, **kw)
    def error(self, m, **kw): self._write("ERROR", m, **kw)


_ok = lambda jid, artifacts=None, **kw: {"status": "completed", "job_id": jid, "artifacts": artifacts or [], "error": None, "logs": [], **kw}
_fail = lambda jid, err, **kw: {"status": "failed", "job_id": jid, "artifacts": [], "error": err, "logs": [{"level": "ERROR", "message": err}], **kw}


# ============================================================
# 🛡️ S1: IssuerVerificationAgent
# ============================================================


class IssuerVerificationAgent:
    """Prueft Issuer-Signaturen gegen Whitelist & Blocklist."""

    def __init__(self):
        self.whitelist = VaultConfig.WHITELIST
        self.blocklist = VaultConfig.BLOCKLIST
        self._verified_count = 0
        self._blocked_count = 0

    def verify(self, stamp_nft: dict) -> bool:
        issuer = stamp_nft.get("issuer_signature", stamp_nft.get("issuer", ""))
        if issuer in self.blocklist:
            self._blocked_count += 1
            return False
        if issuer in self.whitelist:
            self._verified_count += 1
            return True
        return False

    def add_to_whitelist(self, issuer: str) -> bool:
        self.whitelist.add(issuer)
        return True

    def add_to_blocklist(self, issuer: str) -> bool:
        self.blocklist.add(issuer)
        return True

    def get_stats(self) -> dict:
        return {"verified": self._verified_count, "blocked": self._blocked_count,
                "whitelist_size": len(self.whitelist), "blocklist_size": len(self.blocklist)}


# ============================================================
# 🚫 S2: QuarantineManagerAgent
# ============================================================


class QuarantineManagerAgent:
    """Isoliert unverifizierte Marken in Quarantaene-Vault."""

    def __init__(self):
        self._quarantine: List[dict] = []
        self._released_count = 0

    def move_to_quarantine(self, stamp_nft: dict, reason: str = "UNVERIFIED_ISSUER") -> dict:
        entry = {"stamp": stamp_nft, "reason": reason, "quarantined_at": datetime.now(timezone.utc).isoformat(),
                 "quarantine_id": str(uuid.uuid4())[:8]}
        self._quarantine.append(entry)
        return {"status": "QUARANTINED", "quarantine_id": entry["quarantine_id"], "reason": reason,
                "quarantine_size": len(self._quarantine)}

    def list_quarantine(self) -> List[dict]:
        return self._quarantine

    def release_from_quarantine(self, quarantine_id: str, target_album: List[dict]) -> bool:
        for idx, item in enumerate(self._quarantine):
            if item["quarantine_id"] == quarantine_id:
                target_album.append(item["stamp"])
                self._quarantine.pop(idx)
                self._released_count += 1
                return True
        return False

    def get_stats(self) -> dict:
        return {"quarantined": len(self._quarantine), "released": self._released_count}


# ============================================================
# 🔥 S3: BurnAgent
# ============================================================


class BurnAgent:
    """Erkennt Phishing-Muster und loescht gefaehrliche Marken permanent."""

    def __init__(self):
        self._burned_count = 0
        self._phishing_detected = 0

    def detect_phishing(self, stamp_nft: dict) -> bool:
        meta = str(stamp_nft.get("metadata", "")).lower()
        desc = str(stamp_nft.get("description", "")).lower()
        combined = meta + desc
        for pattern in VaultConfig.PHISHING_PATTERNS:
            if pattern in combined:
                self._phishing_detected += 1
                return True
        return False

    def burn(self, stamp_id: str, *collections: List[dict]) -> dict:
        burn_tx = "0x" + hashlib.sha256(f"burn:{stamp_id}:{time.time()}".encode()).hexdigest()
        for collection in collections:
            for idx, item in enumerate(collection):
                sid = item.get("stamp_id", item.get("stamp", {}).get("stamp_id", ""))
                if sid == stamp_id:
                    del collection[idx]
                    self._burned_count += 1
                    return {"status": "BURNED", "stamp_id": stamp_id, "burn_tx_hash": burn_tx}
        return {"status": "NOT_FOUND", "stamp_id": stamp_id}

    def get_stats(self) -> dict:
        return {"burned": self._burned_count, "phishing_detected": self._phishing_detected}


# ============================================================
# 🔄 T1: AtomicSwapExecutorAgent
# ============================================================


class AtomicSwapExecutorAgent:
    """Fuehrt atomare Marke-gegen-Marke-Tauschs aus."""

    def __init__(self):
        self._swap_history: List[dict] = []

    def execute(self, sender: str, my_stamp_id: str, target: str, their_stamp_id: str,
                cash_delta_agx: float = 0.0) -> dict:
        tx_hash = "0x" + hashlib.sha256(f"{my_stamp_id}:{their_stamp_id}:{cash_delta_agx}:{time.time()}".encode()).hexdigest()
        swap_record = {
            "status": "ATOMIC_SWAP_COMPLETED",
            "swap_id": str(uuid.uuid4())[:8],
            "parties": {"initiator": sender, "counterparty": target},
            "exchanged": {"sent": my_stamp_id, "received": their_stamp_id, "cash_delta_agx": cash_delta_agx},
            "tx_hash": tx_hash,
            "escrow_verified": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._swap_history.append(swap_record)
        return swap_record

    def get_history(self) -> List[dict]:
        return self._swap_history


# ============================================================
# 📋 T2: OfferAgent
# ============================================================


class OfferAgent:
    """Erstellt OTC-Angebote fuer spezifische .b2g-Identitaeten."""

    def __init__(self):
        self._offers: Dict[str, dict] = {}

    def create_offer(self, sender: str, offered_stamp_id: str, target_b2g: str,
                     desired_stamp_id: str = "", cash_delta_agx: float = 0.0) -> dict:
        offer_id = hashlib.sha256(f"{sender}:{offered_stamp_id}:{target_b2g}:{time.time()}".encode()).hexdigest()[:16]
        offer = {
            "offer_id": offer_id,
            "sender": sender,
            "target_b2g": target_b2g,
            "offered_stamp": offered_stamp_id,
            "desired_stamp": desired_stamp_id,
            "cash_delta_agx": cash_delta_agx,
            "status": "PENDING",
            "created": datetime.now(timezone.utc).isoformat(),
        }
        self._offers[offer_id] = offer
        return offer

    def get_pending_offers(self, target_b2g: str) -> List[dict]:
        return [o for o in self._offers.values() if o["target_b2g"] == target_b2g and o["status"] == "PENDING"]

    def accept_offer(self, offer_id: str) -> dict:
        if offer_id in self._offers:
            self._offers[offer_id]["status"] = "ACCEPTED"
            return {"status": "ACCEPTED", "offer": self._offers[offer_id]}
        return {"status": "NOT_FOUND"}

    def cancel_offer(self, offer_id: str) -> dict:
        if offer_id in self._offers:
            self._offers[offer_id]["status"] = "CANCELLED"
            return {"status": "CANCELLED"}
        return {"status": "NOT_FOUND"}


# ============================================================
# 📊 T3: TradeMonitorAgent
# ============================================================


class TradeMonitorAgent:
    """Protokolliert alle Trades und prueft Escrow-Status."""

    def __init__(self):
        self._trade_log: List[dict] = []

    def log_trade(self, trade_record: dict) -> dict:
        entry = {"log_id": str(uuid.uuid4())[:8], "trade": trade_record,
                 "logged_at": datetime.now(timezone.utc).isoformat()}
        self._trade_log.append(entry)
        return entry

    def get_history(self, limit: int = 50) -> List[dict]:
        return self._trade_log[-limit:]

    def verify_escrow(self, tx_hash: str) -> dict:
        verified = tx_hash.startswith("0x") and len(tx_hash) >= 66
        return {"tx_hash": tx_hash, "escrow_verified": verified, "checked_at": datetime.now(timezone.utc).isoformat()}

    def get_stats(self) -> dict:
        return {"total_trades": len(self._trade_log), "recent_trades_24h": sum(
            1 for t in self._trade_log if (datetime.now(timezone.utc) - pd.parse_ts(t.get("logged_at", ""))).days < 1)}


# ============================================================
# 🔍 P1: ProvenanceTrackerAgent
# ============================================================


class ProvenanceTrackerAgent:
    """Verfolgt Herkunftskette via Hash-Chain und prueft Echtheit."""

    def track(self, stamp_nft: dict) -> bool:
        chain = stamp_nft.get("provenance_chain", [])
        if not chain:
            return False
        for link in chain:
            if not self._verify_link(link):
                return False
        return True

    def _verify_link(self, link: dict) -> bool:
        link_hash = link.get("hash", "")
        return bool(link_hash) and (link_hash.startswith("0x") or len(link_hash) >= 32)

    def append_provenance(self, stamp_nft: dict, new_owner: str, tx_hash: str) -> dict:
        chain = stamp_nft.get("provenance_chain", [])
        link = {"owner": new_owner, "tx_hash": tx_hash, "timestamp": datetime.now(timezone.utc).isoformat(),
                "hash": hashlib.sha256(f"{new_owner}:{tx_hash}:{time.time()}".encode()).hexdigest()}
        chain.append(link)
        stamp_nft["provenance_chain"] = chain
        return {"stamp_id": stamp_nft.get("stamp_id"), "provenance_depth": len(chain), "new_link": link}


# ============================================================
# 📄 P2: GradingAgent
# ============================================================


class GradingAgent:
    """Bewertet Zustand/Qualitaet der Marke: MINT, EXCELLENT, GOOD, FAIR, POOR."""

    def evaluate(self, stamp_nft: dict) -> str:
        quality = stamp_nft.get("quality_score", stamp_nft.get("rarity_score", 50))
        thresholds = VaultConfig.GRADING_THRESHOLDS
        if quality >= thresholds["MINT"]: return "MINT"
        elif quality >= thresholds["EXCELLENT"]: return "EXCELLENT"
        elif quality >= thresholds["GOOD"]: return "GOOD"
        elif quality >= thresholds["FAIR"]: return "FAIR"
        return "POOR"

    def explain_grade(self, stamp_nft: dict) -> dict:
        grade = self.evaluate(stamp_nft)
        factors = {"rarity": stamp_nft.get("rarity", "COMMON"),
                   "age_days": (datetime.now(timezone.utc) - pd.parse_ts(stamp_nft.get("mint_date", ""))).days if stamp_nft.get("mint_date") else 0,
                   "has_postmark": bool(stamp_nft.get("postmark")),
                   "provenance_depth": len(stamp_nft.get("provenance_chain", [])),
                   "quality_score": stamp_nft.get("quality_score", 50)}
        return {"stamp_id": stamp_nft.get("stamp_id"), "grade": grade, "factors": factors}


# ============================================================
# 🧾 P3: CertificateGeneratorAgent
# ============================================================


class CertificateGeneratorAgent:
    """Erstellt kryptografischen Echtheits- & Zustandspass."""

    def generate(self, stamp_nft: dict, grade: str) -> dict:
        provenance = json.dumps(stamp_nft.get("provenance_chain", []), sort_keys=True, default=str)
        cert_hash = hashlib.sha256(f"{stamp_nft.get('stamp_id')}:{grade}:{provenance}:{time.time()}".encode()).hexdigest()
        cert = {
            "certificate_id": f"CERT-{cert_hash[:12]}",
            "stamp_id": stamp_nft.get("stamp_id"),
            "grade": grade,
            "rarity": stamp_nft.get("rarity", "COMMON"),
            "issuer": stamp_nft.get("issuer_signature", stamp_nft.get("issuer", "UNKNOWN")),
            "certificate_hash": "0x" + cert_hash,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "valid_until": (datetime.now(timezone.utc).replace(
                year=datetime.now(timezone.utc).year + VaultConfig.CERTIFICATE_VALIDITY_YEARS)).isoformat(),
            "signer": "Agent X Philately Authority",
        }
        return cert

    def verify_certificate(self, certificate: dict) -> bool:
        now = datetime.now(timezone.utc)
        valid_until = pd.parse_ts(certificate.get("valid_until", ""))
        return now < valid_until if valid_until else True


# ============================================================
# Time parser helper
# ============================================================


class pd:
    @staticmethod
    def parse_ts(ts_str: str):
        try: return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError): return datetime.now(timezone.utc)


# ============================================================
# 🧠 MASTER: VaultCoordinator
# ============================================================


class VaultCoordinator:
    """Master-Agent: Orchestriert alle 8 Subagenten der Sammler-Wallet."""

    def __init__(self, owner_address: str):
        self.owner = owner_address
        self.logger = JSONLogger("VaultCoordinator", owner_address)
        self.main_album: List[dict] = []

        # 8 Subagenten
        self.issuer = IssuerVerificationAgent()
        self.quarantine = QuarantineManagerAgent()
        self.burner = BurnAgent()
        self.swapper = AtomicSwapExecutorAgent()
        self.offerer = OfferAgent()
        self.monitor = TradeMonitorAgent()
        self.provenance = ProvenanceTrackerAgent()
        self.grader = GradingAgent()
        self.certifier = CertificateGeneratorAgent()

        self.logger.info(f"VaultCoordinator initialized", owner=owner_address)

    def receive_incoming_stamp(self, stamp_nft: dict) -> dict:
        """Eingehende Marke: Issuer-Pruefung → Provenance → Grading → Album oder Quarantaene."""
        self.logger.info("Receiving stamp", stamp_id=stamp_nft.get("stamp_id"))

        # S1: Issuer verification
        if not self.issuer.verify(stamp_nft):
            self.logger.warn("Issuer not verified — quarantining", stamp_id=stamp_nft.get("stamp_id"))
            q_result = self.quarantine.move_to_quarantine(stamp_nft, "UNVERIFIED_ISSUER")
            return _ok("vault", artifacts=[{"action": "QUARANTINED", **q_result}])

        # P1: Provenance check
        if not self.provenance.track(stamp_nft):
            self.logger.warn("Provenance check failed — quarantining", stamp_id=stamp_nft.get("stamp_id"))
            q_result = self.quarantine.move_to_quarantine(stamp_nft, "FAILED_PROVENANCE")
            return _ok("vault", artifacts=[{"action": "QUARANTINED", **q_result}])

        # S3: Phishing check
        if self.burner.detect_phishing(stamp_nft):
            self.logger.alert("Phishing detected — burning", stamp_id=stamp_nft.get("stamp_id"))
            burn_result = self.burner.burn(stamp_nft.get("stamp_id", ""), self.main_album,
                                           *[q["stamp"] for q in self.quarantine._quarantine])
            return _ok("vault", artifacts=[{"action": "BURNED", **burn_result}])

        # P2: Grading
        grade = self.grader.evaluate(stamp_nft)
        stamp_nft["grade"] = grade

        # P1: Append provenance
        self.provenance.append_provenance(stamp_nft, self.owner, hashlib.sha256(str(time.time()).encode()).hexdigest())

        # P3: Certificate
        certificate = self.certifier.generate(stamp_nft, grade)
        stamp_nft["certificate"] = certificate

        # Add to main album
        self.main_album.append(stamp_nft)
        self.logger.info("Stamp accepted into main album", stamp_id=stamp_nft.get("stamp_id"), grade=grade)

        return _ok("vault", artifacts=[{"action": "ACCEPTED", "stamp_id": stamp_nft.get("stamp_id"),
                                         "grade": grade, "certificate": certificate,
                                         "album_size": len(self.main_album)}])

    def execute_trade(self, my_stamp_id: str, target_b2g: str, their_stamp_id: str,
                      cash_delta_agx: float = 0.0) -> dict:
        """Atomaren P2P-Tausch durchfuehren."""
        self.logger.info("Executing trade", my_stamp=my_stamp_id, target=target_b2g)
        swap_result = self.swapper.execute(self.owner, my_stamp_id, target_b2g, their_stamp_id, cash_delta_agx)
        self.monitor.log_trade(swap_result)
        # Transfer ownership in album
        for idx, s in enumerate(self.main_album):
            if s.get("stamp_id") == my_stamp_id:
                self.main_album.pop(idx)
                break
        return _ok("trade", artifacts=[swap_result])

    def create_offer(self, offered_stamp_id: str, target_b2g: str, desired_stamp_id: str = "",
                     cash_delta_agx: float = 0.0) -> dict:
        """OTC-Angebot fuer .b2g-Identitaet erstellen."""
        offer = self.offerer.create_offer(self.owner, offered_stamp_id, target_b2g, desired_stamp_id, cash_delta_agx)
        return _ok("offer", artifacts=[offer])

    def get_vault_status(self) -> dict:
        """Gesamtstatus des Vaults."""
        return _ok("status", artifacts=[{
            "owner": self.owner,
            "album_size": len(self.main_album),
            "album_stamps": [{"stamp_id": s.get("stamp_id"), "rarity": s.get("rarity"), "grade": s.get("grade")}
                           for s in self.main_album[-10:]],
            "issuer_stats": self.issuer.get_stats(),
            "quarantine_stats": self.quarantine.get_stats(),
            "burn_stats": self.burner.get_stats(),
            "trade_stats": self.monitor.get_stats(),
            "pending_offers": len(self.offerer.get_pending_offers(self.owner)),
        }])


# ============================================================
# CLI Entry Point
# ============================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  🏛️  PHILATELY COLLECTOR VAULT — Multi-Agent System")
    print("=" * 70)

    vault = VaultCoordinator(owner_address="kaemmerer.muenchen.b2g")

    # Demo 1: Legitime Marke empfangen
    legit_stamp = {
        "stamp_id": "STAMP-HIS-000001",
        "issuer_signature": "0xOFFICIAL_POST_AUTHORITY",
        "rarity": "LEGENDARY",
        "quality_score": 97,
        "provenance_chain": [{"owner": "original_minter", "tx_hash": "0xabc123", "hash": "0xVALID"}],
        "metadata": "Historische Meilenstein-Zahlung",
        "mint_date": "2026-08-01T00:00:00Z",
        "postmark": {"postmark_hash": "0xpm123"},
    }
    r1 = vault.receive_incoming_stamp(legit_stamp)
    a1 = r1["artifacts"][0]
    print(f"\n📬 Legitime Marke:")
    print(f"   Action: {a1['action']} | Grade: {a1['grade']} | Album: {a1['album_size']}")
    print(f"   Cert: {a1['certificate']['certificate_id']} ({a1['certificate']['grade']})")

    # Demo 2: Phishing-Marke
    phishing_stamp = {
        "stamp_id": "STAMP-FAKE-000099",
        "issuer_signature": "0xPHISHING_SCAMMER",
        "rarity": "COMMON",
        "quality_score": 10,
        "provenance_chain": [{"owner": "scammer", "tx_hash": "0xbad", "hash": "0xVALID"}],
        "metadata": "claim_reward free_mint",
        "description": "Click here to claim your free stamp",
    }
    r2 = vault.receive_incoming_stamp(phishing_stamp)
    a2 = r2["artifacts"][0]
    print(f"\n🚫 Phishing-Marke:")
    print(f"   Action: {a2['action']} | Reason: {a2.get('reason', a2.get('status', 'N/A'))}")

    # Demo 3: Trade
    trade = vault.execute_trade("STAMP-HIS-000001", "sammler.berlin.b2g", "STAMP-GEN-000001", cash_delta_agx=50.0)
    t = trade["artifacts"][0]
    print(f"\n🔄 Atomic Swap:")
    print(f"   Status: {t['status']} | TX: {t['tx_hash'][:20]}...")
    print(f"   Exchanged: {t['exchanged']['sent']} ↔ {t['exchanged']['received']} (+{t['exchanged']['cash_delta_agx']} $AGX)")

    # Demo 4: Vault Status
    status = vault.get_vault_status()
    s = status["artifacts"][0]
    print(f"\n📊 VAULT STATUS:")
    print(f"   Album: {s['album_size']} | Quarantined: {s['quarantine_stats']['quarantined']} | Burned: {s['burn_stats']['burned']}")
    print(f"   Issuer: {s['issuer_stats']['verified']} verified, {s['issuer_stats']['blocked']} blocked")
    print(f"   Trades: {s['trade_stats']['total_trades']} | Offers: {s['pending_offers']}")
    print("=" * 70)
