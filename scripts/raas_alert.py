#!/usr/bin/env python3
"""RaaS ops alerts — Telegram (+ optional Slack). Stdlib only, no extra deps.

Env:
    RAAS_ALERT_ENABLED=true
    TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
    SLACK_WEBHOOK_URL (optional)
    RAAS_ALERT_COOLDOWN_S=3600
    RAAS_STATE_DIR=/data/state
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
from typing import Any, Dict, List, Optional

BOOT_MARKER = "pod_boot.json"
DEDUP_MARKER = "alert_dedup.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def alerts_enabled() -> bool:
    return os.environ.get("RAAS_ALERT_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _env_true(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _state_dir() -> Path:
    return Path(os.environ.get("RAAS_STATE_DIR", "/data/state"))


def telegram_chat_id() -> str:
    return (
        os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        or os.environ.get("ADMIN_TELEGRAM_USER_ID", "").strip()
    )


def send_telegram(message: str) -> Dict[str, Any]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = telegram_chat_id()
    if not token or not chat_id:
        return {"channel": "telegram", "ok": False, "skipped": True, "reason": "missing credentials"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = {"chat_id": chat_id, "text": message[:4096]}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return {"channel": "telegram", "ok": bool(payload.get("ok")), "response": payload}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"channel": "telegram", "ok": False, "error": str(exc)}


def send_slack(message: str) -> Dict[str, Any]:
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return {"channel": "slack", "ok": False, "skipped": True, "reason": "missing webhook"}
    req = urllib.request.Request(
        url,
        data=json.dumps({"text": message}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        return {"channel": "slack", "ok": True}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"channel": "slack", "ok": False, "error": str(exc)}


def send_alert(message: str) -> List[Dict[str, Any]]:
    if not alerts_enabled():
        return [{"ok": False, "skipped": True, "reason": "RAAS_ALERT_ENABLED=false"}]
    results: List[Dict[str, Any]] = []
    tg = send_telegram(message)
    if not tg.get("skipped"):
        results.append(tg)
    slack = send_slack(message)
    if not slack.get("skipped"):
        results.append(slack)
    if not results:
        return [{"ok": False, "skipped": True, "reason": "no channels configured"}]
    return results


def send_alert_dedup(
    key: str,
    message: str,
    *,
    cooldown_s: Optional[float] = None,
) -> List[Dict[str, Any]]:
    if not alerts_enabled():
        return [{"ok": False, "skipped": True, "reason": "RAAS_ALERT_ENABLED=false"}]
    cd = cooldown_s if cooldown_s is not None else float(os.environ.get("RAAS_ALERT_COOLDOWN_S", "3600"))
    digest = hashlib.sha256(f"{key}:{message}".encode()).hexdigest()[:16]
    path = _state_dir() / DEDUP_MARKER
    now = datetime.now(timezone.utc).timestamp()
    state: Dict[str, Any] = {}
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    last = state.get(key, {})
    if last.get("digest") == digest and (now - float(last.get("ts", 0))) < cd:
        return [{"ok": True, "skipped": True, "reason": "dedup_cooldown", "key": key}]
    results = send_alert(message)
    if any(r.get("ok") for r in results):
        state[key] = {"digest": digest, "ts": now, "sent_at": _now_iso()}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return results


def notify_pod_boot(*, state_dir: Optional[Path] = None) -> Optional[List[Dict[str, Any]]]:
    """Alert on pod restart when a previous boot marker exists on the PVC."""
    if not alerts_enabled() or not _env_true("RAAS_ALERT_ON_POD_RESTART"):
        return None
    sd = state_dir or _state_dir()
    marker = sd / BOOT_MARKER
    prev: Optional[Dict[str, Any]] = None
    if marker.is_file():
        try:
            prev = json.loads(marker.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = None
    boot = {
        "boot_id": os.environ.get("POD_NAME") or os.environ.get("HOSTNAME", "unknown"),
        "started_at": _now_iso(),
        "pod_name": os.environ.get("POD_NAME", ""),
        "namespace": os.environ.get("POD_NAMESPACE", ""),
    }
    sd.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(boot, indent=2) + "\n", encoding="utf-8")
    if prev is None:
        return None
    msg = (
        "🔄 Regime-Swarm Pod restart\n"
        f"pod={boot.get('pod_name') or boot['boot_id']}\n"
        f"now={boot['started_at']}\n"
        f"prev={prev.get('started_at', '?')}"
    )
    return send_alert_dedup("pod_restart", msg, cooldown_s=300.0)


def format_rt_check_failure(report: Dict[str, Any]) -> str:
    lines = [
        f"🚨 RT-Check FAILED @ {report.get('ts', '?')}",
        f"failures: {', '.join(report.get('failures') or []) or 'unknown'}",
    ]
    for chk in report.get("checks") or []:
        name = str(chk.get("name", "?"))
        st = str(chk.get("status", "?"))
        if name == "astrocore_hook" and st == "FAIL":
            lines.append(f"  astrocore: {chk.get('reason', st)}")
        elif st not in ("PASS", "ACTIVE", "SKIPPED"):
            extra = ""
            if chk.get("last_ts"):
                extra = f" ts={chk['last_ts']}"
            elif chk.get("last_tick_ts"):
                extra = f" ts={chk['last_tick_ts']}"
            lines.append(f"  {name}: {st}{extra}")
    return "\n".join(lines)


def maybe_alert_rt_failure(report: Dict[str, Any], *, force: bool = False) -> Optional[List[Dict[str, Any]]]:
    if report.get("status") == "PASS":
        return None
    if not force and not _env_true("RAAS_ALERT_ON_RT_FAIL"):
        return None
    if not alerts_enabled():
        return None
    return send_alert_dedup("rt_check_fail", format_rt_check_failure(report))


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: raas_alert.py <message>", file=sys.stderr)
        return 2
    results = send_alert(" ".join(sys.argv[1:]))
    print(json.dumps(results, indent=2))
    return 0 if any(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
