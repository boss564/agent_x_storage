#!/usr/bin/env python3
"""Unit tests for scripts/raas_alert.py (stdlib mocks, no network)."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import raas_alert  # noqa: E402


class RaasAlertTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)

    def test_alerts_disabled_by_default(self) -> None:
        os.environ.pop("RAAS_ALERT_ENABLED", None)
        self.assertFalse(raas_alert.alerts_enabled())
        results = raas_alert.send_alert("test")
        self.assertTrue(results[0].get("skipped"))

    def test_format_rt_check_failure(self) -> None:
        report = {
            "ts": "2026-08-30T09:14:00Z",
            "failures": ["cross_venue_v1=STALE"],
            "checks": [
                {"name": "cross_venue_v1", "status": "STALE", "last_ts": "2026-08-30T08:14:00Z"},
                {"name": "astrocore_hook", "status": "PASS"},
            ],
        }
        text = raas_alert.format_rt_check_failure(report)
        self.assertIn("RT-Check FAILED", text)
        self.assertIn("cross_venue_v1", text)

    def test_dedup_blocks_repeat(self) -> None:
        tmp = Path(self._env.get("TMPDIR", "/tmp")) / "raas_alert_test_state"
        tmp.mkdir(parents=True, exist_ok=True)
        os.environ["RAAS_ALERT_ENABLED"] = "true"
        os.environ["RAAS_STATE_DIR"] = str(tmp)
        os.environ["TELEGRAM_BOT_TOKEN"] = "tok"
        os.environ["TELEGRAM_CHAT_ID"] = "123"

        ok_resp = json.dumps({"ok": True}).encode()

        class FakeResp:
            def read(self) -> bytes:
                return ok_resp

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            first = raas_alert.send_alert_dedup("k", "same message")
            second = raas_alert.send_alert_dedup("k", "same message")
        self.assertTrue(any(r.get("ok") for r in first))
        self.assertTrue(second[0].get("skipped"))
        self.assertEqual(second[0].get("reason"), "dedup_cooldown")

    def test_health_problems_pod_down(self) -> None:
        from scripts.telegram_alert import format_health_alert, health_problems

        report = {
            "generated_at": "2026-08-30T09:00:00Z",
            "pod": {"pod": "regime-swarm-0", "namespace": "trading", "phase": "CrashLoopBackOff", "ready": "false"},
            "components": {
                "CrossVenueMonitor": {"status": "STALE", "age": "70m"},
                "FeedGapMonitor": {"status": "ACTIVE", "age": "1s"},
                "RegimeSwarmDaemon": {"status": "ACTIVE", "age": "1s"},
            },
        }
        problems = health_problems(report)
        self.assertTrue(any("phase=CrashLoopBackOff" in p for p in problems))
        self.assertTrue(any("CrossVenueMonitor=STALE" in p for p in problems))
        text = format_health_alert(report, problems)
        self.assertIn("Regime-Swarm Health", text)

    def test_notify_pod_boot_first_start_no_alert(self) -> None:
        tmp = Path(self._env.get("TMPDIR", "/tmp")) / "raas_boot_test"
        if tmp.is_dir():
            for p in tmp.iterdir():
                p.unlink()
        os.environ["RAAS_ALERT_ENABLED"] = "true"
        os.environ["RAAS_STATE_DIR"] = str(tmp)
        out = raas_alert.notify_pod_boot(state_dir=tmp)
        self.assertIsNone(out)

    def test_notify_pod_boot_restart_alerts(self) -> None:
        tmp = Path(self._env.get("TMPDIR", "/tmp")) / "raas_boot_test2"
        tmp.mkdir(parents=True, exist_ok=True)
        marker = tmp / raas_alert.BOOT_MARKER
        marker.write_text(
            json.dumps({"started_at": "2026-08-30T08:00:00Z", "pod_name": "regime-swarm-0"}),
            encoding="utf-8",
        )
        os.environ["RAAS_ALERT_ENABLED"] = "true"
        os.environ["RAAS_STATE_DIR"] = str(tmp)
        os.environ["TELEGRAM_BOT_TOKEN"] = "tok"
        os.environ["TELEGRAM_CHAT_ID"] = "123"
        os.environ["POD_NAME"] = "regime-swarm-0"

        ok_resp = json.dumps({"ok": True}).encode()

        class FakeResp:
            def read(self) -> bytes:
                return ok_resp

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            out = raas_alert.notify_pod_boot(state_dir=tmp)
        self.assertIsNotNone(out)
        self.assertTrue(any(r.get("ok") for r in out or []))


if __name__ == "__main__":
    unittest.main()
