"""File-backed RaaS store — contracts & runs under data/raas/."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"


def _data_root() -> Path:
    root = os.environ.get("RAAS_DATA_ROOT", "data/raas")
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_contract(
    *,
    tenant_id: str,
    name: str,
    bytecode_hex: str = "",
    abi: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contract_id = str(uuid.uuid4())
    material = f"{tenant_id}|{name}|{bytecode_hex}"
    digest = hashlib.sha256(material.encode()).hexdigest()
    rec = {
        "contract_id": contract_id,
        "tenant_id": tenant_id,
        "name": name,
        "bytecode_sha256": digest,
        "bytecode_len": len(bytecode_hex) // 2 if bytecode_hex else 0,
        "abi_present": bool(abi),
        "scope": SCOPE,
        "live_execution": False,
        "created_at": _now(),
    }
    base = _data_root() / tenant_id / "contracts"
    _write_json(base / f"{contract_id}.json", rec)
    if bytecode_hex:
        (base / f"{contract_id}.hex").write_text(bytecode_hex, encoding="utf-8")
    if abi:
        _write_json(base / f"{contract_id}.abi.json", abi)
    return rec


def get_contract(*, tenant_id: str, contract_id: str) -> Optional[Dict[str, Any]]:
    path = _data_root() / tenant_id / "contracts" / f"{contract_id}.json"
    if not path.exists():
        return None
    return _read_json(path)


def create_run(
    *,
    tenant_id: str,
    contract_id: str,
    n_scenarios: int,
    profile: str = "default",
) -> Dict[str, Any]:
    contract = get_contract(tenant_id=tenant_id, contract_id=contract_id)
    if not contract:
        raise ValueError(f"contract not found: {contract_id}")
    run_id = str(uuid.uuid4())
    rec = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "contract_id": contract_id,
        "contract_sha256": contract["bytecode_sha256"],
        "n_scenarios": int(n_scenarios),
        "profile": profile,
        "status": "PENDING",
        "scope": SCOPE,
        "live_execution": False,
        "created_at": _now(),
        "updated_at": _now(),
        "gate_verdict": None,
        "metrics": {},
    }
    run_dir = _data_root() / tenant_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "run.json", rec)
    return rec


def update_run(tenant_id: str, run_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    run_dir = _data_root() / tenant_id / "runs" / run_id
    path = run_dir / "run.json"
    if not path.exists():
        raise ValueError(f"run not found: {run_id}")
    rec = _read_json(path)
    rec.update(patch)
    rec["updated_at"] = _now()
    _write_json(path, rec)
    return rec


def get_run(*, tenant_id: str, run_id: str) -> Optional[Dict[str, Any]]:
    path = _data_root() / tenant_id / "runs" / run_id / "run.json"
    if not path.exists():
        return None
    return _read_json(path)


def run_dir(tenant_id: str, run_id: str) -> Path:
    return _data_root() / tenant_id / "runs" / run_id


def append_worm_line(tenant_id: str, run_id: str, event: Dict[str, Any]) -> str:
    """Append-only JSONL with hash chain."""
    rd = run_dir(tenant_id, run_id)
    worm = rd / "audit.worm.jsonl"
    prev = "GENESIS"
    if worm.exists():
        last = worm.read_text(encoding="utf-8").strip().splitlines()[-1]
        prev = json.loads(last).get("hash", "GENESIS")
    line = {
        "ts": _now(),
        "prev": prev,
        "event": event,
    }
    digest = hashlib.sha256(
        json.dumps(line, sort_keys=True, default=str).encode()
    ).hexdigest()
    line["hash"] = digest
    with open(worm, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, default=str) + "\n")
    return digest
