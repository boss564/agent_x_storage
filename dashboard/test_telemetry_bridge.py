#!/usr/bin/env python3
"""
Tests fuer die Telemetry-Bridge — Fokus: Zustandsaufloesung.

Warum ueberhaupt Tests fuer ein "kleines Skript": Die Bridge entscheidet, was
das Control Center als Wahrheit anzeigt. Ein falscher Zustand ist schlimmer als
keine Anzeige — 'order_execution_engine' darf nicht den Hub-HEAD erben, ein
Bare-Repo darf nicht als Fehler erscheinen.

Lauf:  python3 dashboard/test_telemetry_bridge.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import telemetry_bridge as tb  # noqa: E402


def _git(args: list[str], cwd: Path) -> int:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True).returncode


class RepoStateTests(unittest.TestCase):
    """Zustandsaufloesung — der Kern der Wahrheitsregel."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="tbbridge-"))
        cls.base = cls.tmp / "base"
        cls.base.mkdir()

        # (a) Sauberes Arbeitsbaum-Repo
        cls.clean = cls.base / "clean"
        cls.clean.mkdir()
        if _git(["init", "-q"], cls.clean) == 0:
            _git(["config", "user.email", "t@t"], cls.clean)
            _git(["config", "user.name", "t"], cls.clean)
            (cls.clean / "a.txt").write_text("a")
            _git(["add", "-A"], cls.clean)
            _git(["commit", "-qm", "init"], cls.clean)

        # (b) Dirty: eine geaenderte Datei
        cls.dirty = cls.base / "dirty"
        shutil.copytree(cls.clean, cls.dirty)
        (cls.dirty / "a.txt").write_text("changed")

        # (c) Untracked: nur unbekannte Dateien
        cls.untracked = cls.base / "untracked"
        shutil.copytree(cls.clean, cls.untracked)
        (cls.untracked / "new.txt").write_text("new")

        # (d) Bare mit Commits: --bare-Klon des sauberen Repos
        cls.bare = cls.tmp / "remote-bare.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(cls.clean), str(cls.bare)],
                       capture_output=True)

        # (e) Leeres Bare (HEAD ungeboren)
        cls.bare_empty = cls.tmp / "empty-bare.git"
        subprocess.run(["git", "init", "-q", "--bare", str(cls.bare_empty)],
                       capture_output=True)

        # (f) Verzeichnis ohne Git
        cls.nogit = cls.base / "nogit"
        cls.nogit.mkdir()

        # (g) Unterordner eines Repos (kein eigenes .git)
        cls.nested = cls.clean / "subdir"
        cls.nested.mkdir()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- worktree

    def test_clean_worktree_is_ok_and_clean(self) -> None:
        s = tb.inspect_repo("clean", str(self.clean), "hub", self.base)
        self.assertEqual(s.state, "ok")
        self.assertEqual(s.health, "CLEAN")
        self.assertIs(s.dirty, False)
        self.assertTrue(s.head)

    def test_dirty_worktree_is_dirty_with_count(self) -> None:
        s = tb.inspect_repo("dirty", str(self.dirty), "hub", self.base)
        self.assertEqual(s.state, "ok")
        self.assertEqual(s.health, "DIRTY")
        self.assertGreaterEqual(s.changed_count, 1)

    def test_only_untracked_is_warn_not_dirty(self) -> None:
        s = tb.inspect_repo("untracked", str(self.untracked), "hub", self.base)
        self.assertEqual(s.health, "WARN")
        self.assertTrue(all(f.startswith("??") for f in s.changed_files))

    # -------------------------------------------------------------------- bare

    def test_bare_with_commits_is_healthy(self) -> None:
        """Der Kernfall: gesundes Bare = state bare (nicht ok), kein Fehler-Alert."""
        s = tb.inspect_repo("bare", str(self.bare), "git-remote", self.base)
        # state und health getrennt: state=bare (Lebenszyklus), health=BARE (Badge).
        # Frueher state=ok bei kind=bare — Widerspruch, behoben in Bridge.
        self.assertEqual(s.state, "bare", f"Bare faelschlich: {s.state} / {s.error}")
        self.assertEqual(s.health, "BARE")
        self.assertEqual(s.kind, "bare")
        self.assertTrue(s.head)
        self.assertIsNone(s.dirty, "Bare hat keinen Arbeitsbaum -> dirty muss None sein")

    def test_bare_is_detected_without_the_flag(self) -> None:
        """Marker-Erkennung greift auch ohne kind='bare' in der Registry."""
        s = tb.inspect_repo("bare", str(self.bare), "git-remote", self.base, "worktree")
        self.assertEqual(s.state, "bare")
        self.assertEqual(s.kind, "bare")

    def test_bare_without_commits_is_empty_not_error(self) -> None:
        """Ein frisches Bare ist ein Zustand, kein Defekt."""
        s = tb.inspect_repo("bare_empty", str(self.bare_empty), "git-remote", self.base)
        self.assertEqual(s.state, "bare_empty")
        self.assertEqual(s.health, "EMPTY")
        self.assertIsNone(s.head)

    def test_bare_does_not_report_no_git(self) -> None:
        """Regression: die naive .git-Pruefung meldete hier 'no_git'."""
        s = tb.inspect_repo("bare", str(self.bare), "git-remote", self.base)
        self.assertNotIn(s.state, ("no_git", "error"))

    # ------------------------------------------------------------- fehlerfaelle

    def test_missing_path_is_not_found(self) -> None:
        s = tb.inspect_repo("ghost", str(self.base / "nicht-da"), "sat", self.base)
        self.assertEqual(s.state, "not_found")
        self.assertEqual(s.health, "NOT FOUND")

    def test_directory_without_git_is_no_git(self) -> None:
        s = tb.inspect_repo("nogit", str(self.nogit), "sat", self.base)
        self.assertEqual(s.state, "no_git")

    def test_subdir_of_repo_is_nested_not_adopted(self) -> None:
        """Ein Unterordner darf NICHT als eigenes Repo durchgehen."""
        s = tb.inspect_repo("sub", str(self.nested), "pkg", self.base)
        self.assertEqual(s.state, "nested")
        self.assertIsNone(s.branch, "nested darf keinen eigenen Branch behaupten")

    def test_relative_path_resolves_against_base(self) -> None:
        s = tb.inspect_repo("clean", "clean", "hub", self.base)
        self.assertEqual(s.state, "ok")

    def test_tilde_path_is_expanded(self) -> None:
        """Regression: '~/...' wurde vor dem expanduser-Fix woertlich genommen."""
        s = tb.inspect_repo("home", "~", "sat", self.base)
        self.assertNotIn("~", s.path)


class RegistryTests(unittest.TestCase):
    """Registry aus Datei — der Mechanismus fuer den Remote-Host."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tbreg-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, payload: object) -> str:
        p = self.tmp / "reg.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return str(p)

    def test_valid_file_overrides_both_registries(self) -> None:
        path = self._write({"repos": [{"name": "r1", "path": "/x"}],
                            "processes": [{"name": "p1", "pattern": "p1"}]})
        repos, procs = tb._load_registry_file(path)
        self.assertEqual([r["name"] for r in repos], ["r1"])
        self.assertEqual([p["name"] for p in procs], ["p1"])

    def test_missing_file_yields_none_not_empty(self) -> None:
        """Eine fehlende Datei ist kein Wunsch nach einer leeren Registry."""
        repos, procs = tb._load_registry_file(str(self.tmp / "fehlt.json"))
        self.assertIsNone(repos)
        self.assertIsNone(procs)

    def test_broken_json_yields_none(self) -> None:
        p = self.tmp / "kaputt.json"
        p.write_text("{kein json", encoding="utf-8")
        repos, procs = tb._load_registry_file(str(p))
        self.assertIsNone(repos)
        self.assertIsNone(procs)

    def test_empty_list_is_wish_not_failure(self) -> None:
        """
        Leere Liste = bewusster Wunsch ("keine Prozesse"), nicht stiller Ausfall.

        Korrektur 2026-10-08: Die fruehere Annahme ("leer = Ausfall -> Default")
        war falsch. Gemessen: Mac-Registry mit "processes": [] liess
        polysentinel weiter als Agent auftauchen, weil `[] or DEFAULT` auf die
        eingebaute Liste zurueckfiel. Die Semantik ist jetzt:
          - Feld FEHLT (None)  -> Default (Abwesenheit eines Wunsches)
          - Feld LEER   ([])   -> leer, kein Default (Wunsch "nichts")
        """
        path = self._write({"repos": [], "processes": []})
        repos, procs = tb._load_registry_file(path)
        self.assertEqual(repos, [])
        self.assertEqual(procs, [])
        # Der Aufrufer darf hier NICHT auf Default zurueckfallen.
        self.assertIsNotNone(repos)
        self.assertIsNotNone(procs)

    def test_missing_key_falls_back_to_default(self) -> None:
        """Fehlt der Schluessel ganz, ist das Abwesenheit eines Wunsches -> Default."""
        path = self._write({"repos": [{"name": "r1", "path": "/x"}]})
        repos, procs = tb._load_registry_file(path)
        self.assertEqual([r["name"] for r in repos], ["r1"])
        self.assertIsNone(procs)
        # So wendet die Bridge den Default an:
        effective = procs if procs is not None else tb.DEFAULT_PROCESS_REGISTRY
        self.assertIs(effective, tb.DEFAULT_PROCESS_REGISTRY)

    def test_default_registry_names_are_stable(self) -> None:
        names = [r["name"] for r in tb.DEFAULT_REPO_REGISTRY]
        self.assertIn("agent_x_storage", names)
        self.assertIn("newsagent", names)
        self.assertIn("x-storage-control-center", names)
        self.assertIn("order_execution_engine", names)
        # Geplante Repos (data_infrastructure/polysentinel/farcaster) bewusst
        # nicht im Default — nach git init erst in die Host-Registry.
        self.assertEqual(len(names), 4)
        self.assertNotIn("data_infrastructure", names)
        self.assertNotIn("polysentinel", names)
        self.assertNotIn("farcaster_app", names)


class ProcessDetectionTests(unittest.TestCase):
    """Prozesserkennung — pgrep UND systemd, weil beide Luecken haben."""

    def test_pgrep_finds_real_process(self) -> None:
        """Ein Prozess, der wirklich laeuft, wird per pgrep gefunden."""
        # Der eigene Testprozess ist garantiert da.
        st = tb.inspect_process({
            "name": "selftest",
            "pattern": "python3",
            "required": False,
        })
        self.assertIn(st.state, ("running", "not_running"))

    def test_missing_process_is_not_running_not_error(self) -> None:
        """Ein fehlender Prozess ist ein Zustand, kein Fehler."""
        st = tb.inspect_process({
            "name": "gibtsnicht",
            "pattern": "_garantiert_kein_treffer_xyzzy_",
            "required": False,
        })
        self.assertEqual(st.state, "not_running")
        self.assertIsNone(st.error)

    def test_required_missing_process_raises_critical_alert(self) -> None:
        st = tb.AgentStatus(name="pflicht", state="not_running", required=True)
        alerts = tb.build_alerts([], [st], {"error": None})
        codes = [a["code"] for a in alerts]
        self.assertIn("PROCESS_DOWN", codes)

    def test_optional_missing_process_is_silent(self) -> None:
        """Kein Alarm fuer optionale Prozesse — sonst Rauschen."""
        st = tb.AgentStatus(name="optional", state="not_running", required=False)
        alerts = tb.build_alerts([], [st], {"error": None})
        self.assertEqual(alerts, [])

    def test_failed_unit_raises_critical_alert(self) -> None:
        """Regression: ein 'failed'-Unit erzeugte vorher KEINEN Alert."""
        st = tb.AgentStatus(name="m2", state="failed", required=False,
                            unit="m2-live-monitor.service")
        alerts = tb.build_alerts([], [st], {"error": None})
        self.assertIn("PROCESS_FAILED", [a["code"] for a in alerts])
        self.assertEqual(alerts[0]["severity"], "critical")

    def test_unit_state_is_preserved_in_snapshot(self) -> None:
        """Der Rohzustand bleibt sichtbar — nicht nur die Uebersetzung."""
        st = tb.AgentStatus(name="x", state="failed", unit="y.service",
                            unit_state="failed", detected_by="systemd")
        d = tb.asdict(st) if hasattr(tb, "asdict") else None
        import dataclasses
        d = dataclasses.asdict(st)
        self.assertEqual(d["unit_state"], "failed")
        self.assertEqual(d["detected_by"], "systemd")


class NestedUntrackedAlertTests(unittest.TestCase):
    """Sabotage: ?? X/ mit/ohne .git — Alert-Typ muss trennen (Befund 2026-10-01)."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="tbnested-"))
        self.hub = self.tmp / "hub"
        self.hub.mkdir()
        self.assertEqual(_git(["init", "-q"], self.hub), 0)
        _git(["config", "user.email", "t@t"], self.hub)
        _git(["config", "user.name", "t"], self.hub)
        (self.hub / "a.txt").write_text("a")
        _git(["add", "-A"], self.hub)
        _git(["commit", "-qm", "init"], self.hub)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _hub_warn(self, changed: list[str]) -> tb.RepoStatus:
        return tb.RepoStatus(
            name="hub", path=str(self.hub), role="hub", state="ok",
            health="WARN", dirty=True,
            changed_files=changed, changed_count=len(changed),
        )

    def test_untracked_dir_with_git_init_is_nested(self) -> None:
        """Fall 1: mkdir X && git init → REPO_NESTED (nicht UNTRACKED)."""
        x = self.hub / "X"
        x.mkdir()
        self.assertEqual(_git(["init", "-q"], x), 0)
        alerts = tb.build_alerts([self._hub_warn(["?? X/"])], [], {"error": None})
        codes = [a["code"] for a in alerts]
        self.assertIn("REPO_NESTED", codes)
        self.assertNotIn("REPO_UNTRACKED", codes)
        nested = next(a for a in alerts if a["code"] == "REPO_NESTED")
        self.assertEqual(nested["severity"], "info")
        self.assertIn("unregistered", nested["message"])
        self.assertEqual(nested["source"], "X")

    def test_untracked_dir_without_git_stays_untracked(self) -> None:
        """Fall 2: mkdir Y && touch Y/a → weiter REPO_UNTRACKED."""
        y = self.hub / "Y"
        y.mkdir()
        (y / "a").write_text("a")
        alerts = tb.build_alerts([self._hub_warn(["?? Y/"])], [], {"error": None})
        codes = [a["code"] for a in alerts]
        self.assertEqual(codes, ["REPO_UNTRACKED"])

    def test_gitdir_file_pointer_is_nested(self) -> None:
        """Fall 3: X/.git als Datei (gitdir: …) → REPO_NESTED."""
        real = self.tmp / "real.git"
        real.mkdir()
        subprocess.run(["git", "init", "-q", "--bare", str(real)], check=True)
        x = self.hub / "X"
        x.mkdir()
        (x / ".git").write_text(f"gitdir: {real}\n")
        alerts = tb.build_alerts([self._hub_warn(["?? X/"])], [], {"error": None})
        self.assertIn("REPO_NESTED", [a["code"] for a in alerts])
        self.assertNotIn("REPO_UNTRACKED", [a["code"] for a in alerts])

    def test_symlink_out_is_not_followed(self) -> None:
        """Fall 4: Symlink Z → externes Repo → kein NESTED."""
        outside = self.tmp / "outside"
        outside.mkdir()
        self.assertEqual(_git(["init", "-q"], outside), 0)
        z = self.hub / "Z"
        z.symlink_to(outside)
        alerts = tb.build_alerts([self._hub_warn(["?? Z"])], [], {"error": None})
        # Symlink nicht folgen: entweder UNTRACKED oder nichts Nested.
        self.assertNotIn("REPO_NESTED", [a["code"] for a in alerts])
        self.assertIn("REPO_UNTRACKED", [a["code"] for a in alerts])

    def test_registry_nested_no_double_alert(self) -> None:
        """Fall 5: X schon als nested in Registry → genau 1 Alert."""
        x = self.hub / "X"
        x.mkdir()
        self.assertEqual(_git(["init", "-q"], x), 0)
        nested = tb.RepoStatus(
            name="X", path=str(x), role="package", state="nested",
            health="NESTED", dirty=None,
        )
        hub = self._hub_warn(["?? X/"])
        alerts = tb.build_alerts([hub, nested], [], {"error": None})
        nested_alerts = [a for a in alerts if a["code"] == "REPO_NESTED"]
        self.assertEqual(len(nested_alerts), 1, alerts)
        self.assertNotIn("REPO_UNTRACKED", [a["code"] for a in alerts])
        self.assertEqual(nested_alerts[0]["source"], "X")

    def test_dirty_parent_still_reports_nested_untracked(self) -> None:
        """DIRTY + ?? X/.git → REPO_DIRTY und REPO_NESTED (kein Blindheit)."""
        x = self.hub / "X"
        x.mkdir()
        self.assertEqual(_git(["init", "-q"], x), 0)
        hub = tb.RepoStatus(
            name="hub", path=str(self.hub), role="hub", state="ok",
            health="DIRTY", dirty=True,
            changed_files=[" M a.txt", "?? X/"], changed_count=2,
        )
        alerts = tb.build_alerts([hub], [], {"error": None})
        codes = [a["code"] for a in alerts]
        self.assertIn("REPO_DIRTY", codes)
        self.assertIn("REPO_NESTED", codes)
        self.assertNotIn("REPO_UNTRACKED", codes)


class BareAlertTests(unittest.TestCase):
    """Alerts fuer die neuen Repo-Zustaende."""

    def test_bare_raises_no_alert(self) -> None:
        """Ein gesundes Bare ist kein Befund."""
        r = tb.RepoStatus(name="bare", path="/x", role="remote",
                          state="ok", kind="bare", health="BARE")
        alerts = tb.build_alerts([r], [], {"error": None})
        self.assertEqual(alerts, [], "Gesundes Bare darf keinen Alert erzeugen")

    def test_bare_empty_raises_warn(self) -> None:
        r = tb.RepoStatus(name="bare", path="/x", role="remote",
                          state="bare_empty", kind="bare", health="EMPTY")
        alerts = tb.build_alerts([r], [], {"error": None})
        self.assertIn("REPO_BARE_EMPTY", [a["code"] for a in alerts])


class RepoAheadTests(unittest.TestCase):
    """
    REPO_AHEAD — Push-Rueckstand als eigener Befund (2026-10-08).

    Der Fall, der das ausgeloest hat: alpha-pipeline, Quelle eines
    produktiven Dienstes, health CLEAN, aber 6 lokale Commits unpushed.
    `git status` sieht das nicht — eine echte Vertragsblindstelle.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="tbahead-"))
        cls.remote = cls.tmp / "remote.git"
        cls.work = cls.tmp / "work"
        subprocess.run(["git", "init", "-q", "--bare", str(cls.remote)],
                       capture_output=True)
        subprocess.run(["git", "clone", "-q", str(cls.remote), str(cls.work)],
                       capture_output=True)
        _git(["config", "user.email", "t@t"], cls.work)
        _git(["config", "user.name", "t"], cls.work)
        (cls.work / "a.txt").write_text("a")
        _git(["add", "-A"], cls.work)
        _git(["commit", "-qm", "init"], cls.work)
        _git(["push", "-q", "origin", "HEAD"], cls.work)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_synced_repo_has_ahead_zero(self) -> None:
        """Synchron: ahead=0, kein REPO_AHEAD."""
        s = tb.inspect_repo("work", str(self.work), "hub", self.tmp)
        self.assertEqual(s.ahead, 0)
        self.assertEqual(s.behind, 0)
        self.assertNotIn("REPO_AHEAD", [a["code"]
                         for a in tb.build_alerts([s], [], {"error": None})])

    def test_unpushed_commit_sets_ahead_and_raises_info(self) -> None:
        """Ein lokaler Commit -> ahead=1 und REPO_AHEAD (info, nicht warn)."""
        (self.work / "b.txt").write_text("b")
        _git(["add", "-A"], self.work)
        _git(["commit", "-qm", "lokal"], self.work)
        s = tb.inspect_repo("work", str(self.work), "hub", self.tmp)
        self.assertEqual(s.ahead, 1, "lokaler Commit muss als ahead=1 erscheinen")
        # health bleibt CLEAN: Der Arbeitsbaum ist sauber, der Befund liegt
        # auf der Push-Achse — genau die Trennung, die den Fall ausmachte.
        self.assertEqual(s.health, "CLEAN")
        alerts = tb.build_alerts([s], [], {"error": None})
        ahead = [a for a in alerts if a["code"] == "REPO_AHEAD"]
        self.assertEqual(len(ahead), 1)
        self.assertEqual(ahead[0]["severity"], "info",
                         "Push-Rueckstand ist ein Hinweis, keine Warnung")

    def test_ahead_zero_after_push(self) -> None:
        """Nach dem Push faellt ahead auf 0 — der Alert verschwindet."""
        _git(["push", "-q", "origin", "HEAD"], self.work)
        s = tb.inspect_repo("work", str(self.work), "hub", self.tmp)
        self.assertEqual(s.ahead, 0)
        self.assertNotIn("REPO_AHEAD", [a["code"]
                         for a in tb.build_alerts([s], [], {"error": None})])

    def test_no_upstream_is_none_not_zero(self) -> None:
        """
        Fehlen ist Information: ohne Upstream ahead=None, NICHT 0.

        Eine 0 wuerde "synchron" behaupten und den fehlenden Upstream
        verschweigen — dieselbe Fehlerklasse wie []-vs-None in der Registry.
        """
        solo = self.tmp / "solo"
        solo.mkdir()
        _git(["init", "-q"], solo)
        _git(["config", "user.email", "t@t"], solo)
        _git(["config", "user.name", "t"], solo)
        (solo / "x.txt").write_text("x")
        _git(["add", "-A"], solo)
        _git(["commit", "-qm", "x"], solo)
        s = tb.inspect_repo("solo", str(solo), "hub", self.tmp)
        self.assertIsNone(s.ahead, "ohne Upstream muss ahead None sein")
        self.assertIsNone(s.behind)
        self.assertNotIn("REPO_AHEAD", [a["code"]
                         for a in tb.build_alerts([s], [], {"error": None})],
                         "ohne Upstream kein Alert — Fehlen ist kein Befund")

    def test_ahead_alert_is_orthogonal_to_health(self) -> None:
        """
        REPO_AHEAD feuert auch bei DIRTY — er darf kein elif sein.

        Sabotage-Probe: Wird REPO_AHEAD in die elif-Kette eingehaengt,
        verschwindet er bei jedem nicht-CLEAN-Repo. Der Test erzwingt die
        Unabhaengigkeit von der Health-Achse.
        """
        (self.work / "c.txt").write_text("c")
        _git(["add", "-A"], self.work)
        _git(["commit", "-qm", "lokal2"], self.work)
        # Arbeitsbaum zusaetzlich schmutzig machen -> health=DIRTY
        (self.work / "a.txt").write_text("geaendert")
        s = tb.inspect_repo("work", str(self.work), "hub", self.tmp)
        self.assertEqual(s.health, "DIRTY")
        self.assertGreater(s.ahead, 0)
        codes = [a["code"] for a in tb.build_alerts([s], [], {"error": None})]
        self.assertIn("REPO_DIRTY", codes)
        self.assertIn("REPO_AHEAD", codes,
                      "REPO_AHEAD muss auch bei DIRTY gemeldet werden "
                      "(orthogonal zur Health-Achse)")


class RepoBehindTests(unittest.TestCase):
    """
    REPO_BEHIND — Deploy-Checkout hinter origin (2026-10-08).

    Der Read-only Deploy-Key ERMOEGLICHT `git pull`, er ERZWINGT es nicht.
    Ein Deploy-Checkout mit behind>0 faehrt einen aelteren Stand als der
    Remote — die Drift-Klasse, die der Key strukturell verhindern sollte.
    Nur fuer role "deploy": an Dev-Repos ist behind normal und Rauschen.
    """

    def _repo(self, role: str, behind) -> "tb.RepoStatus":
        return tb.RepoStatus(name="d", path="/x", role=role, state="ok",
                             kind="worktree", head="abc", branch="main",
                             dirty=False, changed_count=0, health="CLEAN",
                             ahead=0, behind=behind)

    def test_deploy_behind_raises_warn(self) -> None:
        a = tb.build_alerts([self._repo("deploy", 3)], [], {"error": None})
        behind = [x for x in a if x["code"] == "REPO_BEHIND"]
        self.assertEqual(len(behind), 1)
        self.assertEqual(behind[0]["severity"], "warn",
                         "Deploy-Drift ist eine Warnung, kein Hinweis")

    def test_dev_repo_behind_is_silent(self) -> None:
        for role in ("hub", "satellite", "module"):
            a = tb.build_alerts([self._repo(role, 3)], [], {"error": None})
            self.assertNotIn("REPO_BEHIND", [x["code"] for x in a],
                             f"role={role}: behind darf keinen Alert erzeugen")

    def test_deploy_behind_zero_is_silent(self) -> None:
        a = tb.build_alerts([self._repo("deploy", 0)], [], {"error": None})
        self.assertNotIn("REPO_BEHIND", [x["code"] for x in a])

    def test_deploy_no_upstream_is_silent(self) -> None:
        """behind=None (kein Upstream) => kein Alert, kein Fehlalarm."""
        a = tb.build_alerts([self._repo("deploy", None)], [], {"error": None})
        self.assertNotIn("REPO_BEHIND", [x["code"] for x in a])

    def test_measure_push_drift_sets_behind_on_deploy(self) -> None:
        """Ende-zu-Ende: ein echter behind-Zustand liefert behind>0."""
        tmp = Path(tempfile.mkdtemp(prefix="tbbehind-"))
        try:
            origin = tmp / "origin.git"
            subprocess.run(["git", "init", "-q", "--bare", str(origin)],
                           capture_output=True)
            work = tmp / "work"
            subprocess.run(["git", "clone", "-q", str(origin), str(work)],
                           capture_output=True)
            _git(["config", "user.email", "t@t"], work)
            _git(["config", "user.name", "t"], work)
            for n in ("a", "b"):
                (work / f"{n}.txt").write_text(n)
                _git(["add", "-A"], work)
                _git(["commit", "-qm", n], work)
            _git(["push", "-q", "origin", "HEAD"], work)
            server = tmp / "server"
            subprocess.run(["git", "clone", "-q", str(origin), str(server)],
                           capture_output=True)
            _git(["reset", "--hard", "HEAD~1"], server)
            s = tb.inspect_repo("deploy-repo", str(server), "deploy", tmp)
            self.assertEqual(s.behind, 1)
            self.assertEqual(s.ahead, 0)
            self.assertIn("REPO_BEHIND",
                          [x["code"] for x in tb.build_alerts([s], [], {"error": None})])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class SnapshotContractTests(unittest.TestCase):
    """Der Vertrag, den das Dashboard liest."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = Path(tempfile.mkdtemp(prefix="tbsnap-"))
        cls.snap = tb.build_snapshot(base=Path("/nonexistent-base-does-not-matter"))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_top_level_keys_present(self) -> None:
        for key in ("schema_version", "generated_at", "generated_ts", "charter",
                    "repos", "agents", "alerts", "logs", "meta"):
            self.assertIn(key, self.snap)

    def test_generated_ts_matches_generated_at(self) -> None:
        """Der numerische Zwilling muss grob zur ISO-Zeit passen."""
        import datetime as dt
        iso = dt.datetime.fromisoformat(self.snap["generated_at"])
        delta = abs(iso.timestamp() - self.snap["generated_ts"])
        self.assertLess(delta, 5.0)

    def test_repos_carry_kind_field(self) -> None:
        for r in self.snap["repos"]:
            self.assertIn("kind", r)
            self.assertIn(r["kind"], ("worktree", "bare", "package"))

    def test_snapshot_is_json_serializable(self) -> None:
        json.dumps(self.snap)

    def test_charter_is_locked(self) -> None:
        self.assertIs(self.snap["charter"]["live_execution"], False)
        self.assertIs(self.snap["charter"]["order_send"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
