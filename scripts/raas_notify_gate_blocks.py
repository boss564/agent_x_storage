#!/usr/bin/env python3
"""Notify bridge — alert on new simulated gate BLOCK events (ops only).

Default is dry-run (print payload). Use --send to post Telegram/Discord.
Secrets only via environment / config/raas_ops.env (never commit tokens).

Charter: live_execution=false · not_investment_advice · warn≠trip notify

Usage:
  PYTHONPATH=. python3 scripts/raas_notify_gate_blocks.py
  PYTHONPATH=. python3 scripts/raas_notify_gate_blocks.py --send
  make raas-notify-gate-blocks
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SCOPE = "DEFENSIVE_CAUSAL_GROUNDING"
MAP_REF = "docs/RaaS_OPS_AUTOMATION_v0.md"

# Risk-layer reasons only — not HUMAN_GATE_CLOSED alone, not WARN band
_TRIP_REASONS = frozenset(
    {
        "P3_EXEC_RISK",
        "P8_CASCADE_RISK",
        "Z3_CASCADE_UNSAFE",
        "M7_LATENCY_POISON",
        "BHO_DELTA",
        "SIGNAL_INVALID",
    }
)

_WORM_CANDIDATES = (
    "gate_blocks.jsonl",
    "paper_trading_audit.jsonl",
    "flash_crash_retrospective.jsonl",
    "fn_belt_screen.jsonl",
    "barrier_cal_surface.jsonl",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    env = os.environ.get("RAAS_REPO_ROOT", "").strip()
    if env:
        return Path(env)
    cwd = Path.cwd()
    if (cwd / "services" / "fail_closed_gate").is_dir():
        return cwd
    return _ROOT


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _event_id(source: str, entry: Dict[str, Any], line: str) -> str:
    raw = entry.get("hash") or entry.get("_worm_anchor_sha256") or line
    material = f"{source}|{raw}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _is_risk_block(entry: Dict[str, Any]) -> bool:
    """True only for risk-layer BLOCK — not warn-band, not human-latch alone."""
    if entry.get("live_execution") is True:
        return False  # refuse to advertise live path
    decision = str(entry.get("decision") or entry.get("status") or "").upper()
    reasons = entry.get("reasons") or entry.get("gate_reasons") or []
    if isinstance(reasons, str):
        reasons = [reasons]
    reason_set = {str(r) for r in reasons}

    if entry.get("fn_class") == "STRUCTURAL_GAP_A":
        return False  # warn-band / definition gap — not trip notify
    if entry.get("safety_band") == "WARNUNG":
        return False

    if decision == "BLOCKED":
        if reason_set & _TRIP_REASONS:
            return True
        if reason_set == {"HUMAN_GATE_CLOSED"} or reason_set <= {
            "HUMAN_GATE_CLOSED",
            "HUMAN_GATE_OPEN",
            "ALL_CHECKS_PASS",
        }:
            return False
        # Explicit gate_blocks.jsonl feed
        if entry.get("phase") == "gate_block" or entry.get("source") == "gate_blocks":
            return True
        return bool(reason_set & _TRIP_REASONS)

    # Dedicated feed shape
    if entry.get("blocked") is True and (
        reason_set & _TRIP_REASONS or entry.get("phase") == "gate_block"
    ):
        return True
    return False


def _summarize(entry: Dict[str, Any]) -> str:
    ts = entry.get("ts") or entry.get("timestamp") or "?"
    reasons = entry.get("reasons") or entry.get("gate_reasons") or entry.get("reason")
    if isinstance(reasons, list):
        reasons = ",".join(str(r) for r in reasons)
    market = entry.get("market") or entry.get("symbol") or ""
    return f"{ts} {market} {reasons or 'BLOCKED'}".strip()


def collect_blocks(worm_dir: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name in _WORM_CANDIDATES:
        path = worm_dir / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not _is_risk_block(entry):
                continue
            eid = _event_id(name, entry, line)
            out.append(
                {
                    "id": eid,
                    "source": name,
                    "summary": _summarize(entry),
                    "entry": entry,
                }
            )
    return out


def _load_state(path: Path) -> Set[str]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("seen_ids") or [])
    except (json.JSONDecodeError, OSError):
        return set()


def _save_state(path: Path, seen: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Cap growth
    ids = sorted(seen)[-5000:]
    path.write_text(
        json.dumps(
            {"updated_at": _now(), "seen_ids": ids, "scope": SCOPE},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _http_post_json(url: str, payload: Dict[str, Any], *, ok_codes: Set[int]) -> bool:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return int(resp.status) in ok_codes
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read()[:200]!r}", file=sys.stderr)
        return False
    except urllib.error.URLError as exc:
        print(f"URL error: {exc}", file=sys.stderr)
        return False


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _http_post_json(
        url,
        {"chat_id": chat_id, "text": text},
        ok_codes={200},
    )


def send_discord(webhook: str, text: str) -> bool:
    return _http_post_json(webhook, {"content": text[:1900]}, ok_codes={200, 204})


def format_message(blocks: List[Dict[str, Any]], *, total_new: int) -> str:
    lines = [
        "RaaS risk-gate BLOCK (simulated / paper / screen)",
        f"scope={SCOPE}",
        "live_execution=false",
        "not_investment_advice=true",
        "warn_band≠trip (no notify for WARNUNG alone)",
        f"new_blocks={total_new}",
        "",
    ]
    for b in blocks:
        lines.append(f"- [{b['source']}] {b['summary']}")
    lines.append("")
    lines.append(f"map={MAP_REF}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="RaaS gate-block notify bridge")
    p.add_argument(
        "--send",
        action="store_true",
        help="actually post (default: dry-run)",
    )
    p.add_argument(
        "--mark-seen",
        action="store_true",
        help="update dedup state even on dry-run",
    )
    args = p.parse_args(argv)

    root = _repo_root()
    _load_dotenv(root / "config" / "raas_ops.env")
    _load_dotenv(root / ".env")

    worm_dir = root / "logs" / "worm"
    state_path = worm_dir / "notify_gate_state.json"
    max_n = int(os.environ.get("RAAS_NOTIFY_MAX_BLOCKS") or "5")

    all_blocks = collect_blocks(worm_dir)
    seen = _load_state(state_path)
    new_blocks = [b for b in all_blocks if b["id"] not in seen]

    print(f"repo={root}")
    print(f"worm={worm_dir} sources_scanned={len(_WORM_CANDIDATES)}")
    print(f"blocks_total={len(all_blocks)} new={len(new_blocks)} send={args.send}")

    if not new_blocks:
        print("No new risk-layer BLOCK events.")
        return 0

    payload_blocks = new_blocks[-max_n:]
    message = format_message(payload_blocks, total_new=len(new_blocks))
    print("--- message ---")
    print(message)
    print("---------------")

    if not args.send:
        print("Dry-run (pass --send to notify).")
        if args.mark_seen:
            for b in new_blocks:
                seen.add(b["id"])
            _save_state(state_path, seen)
            print(f"State updated: {state_path}")
        return 0

    tg_token = os.environ.get("RAAS_TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.environ.get("RAAS_TELEGRAM_CHAT_ID", "").strip()
    discord = os.environ.get("RAAS_DISCORD_WEBHOOK_URL", "").strip()

    sent = False
    if tg_token and tg_chat:
        ok = send_telegram(tg_token, tg_chat, message)
        print(f"telegram={'ok' if ok else 'FAIL'}")
        sent = sent or ok
    else:
        print("telegram=skipped (no token/chat)")

    if discord:
        ok = send_discord(discord, message)
        print(f"discord={'ok' if ok else 'FAIL'}")
        sent = sent or ok
    else:
        print("discord=skipped (no webhook)")

    if not sent:
        print(
            "FAIL: --send gesetzt, aber kein Kanal konfiguriert "
            "(RAAS_TELEGRAM_* / RAAS_DISCORD_WEBHOOK_URL leer) "
            "oder alle Sends fehlgeschlagen — nichts gesendet.",
            file=sys.stderr,
        )
        return 2

    for b in new_blocks:
        seen.add(b["id"])
    try:
        _save_state(state_path, seen)
        print(f"State updated: {state_path}")
    except OSError as exc:
        print(
            f"FAIL: notify sent but dedup state not writable ({state_path}): {exc}. "
            "Next run may re-notify the same blocks.",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
