#!/usr/bin/env python3
"""
Shadow Execution Engine (SEE) — Paper-Trading-Satellit fuer den Agent X Hub.
===========================================================================

Trockenmodus-Satellit. Empfaengt Handelssignale (NewsBot / PolySentinel /
Agent X Hub), validiert sie gegen Orderbuch-Tiefe, fuehrt VIRTUELLE Orders aus
und verwaltet ein virtuelles Portfolio.

    Es gibt keinen echten Geldfluss. Es gibt keine Live-Execution.
    Es gibt kein Order-Relayer. Nur Messung.

CHARTER (bindend, hart erzwungen — nicht konfigurierbar):
    diagnostic_only = True
    live_execution  = False
    order_send      = False

Der Guard Rail ist absichtlich NICHT ueber Environment-Variablen steuerbar.
Env-Flags sind Betriebsparameter, keine Charter-Parameter. Wer die Charter
aendern will, aendert Code — und das faellt im Review auf.

Architektur (5 Schichten):
    1. PaperOrder            — Polymarket-CLOB-Payload + EIP-712-Mock-Verifikation
    2. MockPolySentinelFeed  — Orderbuch-Snapshots & Ticks (in Produktion: echte Tiefe)
    3. PaperMatchEngine      — Slippage, Partial Fills, Order-Status-Uebergaenge
    4. RiskController        — Pre-Trade-Checks, Drawdown-Lockout, Signal-Inversion
    5. ShadowExecutionEngine — Root: dry_run-Gate, Portfolio, Async-Pipeline

Konventionen (identisch zu agents_b2g/*):
    - Standardisierter JSON-Vertrag: {"status", "job_id", "artifacts", "error", "logs"}
    - JSONL-Log-Telemetrie unter logs/, Audit-Trail unter data/{user_id}/
    - `_safe_call`-Wrapper fuer Failsafe & Retry
    - Multi-Tenancy: alle Artefakte unter data/{user_id}/shadow/

Usage:
    python shadow_execution_engine.py             # Self-Test + Demo (offline)
    python shadow_execution_engine.py --selftest  # nur Charter-Assertions

Import:
    from shadow_execution_engine import ShadowExecutionEngine, PaperOrder

Author: Agent X Hub — Satellite Module
License: internal (diagnostic_only)
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import math
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
# ============================================================================
# 0. CHARTER & CONFIG
# ============================================================================

SEE_VERSION = "0.1.0"

# --- BINDENDE CHARTER -------------------------------------------------------
# Hart verdrahtet. Kein os.getenv an dieser Stelle. Punkt.
CHARTER_DIAGNOSTIC_ONLY: bool = True
CHARTER_LIVE_EXECUTION: bool = False
CHARTER_ORDER_SEND: bool = False

ORDER_SEND_ERROR = "order_send=false Charter-Verletzung"

# Preis-Quantisierung fuer Polymarket-CLOB (Tick Size 0.01 -> 2 Dezimalstellen)
PRICE_QUANTUM = Decimal("0.01")
SIZE_QUANTUM = Decimal("0.0001")

# EIP-712 Domain fuer den (gemockten) CLOB-Orderstruct.
# Die Type-Hash-Berechnung ist echt (keccak-analog via SHA-256-Ersatz), die
# Signaturpruefung ist ein deterministischer Mock — siehe MockEIP712Verifier.
EIP712_DOMAIN_NAME = "Polymarket CTF Exchange"
EIP712_DOMAIN_VERSION = "1"
EIP712_CHAIN_ID = 137  # Polygon Mainnet
EIP712_VERIFYING_CONTRACT = "0x0000000000000000000000000000000000000000"  # Mock
EIP712_ORDER_TYPE = (
    "Order(uint256 salt,address maker,address signer,address taker,"
    "uint256 tokenId,uint256 makerAmount,uint256 takerAmount,uint256 expiration,"
    "uint256 nonce,uint256 feeRateBps,uint8 side,uint8 signatureType)"
)
EIP712_ORDER_TYPE_HASH = hashlib.sha256(EIP712_ORDER_TYPE.encode()).hexdigest()
MOCK_SIGNER_ADDRESS = "0x" + "sha0" + "0" * 36  # deterministisch, nicht kryptographisch


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _q(value: Union[float, int, str, Decimal], quantum: Decimal = PRICE_QUANTUM) -> float:
    """Quantisiert auf CLOB-Tick-Groesse und gibt float zurueck (JSON-freundlich)."""
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def _bps(a: float, b: float) -> float:
    """Differenz in Basispunkten, robust gegen Division durch Null."""
    if b == 0:
        return 0.0 if a == 0 else float("inf")
    return round((a - b) / abs(b) * 10_000, 2)


class ShadowConfig:
    """Zentrale Konfiguration — durchgaengig env-steuerbar (Betriebsparameter).

    WARNUNG: Charter-Parameter (diagnostic_only/live_execution/order_send)
    stehen hier absichtlich NICHT. Sie sind Code-Konstanten.
    """

    # --- Pfade ---
    DATA_ROOT: Path = Path(os.getenv("SEE_DATA_ROOT", "data"))
    LOG_DIR: Path = Path(os.getenv("SEE_LOG_DIR", "logs"))

    # --- Ausfuehrung ---
    EXECUTION_MODE: str = os.getenv("SEE_EXECUTION_MODE", "dry-run")  # dry-run | paper-shadow
    TICK_SIZE: float = float(os.getenv("SEE_TICK_SIZE", "0.01"))
    MAX_BOOK_LEVELS: int = int(os.getenv("SEE_MAX_BOOK_LEVELS", "12"))
    MAX_ORDER_LATENCY_MS: float = float(os.getenv("SEE_MAX_ORDER_LATENCY_MS", "2500.0"))
    BOOK_STALENESS_MS: int = int(os.getenv("SEE_BOOK_STALENESS_MS", "2000"))

    # --- Slippage-Modell ---
    # lineare Impact-Komponente + Penny-Komponente + Marktstress-Multiplikator
    SLIPPAGE_LINEAR_COEF: float = float(os.getenv("SEE_SLIPPAGE_LINEAR_COEF", "0.5"))
    SLIPPAGE_PENNY_COEF: float = float(os.getenv("SEE_SLIPPAGE_PENNY_COEF", "0.004"))
    SLIPPAGE_STRESS_MULTIPLIER: float = float(os.getenv("SEE_SLIPPAGE_STRESS_MULTIPLIER", "2.5"))
    MAX_SLIPPAGE_BPS: float = float(os.getenv("SEE_MAX_SLIPPAGE_BPS", "250.0"))
    TAKER_FEE_BPS: float = float(os.getenv("SEE_TAKER_FEE_BPS", "0.0"))  # Polymarket: 0 bps

    # --- Risiko ---
    DEFAULT_MAX_POSITION_USD: float = float(os.getenv("SEE_MAX_POSITION_USD", "5000.0"))
    DEFAULT_MAX_EVENT_EXPOSURE_USD: float = float(os.getenv("SEE_MAX_EVENT_EXPOSURE_USD", "15000.0"))
    DEFAULT_MAX_CONCURRENT_POSITIONS: int = int(os.getenv("SEE_MAX_CONCURRENT_POSITIONS", "12"))
    MAX_DRAWDOWN_PCT: float = float(os.getenv("SEE_MAX_DRAWDOWN_PCT", "10.0"))
    RISK_WARN_PCT: float = float(os.getenv("SEE_RISK_WARN_PCT", "6.0"))
    DEFAULT_INVERT_SIGNALS: bool = os.getenv("SEE_INVERT_SIGNALS", "false").lower() == "true"

    # Signal-Inversion: unterhalb dieser rollierenden Trefferquote wird gedreht
    MIN_HIT_RATE_FOR_CONFIDENCE: float = float(os.getenv("SEE_MIN_HIT_RATE", "0.5"))
    HIT_RATE_WINDOW: int = int(os.getenv("SEE_HIT_RATE_WINDOW", "100"))
    MIN_SAMPLES_FOR_INVERSION: int = int(os.getenv("SEE_MIN_SAMPLES_FOR_INVERSION", "20"))
    ALLOW_INVERSION_BY_HOST_FLAG: bool = os.getenv("SEE_ALLOW_HOST_INVERSION", "false").lower() == "true"

    # --- Portfolio ---
    INITIAL_BANKROLL_USD: float = float(os.getenv("SEE_INITIAL_BANKROLL_USD", "100000.0"))

    # --- Retry / Failsafe ---
    MAX_RETRIES: int = int(os.getenv("SEE_MAX_RETRIES", "3"))
    RETRY_BACKOFF_BASE_S: float = float(os.getenv("SEE_RETRY_BACKOFF_S", "0.25"))

    @classmethod
    def charter_digest(cls) -> str:
        """Fingerabdruck der Charter-Konstanten fuer den Audit-Trail."""
        return hashlib.sha256(
            f"{CHARTER_DIAGNOSTIC_ONLY}|{CHARTER_LIVE_EXECUTION}|{CHARTER_ORDER_SEND}".encode()
        ).hexdigest()[:16]


# ============================================================================
# 1. TELEMETRIE: JSONL-Logger + Standard-JSON-Vertrag
# ============================================================================


class JSONLogger:
    """Strukturiertes JSONL-Logging, thread-safe (Konvention: agents_b2g)."""

    def __init__(self, agent_name: str = "shadow", user_id: str = "default", log_dir: Optional[Path] = None):
        self.agent_name = agent_name
        self.user_id = user_id
        self._lock = RLock()
        base = Path(log_dir) if log_dir is not None else Path(ShadowConfig.LOG_DIR)
        self.log_path = base / f"shadow_{datetime.now(timezone.utc).strftime('%Y%m%d')}.jsonl"
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Read-only-Umgebung: Telemetrie degradiert, Ausfuehrung nicht.
            self.log_path = Path(os.devnull)

    def _write(self, level: str, msg: str, **extra: Any) -> None:
        entry = {
            "timestamp": _now_iso(),
            "level": level,
            "agent": self.agent_name,
            "user_id": self.user_id,
            "message": msg,
            **extra,
        }
        try:
            with self._lock:
                with open(self.log_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass  # Telemetrie darf niemals die Simulation toeten.

    def info(self, m: str, **kw: Any) -> None:
        self._write("INFO", m, **kw)

    def warn(self, m: str, **kw: Any) -> None:
        self._write("WARN", m, **kw)

    def error(self, m: str, **kw: Any) -> None:
        self._write("ERROR", m, **kw)

    def audit(self, m: str, **kw: Any) -> None:
        self._write("AUDIT", m, **kw)


class OrderSendAttempted(PermissionError):
    """Spezialisierter Charter-Verstoss. Erbt von PermissionError (Charter-Vertrag)."""


def _ok(jid: str, artifacts: Optional[List[Any]] = None, **extra: Any) -> Dict[str, Any]:
    return {"status": "completed", "job_id": jid, "artifacts": artifacts or [], "error": None, "logs": [], **extra}


def _fail(jid: str, err: str, **extra: Any) -> Dict[str, Any]:
    return {
        "status": "failed",
        "job_id": jid,
        "artifacts": [],
        "error": err,
        "logs": [{"level": "ERROR", "message": err}],
        **extra,
    }


def _blocked(jid: str, reason: str, **extra: Any) -> Dict[str, Any]:
    """Risk-/Charter-Blockade — kein Fehler, sondern ein korrektes Ergebnis."""
    return {
        "status": "blocked",
        "job_id": jid,
        "artifacts": [],
        "error": None,
        "logs": [{"level": "INFO", "message": reason}],
        **extra,
    }


def _skipped(jid: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {
        "status": "skipped",
        "job_id": jid,
        "artifacts": [],
        "error": None,
        "logs": [{"level": "INFO", "message": reason}],
        **extra,
    }


def _safe_call(logger: JSONLogger, node: str, fn: Callable[..., Any], *a: Any, **kw: Any) -> Dict[str, Any]:
    """Failsafe & Retry-Wrapper. Charter-Verstoesse werden NICHT retried."""
    jid = str(uuid.uuid4())[:8]
    start = time.monotonic()
    logger.info(f"[{node}] started", job_id=jid)
    last: Optional[BaseException] = None
    for attempt in range(1, ShadowConfig.MAX_RETRIES + 1):
        try:
            r = fn(*a, **kw)
            dur = round((time.monotonic() - start) * 1000, 1)
            logger.info(f"[{node}] completed", job_id=jid, duration_ms=dur, attempt=attempt)
            std = {"completed", "failed", "started", "skipped", "blocked"}
            if isinstance(r, dict) and r.get("status") in std:
                r["job_id"] = r.get("job_id", jid)
                return r
            return _ok(jid, artifacts=[r] if r is not None else [])
        except (OrderSendAttempted, PermissionError):
            # Charter-Verletzung: sofort durchreichen, niemals wiederholen.
            logger.error(f"[{node}] CHARTER-VERLETZUNG — kein Retry", job_id=jid)
            raise
        except Exception as exc:  # noqa: BLE001 — Failsafe-Grenze
            last = exc
            logger.warn(f"[{node}] attempt {attempt} failed: {exc}", job_id=jid)
            if attempt < ShadowConfig.MAX_RETRIES:
                time.sleep(ShadowConfig.RETRY_BACKOFF_BASE_S * (2 ** (attempt - 1)))
    logger.error(f"[{node}] failed: {last}", job_id=jid)
    return _fail(jid, str(last))


async def _maybe_await(value: Union[Awaitable[Any], Any]) -> Any:
    """Erlaubt sync- UND async-Handler an derselben Grenze (kein asyncio.run im Loop!)."""
    if inspect.isawaitable(value):
        return await value
    return value


# --- HARDCODED GUARD RAIL ---------------------------------------------------


class DryRunGuard:
    """Hartes, unumgehbares Safety Gate.

    Jeder Pfad, der ein Order-Relayer-Netzwerk kontaktieren wuerde, laeuft durch
    `assert_dry_run`. Das Charter-Flag ist eine Code-Konstante und wird bei jedem
    Aufruf erneut gelesen — eine Manipulation von aussen (Monkeypatching) wird
    beim naechsten Aufruf erkannt.

    Verstoesse loesen NIEMALS eine Netzwerkaktion aus: die Pruefung liegt VOR
    jedem Call und wirft.
    """

    BLOCKED_MODULES: Tuple[str, ...] = (
        "httpx",
        "aiohttp",
        "requests",
        "urllib.request",
        "urllib3",
        "websockets",
        "websocket",
        "ws",
        "clob_client",
        "eth_account",
    )

    def __init__(self, logger: JSONLogger, enabled: bool = True) -> None:
        self.logger = logger
        self.enabled = enabled
        self.violations: List[Dict[str, Any]] = []
        self.blocked_calls = 0

    @property
    def dry_run(self) -> bool:
        """Wird bei jedem Zugriff aus den Charter-Konstanten NEU berechnet."""
        return bool(CHARTER_DIAGNOSTIC_ONLY and not CHARTER_LIVE_EXECUTION and not CHARTER_ORDER_SEND)

    def assert_dry_run(self, context: str, target: str = "") -> None:
        """Wirft OrderSendAttempted, wenn irgendein Pfad Live-Ausfuehrung anstrebt."""
        if not self.enabled:
            return
        if not self.dry_run:
            self._violation(context, target, "dry_run-Integritaet verletzt (Charter-Konstante manipuliert)")
            raise OrderSendAttempted(ORDER_SEND_ERROR)
        if CHARTER_ORDER_SEND:
            self._violation(context, target, "order_send=true")
            raise OrderSendAttempted(ORDER_SEND_ERROR)
        if CHARTER_LIVE_EXECUTION:
            self._violation(context, target, "live_execution=true")
            raise OrderSendAttempted(ORDER_SEND_ERROR)

    def inspect_caller(self, context: str, depth: int = 6) -> None:
        """Statische Analyse der Aufrufkette: kein HTTP/WS-Client im Pfad.

        Zweite Verteidigungslinie. Selbst wenn jemand einen echten HTTP-Call
        einschmuggelt, ohne `assert_dry_run` zu passieren, faellt es hier auf.
        """
        if not self.enabled:
            return
        frame = inspect.currentframe()
        hops = 0
        try:
            while frame is not None and hops < depth:
                module = frame.f_globals.get("__name__", "")
                for blocked in self.BLOCKED_MODULES:
                    if module == blocked or module.startswith(f"{blocked}."):
                        self._violation(context, module, f"Live-Netzwerk-Modul in Aufrufkette: {module}")
                        raise OrderSendAttempted(ORDER_SEND_ERROR)
                frame = frame.f_back
                hops += 1
        finally:
            del frame  # Referenzzyklus vermeiden

    def _violation(self, context: str, target: str, reason: str) -> None:
        self.blocked_calls += 1
        record = {
            "timestamp": _now_iso(),
            "context": context,
            "target": target,
            "reason": reason,
            "charter": self.charter_state(),
        }
        self.violations.append(record)
        self.logger.error("CHARTER-VERLETZUNG: order_send=false", **record)

    def charter_state(self) -> Dict[str, Any]:
        return {
            "diagnostic_only": CHARTER_DIAGNOSTIC_ONLY,
            "live_execution": CHARTER_LIVE_EXECUTION,
            "order_send": CHARTER_ORDER_SEND,
            "dry_run": self.dry_run,
            "digest": ShadowConfig.charter_digest(),
            "see_version": SEE_VERSION,
        }

    def reject_forbidden_transport(self, transport: str) -> None:
        """Expliziter Abbruchpfad — wird von jeder Netzwerk-Bruecke aufgerufen."""
        self._violation("reject_forbidden_transport", transport, "Live-Transport angefordert")
        raise OrderSendAttempted(ORDER_SEND_ERROR)

# ============================================================================
# 2. ORDER FRAMING & VALIDATION (PaperOrder)
# ============================================================================


class OrderSide(str, Enum):
    """CLOB-Side. Polymarket kodiert BUY als 0, SELL als 1."""

    BUY = "BUY"
    SELL = "SELL"

    @property
    def clob_code(self) -> int:
        return 0 if self is OrderSide.BUY else 1

    @property
    def opposite(self) -> "OrderSide":
        return OrderSide.SELL if self is OrderSide.BUY else OrderSide.BUY


class OrderType(str, Enum):
    GTC = "GTC"
    GTD = "GTD"
    FOK = "FOK"
    FAK = "FAK"


class OrderStatus(str, Enum):
    """Order-Status-Uebergaenge: PENDING -> FILLED/PARTIAL -> CLOSED."""

    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class SignatureType(str, Enum):
    EOA = "EOA"
    POLY_PROXY = "POLY_PROXY"
    POLY_GNOSIS_SAFE = "POLY_GNOSIS_SAFE"

    @property
    def clob_code(self) -> int:
        return {"EOA": 0, "POLY_PROXY": 1, "POLY_GNOSIS_SAFE": 2}[self.value]


class Fill(BaseModel):
    """Ein einzelner (virtueller) Teilmatch."""

    model_config = ConfigDict(frozen=True)

    fill_id: str = Field(default_factory=lambda: f"fill-{uuid.uuid4().hex[:10]}")
    level_index: int
    price: float
    size: float
    notional_usd: float
    fee_usd: float = 0.0
    slippage_bps: float = 0.0
    timestamp: str = Field(default_factory=_now_iso)


class MockEIP712Verifier:
    """Mock-Implementierung einer EIP-712-Signaturpruefung (rein offline).

    Zweck: Formatvalidierung des CLOB-Orders ohne Netzwerk, ohne Private Key,
    ohne Relayer. Der erzeugte Hash ist deterministisch und nachvollziehbar —
    er ist KEINE kryptographische Signatur und wird nie verifiziert gegen einen
    echten Verifying Contract.

    Die drei Pruefungen sind echte Pruefungen:
      A. Digest-Wiedergewinnung: stimmt die Signatur zum Payload? (deterministisch)
      B. Adress-Format: 0x + 40 Hex-Zeichen
      C. Domain-Bindung: chainId/verifyingContract muessen zur CLOB-Domain passen
    """

    EXTERNAL_SIGNER = "external"

    def __init__(self, verifying_contract: str = EIP712_VERIFYING_CONTRACT, chain_id: int = EIP712_CHAIN_ID):
        self.verifying_contract = verifying_contract
        self.chain_id = chain_id

    @staticmethod
    def _canonical_address(seed: str) -> str:
        """Deterministische 20-Byte-Adresse aus einem Seed (0x + 40 hex)."""
        return "0x" + hashlib.sha256(f"ADDR|{seed}".encode()).hexdigest()[:40]

    @staticmethod
    def derive_maker(signer: str, signature_type: "SignatureType") -> str:
        """Polymarket-Realitaet: bei EOA ist maker == signer, bei Proxy/Safe ist
        maker der Funder (Proxy-Wallet) und signer der Schluessel-Inhaber."""
        if signature_type is SignatureType.EOA:
            return signer
        return MockEIP712Verifier._canonical_address(f"proxy|{signer}")

    # --- Domain & Struct-Hash ---

    def domain_separator(self) -> str:
        payload = (
            f"{EIP712_DOMAIN_NAME}|{EIP712_DOMAIN_VERSION}|{self.chain_id}|{self.verifying_contract}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def struct_hash(self, order: "PaperOrder") -> str:
        """Kanonischer Struct-Hash ueber die EIP-712-Felder des Orders."""
        fields = "|".join(
            str(x)
            for x in (
                order.salt,
                order.maker,
                order.signer,
                order.taker,
                order.token_id,
                order.maker_amount,
                order.taker_amount,
                order.expiration,
                order.nonce,
                order.fee_rate_bps,
                order.side.clob_code,
                order.signature_type.clob_code,
            )
        )
        return hashlib.sha256(f"{EIP712_ORDER_TYPE_HASH}|{fields}".encode()).hexdigest()

    def digest(self, order: "PaperOrder") -> str:
        """EIP-712-konformer Digest: keccak256(0x1901 || domainSeparator || structHash) — hier SHA-256."""
        return hashlib.sha256(
            bytes.fromhex("1901") + bytes.fromhex(self.domain_separator()) + bytes.fromhex(self.struct_hash(order))
        ).hexdigest()

    # --- Signatur (Mock) ---

    def sign(self, order: "PaperOrder", signer: Optional[str] = None) -> str:
        """Erzeugt eine deterministische Mock-Signatur (offline, ohne Private Key).

        Der Rueckgabewert kodiert die wiederzugewinnende Signer-Adresse:
            MOCK|0x<40 hex>|<digest-fragment>
        Damit ist die Digest-Wiedergewinnung eine echte, nachpruefbare Funktion —
        kein Zufallswert. `order.signer` bleibt dabei die Authoritaet.
        """
        signer_addr = signer or MockEIP712Verifier._canonical_address(self.EXTERNAL_SIGNER)
        digest = self.digest(order)
        return f"MOCK|{signer_addr}|{digest[:40]}"

    def recover(self, order: "PaperOrder", signature: str) -> Optional[str]:
        """Wiedergewinnung der Signer-Adresse aus der Mock-Signatur."""
        if not signature.startswith("MOCK|"):
            return None
        parts = signature.split("|")
        if len(parts) != 3:
            return None
        return parts[1]

    # --- Verifikation ---

    def verify(self, order: "PaperOrder") -> Tuple[bool, List[str]]:
        """Prueft Format + Signatur. Rueckgabe: (ok, gruende_fuer_ablehnung)."""
        reasons: List[str] = []

        # B. Adressformate
        for label, addr in (("maker", order.maker), ("signer", order.signer), ("taker", order.taker)):
            if addr and not (addr.startswith("0x") and len(addr) == 42):
                reasons.append(f"{label}-Adresse ungueltig: {addr!r}")
        if not order.signature:
            reasons.append("signature fehlt")

        # C. Domain-Bindung
        if order.chain_id != self.chain_id:
            reasons.append(f"chain_id {order.chain_id} != Domain-chainId {self.chain_id}")
        if order.verifying_contract.lower() != self.verifying_contract.lower():
            reasons.append("verifying_contract passt nicht zur CLOB-Domain")

        # A. Digest-Wiedergewinnung
        if order.signature:
            recovered = self.recover(order, order.signature)
            if recovered is None:
                reasons.append("Signatur nicht dekodierbar (erwartet MOCK|<adresse>|<digest>)")
            elif recovered.lower() != order.signer.lower():
                reasons.append("Signatur matcht nicht den signer (Digest-Wiedergewinnung fehlgeschlagen)")

            # D. Maker/Signer-Konsistenz (Proxy-Typen erlauben abweichenden Funder)
            expected_maker = self.derive_maker(order.signer, order.signature_type)
            if order.maker.lower() != expected_maker.lower():
                reasons.append(
                    f"maker {order.maker} inkonsistent zu signer {order.signer} "
                    f"bei signatureType={order.signature_type.value}"
                )

        # Expiration
        if order.expiration and order.expiration < _now_ms():
            reasons.append(f"Order abgelaufen (expiration={order.expiration})")

        return (len(reasons) == 0), reasons


class PaperOrder(BaseModel):
    """CLOB-konformer Paper-Order mit Formatvalidierung und Mock-EIP-712-Pruefung.

    Das Modell ist absichtlich strikt (`extra="forbid"`): ein Tippfehler im
    Payload soll auffallen, nicht stillschweigend ignoriert werden.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    # --- Identitaet ---
    order_id: str = Field(default_factory=lambda: f"see-{uuid.uuid4().hex[:12]}")
    client_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    strategy: str = "unspecified"

    # --- CLOB-Payload ---
    token_id: str
    market_id: str = ""
    event_id: str = ""          # Gruppierung fuer Exposure-Limits
    price: float
    size: float
    side: OrderSide
    order_type: OrderType = OrderType.GTC
    outcome: str = "YES"
    neg_risk: bool = False

    # --- EIP-712-Felder (maker wird per model_validator an signer gekoppelt) ---
    salt: int = Field(default_factory=lambda: random.getrandbits(64))
    maker: Optional[str] = None
    signer: str = MOCK_SIGNER_ADDRESS
    taker: str = "0x0000000000000000000000000000000000000000"
    expiration: int = Field(default_factory=lambda: _now_ms() + 86_400_000)
    nonce: int = Field(default_factory=lambda: random.getrandbits(32))
    fee_rate_bps: int = 0
    signature_type: SignatureType = SignatureType.EOA
    signature: Optional[str] = None
    chain_id: int = EIP712_CHAIN_ID
    verifying_contract: str = EIP712_VERIFYING_CONTRACT

    # --- Risiko-Kontext (aus dem Signal) ---
    confidence: float = 1.0
    book_reference_price: Optional[float] = None
    book_snapshot_ts: Optional[int] = None
    created_at: str = Field(default_factory=_now_iso)

    # --- Status ---
    status: OrderStatus = OrderStatus.PENDING
    filled_size: float = 0.0
    avg_fill_price: float = 0.0
    slippage_bps: float = 0.0
    rejection_reason: Optional[str] = None
    inverted: bool = False
    dry_run: bool = True

    # --- Validatoren ---

    @field_validator("token_id")
    @classmethod
    def _token_id_nonempty(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("token_id darf nicht leer sein (CLOB-Pflichtfeld)")
        return str(v).strip()

    @field_validator("price")
    @classmethod
    def _price_in_range(cls, v: float) -> float:
        if not 0.0 < float(v) < 1.0:
            raise ValueError(f"price muss in (0, 1) liegen — Wahrscheinlichkeits-Share, war {v}")
        return _q(v)

    @field_validator("size")
    @classmethod
    def _size_positive(cls, v: float) -> float:
        if float(v) <= 0:
            raise ValueError(f"size muss > 0 sein, war {v}")
        return _q(v, SIZE_QUANTUM)

    @field_validator("confidence")
    @classmethod
    def _confidence_in_range(cls, v: float) -> float:
        if not 0.0 <= float(v) <= 1.0:
            raise ValueError(f"confidence muss in [0, 1] liegen, war {v}")
        return float(v)

    @model_validator(mode="after")
    def _finalize(self) -> "PaperOrder":
        # maker an signer koppeln (Proxy-Typen: abgeleiteter Funder)
        if self.maker is None:
            object.__setattr__(
                self, "maker", MockEIP712Verifier.derive_maker(self.signer, self.signature_type)
            )
        # Signatur automatisch erzeugen, falls nicht mitgeliefert (Mock-Modus).
        if self.signature is None:
            verifier = MockEIP712Verifier(self.verifying_contract, self.chain_id)
            object.__setattr__(self, "signature", verifier.sign(self, signer=self.signer))
        if self.book_reference_price is None:
            object.__setattr__(self, "book_reference_price", self.price)
        object.__setattr__(self, "dry_run", True)
        return self

    # --- Abgeleitete Groessen ---

    @property
    def notional_usd(self) -> float:
        return round(self.price * self.size, 6)

    @property
    def remaining_size(self) -> float:
        return round(max(self.size - self.filled_size, 0.0), 8)

    @property
    def is_open(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.PARTIAL)

    @property
    def fill_ratio(self) -> float:
        return 0.0 if self.size == 0 else round(self.filled_size / self.size, 6)

    @property
    def maker_amount(self) -> str:
        """CLOB: makerAmount in Base Units (6 Dezimalstellen)."""
        return str(int(round(self.notional_usd * 10**6)))

    @property
    def taker_amount(self) -> str:
        return str(int(round(self.size * 10**6)))

    # --- Serialisierung ---

    def to_clob_payload(self) -> Dict[str, Any]:
        """Polymarket-CLOB-konformer Order-Payload (String-kodierte Betraege)."""
        return {
            "order": {
                "salt": str(self.salt),
                "maker": self.maker,
                "signer": self.signer,
                "taker": self.taker,
                "tokenId": self.token_id,
                "makerAmount": self.maker_amount,
                "takerAmount": self.taker_amount,
                "expiration": str(self.expiration),
                "nonce": str(self.nonce),
                "feeRateBps": str(self.fee_rate_bps),
                "side": self.side.value,
                "signatureType": self.signature_type.clob_code,
                "signature": self.signature,
            },
            "owner": self.maker,
            "orderType": self.order_type.value,
            "clientOrderId": self.client_order_id,
            "dryRun": True,
            "diagnosticOnly": True,
        }

    def eip712_digest(self) -> str:
        verifier = MockEIP712Verifier(self.verifying_contract, self.chain_id)
        return verifier.digest(self)

    def verify_signature(self) -> Tuple[bool, List[str]]:
        """Offline-Formatpruefung. Kein Netzwerk, kein Relayer."""
        verifier = MockEIP712Verifier(self.verifying_contract, self.chain_id)
        return verifier.verify(self)

    def opposite(self) -> "PaperOrder":
        """Spiegelt den Order (fuer Signal-Inversion) — Preis wird komplementiert."""
        mirrored = self.model_copy(deep=True)
        object.__setattr__(mirrored, "side", self.side.opposite)
        object.__setattr__(mirrored, "price", _q(round(1.0 - self.price, 4)))
        object.__setattr__(mirrored, "inverted", True)
        object.__setattr__(mirrored, "status", OrderStatus.PENDING)
        object.__setattr__(mirrored, "filled_size", 0.0)
        object.__setattr__(mirrored, "avg_fill_price", 0.0)
        object.__setattr__(mirrored, "slippage_bps", 0.0)
        return mirrored

    def summarize(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "token_id": self.token_id,
            "event_id": self.event_id,
            "side": self.side.value,
            "price": self.price,
            "size": self.size,
            "filled_size": self.filled_size,
            "fill_ratio": self.fill_ratio,
            "avg_fill_price": self.avg_fill_price,
            "slippage_bps": self.slippage_bps,
            "notional_usd": self.notional_usd,
            "status": self.status.value,
            "inverted": self.inverted,
            "rejection_reason": self.rejection_reason,
        }

# ============================================================================
# 3. MARKTDATEN: Orderbuch-Snapshots aus PolySentinel
# ============================================================================


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float

    @property
    def notional(self) -> float:
        return round(self.price * self.size, 6)


@dataclass
class OrderBookSnapshot:
    """Orderbuch-Tiefe zu einem Token. In Produktion direkt von PolySentinel."""

    token_id: str
    market_id: str = ""
    event_id: str = ""
    outcome: str = "YES"
    bids: List[BookLevel] = field(default_factory=list)
    asks: List[BookLevel] = field(default_factory=list)
    tick_size: float = 0.01
    source: str = "polysentinel"
    snapshot_ts: int = field(default_factory=_now_ms)

    # --- Ableitungen ---

    @property
    def best_bid(self) -> Optional[float]:
        return max((lvl.price for lvl in self.bids), default=None)

    @property
    def best_ask(self) -> Optional[float]:
        return min((lvl.price for lvl in self.asks), default=None)

    @property
    def mid_price(self) -> Optional[float]:
        bb, ba = self.best_bid, self.best_ask
        if bb is None or ba is None:
            return bb if bb is not None else ba
        return _q((bb + ba) / 2)

    @property
    def spread_bps(self) -> float:
        bb, ba = self.best_bid, self.best_ask
        if bb is None or ba is None or bb <= 0:
            return 0.0
        return _bps(ba, bb)

    @property
    def age_ms(self) -> int:
        return max(_now_ms() - self.snapshot_ts, 0)

    @property
    def is_stale(self) -> bool:
        return self.age_ms > ShadowConfig.BOOK_STALENESS_MS

    def depth(self, side: OrderSide) -> List[BookLevel]:
        """asks = was wir kaufen koennen (BUY), bids = was wir verkaufen koennen (SELL)."""
        return self.asks if side is OrderSide.BUY else self.bids

    def total_depth_usd(self, side: OrderSide) -> float:
        return round(sum(lvl.notional for lvl in self.depth(side)), 6)

    def depth_at(self, side: OrderSide, price: float) -> float:
        """Kumulierte Tiefe bis zu einem Preis-Limit."""
        total = 0.0
        for lvl in self.depth(side):
            if side is OrderSide.BUY and lvl.price > price:
                break
            if side is OrderSide.SELL and lvl.price < price:
                break
            total += lvl.size
        return round(total, 8)

    def walk(self, side: OrderSide) -> List[BookLevel]:
        """Buch in Ausfuehrungsreihenfolge (best price first)."""
        levels = self.depth(side)
        return sorted(levels, key=lambda lvl: lvl.price, reverse=(side is OrderSide.SELL))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "market_id": self.market_id,
            "event_id": self.event_id,
            "outcome": self.outcome,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "mid_price": self.mid_price,
            "spread_bps": self.spread_bps,
            "tick_size": self.tick_size,
            "bid_depth_usd": self.total_depth_usd(OrderSide.SELL),
            "ask_depth_usd": self.total_depth_usd(OrderSide.BUY),
            "bid_levels": len(self.bids),
            "ask_levels": len(self.asks),
            "source": self.source,
            "snapshot_ts": self.snapshot_ts,
            "age_ms": self.age_ms,
        }


def build_synthetic_book(
    token_id: str,
    mid: float,
    *,
    market_id: str = "",
    event_id: str = "",
    outcome: str = "YES",
    levels: int = 10,
    tick: float = 0.01,
    depth_usd_per_level: float = 900.0,
    spread_ticks: int = 1,
    imbalance: float = 0.0,
    book_feed: Optional["MockPolySentinelFeed"] = None,
    seed: Optional[int] = None,
    age_ms: int = 0,
) -> OrderBookSnapshot:
    """Baut ein realistisches synthetisches Buch um einen Mid-Preis.

    `imbalance` verschiebt die Tiefe asymmetrisch (-1 = asks duenn, +1 = bids duenn),
    was Slippage in genau eine Richtung teurer macht — genau der Effekt, den die
    Shadow Engine sichtbar machen soll.
    """
    rng = random.Random(seed if seed is not None else hash(token_id) & 0xFFFF)
    mid = min(max(_q(mid), tick * (spread_ticks + 1)), 1.0 - tick * (spread_ticks + 1))
    half_spread = tick * spread_ticks / 2
    best_bid = _q(mid - half_spread)
    best_ask = _q(mid + half_spread)

    bids: List[BookLevel] = []
    asks: List[BookLevel] = []
    for i in range(levels):
        step = tick * i
        bid_price = _q(best_bid - step)
        ask_price = _q(best_ask + step)
        # Tiefe nimmt mit Distanz zum Mid zu (typisches CLOB-Profil) + Jitter
        growth = 1.0 + 0.22 * i
        jitter = rng.uniform(0.85, 1.15)
        bid_size = max(depth_usd_per_level * growth * jitter / max(bid_price, tick), 1.0)
        ask_size = max(depth_usd_per_level * growth * jitter / max(ask_price, tick), 1.0)
        if imbalance > 0:      # bids duenner, asks tiefer
            bid_size *= max(1.0 - imbalance, 0.1)
            ask_size *= 1.0 + imbalance
        elif imbalance < 0:    # asks duenner
            ask_size *= max(1.0 + imbalance, 0.1)
            bid_size *= 1.0 - imbalance
        if 0.0 < bid_price < 1.0:
            bids.append(BookLevel(price=bid_price, size=round(bid_size, 4)))
        if 0.0 < ask_price < 1.0:
            asks.append(BookLevel(price=ask_price, size=round(ask_size, 4)))

    return OrderBookSnapshot(
        token_id=token_id,
        market_id=market_id or f"mkt-{token_id[:8]}",
        event_id=event_id or f"evt-{token_id[:6]}",
        outcome=outcome,
        bids=bids,
        asks=asks,
        tick_size=tick,
        source="synthetic",
        snapshot_ts=_now_ms() - age_ms,
    )


class MockPolySentinelFeed:
    """Orderbuch-/Tick-Feed-Stand-in fuer PolySentinel.

    Zwei Betriebsarten:
      * `publish()`  — Push durch den Host (Produktion: echter PolySentinel-Snapshot)
      * `simulate_step()` — random-walk-Simulation fuer den Offline-Selbsttest

    In Produktion wuerde diese Klasse den Snapshot per NATS/WebSocket empfangen.
    Der Empfangspfad ist hier bewusst NICHT implementiert — das Modul darf kein
    Netzwerk oeffnen. Der Host injiziert Snapshots.
    """

    def __init__(self) -> None:
        self._books: Dict[str, OrderBookSnapshot] = {}
        self._ticks: Dict[str, List[Tuple[int, float]]] = {}
        self._lock = RLock()
        self.publish_count = 0
        self.simulated_steps = 0

    # --- Push (Produktionspfad, host-getrieben) ---

    def publish(self, snapshot: OrderBookSnapshot) -> OrderBookSnapshot:
        with self._lock:
            self._books[snapshot.token_id] = snapshot
            self.publish_count += 1
            mid = snapshot.mid_price
            if mid is not None:
                self._ticks.setdefault(snapshot.token_id, []).append((snapshot.snapshot_ts, mid))
        return snapshot

    def publish_dict(self, payload: Mapping[str, Any]) -> OrderBookSnapshot:
        """Nimmt ein PolySentinel-JSON an und normalisiert es zu einem Snapshot."""
        snap = self.from_payload(payload)
        return self.publish(snap)

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> OrderBookSnapshot:
        def _levels(raw: Iterable[Mapping[str, Any]]) -> List[BookLevel]:
            out: List[BookLevel] = []
            for lvl in raw or []:
                try:
                    price = float(lvl.get("price", lvl.get("p", 0)))
                    size = float(lvl.get("size", lvl.get("s", 0)))
                except (TypeError, ValueError):
                    continue
                if 0.0 < price < 1.0 and size > 0:
                    out.append(BookLevel(price=_q(price), size=round(size, 6)))
            return out

        return OrderBookSnapshot(
            token_id=str(payload.get("token_id", payload.get("tokenId", ""))),
            market_id=str(payload.get("market_id", payload.get("marketId", ""))),
            event_id=str(payload.get("event_id", payload.get("eventId", ""))),
            outcome=str(payload.get("outcome", "YES")),
            bids=_levels(payload.get("bids", [])),
            asks=_levels(payload.get("asks", [])),
            tick_size=float(payload.get("tick_size", payload.get("tickSize", 0.01))),
            source=str(payload.get("source", "polysentinel")),
            snapshot_ts=int(payload.get("snapshot_ts", payload.get("timestamp", _now_ms()))),
        )

    # --- Abruf ---

    def get_book(self, token_id: str, *, max_age_ms: Optional[int] = None) -> Optional[OrderBookSnapshot]:
        with self._lock:
            book = self._books.get(token_id)
        if book is None:
            return None
        limit = ShadowConfig.BOOK_STALENESS_MS if max_age_ms is None else max_age_ms
        if book.age_ms > limit:
            return None  # veraltetes Buch = keine Grundlage fuer eine Simulation
        return book

    def get_books(self, token_ids: Optional[Iterable[str]] = None) -> List[OrderBookSnapshot]:
        with self._lock:
            if token_ids is None:
                return list(self._books.values())
            return [self._books[t] for t in token_ids if t in self._books]

    def last_mid(self, token_id: str) -> Optional[float]:
        with self._lock:
            series = self._ticks.get(token_id) or []
        return series[-1][1] if series else None

    def price_series(self, token_id: str) -> List[Tuple[int, float]]:
        with self._lock:
            return list(self._ticks.get(token_id, []))

    def realized_vol_bps(self, token_id: str, window: int = 20) -> float:
        """Realisierte Volatilitaet aus den letzten Ticks (in bps) — Input fuer Slippage-Stress."""
        series = [p for _, p in self.price_series(token_id)[-window:]]
        if len(series) < 3:
            return 0.0
        rets = [
            (series[i] - series[i - 1]) / series[i - 1]
            for i in range(1, len(series))
            if series[i - 1] > 0
        ]
        if not rets:
            return 0.0
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
        return round(math.sqrt(var) * 10_000, 2)

    # --- Offline-Simulation (nur Selbsttest) ---

    def simulate_step(
        self,
        token_ids: Sequence[str],
        *,
        base_mids: Optional[Mapping[str, float]] = None,
        vol_bps: float = 35.0,
        depth_usd_per_level: float = 900.0,
        seed: Optional[int] = None,
    ) -> List[OrderBookSnapshot]:
        """Ein Random-Walk-Schritt pro Token. Kein Netzwerk, keine echten Daten."""
        rng = random.Random(seed)
        out: List[OrderBookSnapshot] = []
        for idx, token_id in enumerate(token_ids):
            prev = self.last_mid(token_id)
            if prev is None:
                prev = (base_mids or {}).get(token_id, 0.5)
            drift = rng.gauss(0, vol_bps / 10_000)
            mid = min(max(_q(prev * (1.0 + drift)), 0.02), 0.98)
            imbalance = rng.uniform(-0.35, 0.35)
            snap = build_synthetic_book(
                token_id,
                mid,
                event_id=self._books[token_id].event_id if token_id in self._books else "",
                levels=ShadowConfig.MAX_BOOK_LEVELS,
                depth_usd_per_level=depth_usd_per_level,
                imbalance=imbalance,
                seed=(seed or 0) * 1000 + idx,
            )
            out.append(self.publish(snap))
        self.simulated_steps += 1
        return out

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tracked_tokens": len(self._books),
                "publish_count": self.publish_count,
                "simulated_steps": self.simulated_steps,
                "tokens": sorted(self._books.keys()),
            }

# ============================================================================
# 4. MATCH ENGINE & SLIPPAGE-SIMULATION
# ============================================================================


class SlippageModel(str, Enum):
    """Slippage-Modell.

    NONE misst ausschliesslich (Spread-Kreuzung + exakter Buch-Walk) und
    modelliert KEINE Zusatzkosten. Das ist der Default, weil eine unkalibrierte
    Zusatzschaetzung im Paper-Trading die Ergebnisse still verfaelscht — sie
    sieht praezise aus und ist erfunden.

    Die anderen Modelle ADDIEREN eine bewusste, dokumentierte Zusatzkomponente
    (Adverse Selection, Queue-Verlust). Wer sie nutzt, kalibriert sie gegen
    echte Fill-Daten und benennt die Annahme im Bericht.
    """

    NONE = "none"
    LINEAR = "linear"                    # proportional zur Buch-Auslastung
    DEPTH_WEIGHTED = "depth_weighted"    # + Penny-/Level-Komponente
    STRESS = "stress"                    # + Volatilitaets-Multiplikator


class MatchResult(BaseModel):
    """Ergebnis eines Match-Versuchs inkl. Slippage-Zerlegung."""

    model_config = ConfigDict(extra="forbid")

    order_id: str
    status: OrderStatus
    requested_size: float
    filled_size: float = 0.0
    avg_price: float = 0.0
    reference_price: Optional[float] = None
    notional_usd: float = 0.0
    fee_usd: float = 0.0
    slippage_bps: float = 0.0
    slippage_components: Dict[str, float] = Field(default_factory=dict)
    levels_consumed: int = 0
    partial: bool = False
    book_age_ms: int = 0
    book_depth_usd: float = 0.0
    rejection_reason: Optional[str] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "status": self.status.value,
            "requested_size": self.requested_size,
            "filled_size": self.filled_size,
            "avg_price": self.avg_price,
            "reference_price": self.reference_price,
            "notional_usd": self.notional_usd,
            "fee_usd": self.fee_usd,
            "slippage_bps": self.slippage_bps,
            "slippage_components": self.slippage_components,
            "levels_consumed": self.levels_consumed,
            "partial": self.partial,
            "book_age_ms": self.book_age_ms,
            "book_depth_usd": self.book_depth_usd,
            "rejection_reason": self.rejection_reason,
            "diagnostics": self.diagnostics,
        }


class PaperMatchEngine:
    """Virtuelle Ausfuehrung gegen echte Orderbuch-Tiefe.

    Es wird NICHTS gesendet. Der Match ist eine reine Buch-Simulation:
    der Order walkt die Tiefe, jeder konsumierte Level erzeugt einen Fill.

    Status-Uebergaenge:
        PENDING  --(voll gefuellt)--> FILLED  --> CLOSED
        PENDING  --(teilweise)------> PARTIAL --> FILLED/PARTIAL/CLOSED
        PENDING  --(keine Tiefe)----> REJECTED
        PARTIAL  --(Rest gecancelt)--> CLOSED
    """

    def __init__(self, feed: MockPolySentinelFeed, logger: JSONLogger, guard: DryRunGuard) -> None:
        self.feed = feed
        self.logger = logger
        self.guard = guard
        self.match_count = 0
        self.total_slippage_bps_weighted = 0.0

    # --- Impact-Komponenten ---

    def _impact_components(
        self,
        book: OrderBookSnapshot,
        side: OrderSide,
        size: float,
        model: SlippageModel,
    ) -> Dict[str, float]:
        """Zerlegt den erwarteten Impact in nachvollziehbare Komponenten (bps).

        WICHTIG: Alle Komponenten werden am BUCH gemessen, nicht am Mid-Preis.
        Der haeufigste Modellierfehler ist, Slippage gegen den Mid zu rechnen —
        ein BUY, der genau auf dem Best-Ask liegt, hat dann 0 bps Slippage, obwohl
        er den halben Spread gezahlt hat. Gemessen wird daher gegen den
        ausfuehrbaren Referenzpreis (Ask beim Kauf, Bid beim Verkauf).
        """
        levels = book.walk(side)
        if not levels:
            return {
                "depth_utilization_frac": 0.0, "spread_bps": 0.0, "spread_cross_bps": 0.0,
                "walk_impact_bps": 0.0, "stress_multiplier": 1.0, "vol_bps": 0.0,
                "modeled_additional_bps": 0.0,
            }

        ref = levels[0].price  # best ask (BUY) / best bid (SELL) — die Ausfuehrungsbasis
        available = sum(lvl.size for lvl in levels)
        utilization = 0.0 if available <= 0 else min(size / available, 5.0)

        # (1) Spread-Kontext: der Spread ist NICHT Teil der Slippage. Ein BUY, der
        #     auf dem Best-Ask fillt, zahlt eine halbe Spread-Spanne gegenueber dem
        #     Mid — aber das ist der Preis des sofortigen Abschlusses, keine
        #     Verschlechterung gegenueber der eigenen Order-Referenz. Die Slippage
        #     misst ausschliesslich die Verschlechterung gegenueber `ref`.
        #     Der Spread wird als Kontextkomponente gefuehrt, damit Berichte ihn
        #     ausweisen koennen, ohne ihn mit Slippage zu vermischen.
        spread_cross_bps = 0.0
        mid = book.mid_price
        if mid and mid > 0:
            spread_cross_bps = abs(ref - mid) / mid * 10_000

        # (2) Walk-Impact: exakter Volumen-gewichteter Durchschnittspreis der konsumierten Level
        consumed_levels: List[Tuple[float, float]] = []
        remaining = size
        for lvl in levels:
            if remaining <= 0:
                break
            take = min(remaining, lvl.size)
            consumed_levels.append((lvl.price, take))
            remaining -= take
        walk_impact_bps = 0.0
        if consumed_levels:
            filled = sum(sz for _, sz in consumed_levels)
            vwap = sum(p * sz for p, sz in consumed_levels) / filled
            walk_impact_bps = (vwap - ref) / ref * 10_000
        # WICHTIG: `ref` ist der Best-Level. Fuer den Impact gegenueber dem Mid
        # addiert der Aufrufer die Spread-Komponente — hier bleibt es beim
        # reinen Walk-Aufschlag, damit die Komponenten sich nicht ueberlappen.
        walk_impact_bps = max(walk_impact_bps, 0.0)

        if model is SlippageModel.NONE:
            return {
                "depth_utilization_frac": round(utilization, 6), "spread_bps": round(book.spread_bps, 4),
                "spread_cross_bps": round(spread_cross_bps, 4), "walk_impact_bps": round(walk_impact_bps, 4),
                "stress_multiplier": 1.0, "vol_bps": 0.0, "modeled_additional_bps": 0.0,
            }

        # (3) Modellierte Zusatzkosten (Adverse Selection, Queue-Verlust, Latenz).
        #     Nur wenn EXPLIZIT ein Modell gewaehlt wurde — der Default (NONE)
        #     schaetzt nicht, er misst.
        model_coef = {
            SlippageModel.LINEAR: ShadowConfig.SLIPPAGE_LINEAR_COEF,
            SlippageModel.DEPTH_WEIGHTED: ShadowConfig.SLIPPAGE_LINEAR_COEF,
            SlippageModel.STRESS: ShadowConfig.SLIPPAGE_LINEAR_COEF + ShadowConfig.SLIPPAGE_PENNY_COEF,
        }.get(model, 0.0)
        modeled_additional_bps = utilization * model_coef * 100.0

        # (4) Stress: realisierte Volatilitaet skaliert die Zusatzkomponente
        stress_multiplier = 1.0
        vol_bps = 0.0
        if model is SlippageModel.STRESS:
            vol_bps = self.feed.realized_vol_bps(book.token_id)
            if vol_bps > 0:
                stress_multiplier = min(
                    1.0 + vol_bps / 100.0 * (ShadowConfig.SLIPPAGE_STRESS_MULTIPLIER - 1.0),
                    ShadowConfig.SLIPPAGE_STRESS_MULTIPLIER,
                )

        return {
            "depth_utilization_frac": round(utilization, 6),
            "spread_bps": round(book.spread_bps, 4),
            "spread_cross_bps": round(spread_cross_bps, 4),
            "walk_impact_bps": round(walk_impact_bps, 4),
            "stress_multiplier": round(stress_multiplier, 4),
            "vol_bps": vol_bps,
            "modeled_additional_bps": round(modeled_additional_bps, 4),
        }

    def preview_slippage(
        self,
        book: OrderBookSnapshot,
        order: PaperOrder,
        model: SlippageModel = SlippageModel.NONE,
    ) -> Dict[str, Any]:
        """Slippage-BUDGET (Unter-/Obergrenze) OHNE die Order zu mutieren.

        Warum ein Band und keine Zahl: der reale Fill-Preis liegt auf einem
        diskreten Tick-Raster, waehrend die Kostenrechnung kontinuierlich ist.
        Bei Tick 0,01 und Preis ~0,51 entspricht ein einziger Tick 196 bps —
        jeder Punktwert in diesem Bereich ist eine Scheingenauigkeit.

        Deshalb:
          * `lower_bps`  = Spread-Kreuzung + halber Tick (optimistischer Fall)
          * `upper_bps`  = Spread-Kreuzung + Walk-Impact + ganzer Tick + Zuschlag
          * `expected_slippage_bps` = der zentrale Schaetzwert (weiterhin die
            Zahl, gegen die das Risk-Budget geprueft wird)

        Der Cap (`MAX_SLIPPAGE_BPS`) wird NICHT auf die Messung angewandt, sondern
        nur als `exceeds_budget` berichtet — Kappen erzeugt aus einer Messung
        eine Stellungnahme.
        """
        comps = self._impact_components(book, order.side, order.size, model)
        ref = book.best_ask if order.side is OrderSide.BUY else book.best_bid
        direction = 1 if order.side is OrderSide.BUY else -1
        fillable = book.depth_at(order.side, order.price)
        full_fill = fillable >= order.size - 1e-9

        spread_bps = comps["spread_cross_bps"]
        walk_bps = comps["walk_impact_bps"]
        additional_bps = comps["modeled_additional_bps"] * comps["stress_multiplier"]
        quant_bps = (book.tick_size / ref * 10_000) if ref else 0.0

        # Gemessene Slippage = Verschlechterung gegenueber dem Best-Level.
        # Der Spread taucht hier absichtlich NICHT auf (siehe _impact_components).
        measured_bps = walk_bps + additional_bps
        if full_fill:
            lower_bps = 0.0
            upper_bps = walk_bps + additional_bps + quant_bps
        else:
            # Teilfuellung: nur der gefuellte Anteil traegt Kosten, der Rest ist
            # Opportunitaetskosten und wird separat ausgewiesen.
            ratio = fillable / order.size if order.size else 0.0
            lower_bps = 0.0
            upper_bps = (walk_bps + additional_bps) * ratio + quant_bps

        est_price = _q(ref * (1 + direction * measured_bps / 10_000)) if ref is not None else None
        return {
            "model": model.value,
            "reference_price": ref,
            "reference_label": "best_ask" if order.side is OrderSide.BUY else "best_bid",
            "estimated_avg_price": est_price,
            "expected_slippage_bps": round(measured_bps, 2),
            "slippage_band_bps": [round(lower_bps, 2), round(upper_bps, 2)],
            "walk_impact_bps": round(walk_bps, 2),
            "additional_slippage_bps": round(additional_bps, 2),
            "spread_context_bps": round(spread_bps, 2),
            "quantization_bps": round(quant_bps, 2),
            "slippage_components": comps,
            "fillable_size": round(fillable, 8),
            "fillable_ratio": round(fillable / order.size, 6) if order.size else 0.0,
            "full_fill": full_fill,
            "opportunity_cost_size": round(max(order.size - fillable, 0.0), 8),
            "book_depth_usd": book.total_depth_usd(order.side),
            "book_age_ms": book.age_ms,
            "exceeds_budget": measured_bps > ShadowConfig.MAX_SLIPPAGE_BPS,
            "budget_bps": ShadowConfig.MAX_SLIPPAGE_BPS,
        }

    # --- Fill-Walk ---

    def _walk_book(
        self, book: OrderBookSnapshot, order: PaperOrder
    ) -> Tuple[List[Fill], float, int]:
        """Konsumiert Buch-Tiefe limit-konform und liefert Fills, Rest und Level-Zahl."""
        limit = order.price
        side = order.side
        remaining = order.remaining_size if order.status is OrderStatus.PARTIAL else order.size
        fills: List[Fill] = []
        levels_used = 0

        for idx, level in enumerate(book.walk(side)):
            if remaining <= 0:
                break
            # Limit-Pruefung: BUY darf nicht teurer als price, SELL nicht billiger
            if side is OrderSide.BUY and level.price > limit:
                break
            if side is OrderSide.SELL and level.price < limit:
                break

            take = min(remaining, level.size)
            if take <= 0:
                continue
            notional = round(level.price * take, 6)
            fee = round(notional * ShadowConfig.TAKER_FEE_BPS / 10_000, 6)
            fills.append(
                Fill(
                    level_index=idx,
                    price=level.price,
                    size=round(take, 6),
                    notional_usd=notional,
                    fee_usd=fee,
                )
            )
            remaining = round(remaining - take, 8)
            levels_used += 1

        return fills, round(remaining, 8), levels_used

    # --- Match ---

    def match(
        self,
        order: PaperOrder,
        book: OrderBookSnapshot,
        *,
        model: SlippageModel = SlippageModel.NONE,
        allow_partial: bool = True,
    ) -> MatchResult:
        """Fuehrt eine virtuelle Order gegen das Buch aus (kein Senden, kein Netzwerk)."""
        # Erste Verteidigungslinie: Charter + Aufrufkette
        self.guard.assert_dry_run(f"PaperMatchEngine.match:{order.order_id}", order.token_id)
        self.guard.inspect_caller(f"PaperMatchEngine.match:{order.order_id}")

        ref = book.best_ask if order.side is OrderSide.BUY else book.best_bid
        depth_usd = book.total_depth_usd(order.side)

        # Order-Typ: FOK/FAK brechen bei fehlender Gesamttiefe ab
        available = book.depth_at(order.side, 1.0 if order.side is OrderSide.BUY else 0.0)
        if order.order_type is OrderType.FOK and available < order.size:
            result = MatchResult(
                order_id=order.order_id,
                status=OrderStatus.REJECTED,
                requested_size=order.size,
                reference_price=ref,
                rejection_reason=f"FOK: Tiefe {available:.4f} < Order {order.size:.4f}",
                book_age_ms=book.age_ms,
                book_depth_usd=depth_usd,
            )
            self._apply(order, result)
            return result

        fills, remaining, levels_used = self._walk_book(book, order)

        if not fills:
            result = MatchResult(
                order_id=order.order_id,
                status=OrderStatus.REJECTED,
                requested_size=order.size,
                reference_price=ref,
                rejection_reason="keine ausfuehrbare Tiefe innerhalb des Limits",
                book_age_ms=book.age_ms,
                book_depth_usd=depth_usd,
            )
            self._apply(order, result)
            return result

        filled = round(sum(f.size for f in fills), 8)
        notional = round(sum(f.notional_usd for f in fills), 6)
        fee = round(sum(f.fee_usd for f in fills), 6)
        avg_price = _q(notional / filled) if filled > 0 else 0.0

        # Slippage wird GEGEN DEN AUSFUEHRBAREN REFERENZPREIS gemessen, nicht gegen
        # den Mid. Ein BUY, der auf dem Best-Ask fuellt, hat 0 Slippage — aber der
        # halbe Spread ist bereits als Kosten im avg_price enthalten. Diese Trennung
        # ist wichtig: Spread-Kosten sind keine Slippage, sie sind der Preis des
        # sofortigen Abschlusses.
        slippage_realized_bps = _bps(avg_price, ref) if ref else 0.0
        # BUY: teurer als der Best-Ask = positive Slippage. SELL: billiger = positive Slippage.
        # MERKREGEL: Slippage ist immer eine VERSCHLECHTERUNG > 0, eine Verbesserung < 0.
        if order.side is OrderSide.SELL:
            slippage_realized_bps = -slippage_realized_bps
        # Spread ist Kontext (halbierter Spread gegenueber dem Mid), keine Kosten,
        # die die Slippage vergroessern. Beide Komponenten sind vorzeichenbehaftet:
        # negativ = guenstiger als die Referenz.
        spread_cross_bps = _bps(ref, book.mid_price) if (ref and book.mid_price) else 0.0

        partial = remaining > 1e-9
        if partial and not allow_partial:
            result = MatchResult(
                order_id=order.order_id,
                status=OrderStatus.REJECTED,
                requested_size=order.size,
                reference_price=ref,
                rejection_reason=f"Partial Fill nicht erlaubt (Rest {remaining:.6f})",
                book_age_ms=book.age_ms,
                book_depth_usd=depth_usd,
            )
            self._apply(order, result)
            return result

        status = OrderStatus.PARTIAL if partial else OrderStatus.FILLED
        comps = self._impact_components(book, order.side, filled, model)

        # Impact-Zerlegung der Fills (Fill-Level-Slippage)
        for f in fills:
            f_slip = _bps(f.price, ref) if ref else 0.0
            object.__setattr__(f, "slippage_bps", round(-f_slip if order.side is OrderSide.SELL else f_slip, 2))

        result = MatchResult(
            order_id=order.order_id,
            status=status,
            requested_size=order.size,
            filled_size=filled,
            avg_price=avg_price,
            reference_price=ref,
            notional_usd=notional,
            fee_usd=fee,
            slippage_bps=round(slippage_realized_bps, 2),
            slippage_components=comps,
            levels_consumed=levels_used,
            partial=partial,
            book_age_ms=book.age_ms,
            book_depth_usd=depth_usd,
            diagnostics={
                "asks": book.best_ask,
                "bids": book.best_bid,
                "mid_price": book.mid_price,
                "spread_bps": book.spread_bps,
                "spread_cost_bps": round(abs(spread_cross_bps), 2),
                # Effektive Kosten = |Slippage| + |Spread-Anteil|. Immer >= 0.
                "effective_cost_bps": round(abs(spread_cross_bps) + abs(slippage_realized_bps), 2),
                "total_cost_usd": round(
                    notional * (abs(spread_cross_bps) + abs(slippage_realized_bps)) / 10_000, 6
                ),
                "ticks_consumed": levels_used,
                "remaining_size": remaining,
                "fill_prices": [f.price for f in fills],
                # Ein Cap-Flag ist ein Budget-Signal, kein Messwert.
                "slippage_over_budget": abs(slippage_realized_bps) > ShadowConfig.MAX_SLIPPAGE_BPS,
            },
        )
        object.__setattr__(order, "_fills", fills)  # type: ignore[attr-defined]
        self._apply(order, result)
        self.match_count += 1
        self.total_slippage_bps_weighted += abs(result.slippage_bps)
        return result

    async def match_async(
        self,
        order: PaperOrder,
        book: OrderBookSnapshot,
        *,
        model: SlippageModel = SlippageModel.NONE,
        allow_partial: bool = True,
        latency_ms: float = 0.0,
    ) -> MatchResult:
        """Async-Variante: simuliert Netzwerklatenz, ohne Netzwerk zu benutzen."""
        self.guard.assert_dry_run(f"PaperMatchEngine.match_async:{order.order_id}", order.token_id)
        if latency_ms > 0:
            if latency_ms > ShadowConfig.MAX_ORDER_LATENCY_MS:
                raise TimeoutError(
                    f"simulierte Latenz {latency_ms}ms > Limit {ShadowConfig.MAX_ORDER_LATENCY_MS}ms"
                )
            await asyncio.sleep(latency_ms / 1000.0)
        return self.match(order, book, model=model, allow_partial=allow_partial)

    # --- Status-Transition ---

    def _apply(self, order: PaperOrder, result: MatchResult) -> None:
        """Schreibt das Match-Ergebnis in den Order-Status (Zustandsmaschine)."""
        if result.status is OrderStatus.REJECTED:
            object.__setattr__(order, "status", OrderStatus.REJECTED)
            object.__setattr__(order, "rejection_reason", result.rejection_reason)
            return

        prev_filled = order.filled_size
        new_filled = round(prev_filled + result.filled_size, 8)
        if new_filled > 0:
            blended = (
                (order.avg_fill_price * prev_filled) + (result.avg_price * result.filled_size)
            ) / new_filled
            object.__setattr__(order, "avg_fill_price", _q(blended))
        object.__setattr__(order, "filled_size", new_filled)
        object.__setattr__(order, "slippage_bps", result.slippage_bps)
        object.__setattr__(order, "status", result.status)

    def close_partial(self, order: PaperOrder, reason: str = "residual cancelled") -> PaperOrder:
        """PARTIAL -> CLOSED: Restmenge wird explizit verworfen (kein Nachschicken!)."""
        self.guard.assert_dry_run(f"PaperMatchEngine.close_partial:{order.order_id}", order.token_id)
        if order.status is OrderStatus.PARTIAL:
            object.__setattr__(order, "status", OrderStatus.CLOSED)
            self.logger.info(
                "Partial-Rest geschlossen (kein Nachschicken im Shadow-Modus)",
                order_id=order.order_id,
                filled_size=order.filled_size,
                requested_size=order.size,
                residual=order.remaining_size,
                reason=reason,
            )
        elif order.status is OrderStatus.FILLED:
            object.__setattr__(order, "status", OrderStatus.CLOSED)
        return order

    def metrics(self) -> Dict[str, Any]:
        avg = 0.0 if self.match_count == 0 else round(self.total_slippage_bps_weighted / self.match_count, 2)
        return {"matches": self.match_count, "avg_abs_slippage_bps": avg}

# ============================================================================
# 5. RISK & POSITION MANAGEMENT
# ============================================================================


@dataclass
class Position:
    """Virtuelle Position in einem Outcome-Token."""

    token_id: str
    market_id: str
    event_id: str
    outcome: str
    size: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    opened_at: str = field(default_factory=_now_iso)
    last_update: str = field(default_factory=_now_iso)

    @property
    def is_open(self) -> bool:
        return self.size > 1e-9

    @property
    def avg_cost_usd(self) -> float:
        return round(self.avg_price * self.size, 6)

    def unrealized_pnl(self, mark: Optional[float]) -> float:
        if mark is None or not self.is_open:
            return 0.0
        return round((mark - self.avg_price) * self.size, 6)

    def exposure_usd(self, mark: Optional[float] = None) -> float:
        price = mark if mark is not None else self.avg_price
        return round(price * self.size, 6)

    def to_dict(self, mark: Optional[float] = None) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "market_id": self.market_id,
            "event_id": self.event_id,
            "outcome": self.outcome,
            "size": self.size,
            "avg_price": self.avg_price,
            "avg_cost_usd": self.avg_cost_usd,
            "mark_price": mark,
            "exposure_usd": self.exposure_usd(mark),
            "unrealized_pnl": self.unrealized_pnl(mark),
            "realized_pnl": round(self.realized_pnl, 6),
            "fees_paid": round(self.fees_paid, 6),
            "is_open": self.is_open,
            "opened_at": self.opened_at,
            "last_update": self.last_update,
        }


@dataclass
class RiskLimits:
    """Pre-Trade-Limits. Werden pro Engine-Instanz gesetzt."""

    max_position_usd: float = ShadowConfig.DEFAULT_MAX_POSITION_USD
    max_event_exposure_usd: float = ShadowConfig.DEFAULT_MAX_EVENT_EXPOSURE_USD
    max_concurrent_positions: int = ShadowConfig.DEFAULT_MAX_CONCURRENT_POSITIONS
    max_drawdown_pct: float = ShadowConfig.MAX_DRAWDOWN_PCT
    max_slippage_bps: float = ShadowConfig.MAX_SLIPPAGE_BPS
    max_order_notional_usd: Optional[float] = None
    min_confidence: float = 0.0
    allowed_events: Optional[Sequence[str]] = None
    blocked_events: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_position_usd": self.max_position_usd,
            "max_event_exposure_usd": self.max_event_exposure_usd,
            "max_concurrent_positions": self.max_concurrent_positions,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_slippage_bps": self.max_slippage_bps,
            "max_order_notional_usd": self.max_order_notional_usd,
            "min_confidence": self.min_confidence,
            "allowed_events": list(self.allowed_events) if self.allowed_events else None,
            "blocked_events": list(self.blocked_events),
        }


class RiskDecision(BaseModel):
    """Ergebnis eines Pre-Trade-Checks — inkl. vollstaendiger Begruendung."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    checks: Dict[str, bool] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    adjusted_size: Optional[float] = None
    drawdown: Dict[str, Any] = Field(default_factory=dict)
    limits: Dict[str, Any] = Field(default_factory=dict)
    checked_at: str = Field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


class Clock:
    """Monoton steigende Zeitquelle (testsicher, nie rueckwaerts)."""

    def __init__(self, start: Optional[float] = None) -> None:
        self._t = float(start if start is not None else time.time())

    def advance(self, seconds: float) -> float:
        self._t += max(0.0, float(seconds))
        return self._t

    def now(self) -> float:
        return self._t


class RiskController:
    """Pre-Trade-Checks, Drawdown-Lockout und Signal-Inversion.

    Vier Verantwortlichkeiten:
      1. Pre-Trade-Risk-Checks (Positionsgroesse, Event-Exposure, Parallelitaet,
         Slippage-Budget, Confidence, Latenz/Staleness).
      2. Automated Drawdown-Lockout: faellt das virtuelle Portfolio unter
         (1 - max_drawdown_pct) des Peak-Equity, wird der Handel gesperrt.
      3. Signal-Inversion: Flagge `invert_signals`. Bei `auto` entscheidet die
         rollierende Trefferquote — schwache Signale werden zum Kontra-Indikator.
      4. Signal-Scoring: rollierende Hit-Rate je Strategie/Token fuer (3).
    """

    def __init__(self, logger: JSONLogger, limits: Optional[RiskLimits] = None, clock: Optional[Clock] = None) -> None:
        self.logger = logger
        self.limits = limits or RiskLimits()
        self.clock = clock or Clock()
        self.model = SlippageModel.NONE

        # --- Signalqualitaet (rollierend, je Strategie) ---
        self._hit_rate: Dict[str, float] = {}
        self._hit_count: Dict[str, int] = {}
        self._sample_count: Dict[str, int] = {}
        self._pnl_history: Dict[str, List[float]] = {}
        self.inversion_events: List[Dict[str, Any]] = []

        # --- Drawdown-Zustand ---
        self.peak_equity = ShadowConfig.INITIAL_BANKROLL_USD
        self.lockout_active = False
        self.lockout_reason: Optional[str] = None
        self.lockout_count = 0
        self.manual_unlocks = 0

    # ------------------------------------------------------------------
    # 5.1 Signal-Scoring
    # ------------------------------------------------------------------

    def register_outcome(self, strategy: str, hit: bool, pnl_delta: float = 0.0) -> Dict[str, Any]:
        """Meldet das Ergebnis eines (simulierten) Signals an das Scoringsystem."""
        samples = self._sample_count.get(strategy, 0) + 1
        hits = self._hit_count.get(strategy, 0) + (1 if hit else 0)
        self._sample_count[strategy] = samples
        self._hit_count[strategy] = hits
        self._hit_rate[strategy] = round(hits / samples, 4)
        self._pnl_history.setdefault(strategy, []).append(round(pnl_delta, 6))
        if len(self._pnl_history[strategy]) > ShadowConfig.HIT_RATE_WINDOW:
            self._pnl_history[strategy] = self._pnl_history[strategy][-ShadowConfig.HIT_RATE_WINDOW:]
        return self.signal_quality(strategy)

    def signal_quality(self, strategy: str) -> Dict[str, Any]:
        samples = self._sample_count.get(strategy, 0)
        hit_rate = self._hit_rate.get(strategy, 0.5)
        return {
            "strategy": strategy,
            "samples": samples,
            "hit_rate": hit_rate,
            "source": "measured" if samples > 0 else "prior",
            "confidence_low": samples < ShadowConfig.MIN_SAMPLES_FOR_INVERSION,
            "threshold": ShadowConfig.MIN_HIT_RATE_FOR_CONFIDENCE,
            "would_invert": hit_rate < ShadowConfig.MIN_HIT_RATE_FOR_CONFIDENCE,
        }

    # ------------------------------------------------------------------
    # 5.2 Signal-Inversion
    # ------------------------------------------------------------------

    def maybe_invert(
        self,
        order: PaperOrder,
        *,
        invert_signals: Optional[bool] = None,
        strategy: Optional[str] = None,
    ) -> Tuple[PaperOrder, Dict[str, Any]]:
        """Dreht ein Signal um, wenn es als Kontra-Indikator taugt.

        Entscheidungsregel (dokumentiert, auditierbar):
          1. `invert_signals is True`  -> IMMER invertieren (Wille des Hosts).
          2. `invert_signals is None`  -> Auto: invertiere, wenn mindestens
             MIN_SAMPLES_FOR_INVERSION Messungen vorliegen UND hit_rate < Threshold.
          3. `invert_signals is False` -> NIE invertieren.

        Sicherheitsnetz: Auto-Inversion ist nur aktiv, wenn
        `SEE_ALLOW_HOST_INVERSION=true` gesetzt ist. Ohne Messhistorie wird
        nicht geraten — ein Vorzeichenwechsel aus Bauchgefuehl ist kein Risk-Management.
        """
        strategy_key = strategy or order.strategy
        quality = self.signal_quality(strategy_key)
        decision: Dict[str, Any] = {
            "strategy": strategy_key,
            "requested": invert_signals,
            "quality": quality,
            "inverted": False,
            "reason": "keine Inversion",
        }

        if invert_signals is False:
            decision["reason"] = "invert_signals=False (explizit aus)"
            return order, decision

        if invert_signals is True:
            decision["reason"] = "invert_signals=True (explizit an)"
        else:
            # AUTO — nur mit ausreichend Evidenz
            if not ShadowConfig.ALLOW_INVERSION_BY_HOST_FLAG:
                decision["reason"] = (
                    "Auto-Inversion deaktiviert (SEE_ALLOW_HOST_INVERSION=false) — "
                    "kein Vorzeichenwechsel ohne Host-Freigabe"
                )
                return order, decision
            if quality["samples"] < ShadowConfig.MIN_SAMPLES_FOR_INVERSION:
                decision["reason"] = (
                    f"zu wenig Evidenz fuer Auto-Inversion "
                    f"({quality['samples']}/{ShadowConfig.MIN_SAMPLES_FOR_INVERSION})"
                )
                return order, decision
            if quality["hit_rate"] >= ShadowConfig.MIN_HIT_RATE_FOR_CONFIDENCE:
                decision["reason"] = (
                    f"Trefferquote {quality['hit_rate']:.2%} >= Schwelle "
                    f"{ShadowConfig.MIN_HIT_RATE_FOR_CONFIDENCE:.2%} — Signal bleibt"
                )
                return order, decision
            decision["reason"] = (
                f"Trefferquote {quality['hit_rate']:.2%} < Schwelle "
                f"{ShadowConfig.MIN_HIT_RATE_FOR_CONFIDENCE:.2%} — Kontra-Indikator"
            )

        inverted = order.opposite()
        decision.update(
            {
                "inverted": True,
                "original": {"side": order.side.value, "price": order.price, "order_id": order.order_id},
                "inverted_order": {"side": inverted.side.value, "price": inverted.price, "order_id": inverted.order_id},
            }
        )
        self.inversion_events.append({"timestamp": _now_iso(), **decision})
        self.logger.warn(
            "Signal invertiert (Kontra-Indikator)",
            original_side=order.side.value,
            inverted_side=inverted.side.value,
            hit_rate=quality["hit_rate"],
            samples=quality["samples"],
            reason=decision["reason"],
        )
        return inverted, decision

    # ------------------------------------------------------------------
    # 5.3 Drawdown-Lockout
    # ------------------------------------------------------------------

    def update_equity(self, equity: float) -> Dict[str, Any]:
        """Aktualisiert Peak und prueft die Notbremse."""
        self.peak_equity = max(self.peak_equity, equity)
        dd_pct = 0.0 if self.peak_equity <= 0 else (self.peak_equity - equity) / self.peak_equity * 100
        dd_pct = max(dd_pct, 0.0)

        if not self.lockout_active and dd_pct >= self.limits.max_drawdown_pct:
            self.lockout_active = True
            self.lockout_count += 1
            self.lockout_reason = (
                f"DRAWDOWN_LOCKOUT: {dd_pct:.2f}% >= Limit {self.limits.max_drawdown_pct:.2f}%"
            )
            self.logger.error(self.lockout_reason, equity=equity, peak_equity=self.peak_equity, dd_pct=round(dd_pct, 4))

        return {
            "equity": round(equity, 6),
            "peak_equity": round(self.peak_equity, 6),
            "drawdown_pct": round(dd_pct, 4),
            "max_drawdown_pct": self.limits.max_drawdown_pct,
            "lockout_active": self.lockout_active,
            "lockout_reason": self.lockout_reason,
            "warn": dd_pct >= ShadowConfig.RISK_WARN_PCT,
        }

    def unlock(self, reason: str = "manual") -> bool:
        """Manuelles Entsperren — im Shadow-Modus erlaubt, im Live-Betrieb waere hier ein Vier-Augen-Prinzip."""
        if not self.lockout_active:
            return False
        self.logger.warn("Drawdown-Lockout manuell aufgehoben", reason=reason, peak_equity=self.peak_equity)
        self.lockout_active = False
        self.lockout_reason = None
        self.manual_unlocks += 1
        return True

    # ------------------------------------------------------------------
    # 5.4 Pre-Trade-Checks
    # ------------------------------------------------------------------

    def check_order(
        self,
        order: PaperOrder,
        *,
        positions: Mapping[str, Position],
        equity: float,
        book: Optional[OrderBookSnapshot] = None,
        expected_slippage_bps: Optional[float] = None,
        mark_prices: Optional[Mapping[str, float]] = None,
    ) -> RiskDecision:
        """Vollstaendiger Pre-Trade-Check. Reine Leseoperation — mutiert nichts."""
        limits = self.limits
        marks = dict(mark_prices or {})
        if book is not None and book.mid_price is not None:
            marks.setdefault(order.token_id, book.mid_price)

        checks: Dict[str, bool] = {}
        reasons: List[str] = []
        warnings: List[str] = []

        # (0) Charter
        checks["charter_dry_run"] = True  # erzwungen in DryRunGuard, hier dokumentiert

        # (1) Drawdown-Lockout
        dd = self.update_equity(equity)
        checks["drawdown_within_limit"] = not dd["lockout_active"]
        if dd["lockout_active"]:
            reasons.append(dd["lockout_reason"] or "Drawdown-Lockout aktiv")
        elif dd["warn"]:
            warnings.append(f"Drawdown naehert sich Limit: {dd['drawdown_pct']:.2f}%")

        # (2) Markt vorhanden & frisch
        if book is None:
            checks["book_available"] = False
            reasons.append("kein Orderbuch-Snapshot (fehlend oder veraltet)")
            checks["book_fresh"] = False
        else:
            checks["book_available"] = True
            checks["book_fresh"] = not book.is_stale
            if book.is_stale:
                reasons.append(f"Orderbuch veraltet ({book.age_ms}ms > {ShadowConfig.BOOK_STALENESS_MS}ms)")
            if book.best_bid is None or book.best_ask is None:
                warnings.append("einseitiges Buch (kein Bid oder kein Ask)")

        # (3) Positionsgroesse
        notion = order.notional_usd
        checks["position_size_ok"] = notion <= limits.max_position_usd
        if not checks["position_size_ok"]:
            reasons.append(f"Positionsgroesse {notion:,.2f}$ > Limit {limits.max_position_usd:,.2f}$")

        # (4) Order-Notional (optional)
        if limits.max_order_notional_usd is not None:
            checks["order_notional_ok"] = notion <= limits.max_order_notional_usd
            if not checks["order_notional_ok"]:
                reasons.append(
                    f"Order-Notional {notion:,.2f}$ > Limit {limits.max_order_notional_usd:,.2f}$"
                )
        else:
            checks["order_notional_ok"] = True

        # (5) Event-Exposure (bestehend + neu)
        current_event = sum(
            p.exposure_usd(marks.get(tid, p.avg_price))
            for tid, p in positions.items()
            if p.event_id == order.event_id and p.is_open
        )
        projected_event = round(current_event + notion, 6)
        checks["event_exposure_ok"] = projected_event <= limits.max_event_exposure_usd
        if not checks["event_exposure_ok"]:
            reasons.append(
                f"Event-Exposure {projected_event:,.2f}$ > Limit {limits.max_event_exposure_usd:,.2f}$ "
                f"(Event {order.event_id})"
            )

        # (6) Parallelitaet
        open_positions = [p for p in positions.values() if p.is_open]
        is_new_token = order.token_id not in positions or not positions[order.token_id].is_open
        projected_count = len(open_positions) + (1 if is_new_token else 0)
        checks["concurrent_positions_ok"] = projected_count <= limits.max_concurrent_positions
        if not checks["concurrent_positions_ok"]:
            reasons.append(
                f"max. parallele Positionen: {projected_count} > {limits.max_concurrent_positions}"
            )

        # (7) Slippage-Budget
        if expected_slippage_bps is not None:
            checks["slippage_within_budget"] = abs(expected_slippage_bps) <= limits.max_slippage_bps
            if not checks["slippage_within_budget"]:
                reasons.append(
                    f"erwartete Slippage {expected_slippage_bps:.1f}bps > Budget {limits.max_slippage_bps:.1f}bps"
                )
        else:
            checks["slippage_within_budget"] = True

        # (8) Confidence
        checks["confidence_ok"] = order.confidence >= limits.min_confidence
        if not checks["confidence_ok"]:
            reasons.append(f"Confidence {order.confidence:.2f} < Minimum {limits.min_confidence:.2f}")

        # (9) Event-Whitelist/Blacklist
        checks["event_allowed"] = True
        if limits.allowed_events and order.event_id not in limits.allowed_events:
            checks["event_allowed"] = False
            reasons.append(f"Event {order.event_id} nicht in der Whitelist")
        if order.event_id in tuple(limits.blocked_events):
            checks["event_allowed"] = False
            reasons.append(f"Event {order.event_id} ist blockiert")

        # (10) Equity-Deckung
        checks["equity_sufficient"] = notion <= equity
        if not checks["equity_sufficient"]:
            reasons.append(f"Notional {notion:,.2f}$ > verfuegbares Equity {equity:,.2f}$")

        allowed = all(checks.values())
        return RiskDecision(
            allowed=allowed,
            checks=checks,
            reasons=reasons,
            warnings=warnings,
            drawdown=dd,
            limits=limits.to_dict(),
        )

    def size_for_risk(self, order: PaperOrder, equity: float) -> float:
        """Reduziert die Ordergroesse auf das kleinste bindende Limit (Risk-Sizing)."""
        price = max(order.price, 0.01)
        by_position = self.limits.max_position_usd / price
        by_equity = equity / price
        candidates = [order.size, by_position, by_equity]
        if self.limits.max_order_notional_usd is not None:
            candidates.append(self.limits.max_order_notional_usd / price)
        return _q(max(min(candidates), 0.0), SIZE_QUANTUM)

    def stats(self) -> Dict[str, Any]:
        return {
            "peak_equity": round(self.peak_equity, 2),
            "lockout_active": self.lockout_active,
            "lockout_reason": self.lockout_reason,
            "lockout_count": self.lockout_count,
            "manual_unlocks": self.manual_unlocks,
            "inversions": len(self.inversion_events),
            "strategies_tracked": len(self._sample_count),
            "limits": self.limits.to_dict(),
        }

# ============================================================================
# 6. ROOT: SHADOW EXECUTION ENGINE
# ============================================================================


class Signal(BaseModel):
    """Eingehendes Handelssignal (NewsBot / PolySentinel / Agent X Hub).

    Bewusst locker typisiert: Signale kommen aus fremden Systemen und sollen
    nicht daran scheitern, dass ein Feld fehlt. `PaperOrder` ist danach streng.
    """

    model_config = ConfigDict(extra="allow")

    signal_id: str = Field(default_factory=lambda: f"sig-{uuid.uuid4().hex[:10]}")
    source: str = "agent_x_hub"
    strategy: str = "unspecified"
    token_id: str
    market_id: str = ""
    event_id: str = ""
    side: OrderSide = OrderSide.BUY
    price: float
    size: float
    order_type: OrderType = OrderType.GTC
    confidence: float = 1.0
    outcome: str = "YES"
    created_at: str = Field(default_factory=_now_iso)

    def to_order(self, **overrides: Any) -> PaperOrder:
        payload: Dict[str, Any] = {
            "signal_id": self.signal_id,
            "strategy": self.strategy,
            "token_id": self.token_id,
            "market_id": self.market_id,
            "event_id": self.event_id or self.market_id or self.token_id,
            "side": self.side,
            "price": self.price,
            "size": self.size,
            "order_type": self.order_type,
            "confidence": self.confidence,
            "outcome": self.outcome,
        }
        payload.update(overrides)
        return PaperOrder(**payload)


class Portfolio:
    """Virtuelles Portfolio. Kein Custody, kein Ledger, kein Transfer."""

    def __init__(self, bankroll: float = ShadowConfig.INITIAL_BANKROLL_USD) -> None:
        self.initial_bankroll = float(bankroll)
        self.cash = float(bankroll)
        self.positions: Dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.closed_trades = 0
        self.turnover_usd = 0.0

    # --- Buchungen (virtuell) ---

    def apply_buy(self, order: PaperOrder, book: Optional[OrderBookSnapshot] = None) -> Position:
        """BUY erhoeht die Position und reduziert Cash."""
        price = order.avg_fill_price
        size = order.filled_size
        cost = round(price * size, 6)
        pos = self.positions.get(order.token_id)
        if pos is None:
            pos = Position(
                token_id=order.token_id,
                market_id=order.market_id,
                event_id=order.event_id,
                outcome=order.outcome,
            )
            self.positions[order.token_id] = pos
        new_size = round(pos.size + size, 8)
        if new_size > 0:
            pos.avg_price = _q(((pos.avg_price * pos.size) + cost) / new_size)
        pos.size = new_size
        pos.realized_pnl -= 0.0
        pos.fees_paid += 0.0
        pos.last_update = _now_iso()
        self.cash = round(self.cash - cost, 6)
        self.turnover_usd = round(self.turnover_usd + cost, 6)
        return pos

    def apply_sell(self, order: PaperOrder, book: Optional[OrderBookSnapshot] = None) -> Tuple[Position, float]:
        """SELL reduziert die Position und realisiert PnL."""
        price = order.avg_fill_price
        size = min(order.filled_size, self.positions.get(order.token_id, Position("", "", "", "")).size)
        pos = self.positions.get(order.token_id)
        if pos is None or pos.size <= 0:
            return Position(order.token_id, order.market_id, order.event_id, order.outcome), 0.0
        proceeds = round(price * size, 6)
        pnl = round((price - pos.avg_price) * size, 6)
        pos.size = round(pos.size - size, 8)
        pos.realized_pnl = round(pos.realized_pnl + pnl, 6)
        pos.last_update = _now_iso()
        self.cash = round(self.cash + proceeds, 6)
        self.realized_pnl = round(self.realized_pnl + pnl, 6)
        self.turnover_usd = round(self.turnover_usd + proceeds, 6)
        if pos.size <= 1e-9:
            self.closed_trades += 1
        return pos, pnl

    def charge_fee(self, fee_usd: float) -> None:
        self.total_fees = round(self.total_fees + fee_usd, 6)
        self.cash = round(self.cash - fee_usd, 6)

    # --- Bewertung ---

    def open_positions(self) -> List[Position]:
        return [p for p in self.positions.values() if p.is_open]

    def exposure_usd(self, marks: Optional[Mapping[str, float]] = None) -> float:
        marks = marks or {}
        return round(sum(p.exposure_usd(marks.get(p.token_id)) for p in self.open_positions()), 6)

    def event_exposure_usd(self, marks: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
        marks = marks or {}
        out: Dict[str, float] = {}
        for p in self.open_positions():
            out[p.event_id] = round(out.get(p.event_id, 0.0) + p.exposure_usd(marks.get(p.token_id)), 6)
        return out

    def unrealized_pnl(self, marks: Optional[Mapping[str, float]] = None) -> float:
        marks = marks or {}
        return round(sum(p.unrealized_pnl(marks.get(p.token_id)) for p in self.open_positions()), 6)

    def equity(self, marks: Optional[Mapping[str, float]] = None) -> float:
        return round(self.cash + self.exposure_usd(marks), 6)

    def snapshot(self, marks: Optional[Mapping[str, float]] = None, *, top_n: int = 10) -> Dict[str, Any]:
        marks = marks or {}
        open_pos = self.open_positions()
        equity = self.equity(marks)
        return {
            "initial_bankroll_usd": round(self.initial_bankroll, 2),
            "cash_usd": round(self.cash, 2),
            "exposure_usd": round(self.exposure_usd(marks), 2),
            "equity_usd": round(equity, 2),
            "realized_pnl_usd": round(self.realized_pnl, 2),
            "unrealized_pnl_usd": round(self.unrealized_pnl(marks), 2),
            "total_fees_usd": round(self.total_fees, 4),
            "total_pnl_usd": round(equity - self.initial_bankroll, 2),
            "total_pnl_pct": round((equity / self.initial_bankroll - 1) * 100, 3) if self.initial_bankroll else 0.0,
            "open_positions": len(open_pos),
            "closed_trades": self.closed_trades,
            "turnover_usd": round(self.turnover_usd, 2),
            "event_exposure_usd": self.event_exposure_usd(marks),
            "positions": [p.to_dict(marks.get(p.token_id)) for p in open_pos][:top_n],
        }


class ShadowExecutionEngine:
    """Root-Agent: Paper-Trading-Satellit des Agent X Hub.

    Der komplette Pfad ist offline. Es gibt genau drei Ausgaenge:
      1. `_match`   — virtuelle Ausfuehrung gegen das Buch
      2. `snapshot` — Portfolio-Bewertung
      3. `_archive` — Audit-Trail auf Platte

    Jeder dieser Pfade laeuft durch `self.guard.assert_dry_run`.
    """

    def __init__(
        self,
        user_id: str = "default",
        *,
        bankroll: float = ShadowConfig.INITIAL_BANKROLL_USD,
        limits: Optional[RiskLimits] = None,
        invert_signals: Optional[bool] = ShadowConfig.DEFAULT_INVERT_SIGNALS,
        data_root: Optional[Union[Path, str]] = None,
        log_dir: Optional[Union[Path, str]] = None,
        clock: Optional[Clock] = None,
        guard_enabled: bool = True,
        persist: bool = True,
    ) -> None:
        # --- Charter-Zustand (read-only Sicht) ---
        self.dry_run: bool = True  # hart verdrahtet; siehe DryRunGuard
        self.diagnostic_only: bool = CHARTER_DIAGNOSTIC_ONLY
        self.live_execution: bool = CHARTER_LIVE_EXECUTION
        self.order_send: bool = CHARTER_ORDER_SEND
        self.execution_mode: str = ShadowConfig.EXECUTION_MODE

        self.user_id = user_id
        self.persist = persist
        self.clock = clock or Clock()
        self.logger = JSONLogger("ShadowExecutionEngine", user_id, log_dir=log_dir)
        self.data_dir = (Path(data_root) if data_root is not None else Path(ShadowConfig.DATA_ROOT)) / user_id / "shadow"
        if self.persist:
            try:
                self.data_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.persist = False

        # --- Guard Rail ---
        self.guard = DryRunGuard(self.logger, enabled=guard_enabled)
        self.guard.assert_dry_run("ShadowExecutionEngine.__init__")

        # --- Komponenten ---
        self.portfolio = Portfolio(bankroll)
        self.risk = RiskController(self.logger, limits=limits, clock=self.clock)
        self.feed = MockPolySentinelFeed()
        self.matcher = PaperMatchEngine(self.feed, self.logger, self.guard)

        # --- Signal-Inversion ---
        self.invert_signals = invert_signals
        self.inversion_decisions: List[Dict[str, Any]] = []

        # --- Buchhaltung ---
        self.closed_orders: List[PaperOrder] = []
        self.rejected_orders: List[PaperOrder] = []
        self.blocked_orders: List[Dict[str, Any]] = []
        self.pipeline_runs = 0
        self.audit_entries: List[Dict[str, Any]] = []

        self.logger.audit("Shadow Execution Engine gestartet", **self.charter_report())

    # ------------------------------------------------------------------
    # Charter-Oberflaeche
    # ------------------------------------------------------------------

    def charter_report(self) -> Dict[str, Any]:
        """Charter-Zustand fuer Dashboard/Audit — inkl. Verstoessen."""
        return {
            **self.guard.charter_state(),
            "execution_mode": self.execution_mode,
            "user_id": self.user_id,
            "blocked_calls": self.guard.blocked_calls,
            "violations": len(self.guard.violations),
        }

    def assert_charter(self) -> None:
        """Explizite Charter-Pruefung — fuer Pre-Flight-Checks im Host."""
        self.guard.assert_dry_run("ShadowExecutionEngine.assert_charter")
        self.guard.inspect_caller("ShadowExecutionEngine.assert_charter")

    def reject_live_transport(self, transport: str) -> None:
        """Bruecke fuer Hosts: jeder Versuch, einen echten Relayer anzubinden, bricht hier ab."""
        self.guard.reject_forbidden_transport(transport)

    # ------------------------------------------------------------------
    # 6.1 Marktdaten injizieren
    # ------------------------------------------------------------------

    def publish_book(self, payload: Union[Mapping[str, Any], OrderBookSnapshot]) -> OrderBookSnapshot:
        self.assert_charter()
        if isinstance(payload, OrderBookSnapshot):
            return self.feed.publish(payload)
        return self.feed.publish_dict(payload)

    def seed_demo_market(
        self,
        token_id: str,
        mid: float = 0.5,
        *,
        event_id: str = "evt-demo",
        market_id: str = "mkt-demo",
        depth_usd_per_level: float = 900.0,
        imbalance: float = 0.0,
        levels: int = 10,
    ) -> OrderBookSnapshot:
        """Setzt ein synthetisches Buch (nur fuer Offline-Selbsttest/Demo)."""
        self.assert_charter()
        book = build_synthetic_book(
            token_id,
            mid,
            market_id=market_id,
            event_id=event_id,
            levels=levels,
            depth_usd_per_level=depth_usd_per_level,
            imbalance=imbalance,
        )
        self.feed.publish(book)
        return book

    def mark_prices(self) -> Dict[str, float]:
        """Mid-Preise aller bekannten Buecher als Bewertungsgrundlage."""
        out: Dict[str, float] = {}
        for book in self.feed.get_books():
            mid = book.mid_price
            if mid is not None:
                out[book.token_id] = mid
        return out

    # ------------------------------------------------------------------
    # 6.2 Signal-Verarbeitung (sync)
    # ------------------------------------------------------------------

    def process_signal(
        self,
        signal: Union[Signal, Mapping[str, Any]],
        *,
        size: Optional[float] = None,
        max_slippage_bps: Optional[float] = None,
        allow_partial: bool = True,
        slippage_model: SlippageModel = SlippageModel.NONE,
    ) -> Dict[str, Any]:
        """Vollstaendige Signal-Pipeline: Order -> Gate -> Risk -> Match -> Portfolio.

        Reihenfolge ist bindend:
            1. Framing/Formatvalidierung (PaperOrder)
            2. Charter-Gate (dry_run)
            3. Signal-Inversion
            4. Pre-Trade-Risk
            5. Match (virtuell)
            6. Portfolio-Buchung
        """
        signal = signal if isinstance(signal, Signal) else Signal(**dict(signal))

        # --- 1. Framing ---
        order = signal.to_order(size=size if size is not None else signal.size)
        ok, reasons = order.verify_signature()
        if not ok:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = f"EIP-712-Formatpruefung fehlgeschlagen: {'; '.join(reasons)}"
            self.rejected_orders.append(order)
            self.logger.warn("Order abgelehnt (Format)", order_id=order.order_id, reasons=reasons)
            return _fail("framing", order.rejection_reason, artifacts=[order.summarize()])

        # --- 2. Charter-Gate ---
        self.guard.assert_dry_run(f"process_signal:{order.order_id}", order.token_id)

        # --- 3. Signal-Inversion ---
        chosen_order = order
        inversion_decision: Optional[Dict[str, Any]] = None
        if self.invert_signals is not None or ShadowConfig.ALLOW_INVERSION_BY_HOST_FLAG:
            chosen_order, inversion_decision = self.risk.maybe_invert(order, invert_signals=self.invert_signals)
            if inversion_decision["inverted"]:
                self.inversion_decisions.append(inversion_decision)

        target = chosen_order if chosen_order.book_snapshot_ts else chosen_order
        token_id = target.token_id
        book = self.feed.get_book(token_id)
        if book is None and self.persist:
            self.logger.warn("Kein Buch fuer Token — Signal abgewiesen", token_id=token_id)

        # --- 4. Pre-Trade-Risk ---
        preview = self.matcher.preview_slippage(book, target, slippage_model) if book else {}
        expected_slip = preview.get("expected_slippage_bps")
        effective_limit = max_slippage_bps if max_slippage_bps is not None else self.risk.limits.max_slippage_bps
        original_limit = self.risk.limits.max_slippage_bps
        self.risk.limits.max_slippage_bps = effective_limit
        try:
            decision = self.risk.check_order(
                target,
                positions=self.portfolio.positions,
                equity=self.portfolio.equity(self.mark_prices()),
                book=book,
                expected_slippage_bps=expected_slip,
                mark_prices=self.mark_prices(),
            )
        finally:
            self.risk.limits.max_slippage_bps = original_limit

        if not decision.allowed:
            target.status = OrderStatus.REJECTED
            target.rejection_reason = "; ".join(decision.reasons) or "Risk-Check fehlgeschlagen"
            self.rejected_orders.append(target)
            self.blocked_orders.append({"order_id": target.order_id, "risk": decision.to_dict()})
            self._archive("risk_block", {"order": target.summarize(), "risk": decision.to_dict()})
            return _blocked(
                "risk",
                target.rejection_reason,
                artifacts=[{"order": target.summarize(), "risk": decision.to_dict(), "preview": preview}],
            )

        # --- 5. Match ---
        result = self.matcher.match(target, book, model=slippage_model, allow_partial=allow_partial)

        # --- 6. Portfolio ---
        pnl_delta = 0.0
        if result.status in (OrderStatus.FILLED, OrderStatus.PARTIAL) and result.filled_size > 0:
            if target.side is OrderSide.BUY:
                self.portfolio.apply_buy(target)
            else:
                _, pnl_delta = self.portfolio.apply_sell(target)
            self.portfolio.charge_fee(result.fee_usd)
            self.risk.register_outcome(target.strategy, hit=pnl_delta >= 0, pnl_delta=pnl_delta)

        if result.status in (OrderStatus.FILLED, OrderStatus.REJECTED):
            self.closed_orders.append(target)

        equity = self.portfolio.equity(self.mark_prices())
        dd = self.risk.update_equity(equity)

        event = {
            "order": target.summarize(),
            "match": result.to_dict(),
            "risk_checks": decision.checks,
            "risk_warnings": decision.warnings,
            "inversion": inversion_decision,
            "equity_usd": round(equity, 2),
            "drawdown_pct": dd["drawdown_pct"],
            "signal_source": signal.source,
        }
        self._archive("paper_fill", event)
        self.logger.info(
            "Paper-Order verarbeitet",
            order_id=target.order_id,
            status=result.status.value,
            filled=result.filled_size,
            avg_price=result.avg_price,
            slippage_bps=result.slippage_bps,
        )

        status = "completed" if result.status in (OrderStatus.FILLED, OrderStatus.PARTIAL) else "failed"
        artifacts = [event]
        return {
            "status": status,
            "job_id": target.order_id,
            "artifacts": artifacts,
            "error": result.rejection_reason,
            "logs": [],
        }

    # ------------------------------------------------------------------
    # 6.3 Async-Pfad
    # ------------------------------------------------------------------

    async def process_signal_async(
        self,
        signal: Union[Signal, Mapping[str, Any]],
        *,
        size: Optional[float] = None,
        latency_ms: float = 0.0,
        slippage_model: SlippageModel = SlippageModel.NONE,
        max_slippage_bps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Async-Signalverarbeitung. `latency_ms` simuliert Netzwerklatenz — ohne Netzwerk."""
        signal = signal if isinstance(signal, Signal) else Signal(**dict(signal))
        self.guard.assert_dry_run(f"process_signal_async:{signal.signal_id}", signal.token_id)

        if latency_ms > 0:
            if latency_ms > ShadowConfig.MAX_ORDER_LATENCY_MS:
                return _fail(
                    "latency",
                    f"simulierte Latenz {latency_ms}ms > Limit {ShadowConfig.MAX_ORDER_LATENCY_MS}ms",
                )
            await asyncio.sleep(latency_ms / 1000.0)

        handler = lambda: self.process_signal(  # noqa: E731
            signal, size=size, max_slippage_bps=max_slippage_bps, slippage_model=slippage_model
        )
        return await _maybe_await(asyncio.to_thread(handler))

    async def run_signal_batch(
        self,
        signals: Sequence[Union[Signal, Mapping[str, Any]]],
        *,
        concurrency: int = 4,
        latency_ms: float = 0.0,
        slippage_model: SlippageModel = SlippageModel.NONE,
    ) -> Dict[str, Any]:
        """Fuehrt einen Signal-Batch mit begrenzter Parallelitaet aus."""
        self.assert_charter()
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _one(sig: Union[Signal, Mapping[str, Any]]) -> Dict[str, Any]:
            async with semaphore:
                try:
                    return await self.process_signal_async(sig, latency_ms=latency_ms, slippage_model=slippage_model)
                except OrderSendAttempted as exc:
                    return _fail("charter", str(exc))
                except Exception as exc:  # noqa: BLE001
                    return _fail("batch", str(exc))

        results = await asyncio.gather(*[_one(s) for s in signals])
        self.pipeline_runs += 1
        return _ok(
            f"batch-{uuid.uuid4().hex[:8]}",
            artifacts=[
                {
                    "processed": len(results),
                    "completed": sum(1 for r in results if r["status"] == "completed"),
                    "failed": sum(1 for r in results if r["status"] == "failed"),
                    "blocked": sum(1 for r in results if r["status"] == "blocked"),
                    "results": results,
                    "portfolio": self.portfolio.snapshot(self.mark_prices()),
                }
            ],
        )

    # ------------------------------------------------------------------
    # 6.4 Async-Tick-Schleife
    # ------------------------------------------------------------------

    async def run_async(
        self,
        token_ids: Optional[Sequence[str]] = None,
        *,
        ticks: int = 5,
        tick_interval_s: float = 0.5,
        strategy: Callable[[OrderBookSnapshot, int], Optional[Signal]] = None,
        mark_to_market: bool = True,
    ) -> Dict[str, Any]:
        """Tick-Schleife: Buch -> Strategie -> Signal -> Paper-Match.

        `strategy` ist ein Host-Callback. Ohne Callback laeuft die Engine im
        reinen Beobachtungsmodus (Mark-to-Market, keine Orders).
        """
        self.assert_charter()
        tokens = list(token_ids or [b.token_id for b in self.feed.get_books()])
        timeline: List[Dict[str, Any]] = []

        for tick in range(ticks):
            books = self.feed.simulate_step(tokens, seed=tick)
            for book in books:
                self.guard.assert_dry_run(f"run_async:tick{tick}", book.token_id)
                if strategy is None:
                    continue
                signal = strategy(book, tick)
                if signal is None:
                    continue
                results = await self.process_signal_async(signal)
                timeline.append({"tick": tick, "token_id": book.token_id, "result": results})

            if mark_to_market:
                marks = self.mark_prices()
                equity = self.portfolio.equity(marks)
                self.risk.update_equity(equity)
                timeline.append(
                    {
                        "tick": tick,
                        "mark": {
                            "equity_usd": round(equity, 2),
                            "cash_usd": round(self.portfolio.cash, 2),
                            "exposure_usd": round(self.portfolio.exposure_usd(marks), 2),
                            "drawdown_pct": round((1 - equity / self.risk.peak_equity) * 100, 3),
                        },
                    }
                )
            if tick_interval_s > 0:
                await asyncio.sleep(tick_interval_s)

        return _ok("run", artifacts=[{"ticks": ticks, "timeline": timeline, "portfolio": self.snapshot()}])

    # ------------------------------------------------------------------
    # 6.5 Auswertung
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        self.assert_charter()
        marks = self.mark_prices()
        port = self.portfolio.snapshot(marks)
        equity = port["equity_usd"]
        dd = self.risk.update_equity(equity)

        fills = [o for o in self.closed_orders if o.filled_size > 0]
        total_filled = sum(o.filled_size for o in fills)
        slippages = [abs(o.slippage_bps) for o in fills]
        slippage_stats = {
            "count": len(slippages),
            "mean_bps": round(sum(slippages) / len(slippages), 2) if slippages else 0.0,
            "max_bps": round(max(slippages), 2) if slippages else 0.0,
            "p95_bps": _percentile(slippages, 95),
        }

        return {
            **port,
            "charter": self.charter_report(),
            "scope": {
                "engine": "ShadowExecutionEngine",
                "version": SEE_VERSION,
                "execution_mode": self.execution_mode,
                "orders_processed": len(self.closed_orders),
                "orders_rejected": len(self.rejected_orders),
                "orders_blocked": len(self.blocked_orders),
                "total_filled_size": round(total_filled, 6),
                "inversions": len(self.inversion_decisions),
                "matches": self.matcher.match_count,
                "pipeline_runs": self.pipeline_runs,
            },
            "slippage": slippage_stats,
            "matcher": self.matcher.metrics(),
            "risk": self.risk.stats(),
            "market": self.feed.stats(),
            "drawdown": dd,
            "mark_prices": marks,
        }

    def report(self, *, persist: bool = True) -> Dict[str, Any]:
        """Vollstaendiger Bericht + optionaler Persist des Portfolio-Snapshots."""
        snap = self.snapshot()
        if persist:
            self._write_json(self.data_dir / f"portfolio_snapshot_{_now_ms()}.json", snap)
        return snap

    def export_audit_trail(self) -> Path:
        """Schreibt den Audit-Trail als JSONL (GoBD-Stil: append-only, hash-verkettet)."""
        path = self.data_dir / "shadow_audit_trail.jsonl"
        prev = "GENESIS"
        lines: List[str] = []
        for entry in self.audit_entries:
            digest = hashlib.sha256(f"{prev}|{json.dumps(entry, sort_keys=True, default=str)}".encode()).hexdigest()
            record = {**entry, "prev_hash": prev, "hash": digest}
            lines.append(json.dumps(record, default=str))
            prev = digest
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + ("\n" if lines else ""))
        except OSError as exc:
            self.logger.warn("Audit-Trail nicht schreibbar", error=str(exc))
        return path

    # ------------------------------------------------------------------
    # interne Helfer
    # ------------------------------------------------------------------

    def _archive(self, kind: str, payload: Mapping[str, Any]) -> None:
        entry = {
            "timestamp": _now_iso(),
            "kind": kind,
            "user_id": self.user_id,
            "charter_digest": ShadowConfig.charter_digest(),
            "payload": dict(payload),
        }
        self.audit_entries.append(entry)
        if self.persist and len(self.audit_entries) % 25 == 0:
            self.export_audit_trail()

    def _write_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        if not self.persist:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str)
        except OSError as exc:
            self.logger.warn("Snapshot nicht schreibbar", error=str(exc))


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(math.ceil(pct / 100 * len(ordered))) - 1, len(ordered) - 1)
    return round(ordered[max(idx, 0)], 2)

# ============================================================================
# 7. SELF-TEST (Charter-Assertions) & DEMO
# ============================================================================


class CharterViolation(AssertionError):
    """Self-Test-Fehler: Charter wurde verletzt."""


def selftest(verbose: bool = True) -> Dict[str, Any]:
    """Beweist die Charter-Eigenschaften. Kein Netzwerk, keine externen Daten.

    Geprueft wird nicht die Absicht, sondern das Verhalten:
      1. dry_run ist True und nicht von aussen umschaltbar
      2. Ein Live-Relayer-Pfad bricht mit PermissionError ab
      3. `reject_live_transport` bricht ab
      4. PaperOrder: Formatvalidierung greift (Preis, Size, Token)
      5. EIP-712-Mock: Signatur verifiziert und Manipulation faellt auf
      6. Partial Fill + Status-Uebergaenge funktionieren
      7. Drawdown-Lockout greift
      8. Signal-Inversion dreht den Order korrekt
    """
    checks: List[Dict[str, Any]] = []
    log_dir = Path(os.getenv("SEE_SELFTEST_LOG_DIR", "/tmp/see_selftest_logs"))
    data_dir = Path(os.getenv("SEE_SELFTEST_DATA_DIR", "/tmp/see_selftest_data"))
    engine = ShadowExecutionEngine(
        user_id="selftest", bankroll=10_000.0, data_root=data_dir, log_dir=log_dir, persist=False
    )

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": bool(condition), "detail": detail})
        if verbose:
            print(f"  [{'OK ' if condition else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")

    # --- 1. Charter-Konstanten ---
    check("charter.dry_run", engine.dry_run is True)
    check("charter.diagnostic_only", CHARTER_DIAGNOSTIC_ONLY is True)
    check("charter.live_execution_false", CHARTER_LIVE_EXECUTION is False)
    check("charter.order_send_false", CHARTER_ORDER_SEND is False)

    # --- 2. DryRunGuard wirft bei Live-Ausfuehrung ---
    # HINWEIS: `CHARTER_ORDER_SEND` ist eine Modul-Konstante. Ein `import`-Rebind
    # waere wirkungslos (Python-Konstanten sind keine Pointer) — deshalb wird der
    # Guard gegen einen echten manipulierten Zustand geprueft: das Modul-Objekt
    # selbst wird mutiert, genau wie es ein Monkeypatch-Angriff taete.
    sabotage_ok = False
    try:
        _see = sys.modules[__name__]
        original = _see.CHARTER_ORDER_SEND
        _see.CHARTER_ORDER_SEND = True  # simulierte Manipulation derselben Modul-Instanz
        try:
            engine.guard.assert_dry_run("selftest.sabotage")
        except PermissionError as exc:
            sabotage_ok = str(exc) == ORDER_SEND_ERROR
        finally:
            _see.CHARTER_ORDER_SEND = original
    except KeyError:
        sabotage_ok = False
    check("guard.detects_charter_tampering", sabotage_ok, "Manipulation derselben Modul-Instanz erkannt")
    check("guard.dry_run_restored", engine.guard.dry_run is True)

    # --- 3. reject_live_transport ---
    raised = False
    try:
        engine.reject_live_transport("https://clob.polymarket.com")
    except PermissionError as exc:
        raised = str(exc) == ORDER_SEND_ERROR
    check("guard.reject_live_transport", raised)
    check("guard.violations_logged", len(engine.guard.violations) >= 1)

    # --- 4. PaperOrder-Validierung ---
    book = engine.seed_demo_market("tok-selftest", 0.5, event_id="evt-selftest")
    order = PaperOrder(token_id="tok-selftest", price=0.5, size=100, side=OrderSide.BUY, event_id="evt-selftest")
    check("order.payload_clob_conform", order.to_clob_payload()["order"]["makerAmount"].isdigit())
    invalid_payloads = [
        {"price": 1.5},        # Preis ausserhalb (0,1)
        {"price": 0.0},        # Preis = 0
        {"size": -5},          # negative Size
        {"size": 0},           # Size = 0
        {"token_id": ""},      # CLOB-Pflichtfeld fehlt
        {"confidence": 1.4},   # Confidence out of range
    ]
    rejected = 0
    for bad in invalid_payloads:
        payload = {"token_id": "t", "price": 0.5, "size": 10, "side": OrderSide.BUY}
        payload.update(bad)
        try:
            PaperOrder(**payload)
        except Exception:
            rejected += 1
    check(
        "order.validation_rejects_bad_input",
        rejected == len(invalid_payloads),
        f"{rejected}/{len(invalid_payloads)} ungueltige Payloads abgelehnt",
    )

    # --- 5. EIP-712-Mock ---
    ok_sig, reasons = order.verify_signature()
    check("eip712.signature_valid", ok_sig, "; ".join(reasons))
    # Manipulation der Signatur selbst (nicht nur des Payloads)
    tampered = order.model_copy(deep=True)
    object.__setattr__(
        tampered,
        "signature",
        "MOCK|" + MockEIP712Verifier._canonical_address("angreifer") + "|" + "0" * 40,
    )
    ok_tampered, tamper_reasons = tampered.verify_signature()
    check("eip712.tamper_detected", not ok_tampered, "; ".join(tamper_reasons))

    # --- 6. Partial Fill + Status ---
    thin = build_synthetic_book("tok-thin", 0.5, levels=2, depth_usd_per_level=20.0, seed=7)
    big = PaperOrder(token_id="tok-thin", price=0.9, size=10_000, side=OrderSide.BUY, event_id="evt-thin")
    res = engine.matcher.match(big, thin)
    check("match.partial_fill", res.status is OrderStatus.PARTIAL and res.filled_size > 0,
          f"gefuellt {res.filled_size}/{res.requested_size}")
    engine.matcher.close_partial(big)
    check("match.partial_to_closed", big.status is OrderStatus.CLOSED)

    # --- 7. Drawdown-Lockout ---
    lock_engine = ShadowExecutionEngine(user_id="selftest-lock", bankroll=1_000.0, data_root=data_dir,
                                       log_dir=log_dir, persist=False)
    lock_engine.seed_demo_market("tok-lock", 0.5, event_id="evt-lock")
    lock_engine.risk.update_equity(1_000.0)          # Peak
    dd = lock_engine.risk.update_equity(880.0)       # -12% > 10%
    check("risk.drawdown_lockout", dd["lockout_active"] and dd["drawdown_pct"] >= 10.0,
          f"DD {dd['drawdown_pct']}%")
    blocked = lock_engine.process_signal(
        Signal(token_id="tok-lock", market_id="m", event_id="evt-lock", side=OrderSide.BUY, price=0.55, size=10)
    )
    check("risk.lockout_blocks_trading", blocked["status"] == "blocked", blocked.get("error") or "")

    # --- 8. Signal-Inversion ---
    inv_engine = ShadowExecutionEngine(user_id="selftest-inv", bankroll=50_000.0, data_root=data_dir,
                                      log_dir=log_dir, invert_signals=True, persist=False)
    inv_engine.seed_demo_market("tok-inv", 0.5, event_id="evt-inv")
    original = PaperOrder(token_id="tok-inv", price=0.6, size=10, side=OrderSide.BUY, event_id="evt-inv")
    inverted, decision = inv_engine.risk.maybe_invert(original, invert_signals=True)
    check(
        "risk.signal_inversion",
        decision["inverted"] and inverted.side is OrderSide.SELL and abs(inverted.price - 0.4) < 0.011,
        f"{original.side.value}@{original.price} -> {inverted.side.value}@{inverted.price}",
    )
    no_inv, decision2 = inv_engine.risk.maybe_invert(original, invert_signals=False)
    check("risk.inversion_disabled", not decision2["inverted"] and no_inv.side is OrderSide.BUY)

    # --- 9. End-to-End-Paper-Fill ---
    full_engine = ShadowExecutionEngine(user_id="selftest-e2e", bankroll=100_000.0, data_root=data_dir,
                                        log_dir=log_dir, persist=False)
    for i in range(12):
        full_engine.feed.simulate_step([f"tok-e2e-{i}"], base_mids={f"tok-e2e-{i}": 0.5}, seed=i)
    result = full_engine.process_signal(
        Signal(token_id="tok-e2e-0", market_id="mkt", event_id="evt-e2e", side=OrderSide.BUY, price=0.95, size=50)
    )
    check("e2e.paper_fill_completed", result["status"] == "completed", result.get("error") or "")
    snap = full_engine.snapshot()
    check("e2e.portfolio_updated", snap["open_positions"] >= 1 and snap["exposure_usd"] > 0,
          f"Equity {snap['equity_usd']} USD")
    check("e2e.no_charter_violations", len(full_engine.guard.violations) == 0)

    passed = sum(1 for c in checks if c["passed"])
    summary = {
        "passed": passed,
        "total": len(checks),
        "failed": [c["check"] for c in checks if not c["passed"]],
        "charter": engine.charter_report(),
        "checks": checks,
    }
    if verbose:
        print(f"\n  Ergebnis: {passed}/{len(checks)} Checks bestanden")
        if summary["failed"]:
            print(f"  FEHLGESCHLAGEN: {summary['failed']}")
    return summary


def _demo_strategy(book: OrderBookSnapshot, tick: int) -> Optional[Signal]:
    """Beispiel-Strategie: kauft ab Tick 1 in gruenen Ticks, verkauft in roten."""
    mid = book.mid_price
    if mid is None:
        return None
    if mid < 0.35:
        return Signal(
            token_id=book.token_id,
            market_id=book.market_id,
            event_id=book.event_id,
            side=OrderSide.BUY,
            price=_q(min(mid + 0.05, 0.95)),
            size=200.0,
            strategy="demo_mean_reversion",
            confidence=0.7,
            source="demo",
        )
    if mid > 0.65:
        return Signal(
            token_id=book.token_id,
            market_id=book.market_id,
            event_id=book.event_id,
            side=OrderSide.SELL,
            price=_q(max(mid - 0.05, 0.05)),
            size=100.0,
            strategy="demo_mean_reversion",
            confidence=0.6,
            source="demo",
        )
    return None


async def demo() -> Dict[str, Any]:
    """Offline-Demo: keine echten Daten, kein Netzwerk, kein Relayer."""
    print("=" * 78)
    print("  SHADOW EXECUTION ENGINE — Paper-Trading-Satellit (diagnostic_only)")
    print("=" * 78)

    engine = ShadowExecutionEngine(user_id="demo", bankroll=100_000.0, persist=True)
    print(f"\n  Charter: {json.dumps(engine.charter_report(), indent=None)}")

    tokens = [f"tok-{i}" for i in range(4)]
    for i, token in enumerate(tokens):
        engine.seed_demo_market(
            token,
            0.45 + 0.05 * i,
            event_id=f"evt-{i // 2}",
            depth_usd_per_level=700.0 + 100 * i,
            imbalance=0.1 * (i - 1.5),
        )

    print("\n  --- Signal-Pipeline: 6 Signale (inkl. Oversize + stale book) ---")
    scenarios = [
        Signal(token_id="tok-0", event_id="evt-0", side=OrderSide.BUY, price=0.52, size=500, strategy="demo"),
        Signal(token_id="tok-1", event_id="evt-0", side=OrderSide.BUY, price=0.51, size=1_200, strategy="demo"),
        Signal(token_id="tok-2", event_id="evt-1", side=OrderSide.BUY, price=0.47, size=8_000, strategy="demo"),
        Signal(token_id="tok-3", event_id="evt-1", side=OrderSide.SELL, price=0.55, size=300, strategy="demo"),
        Signal(token_id="tok-0", event_id="evt-0", side=OrderSide.BUY, price=0.60, size=12_000, strategy="demo"),
        Signal(token_id="tok-1", event_id="evt-0", side=OrderSide.BUY, price=0.99, size=3_000, strategy="demo"),
    ]
    for i, sig in enumerate(scenarios, start=1):
        out = engine.process_signal(sig)
        art = out["artifacts"][0] if out.get("artifacts") else {}
        match = art.get("match", {})
        diag = match.get("diagnostics", {})
        print(
            f"   [{i}] {out['status']:<9} {sig.side.value:<4} {sig.token_id} "
            f"req={sig.size:<8} fill={match.get('filled_size', 0):<9} "
            f"avg={match.get('avg_price', 0):<6} slip={match.get('slippage_bps', 0):>8}bps "
            f"eff_kosten={diag.get('effective_cost_bps', 0):>8}bps "
            f"{out.get('error') or ''}"
        )

    print("\n  --- Async-Tick-Schleife (8 Ticks, Demo-Strategie) ---")
    result = await engine.run_async(tokens, ticks=8, tick_interval_s=0.0, strategy=_demo_strategy)
    timeline = result["artifacts"][0]["timeline"]
    order_events = [t for t in timeline if "result" in t]
    print(f"   Ticks: 8 | Order-Events: {len(order_events)}")

    print("\n  --- Drawdown-Lockout-Test (simulierter Verlust) ---")
    engine.risk.update_equity(100_000.0)
    dd = engine.risk.update_equity(89_000.0)
    print(f"   drawdown={dd['drawdown_pct']}% lockout={dd['lockout_active']} grund={dd['lockout_reason']}")
    after_lock = engine.process_signal(
        Signal(token_id="tok-0", event_id="evt-0", side=OrderSide.BUY, price=0.52, size=100)
    )
    print(f"   Signal nach Lockout: {after_lock['status']} — {(after_lock.get('logs') or [{}])[0].get('message', '')}")
    engine.risk.unlock("demo-abschluss")

    print("\n  --- Signal-Inversion (Trefferquote simulieren) ---")
    for _ in range(30):
        engine.risk.register_outcome("schwache_strategie", hit=False, pnl_delta=-12.0)
    quality = engine.risk.signal_quality("schwache_strategie")
    print(f"   Trefferquote schwache_strategie: {quality['hit_rate']:.1%} ({quality['samples']} Proben)")
    inv_order, inv_decision = engine.risk.maybe_invert(
        PaperOrder(token_id="tok-2", event_id="evt-1", side=OrderSide.BUY, price=0.6, size=100),
        invert_signals=None,
        strategy="schwache_strategie",
    )
    print(f"   Inversion: {inv_decision['inverted']} — {inv_decision['reason']}")

    snap = engine.report()
    trail = engine.export_audit_trail()
    print("\n  --- Portfolio ---")
    print(f"   Equity:          {snap['equity_usd']:>12,.2f} USD")
    print(f"   Cash:            {snap['cash_usd']:>12,.2f} USD")
    print(f"   Exposure:        {snap['exposure_usd']:>12,.2f} USD")
    print(f"   Realisiert:      {snap['realized_pnl_usd']:>12,.2f} USD")
    print(f"   Offene Pos.:     {snap['open_positions']}")
    print(f"   Slippage (mean/max/p95): {snap['slippage']['mean_bps']} / {snap['slippage']['max_bps']} / {snap['slippage']['p95_bps']} bps")
    print(f"   Charter-Verstoesse: {snap['charter']['violations']} (blockiert: {snap['charter']['blocked_calls']})")
    print(f"   Audit-Trail:     {trail}")
    print("=" * 78)
    return snap


def _main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if "--selftest" in args:
        result = selftest()
        return 0 if not result["failed"] else 1

    print("Self-Test:")
    result = selftest()
    if result["failed"]:
        print("\nSelf-Test FEHLGESCHLAGEN — Demo wird uebersprungen.")
        return 1

    try:
        asyncio.run(demo())
    except RuntimeError:
        # bereits laufender Loop (z. B. in Jupyter/Streamlit)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(demo())
        finally:
            loop.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
