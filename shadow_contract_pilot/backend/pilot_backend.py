#!/usr/bin/env python3
# shadow_contract_pilot/backend/pilot_backend.py
"""
Backend für den Shadow-Contract-Piloten.

Stellt die REST-API für das Dashboard bereit und orchestriert die
Interaktion mit dem VOB_Shadow_Escrow Smart Contract auf Gnosis Chain.

Integration:
  - Wave 16 (Monerium SEPA-Bridge): EURe Mint/Burn
  - Wave 18 (Shadow Contract): 14-Phasen-Lifecycle
  - Wave 20 (CertiK Audit): Conservation-of-Funds Invariante

Usage:
    python pilot_backend.py                  # Dev-Server auf :5001
    python pilot_backend.py --prod            # Produktion mit Gunicorn
    python pilot_backend.py --mock            # Mock-Daten ohne Chain
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ================================================================
# Configuration (Entkopplung — keine Hardcoded-Pfade)
# ================================================================


class PilotConfig:
    """Zentrale Konfiguration für den Shadow-Contract-Piloten."""

    # Chain
    RPC_URL: str = os.getenv("GNOSIS_RPC", "https://rpc.gnosischain.com")
    CHAIN_ID: int = int(os.getenv("GNOSIS_CHAIN_ID", "100"))

    # Contract
    CONTRACT_ADDRESS: str = os.getenv(
        "SHADOW_CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000"
    )

    # EURe Token (Monerium, Wave 16)
    EURE_TOKEN_ADDRESS: str = os.getenv(
        "EURE_TOKEN_ADDRESS", "0xcB444e90D8198415266c6a2724b7900fb12FC56E"
    )

    # Account
    PRIVATE_KEY: str = os.getenv("PILOT_PRIVATE_KEY", "")

    # Server
    HOST: str = os.getenv("PILOT_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PILOT_PORT", "5001"))
    DEBUG: bool = os.getenv("PILOT_DEBUG", "true").lower() == "true"

    # Dashboard
    DASHBOARD_DIR: Path = Path(__file__).resolve().parent.parent / "dashboard"

    # Multi-Tenancy
    USER_ID: str = os.getenv("PILOT_USER_ID", "pilot_default")

    # Mock-Mode (kein RPC, keine Chain)
    MOCK_MODE: bool = os.getenv("PILOT_MOCK", "true").lower() == "true"


# ================================================================
# Flask App
# ================================================================

app = Flask(
    __name__,
    static_folder=str(PilotConfig.DASHBOARD_DIR),
    static_url_path="",
)
CORS(app)


# ================================================================
# Chain Connection (graceful fallback to mock)
# ================================================================

w3 = None
contract = None
account = None
chain_connected = False


def _init_chain() -> None:
    """Initialize Web3 connection. Falls back to mock on any failure."""
    global w3, contract, account, chain_connected

    if PilotConfig.MOCK_MODE or not PilotConfig.PRIVATE_KEY:
        print("  ⚠️  Mock-Mode — keine Chain-Verbindung")
        return

    try:
        from web3 import Web3
        from eth_account import Account

        w3 = Web3(Web3.HTTPProvider(PilotConfig.RPC_URL))
        if not w3.is_connected():
            raise ConnectionError(f"Cannot connect to {PilotConfig.RPC_URL}")

        if PilotConfig.PRIVATE_KEY and PilotConfig.PRIVATE_KEY != "":
            account = Account.from_key(PilotConfig.PRIVATE_KEY)
            print(f"  ✓ Chain connected: {PilotConfig.RPC_URL}")
            print(f"  ✓ Account: {account.address[:10]}...")

        if PilotConfig.CONTRACT_ADDRESS != "0x" + "0" * 40:
            # Contract ABI (minimal — nur die read-Funktionen fürs Dashboard)
            contract_abi = _load_contract_abi()
            contract = w3.eth.contract(
                address=w3.to_checksum_address(PilotConfig.CONTRACT_ADDRESS),
                abi=contract_abi,
            )
            print(f"  ✓ Contract: {PilotConfig.CONTRACT_ADDRESS[:10]}...")

        chain_connected = True
    except ImportError:
        print("  ⚠️  web3/eth_account nicht installiert — Mock-Mode")
    except Exception as exc:
        print(f"  ⚠️  Chain-Init fehlgeschlagen: {exc} — Mock-Mode")


def _load_contract_abi() -> list:
    """Minimale ABI für Read-Only-Dashboard-Zugriff."""
    return [
        {
            "inputs": [],
            "name": "getProjectStatus",
            "outputs": [
                {"internalType": "uint256", "name": "totalBudget", "type": "uint256"},
                {"internalType": "uint256", "name": "totalReleased", "type": "uint256"},
                {"internalType": "uint256", "name": "retentionVault", "type": "uint256"},
                {"internalType": "uint256", "name": "taxVault", "type": "uint256"},
                {"internalType": "bool", "name": "isActive", "type": "bool"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "string", "name": "_ozId", "type": "string"}],
            "name": "getMilestone",
            "outputs": [
                {"internalType": "string", "name": "ozId", "type": "string"},
                {"internalType": "string", "name": "description", "type": "string"},
                {"internalType": "uint256", "name": "grossAmount", "type": "uint256"},
                {"internalType": "uint256", "name": "releaseableAmount", "type": "uint256"},
                {"internalType": "bool", "name": "isCompleted", "type": "bool"},
                {"internalType": "bytes32", "name": "popwProofHash", "type": "bytes32"},
                {"internalType": "uint256", "name": "completedAt", "type": "uint256"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "getMilestoneCount",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "name": "milestoneIds",
            "outputs": [{"internalType": "string", "name": "", "type": "string"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "verifyBHOInvariant",
            "outputs": [
                {"internalType": "bool", "name": "", "type": "bool"},
                {"internalType": "int256", "name": "delta", "type": "int256"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
    ]


# ================================================================
# Mock Data Store (wenn keine Chain verfügbar)
# ================================================================


class MockDataStore:
    """In-Memory-Daten für Mock-Betrieb. Spiegelt den Smart Contract wider."""

    def __init__(self):
        self.total_budget = Decimal("1274896.80")
        self.total_released = Decimal("434778.00")
        self.retention_vault = Decimal("21738.90")
        self.tax_vault = Decimal("82607.82")
        self.is_active = True
        self.milestones: list[dict] = [
            {
                "ozId": "01.01.0010",
                "description": "Baugrubenaushub Bodenklasse 3-4",
                "grossAmount": Decimal("202500.00"),
                "releaseableAmount": Decimal("0"),
                "isCompleted": True,
                "popwProofHash": "0x4e8a2b1c9f0d8e7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c",
                "completedAt": 1722528000,
            },
            {
                "ozId": "03.01.0010",
                "description": "Stahlbetonsohle C30/37 gießen",
                "grossAmount": Decimal("297500.00"),
                "releaseableAmount": Decimal("0"),
                "isCompleted": False,
                "popwProofHash": None,
                "completedAt": 0,
            },
            {
                "ozId": "02.01.0050",
                "description": "Edelstahl-Druckleitung DN300",
                "grossAmount": Decimal("10200.00"),
                "releaseableAmount": Decimal("0"),
                "isCompleted": False,
                "popwProofHash": None,
                "completedAt": 0,
            },
        ]
        self.transactions: list[dict] = [
            {
                "timestamp": "2026-08-01T10:00:00Z",
                "event": "Projekt finanziert",
                "amount": Decimal("1274896.80"),
            },
            {
                "timestamp": "2026-08-15T14:00:00Z",
                "event": "Abschlag #1 freigegeben",
                "amount": Decimal("302787.80"),
            },
            {
                "timestamp": "2026-09-15T14:00:00Z",
                "event": "Abschlag #2 freigegeben",
                "amount": Decimal("287648.41"),
            },
        ]


mock_store = MockDataStore()


# ================================================================
# Data Sources
# ================================================================


def _read_from_chain() -> dict:
    """Liest den Projektstatus live vom Smart Contract."""
    try:
        status = contract.functions.getProjectStatus().call()
        count = contract.functions.getMilestoneCount().call()
        milestones = []
        for i in range(count):
            oz_id = contract.functions.milestoneIds(i).call()
            m = contract.functions.getMilestone(oz_id).call()
            milestones.append({
                "ozId": m[0],
                "description": m[1],
                "grossAmount": Decimal(str(m[2])) / Decimal("100"),
                "releaseableAmount": Decimal(str(m[3])) / Decimal("100"),
                "isCompleted": m[4],
                "popwProofHash": "0x" + m[5].hex() if m[5] != b'\x00' * 32 else None,
                "completedAt": m[6],
            })

        # BHO Invariante prüfen
        bho_ok, bho_delta = contract.functions.verifyBHOInvariant().call()

        gross_total = sum(m["grossAmount"] for m in milestones)
        completed_total = sum(
            m["grossAmount"] for m in milestones if m["isCompleted"]
        )
        progress = round(float(completed_total / gross_total * 100), 1) if gross_total > 0 else 0

        return {
            "source": "chain",
            "contractAddress": PilotConfig.CONTRACT_ADDRESS,
            "totalBudget": Decimal(str(status[0])) / Decimal("100"),
            "totalReleased": Decimal(str(status[1])) / Decimal("100"),
            "retentionVault": Decimal(str(status[2])) / Decimal("100"),
            "taxVault": Decimal(str(status[3])) / Decimal("100"),
            "isActive": status[4],
            "progress": progress,
            "milestones": milestones,
            "transactions": [],  # Events vom Indexer (nicht im Contract-State)
            "bhoInvariant": {"ok": bho_ok, "delta": str(bho_delta)},
            "lastUpdate": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return {
            "source": "chain_error",
            "error": str(exc),
            "contractAddress": PilotConfig.CONTRACT_ADDRESS,
        }


def _read_from_mock() -> dict:
    """Mock-Daten für Offline-Betrieb und Demo."""
    gross_total = sum(m["grossAmount"] for m in mock_store.milestones)
    completed_total = sum(
        m["grossAmount"] for m in mock_store.milestones if m["isCompleted"]
    )
    progress = round(float(completed_total / gross_total * 100), 1) if gross_total > 0 else 0

    return {
        "source": "mock",
        "contractAddress": PilotConfig.CONTRACT_ADDRESS or "0x4B2c889a7182E89100223",
        "totalBudget": float(mock_store.total_budget),
        "totalReleased": float(mock_store.total_released),
        "retentionVault": float(mock_store.retention_vault),
        "taxVault": float(mock_store.tax_vault),
        "isActive": mock_store.is_active,
        "progress": progress,
        "milestones": [
            {
                "ozId": m["ozId"],
                "description": m["description"],
                "grossAmount": float(m["grossAmount"]),
                "releaseableAmount": float(m["releaseableAmount"]),
                "isCompleted": m["isCompleted"],
                "popwProofHash": m["popwProofHash"],
                "completedAt": m["completedAt"],
            }
            for m in mock_store.milestones
        ],
        "transactions": [
            {
                "timestamp": t["timestamp"],
                "event": t["event"],
                "amount": float(t["amount"]),
            }
            for t in mock_store.transactions
        ],
        "bhoInvariant": {
            "ok": True,
            "delta": "0.00",
        },
        "lastUpdate": datetime.now(timezone.utc).isoformat(),
    }


# ================================================================
# API Endpoints
# ================================================================


@app.route("/")
def index():
    """Dashboard ausliefern."""
    return send_from_directory(str(PilotConfig.DASHBOARD_DIR), "index.html")


@app.route("/api/shadow-pilot/status", methods=["GET"])
def get_status():
    """Gibt den aktuellen Status des Shadow-Contract-Piloten zurück."""
    if chain_connected:
        data = _read_from_chain()
        if data.get("source") == "chain_error":
            # Fallback zu Mock bei Chain-Fehler
            data = _read_from_mock()
            data["source"] = "mock_fallback"
    else:
        data = _read_from_mock()
    return jsonify(data)


@app.route("/api/shadow-pilot/deploy", methods=["POST"])
def deploy_contract():
    """Deployt den Shadow-Contract (nur im Mock-Mode)."""
    if chain_connected:
        return jsonify({
            "status": "NOT_IMPLEMENTED",
            "message": "Live-Deployment nur über Hardhat/Foundry-Skripte",
        }), 501

    return jsonify({
        "status": "DEPLOYED_MOCK",
        "contractAddress": "0x4B2c889a7182E89100223",
        "txHash": "0x" + "a" * 64,
        "blockNumber": 18492011,
    })


@app.route("/api/shadow-pilot/milestone/complete", methods=["POST"])
def complete_milestone():
    """Markiert einen Meilenstein als abgeschlossen."""
    data = request.json or {}
    oz_id = data.get("ozId")
    proof_hash = data.get("proofHash", "0x" + "0" * 64)

    if not oz_id:
        return jsonify({"status": "ERROR", "message": "ozId required"}), 400

    if chain_connected and contract:
        # Echter Contract-Call
        try:
            tx = contract.functions.completeMilestone(
                oz_id, bytes.fromhex(proof_hash[2:])
            ).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 200_000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            return jsonify({
                "status": "COMPLETED",
                "ozId": oz_id,
                "proofHash": proof_hash,
                "txHash": tx_hash.hex(),
            })
        except Exception as exc:
            return jsonify({"status": "ERROR", "message": str(exc)}), 500

    # Mock
    for m in mock_store.milestones:
        if m["ozId"] == oz_id:
            m["isCompleted"] = True
            m["popwProofHash"] = proof_hash
            m["completedAt"] = int(time.time())
            return jsonify({
                "status": "COMPLETED_MOCK",
                "ozId": oz_id,
                "proofHash": proof_hash,
            })

    return jsonify({"status": "ERROR", "message": f"Milestone {oz_id} not found"}), 404


@app.route("/api/shadow-pilot/milestone/release", methods=["POST"])
def release_milestone():
    """Löst die Auszahlung für einen Meilenstein aus."""
    data = request.json or {}
    oz_id = data.get("ozId")

    if not oz_id:
        return jsonify({"status": "ERROR", "message": "ozId required"}), 400

    # Mock
    for m in mock_store.milestones:
        if m["ozId"] == oz_id and m["isCompleted"]:
            gross = m["grossAmount"]
            net = gross - (gross * Decimal("19") / Decimal("119")) - (gross * Decimal("5") / Decimal("100"))
            m["releaseableAmount"] = Decimal("0")
            mock_store.transactions.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": f"Abschlag {oz_id} freigegeben",
                "amount": float(net),
            })
            return jsonify({
                "status": "RELEASED_MOCK",
                "ozId": oz_id,
                "netAmount": float(net),
            })

    return jsonify({"status": "ERROR", "message": f"Cannot release {oz_id}"}), 400


@app.route("/api/shadow-pilot/close", methods=["POST"])
def close_project():
    """Schließt das Projekt ab."""
    if chain_connected and contract:
        return jsonify({
            "status": "NOT_IMPLEMENTED",
            "message": "Live-Close nur über Multisig",
        }), 501

    mock_store.is_active = False
    mock_store.transactions.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "Projekt abgeschlossen",
        "amount": float(mock_store.total_released),
    })
    return jsonify({
        "status": "CLOSED_MOCK",
        "totalReleased": float(mock_store.total_released),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/shadow-pilot/health", methods=["GET"])
def health():
    """Health-Check für Ops-Monitoring (Wave 7/8)."""
    return jsonify({
        "status": "healthy",
        "mode": "mock" if not chain_connected else "live",
        "contract": PilotConfig.CONTRACT_ADDRESS,
        "chain": "gnosis" if chain_connected else "none",
        "user_id": PilotConfig.USER_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ================================================================
# Main
# ================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Shadow Contract Pilot Backend")
    parser.add_argument("--mock", action="store_true", default=True,
                        help="Mock-Mode (Standard)")
    parser.add_argument("--live", action="store_true",
                        help="Live-Mode mit Chain-Verbindung")
    parser.add_argument("--prod", action="store_true",
                        help="Produktion (kein Debug)")
    parser.add_argument("--host", type=str, default=PilotConfig.HOST)
    parser.add_argument("--port", type=int, default=PilotConfig.PORT)
    args = parser.parse_args()

    if args.live:
        PilotConfig.MOCK_MODE = False
    if args.prod:
        PilotConfig.DEBUG = False

    print("=" * 55)
    print("  🏗️  VOB Shadow-Contract Pilot — Backend")
    print("=" * 55)
    print(f"  Mode:      {'Mock' if PilotConfig.MOCK_MODE else 'Live'}")
    print(f"  Chain:     {PilotConfig.RPC_URL}")
    print(f"  Contract:  {PilotConfig.CONTRACT_ADDRESS}")
    print(f"  Dashboard: {PilotConfig.DASHBOARD_DIR}")
    print(f"  Server:    http://{args.host}:{args.port}")
    print("=" * 55)

    _init_chain()

    if args.prod:
        # Gunicorn-kompatibel
        app.run(host=args.host, port=args.port, debug=False)
    else:
        app.run(host=args.host, port=args.port, debug=PilotConfig.DEBUG)


if __name__ == "__main__":
    main()
