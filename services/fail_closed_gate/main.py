"""Fail-closed gate HTTP service — Option A (isolated infra-gate).

Endpoints:
  GET  /health
  GET  /v1/human_gate
  POST /v1/human_gate   — requires X-Human-Gate-Token (manual open/close)
  POST /v1/evaluate     — returns BLOCKED|RELEASED; never executes trades

Default HUMAN_GATE_OPEN=false. Charter: DEFENSIVE_CAUSAL_GROUNDING.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from gate_core import (
    SCOPE,
    GateInput,
    TradeSignal,
    evaluate_gate,
)

app = FastAPI(title="Agent X Fail-Closed Gate", version="0.1.0")

# Process-local human latch (default CLOSED). Env seeds initial state only.
_human_open: bool = os.environ.get("HUMAN_GATE_OPEN", "false").lower() in (
    "1",
    "true",
    "yes",
)
_TOKEN = os.environ.get("HUMAN_GATE_TOKEN", "")


class SignalBody(BaseModel):
    signal_id: str
    source: str = Field(..., description="P4 | P5 | P7")
    notional_eur: float = 0.0
    stress_score: float = 0.0
    oracle_ok: bool = True
    scenario_ok: bool = True


class EvaluateBody(BaseModel):
    signal: SignalBody
    exec_risk: float = 0.0
    cascade_risk: float = 0.0
    latency_spike: Optional[float] = None
    bho_delta: float = 0.0
    # Client cannot force-open: server uses latch unless override_denied
    respect_human_latch: bool = True


class HumanGateBody(BaseModel):
    open: bool
    confirm: str = Field(
        ...,
        description="Must be OPEN_GATE or CLOSE_GATE",
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "scope": SCOPE,
        "human_gate_open": _human_open,
        "live_execution": False,
    }


@app.get("/v1/human_gate")
def get_human_gate() -> Dict[str, Any]:
    return {
        "open": _human_open,
        "default": "CLOSED",
        "scope": SCOPE,
        "live_execution": False,
    }


@app.post("/v1/human_gate")
def set_human_gate(
    body: HumanGateBody,
    x_human_gate_token: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    global _human_open
    if not _TOKEN:
        raise HTTPException(
            status_code=403,
            detail="HUMAN_GATE_TOKEN unset — refuse remote open (fail-closed)",
        )
    if x_human_gate_token != _TOKEN:
        raise HTTPException(status_code=401, detail="invalid human gate token")
    if body.open and body.confirm != "OPEN_GATE":
        raise HTTPException(status_code=400, detail="confirm must be OPEN_GATE")
    if not body.open and body.confirm != "CLOSE_GATE":
        raise HTTPException(status_code=400, detail="confirm must be CLOSE_GATE")
    _human_open = bool(body.open)
    return {
        "open": _human_open,
        "scope": SCOPE,
        "live_execution": False,
        "note": "RELEASED freigabe only — Agent X does not send orders",
    }


@app.post("/v1/evaluate")
def evaluate(body: EvaluateBody) -> Dict[str, Any]:
    human = _human_open if body.respect_human_latch else False
    # Even if respect_human_latch=False, never auto-open: force closed
    if not body.respect_human_latch:
        human = False
    inp = GateInput(
        signal=TradeSignal(
            signal_id=body.signal.signal_id,
            source=body.signal.source,
            notional_eur=body.signal.notional_eur,
            stress_score=body.signal.stress_score,
            oracle_ok=body.signal.oracle_ok,
            scenario_ok=body.signal.scenario_ok,
        ),
        exec_risk=body.exec_risk,
        cascade_risk=body.cascade_risk,
        latency_spike=body.latency_spike,
        bho_delta=body.bho_delta,
        human_gate_open=human,
    )
    verdict = evaluate_gate(inp)
    out = verdict.to_dict()
    out["human_latch"] = _human_open
    return out
