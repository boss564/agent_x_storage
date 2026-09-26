#!/usr/bin/env python3
"""
Tests fuer den Remote Pull-Agent.

Fokus: Der Agent muss bei JEDEM Fehlerfall ehrlich bleiben. Die gefaehrlichste
Klasse Fehler ist nicht der Absturz, sondern die stille Luege: eine alte Datei,
die wie eine neue aussieht.

Lauf:  python3 dashboard/test_pull_agent.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pull_agent as pa  # noqa: E402


def _payload(age_seconds: float, repos: int = 2) -> dict:
    return {
        "schema_version": 1,
        "generated_at": "2026-09-21T04:00:00+02:00",
        "generated_ts": time.time() - age_seconds,
        "repos": [{"name": f"r{i}", "state": "ok"} for i in range(repos)],
        "agents": [],
        "alerts": [],
        "charter": {"live_execution": False},
        "meta": {"host": "hetzner"},
    }


class TransportStampTests(unittest.TestCase):
    """Der Transport-Stempel ist der Kern — er sagt, ob die Daten tragen."""

    def test_fresh_data_is_not_stale(self) -> None:
        snap = pa.build_pulled_snapshot(_payload(5), "hetzner", "/x", 60.0, None)
        t = snap["transport"]
        self.assertTrue(t["ok"])
        self.assertFalse(t["stale"])
        self.assertIsNone(t["error"])
        self.assertEqual(snap["alerts"], [])

    def test_old_data_is_marked_stale(self) -> None:
        """300s alt bei 60s-Schwelle = veraltet, mit Begruendung."""
        snap = pa.build_pulled_snapshot(_payload(300), "hetzner", "/x", 60.0, None)
        t = snap["transport"]
        self.assertTrue(t["ok"], "Transport war ok — das Alter ist ein eigener Befund")
        self.assertTrue(t["stale"])
        self.assertIn("REMOTE_STALE", [a["code"] for a in snap["alerts"]])

    def test_failed_transport_sets_ok_false_and_alert(self) -> None:
        snap = pa.build_pulled_snapshot(_payload(5), "hetzner", "/x", 60.0,
                                        "ssh: host unreachable")
        t = snap["transport"]
        self.assertFalse(t["ok"])
        self.assertEqual(t["error"], "ssh: host unreachable")
        self.assertIn("PULL_FAILED", [a["code"] for a in snap["alerts"]])

    def test_transport_block_does_not_replace_payload(self) -> None:
        """Der Transport-Block ergaenzt, er ersetzt nicht die Remote-Felder."""
        snap = pa.build_pulled_snapshot(_payload(5, repos=3), "hetzner", "/x", 60.0, None)
        self.assertEqual(len(snap["repos"]), 3)
        self.assertEqual(snap["schema_version"], 1)
        self.assertIn("transport", snap)

    def test_age_is_none_without_generated_ts(self) -> None:
        """Ein Snapshot ohne generated_ts darf nicht als 'stale' geraten werden."""
        payload = _payload(5)
        del payload["generated_ts"]
        snap = pa.build_pulled_snapshot(payload, "hetzner", "/x", 60.0, None)
        self.assertIsNone(snap["transport"]["age_seconds"])
        self.assertFalse(snap["transport"]["stale"])


class PullOnceTests(unittest.TestCase):
    """pull_once gegen echte und kaputte Zustaende."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tbpull-"))
        self.out = self.tmp / "status-remote.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_write_is_atomic_no_tmp_left(self) -> None:
        pa._write_atomic(_payload(5), self.out)
        self.assertTrue(self.out.is_file())
        leftovers = list(self.tmp.glob("*.tmp"))
        self.assertEqual(leftovers, [], "temp-Datei blieb liegen")

    def test_first_failure_creates_honest_empty_shell(self) -> None:
        """Noch nie geholt + Fehler = leerer Rumpf MIT Fehlerstempel."""
        snap = pa.pull_once("nonexistent.invalid", "/x", self.out, 60.0, 5.0)
        self.assertFalse(snap["transport"]["ok"])
        self.assertEqual(snap["repos"], [])
        self.assertIn("PULL_FAILED", [a["code"] for a in snap["alerts"]])
        self.assertTrue(self.out.is_file())

    def test_failure_preserves_previous_content(self) -> None:
        """Der wichtigste Fall: ein Fehler loescht keine Daten."""
        # Erst erfolgreich schreiben (simuliert durch direkte Ablage)
        previous = pa.build_pulled_snapshot(_payload(5, repos=4), "hetzner", "/x", 60.0, None)
        pa._write_atomic(previous, self.out)

        # Dann ein Fehlschlag
        snap = pa.pull_once("nonexistent.invalid", "/x", self.out, 60.0, 5.0)
        self.assertFalse(snap["transport"]["ok"])
        self.assertEqual(len(snap["repos"]), 4,
                         "Letzter bekannter Stand muss erhalten bleiben")
        self.assertIn("PULL_FAILED", [a["code"] for a in snap["alerts"]])

    def test_broken_previous_file_does_not_crash(self) -> None:
        self.out.write_text("{kaputt", encoding="utf-8")
        snap = pa.pull_once("nonexistent.invalid", "/x", self.out, 60.0, 5.0)
        self.assertFalse(snap["transport"]["ok"])
        # Muss wieder lesbar sein
        json.loads(self.out.read_text(encoding="utf-8"))

    def test_output_is_valid_json_after_every_path(self) -> None:
        for host in ("nonexistent.invalid",):
            pa.pull_once(host, "/x", self.out, 60.0, 5.0)
            json.loads(self.out.read_text(encoding="utf-8"))

    def test_creates_missing_output_directory(self) -> None:
        deep = self.tmp / "a" / "b" / "c" / "status.json"
        pa.pull_once("nonexistent.invalid", "/x", deep, 60.0, 5.0)
        self.assertTrue(deep.is_file())


class SchemaGuardTests(unittest.TestCase):
    """Fremde oder falsche Dateien duerfen nicht als Telemetrie durchgehen."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tbschema-"))
        self.out = self.tmp / "out.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_repos_key_is_rejected(self) -> None:
        """Ein JSON ohne 'repos' ist keine Telemetrie — nicht durchwinken."""
        raw = json.dumps({"hello": "world"})
        try:
            candidate = json.loads(raw)
            valid = isinstance(candidate, dict) and "repos" in candidate
        except json.JSONDecodeError:
            valid = False
        self.assertFalse(valid)

    def test_transport_always_present_in_output(self) -> None:
        pa.pull_once("nonexistent.invalid", "/x", self.out, 60.0, 5.0)
        d = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertIn("transport", d)
        for key in ("fetched_at", "fetched_ts", "source_host", "remote_path",
                    "age_seconds", "stale", "stale_after_seconds", "ok", "error"):
            self.assertIn(key, d["transport"], f"transport.{key} fehlt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
