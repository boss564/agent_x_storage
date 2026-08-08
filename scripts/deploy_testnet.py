#!/usr/bin/env python3
"""
AGENT X B2G — Testnet Deployment auf Gnosis Chiado.

Deployt den VOB_Shadow_Escrow Smart Contract auf Chiado Testnet.
Erwartet OPERATOR_PRIVATE_KEY in der Umgebung oder .env.testnet.

Usage:
    # 1. Faucet: https://faucet.chiadochain.net/
    # 2. Deploy:
    export GNOSIS_CHIADO_RPC_URL="https://rpc.chiadochain.net"
    export OPERATOR_PRIVATE_KEY="0x..."
    python3 scripts/deploy_testnet.py

    # 3. Verify: Explorer-Link aus der Ausgabe öffnen
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env():
    """Lädt .env.testnet falls vorhanden."""
    env_file = PROJECT_ROOT / ".env.testnet"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    if key not in os.environ:
                        os.environ[key] = val.strip().strip('"')


def rpc_call(url: str, method: str, params: list) -> dict:
    """Führt einen JSON-RPC-Call aus (urllib, keine web3-Abhängigkeit)."""
    import urllib.request
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def derive_address(pk: str) -> str:
    """Leitet die Adresse aus dem Private Key ab."""
    try:
        from eth_account import Account
        return Account.from_key(pk).address
    except ImportError:
        pass
    # Fallback: manuell via sha3
    try:
        import hashlib
        from eth_keys import keys
        pk_bytes = bytes.fromhex(pk[2:] if pk.startswith("0x") else pk)
        return keys.PrivateKey(pk_bytes).public_key.to_checksum_address()
    except ImportError:
        raise RuntimeError("Installiere eth-account: pip install eth-account")


def sign_and_send(url: str, pk: str, to: str | None, data: str, value_wei: int = 0,
                  gas: int = 2_000_000) -> dict:
    """Signiert und sendet eine Transaktion via eth_sendRawTransaction."""
    try:
        from eth_account import Account
    except ImportError:
        raise RuntimeError("Installiere eth-account: pip install eth-account")

    acct = Account.from_key(pk)
    nonce_resp = rpc_call(url, "eth_getTransactionCount", [acct.address, "latest"])
    nonce = int(nonce_resp["result"], 16)

    gas_price_resp = rpc_call(url, "eth_gasPrice", [])
    gas_price = int(gas_price_resp["result"], 16)

    chain_id_resp = rpc_call(url, "eth_chainId", [])
    chain_id = int(chain_id_resp["result"], 16)

    tx = {
        "from": acct.address,
        "nonce": hex(nonce),
        "gas": hex(gas),
        "gasPrice": hex(gas_price),
        "chainId": chain_id,
        "data": data,
        "value": hex(value_wei),
    }
    if to:
        tx["to"] = to

    signed = acct.sign_transaction(tx)
    send_resp = rpc_call(url, "eth_sendRawTransaction", [signed.raw_transaction.hex()])
    if "error" in send_resp:
        raise RuntimeError(f"Send failed: {send_resp['error']}")
    return {"tx_hash": send_resp["result"], "from": acct.address, "nonce": nonce,
            "gas_price_wei": gas_price}


def wait_for_receipt(url: str, tx_hash: str, timeout_s: int = 120) -> dict:
    """Wartet auf Transaktions-Receipt."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = rpc_call(url, "eth_getTransactionReceipt", [tx_hash])
        if resp.get("result") and resp["result"] is not None:
            return resp["result"]
        time.sleep(2)
    raise TimeoutError(f"Kein Receipt für {tx_hash} nach {timeout_s}s")


def main():
    load_env()

    rpc_url = os.getenv("GNOSIS_CHIADO_RPC_URL", "https://rpc.chiadochain.net")
    private_key = os.getenv("OPERATOR_PRIVATE_KEY", "")

    print("=" * 60)
    print("     🚀 AGENT X B2G — TESTNET DEPLOYMENT (CHIADO)")
    print("=" * 60)
    print(f"  RPC:  {rpc_url}")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print()

    # 1. Verbindung prüfen
    print("1. Prüfe RPC-Verbindung...")
    try:
        chain_id = int(rpc_call(rpc_url, "eth_chainId", [])["result"], 16)
        block = int(rpc_call(rpc_url, "eth_blockNumber", [])["result"], 16)
        print(f"   -> Chain ID: {chain_id} | Block: {block:,}")
    except Exception as e:
        print(f"   ❌ RPC nicht erreichbar: {e}")
        return 1

    # 2. Wallet prüfen
    if not private_key or private_key == "0x" + "0" * 64:
        print("\n   ⚠️  OPERATOR_PRIVATE_KEY nicht gesetzt.")
        print("   Setze in .env.testnet oder via export.")
        print("   Faucet: https://faucet.chiadochain.net/")
        return 1

    print("\n2. Prüfe Wallet...")
    try:
        addr = derive_address(private_key)
        bal = rpc_call(rpc_url, "eth_getBalance", [addr, "latest"])
        xdai = int(bal["result"], 16) / 1e18
        print(f"   -> Adresse:  {addr}")
        print(f"   -> Guthaben: {xdai:.6f} xDAI")
        if xdai < 0.001:
            print(f"   -> ⚠️  WARNUNG: < 0.001 xDAI — Faucet benötigt!")
            print(f"   -> Faucet: https://faucet.chiadochain.net/")
            return 1
    except ImportError:
        print("   -> ⚠️  eth-account nicht installiert. Installiere: pip install eth-account")
        return 1

    # 3. Deploy Contract
    print("\n3. Deploye VOB_Shadow_Escrow...")
    contract_src = PROJECT_ROOT / "shadow_contract_pilot" / "contract" / "VOB_Shadow_Escrow.sol"
    if contract_src.exists():
        src_size = contract_src.stat().st_size
        print(f"   -> Contract-Source: {contract_src} ({src_size} bytes)")
        print(f"   -> ⚠️  Kein Compiler vorhanden — verwende Mock-Bytecode für Dry-Run")

    # Real compiled bytecode from Foundry (forge build)
    mock_bytecode = "0x60806040..."  # minimal fallback
    bytecode = mock_bytecode  # fallback
    artifact_path = PROJECT_ROOT / "out" / "VOB_Shadow_Escrow.sol" / "VOB_Shadow_Escrow.json"
    if artifact_path.exists():
        import json as _json
        artifact = _json.loads(artifact_path.read_text())
        bytecode = artifact["bytecode"]["object"]
        print(f"   -> Bytecode:   Kompiliert ({len(bytecode)} chars, {(len(bytecode)-2)//2} bytes)")
    else:
        # Suche rekursiv
        import glob as _g
        candidates = _g.glob(str(PROJECT_ROOT / "out" / "**" / "VOB_Shadow_Escrow.json"), recursive=True)
        if candidates:
            import json as _json2
            artifact = _json2.loads(open(candidates[0]).read())
            bytecode = artifact["bytecode"]["object"]
            print(f"   -> Bytecode:   Kompiliert ({len(bytecode)} chars, {(len(bytecode)-2)//2} bytes)")
        else:
            print(f"   -> Bytecode:   Mock (kein kompiliertes Artefakt gefunden)")

    # ---- Crash-Safety: prüfe ob bereits eine TX läuft ----
    state_file = PROJECT_ROOT / ".deployment_state.json"
    state = {}
    if state_file.exists():
        state = json.loads(state_file.read_text())
        pending_tx = state.get("tx_hash")
        if pending_tx:
            print(f"   -> Vorherige TX gefunden: {pending_tx[:20]}...")
            try:
                receipt = wait_for_receipt(rpc_url, pending_tx, timeout_s=30)
                if receipt.get("status") == "0x1" or receipt.get("contractAddress"):
                    contract_addr = receipt.get("contractAddress", state.get("contract_address", "unknown"))
                    print(f"   ✅ Bereits deployed: {contract_addr}")
                    state_file.write_text(json.dumps({"status": "completed", "contract_address": contract_addr, "tx_hash": pending_tx}, indent=2))
                    return 0
                else:
                    print(f"   ⚠️  TX revertiert — neuer Versuch.")
            except TimeoutError:
                print(f"   ⚠️  TX noch pending — warte oder breche ab (Ctrl+C).")
                return 1

    print(f"   -> Signiere Transaktion...")

    try:
        result = sign_and_send(rpc_url, private_key, None, bytecode)
        tx_hash = result["tx_hash"]
        # Speichere sofort für Crash-Recovery
        state = {"tx_hash": tx_hash, "nonce": result["nonce"], "status": "pending"}
        state_file.write_text(json.dumps(state, indent=2))
        print(f"   -> Tx gesendet: {tx_hash} (State gesichert)")
        print(f"   -> Warte auf Bestätigung...")

        receipt = wait_for_receipt(rpc_url, tx_hash)
        contract_addr = receipt.get("contractAddress", "unknown")
        block_num = int(receipt.get("blockNumber", "0x0"), 16)
        gas_used = int(receipt.get("gasUsed", "0x0"), 16)

        print(f"\n   ✅ DEPLOYED!")
        print(f"   -> Contract:     {contract_addr}")
        print(f"   -> Block:        {block_num:,}")
        print(f"   -> Gas gebruikt: {gas_used:,}")
        print(f"   -> Explorer:     https://gnosis-chiado.blockscout.com/address/{contract_addr}")

        # Speichere Deployment-Info
        deployed_file = PROJECT_ROOT / ".deployed_contracts.json"
        deployed = {}
        if deployed_file.exists():
            deployed = json.loads(deployed_file.read_text())
        deployed["gnosis_chiado"] = {
            "contract_address": contract_addr,
            "tx_hash": tx_hash,
            "deployer": result["from"],
            "block": block_num,
            "gas_used": gas_used,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        deployed_file.write_text(json.dumps(deployed, indent=2))
        # Crash-Safety: Deployment erfolgreich → State bereinigen
        state_file.write_text(json.dumps({"status": "completed", "contract_address": contract_addr, "tx_hash": tx_hash}, indent=2))
        print(f"   -> Gespeichert:  {deployed_file}")

    except Exception as e:
        print(f"\n   ❌ Deployment fehlgeschlagen: {e}")
        return 1

    print(f"\n{'='*60}")
    print("✅ DEPLOYMENT ERFOLGREICH")
    print(f"{'='*60}")
    print(f"Nächster Schritt:")
    print(f"  Pilot-Backend auf Live-Modus umstellen:")
    print(f"  PILOT_MOCK=false SHADOW_CONTRACT_ADDRESS={contract_addr} python3 shadow_contract_pilot/backend/pilot_backend.py --live")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
