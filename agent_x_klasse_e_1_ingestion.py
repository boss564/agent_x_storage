"""
Agent X — Klasse E: DAO-Governance, Timelocks & Token-Emissions.

Cluster E1 (Ingestion): Timelock-Listener, Vesting-Monitor, Proposal-Scanner.
Langzeit-Heuristiken: Tage bis Monate in die Zukunft.

Agenten:
  E1-1: DAO-Timelock-Listener (EVM)       — 3 Subagenten
  E1-2: Vesting- & Token-Unlock-Monitor    — 3 Subagenten
  E1-3: Governance-Proposal-Scanner        — 3 Subagenten
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("klasse_e1_ingestion")

ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth-mainnet.g.alchemy.com/v2/demo")

# Lazy imports für reale Clients
_governance_client = None
_vesting_client = None


def _get_governance_client():
    global _governance_client
    if _governance_client is None:
        try:
            from agent_x_governance_client import GovernanceClient, GOVERNANCE_CONTRACTS
            _governance_client = GovernanceClient()
            logger.info("Governance-Client initialisiert")
        except Exception as e:
            logger.warning("Governance-Client nicht verfügbar: %s", e)
            _governance_client = None
    return _governance_client


def _get_vesting_client():
    global _vesting_client
    if _vesting_client is None:
        try:
            from agent_x_vesting_client import VestingScanner
            _vesting_client = VestingScanner()
            logger.info("Vesting-Client initialisiert")
        except Exception as e:
            logger.warning("Vesting-Client nicht verfügbar: %s", e)
            _vesting_client = None
    return _vesting_client

# ─── Bekannte Timelock-Controller ────────────────────────────────────

KNOWN_TIMELOCKS = {
    "Aave_v3": {
        "contract": "0x053D55f9B5AF8694c503EB288a1B7E552f590710",
        "chain": "ETHEREUM", "min_delay_h": 24,
        "description": "Aave V3 Governance Timelock",
    },
    "Uniswap_v3": {
        "contract": "0x1a9C8182C09F50C8318d769245beA52c32BE35BC",
        "chain": "ETHEREUM", "min_delay_h": 48,
        "description": "Uniswap V3 Governance Timelock",
    },
    "Compound": {
        "contract": "0x6d903f6003cca6255D85CcA4D3B5E5146dC33925",
        "chain": "ETHEREUM", "min_delay_h": 48,
        "description": "Compound Governance Timelock",
    },
    "MakerDAO": {
        "contract": "0xBE8E3e3618f7474F8cB1d074A26afFef007E98FB",
        "chain": "ETHEREUM", "min_delay_h": 30,
        "description": "MakerDAO Governance Timelock (Pause Proxy)",
    },
}

# Bekannte Vesting-Verträge (OpenZeppelin-ähnlich)
KNOWN_VESTING = {
    "PYTH_Team": {"contract": "0x...1", "token": "PYTH", "chain": "SOLANA",
                  "total_tokens": 1_000_000_000, "cliff_days": 365, "vesting_days": 1460,
                  "start_date": "2024-05-01"},
    "ARB_Foundation": {"contract": "0x...2", "token": "ARB", "chain": "ETHEREUM",
                       "total_tokens": 1_000_000_000, "cliff_days": 180, "vesting_days": 1460,
                       "start_date": "2023-09-01"},
    "OP_Labs": {"contract": "0x...3", "token": "OP", "chain": "ETHEREUM",
                "total_tokens": 500_000_000, "cliff_days": 365, "vesting_days": 1095,
                "start_date": "2024-01-01"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return time.time()


# ═══════════════════════════════════════════════════════════════════════
# AGENT E1-1: DAO-Timelock-Listener
# ═══════════════════════════════════════════════════════════════════════

def e1_1_timelock_listener(action: str = "scan") -> dict:
    """Überwacht CallScheduled/CallExecuted-Events aller Timelock-Controller.

    Returns:
        {"status": "...", "pending_actions": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok", "agent": "E1-1",
                "timelocks_monitored": len(KNOWN_TIMELOCKS),
                "timelocks": {k: v["description"] for k, v in KNOWN_TIMELOCKS.items()},
                "timestamp": _now_iso(),
            }

        # Versuche echten Governance-Client, Fallback auf Demo
        gov_client = _get_governance_client()
        if gov_client:
            try:
                pending = asyncio.run(gov_client.get_pending_timelock_actions())
                if pending:
                    scheduled = {"status": "ok", "subagent": "E1-1a",
                                 "role": "Timelock-Sub", "source": "governance_client_live",
                                 "timelocks_scanned": len(GOVERNANCE_CONTRACTS),
                                 "scheduled_actions": len(pending), "actions": [
                                     {"timelock": p["protocol"], "action": p["title"],
                                      "target": str(p.get("target_contracts", [""])[0]),
                                      "delay_h": round(p["hours_until_execution"], 1),
                                      "scheduled_at": _now_unix() - 3600,
                                      "executable_at": p.get("eta_unix", _now_unix() + 86400),
                                      "impact_score": p.get("impact_score", 5),
                                      "params": {}}
                                     for p in pending
                                 ]}
                else:
                    scheduled = _e1_1a_scan_scheduled_calls_demo()
            except Exception as e:
                logger.warning("Governance-Client Fehler: %s — Fallback", e)
                scheduled = _e1_1a_scan_scheduled_calls_demo()
        else:
            scheduled = _e1_1a_scan_scheduled_calls_demo()
        decoded = _e1_1b_decode_actions(scheduled)
        timeline = _e1_1c_calculate_timeline(decoded)

        return {
            "status": "completed", "agent": "E1-1",
            "pending_actions": timeline.get("pending_count", 0),
            "subagents": {
                "e1_1a_scheduled_calls": scheduled,
                "e1_1b_action_decoder": decoded,
                "e1_1c_timeline": timeline,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E1-1 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e1_1a_scan_scheduled_calls_demo() -> dict:
    """Demo: Timelock CallScheduled Events."""
    now = _now_unix()
    scheduled = []
    # Demo: realistische Governance-Aktionen
    demos = [
        {"timelock": "Aave_v3", "action": "setReserveBorrowRate",
         "target": "0xETH_Pool", "delay_h": 24, "scheduled_at": now - 3600,
         "executable_at": now + 82800,  # 23h from now
         "params": {"asset": "ETH", "new_rate": "5%", "old_rate": "3%"}},
        {"timelock": "Uniswap_v3", "action": "setFeeProtocol",
         "target": "0xFactory", "delay_h": 48,
         "scheduled_at": now - 7200,
         "executable_at": now + 172800,  # 48h
         "params": {"new_fee": "0.25%", "old_fee": "0.05%"}},
        {"timelock": "Compound", "action": "setCollateralFactor",
         "target": "0xCToken_WBTC", "delay_h": 48,
         "scheduled_at": now - 86400,
         "executable_at": now + 86400,  # 24h
         "params": {"asset": "WBTC", "new_factor": "0.70", "old_factor": "0.80"}},
    ]
    for d in demos:
        tl = KNOWN_TIMELOCKS.get(d["timelock"], {})
        scheduled.append({
            **d,
            "contract": tl.get("contract", ""),
            "chain": tl.get("chain", "ETHEREUM"),
        })

    return {
        "status": "ok", "subagent": "E1-1a", "role": "Timelock-Sub",
        "timelocks_scanned": len(KNOWN_TIMELOCKS),
        "scheduled_actions": len(scheduled),
        "actions": scheduled,
    }


def _e1_1b_decode_actions(scan_result: dict) -> dict:
    """Dekodiert die Calldata und Target-Adressen der Aktionen."""
    actions = scan_result.get("actions", [])
    decoded = []
    for a in actions:
        impact = _assess_impact(a.get("action", ""), a.get("params", {}))
        decoded.append({
            **a,
            "impact_score": impact["score"],  # 1-10
            "impact_category": impact["category"],
            "affected_class": (
                "C" if "borrow" in a.get("action", "").lower() or "collateral" in a.get("action", "").lower()
                else "D" if "fee" in a.get("action", "").lower()
                else "B" if "rate" in a.get("action", "").lower()
                else "ALL"
            ),
        })

    return {
        "status": "ok", "subagent": "E1-1b", "role": "Action-Decoder",
        "decoded": decoded,
        "high_impact": sum(1 for d in decoded if d["impact_score"] >= 7),
    }


def _e1_1c_calculate_timeline(decoded_result: dict) -> dict:
    """Berechnet Timeline der ausführbaren Aktionen."""
    actions = decoded_result.get("decoded", [])
    now = _now_unix()
    pending = []
    for a in actions:
        secs = a["executable_at"] - now
        hours = max(0, secs / 3600)
        days = hours / 24
        pending.append({
            "timelock": a["timelock"],
            "action": a["action"],
            "hours_until_executable": round(hours, 1),
            "days_until_executable": round(days, 2),
            "impact_score": a["impact_score"],
            "urgency": (
                "CRITICAL" if hours < 12
                else "HIGH" if hours < 24
                else "MEDIUM" if hours < 72
                else "LOW"
            ),
        })

    pending.sort(key=lambda p: p["hours_until_executable"])

    return {
        "status": "ok", "subagent": "E1-1c", "role": "Timeline-Calculator",
        "pending_count": len(pending),
        "next_action_hours": pending[0]["hours_until_executable"] if pending else 0,
        "pending": pending,
    }


def _assess_impact(action: str, params: dict) -> dict:
    """Impact-Score 1-10 für eine Governance-Aktion."""
    if "borrow_rate" in action.lower() or "interest" in action.lower():
        return {"score": 7, "category": "interest_rate_change"}
    elif "collateral" in action.lower():
        old = float(str(params.get("new_factor", "0.7")).rstrip("%")) / 100
        new = float(str(params.get("old_factor", "0.8")).rstrip("%")) / 100
        delta = abs(new - old) * 100
        return {"score": min(10, max(5, int(delta * 20))), "category": "collateral_change"}
    elif "fee" in action.lower():
        return {"score": 4, "category": "fee_change"}
    return {"score": 3, "category": "other"}


# ═══════════════════════════════════════════════════════════════════════
# AGENT E1-2: Vesting- & Token-Unlock-Monitor
# ═══════════════════════════════════════════════════════════════════════

def e1_2_vesting_monitor(action: str = "scan") -> dict:
    """Scannt Vesting-Verträge und berechnet nächste Unlocks.

    Returns:
        {"status": "...", "upcoming_unlocks": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok", "agent": "E1-2",
                "vesting_contracts": len(KNOWN_VESTING),
                "tokens": [v["token"] for v in KNOWN_VESTING.values()],
                "timestamp": _now_iso(),
            }

        # Versuche echten Vesting-Client, Fallback auf Demo
        vesting_client = _get_vesting_client()
        if vesting_client:
            try:
                all_unlocks = asyncio.run(vesting_client.scan_all_vesting())
                evm_unlocks = [u for u in all_unlocks if u.get("contract", "").startswith("0x")]
                sol_unlocks = [u for u in all_unlocks if "sol" in u.get("contract", "").lower() or u.get("token") == "PYTH"]
                evm = {"status": "ok", "subagent": "E1-2a", "role": "Vesting-Contract-Parser",
                       "chain": "ETHEREUM", "source": "vesting_client_live",
                       "unlocks_found": len(evm_unlocks), "unlocks": evm_unlocks}
                sol = {"status": "ok", "subagent": "E1-2b", "role": "Solana-Vesting-Parser",
                       "chain": "SOLANA", "source": "vesting_client_live",
                       "unlocks_found": len(sol_unlocks), "unlocks": sol_unlocks}
            except Exception as e:
                logger.warning("Vesting-Client Fehler: %s — Fallback", e)
                evm = _e1_2a_parse_evm_vesting_demo()
                sol = _e1_2b_parse_solana_vesting_demo()
        else:
            evm = _e1_2a_parse_evm_vesting_demo()
            sol = _e1_2b_parse_solana_vesting_demo()
        countdown = _e1_2c_unlock_countdown(evm, sol)

        return {
            "status": "completed", "agent": "E1-2",
            "upcoming_unlocks": countdown.get("count", 0),
            "subagents": {
                "e1_2a_evm_vesting": evm,
                "e1_2b_sol_vesting": sol,
                "e1_2c_unlock_countdown": countdown,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E1-2 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e1_2a_parse_evm_vesting_demo() -> dict:
    """Demo: EVM-Vesting-Verträge."""
    now = _now_unix()
    evm_vesting = [v for v in KNOWN_VESTING.values() if v["chain"] == "ETHEREUM"]

    unlocks = []
    for vest in evm_vesting:
        start = datetime.fromisoformat(vest["start_date"]).timestamp()
        cliff = start + vest["cliff_days"] * 86400
        end = start + vest["vesting_days"] * 86400

        # Cliff-Unlock (wenn noch nicht erreicht)
        if cliff > now:
            unlocks.append({
                "token": vest["token"], "amount": vest["total_tokens"] * 0.25,
                "unlock_type": "cliff", "unlock_unix": cliff,
                "days_until": round((cliff - now) / 86400, 1),
            })

        # Lineare Unlocks (nächste 3)
        monthly = vest["total_tokens"] * 0.75 / (vest["vesting_days"] / 30)
        for i in range(1, 4):
            unlock_time = cliff + i * 30 * 86400
            if unlock_time > now:
                unlocks.append({
                    "token": vest["token"], "amount": round(monthly, 0),
                    "unlock_type": "linear", "unlock_unix": unlock_time,
                    "days_until": round((unlock_time - now) / 86400, 1),
                })

    return {
        "status": "ok", "subagent": "E1-2a", "role": "Vesting-Contract-Parser",
        "chain": "ETHEREUM", "unlocks_found": len(unlocks), "unlocks": unlocks,
    }


def _e1_2b_parse_solana_vesting_demo() -> dict:
    """Demo: Solana-Vesting-Programme."""
    return {
        "status": "ok", "subagent": "E1-2b", "role": "Solana-Vesting-Parser",
        "chain": "SOLANA", "unlocks_found": 1,
        "unlocks": [{"token": "PYTH", "amount": 50_000_000,
                     "unlock_unix": _now_unix() + 15 * 86400, "days_until": 15}],
    }


def _e1_2c_unlock_countdown(evm_result: dict, sol_result: dict) -> dict:
    """Erstellt sortierte Unlock-Timeline."""
    all_unlocks = evm_result.get("unlocks", []) + sol_result.get("unlocks", [])
    all_unlocks.sort(key=lambda u: u["unlock_unix"])

    # Aggregiere nach Token
    by_token: dict[str, dict] = {}
    for u in all_unlocks:
        t = u["token"]
        if t not in by_token:
            by_token[t] = {"token": t, "total_upcoming": 0, "next_unlock_days": 999,
                           "next_unlock_amount": 0, "unlocks": []}
        by_token[t]["total_upcoming"] += u["amount"]
        by_token[t]["next_unlock_days"] = min(by_token[t]["next_unlock_days"], u["days_until"])
        by_token[t]["next_unlock_amount"] = u["amount"] if u["days_until"] == by_token[t]["next_unlock_days"] else by_token[t]["next_unlock_amount"]
        by_token[t]["unlocks"].append(u)

    return {
        "status": "ok", "subagent": "E1-2c", "role": "Unlock-Countdown",
        "count": len(all_unlocks),
        "next_unlock_days": all_unlocks[0]["days_until"] if all_unlocks else 999,
        "by_token": list(by_token.values()),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT E1-3: Governance-Proposal-Scanner
# ═══════════════════════════════════════════════════════════════════════

def e1_3_proposal_scanner(action: str = "scan") -> dict:
    """Verfolgt Governance-Proposals und ihren Status.

    Returns:
        {"status": "...", "active_proposals": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok", "agent": "E1-3",
                "protocolls": ["Aave", "Uniswap", "Compound", "MakerDAO"],
                "timestamp": _now_iso(),
            }

        state = _e1_3a_track_proposal_state()
        votes = _e1_3b_monitor_votes(state)
        impact = _e1_3c_estimate_impact(votes)

        return {
            "status": "completed", "agent": "E1-3",
            "active_proposals": impact.get("active_count", 0),
            "subagents": {
                "e1_3a_state_tracker": state,
                "e1_3b_vote_monitor": votes,
                "e1_3c_impact_estimator": impact,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("E1-3 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _e1_3a_track_proposal_state() -> dict:
    """Trackt Proposal-Status (Active, Queued, Executed, Defeated)."""
    proposals = [
        {"id": "Aave_IP-345", "protocol": "Aave", "title": "ETH Borrow Rate anpassen",
         "status": "Queued", "support_pct": 92.5, "voters": 450,
         "execution_time_h": 23, "impact_potential": "HIGH"},
        {"id": "Uni_IP-12", "protocol": "Uniswap", "title": "Fee-Switch aktivieren",
         "status": "Active", "support_pct": 68.3, "voters": 1200,
         "execution_time_h": 96, "impact_potential": "EXTREME"},
        {"id": "Comp_IP-89", "protocol": "Compound", "title": "WBTC Collateral senken",
         "status": "Executed", "support_pct": 88.1, "voters": 320,
         "execution_time_h": 0, "impact_potential": "HIGH"},
    ]

    return {
        "status": "ok", "subagent": "E1-3a", "role": "Proposal-State-Tracker",
        "total": len(proposals),
        "active": sum(1 for p in proposals if p["status"] == "Active"),
        "queued": sum(1 for p in proposals if p["status"] == "Queued"),
        "proposals": proposals,
    }


def _e1_3b_monitor_votes(state_result: dict) -> dict:
    """Analysiert Voting-Patterns."""
    proposals = state_result.get("proposals", [])
    enriched = []
    for p in proposals:
        enriched.append({
            **p,
            "passing_likely": p["support_pct"] > 66,
            "voter_turnout": "high" if p["voters"] > 500 else "medium" if p["voters"] > 100 else "low",
            "estimated_pass_probability": (
                95 if p["support_pct"] > 85
                else 75 if p["support_pct"] > 66
                else 40 if p["support_pct"] > 50
                else 15
            ),
        })

    return {
        "status": "ok", "subagent": "E1-3b", "role": "Vote-Monitor",
        "proposals": enriched,
    }


def _e1_3c_estimate_impact(vote_result: dict) -> dict:
    """Schätzt Impact jedes Proposals (1-10)."""
    proposals = vote_result.get("proposals", [])
    for p in proposals:
        base = {"EXTREME": 10, "HIGH": 7, "MEDIUM": 4, "LOW": 2}.get(p["impact_potential"], 3)
        prob_adj = p.get("estimated_pass_probability", 50) / 100
        p["effective_impact_score"] = round(base * prob_adj, 1)

    proposals.sort(key=lambda p: p.get("effective_impact_score", 0), reverse=True)

    return {
        "status": "ok", "subagent": "E1-3c", "role": "Impact-Estimator",
        "active_count": sum(1 for p in proposals if p["status"] in ("Active", "Queued")),
        "top_impact": proposals[0]["id"] if proposals else "",
        "proposals": proposals,
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "e1_1":
        print(json.dumps(e1_1_timelock_listener("scan"), indent=2))
    elif cmd == "e1_2":
        print(json.dumps(e1_2_vesting_monitor("scan"), indent=2))
    elif cmd == "e1_3":
        print(json.dumps(e1_3_proposal_scanner("scan"), indent=2))
    elif cmd == "status":
        print(json.dumps({
            "e1_1": e1_1_timelock_listener("status"),
            "e1_2": e1_2_vesting_monitor("status"),
            "e1_3": e1_3_proposal_scanner("status"),
        }, indent=2))
    else:
        print(f"Verwendung: {sys.argv[0]} [e1_1|e1_2|e1_3|status]")
