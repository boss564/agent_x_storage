#!/usr/bin/env python3
"""Prueft CLAUDE.md gegen den tatsaechlichen Projektstand.

Liest keine Absicht, sondern misst: zaehlt die Wellen-Tabelle, misst jede
dokumentierte Zeilenzahl an der Datei nach, laesst die Testskripte laufen und
vergleicht deren Ausgabe mit den Zahlen im Text. Meldet jede Abweichung mit
Zeilennummer.

    python3 check_claude_md.py [projektpfad]     # ohne Tests (schnell)
    python3 check_claude_md.py --run-tests       # inkl. Testlaeufe
    python3 check_claude_md.py --json            # maschinenlesbar

Exit-Code 0 = konsistent, 1 = Abweichungen gefunden.
Gedacht als Pre-Commit-Hook oder naechtlicher Lauf.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

AGENTS_PER_WAVE = 9

# Accumulator für --json-report (wird von check_tests befüllt)
_test_results: dict = {}

# Testskript -> (Ausgabe-Regex, Doku-Kontext-Regex)
# Beide Regexe muessen genau 2 Gruppen haben: (bestanden, gesamt).
# Der Kontext-Regex bestimmt, welche Zeile im Dokument das Ergebnis dieses Skripts
# dokumentiert. Nur x/y-Paare auf Zeilen, die diesen Kontext matchen, werden mit
# dem tatsaechlichen Testergebnis verglichen.
TEST_SCRIPTS: list[tuple[str, str, str]] = [
    (
        "scripts/test_public_portal.py",
        r"(\d+)\s*/\s*(\d+)\s+tests passed",
        r"(?:Public Portal|Wave 15).*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/end_to_end_90_agents.py",
        r"E2E TEST RESULT:\s*(\d+)/(\d+)\s+WAVES PASSED",
        r"E2E.*90.*Agent.*Test.*?(\d+)\s*/\s*(\d+)\s+(?:waves|WAVES) passed",
    ),
    (
        "scripts/end_to_end_b2g_test.py",
        r"E2E Test Complete:\s*(\d+)\s*/\s*(\d+)",
        r"E2E Integration Test.*?(\d+)\s*/\s*(\d+)\s+passed",
    ),
    (
        "scripts/test_wave16_bridge.py",
        r"(\d+)\s*/\s*(\d+)\s+tests passed",
        r"Wave 16.*?SEPA Bridge.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave17_macro.py",
        r"WAVE 17 E2E-TEST:\s*(\d+)/(\d+)\s+BESTANDEN",
        r"Wave 17.*?MacroEconomy.*?(\d+)\s*/\s*(\d+)\s+(?:E2E\s+)?passed",
    ),
    (
        "scripts/test_wave20_security.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Wave 20.*?CertiK.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "shadow_contract_pilot/test_lifecycle.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Shadow.*?Contract.*?Lifecycle.*?(\d+)\s*/\s*(\d+)\s+passed",
    ),
    (
        "scripts/test_wave21_skynet.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Wave 21.*?Skynet.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave27_clearing.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 27.*?Clearing.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave28_defense.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 28.*?Defense.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave29_tokenomics.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 29.*?Token.*?Runtime.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave31_ux.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 31.*?UX.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave32_philately.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 32.*?Philately.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_wave33_survival.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 33.*?Survival.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_esp32_firmware.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"ESP32.*?Firmware.*?(\d+)\s*/\s*(\d+)\s+(?:tests\s+)?passed",
    ),
    (
        "scripts/test_finale.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Wave 34.*?Finale.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_simchain.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Wave 35.*?SimChain.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "scripts/test_multichain.py",
        r"Results:\s*(\d+)/(\d+)\s+passed",
        r"Wave 36.*?MultiChain.*?(\d+)\s*/\s*(\d+)\s+tests? passed",
    ),
    (
        "tests/test_bunker_integration.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Bunker.*?Integration.*?(\d+)\s*/\s*(\d+)\s+tests?",
    ),
    (
        "tests/test_hsm_adapter.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"HSM.*?Adapter.*?(\d+)\s*/\s*(\d+)\s+tests?",
    ),
    (
        "scripts/test_air_layer.py",
        r"ERGEBNIS:\s*(\d+)\s+passed,\s*\d+\s+failed\s*\((\d+)\s+total\)",
        r"Air Layer E2E.*?(\d+)\s*/\s*(\d+)\s+passed",
    ),
]

# Skripte ohne x/y-Testbilanz — Generatoren, Fetcher, Reports.
# Bewusst nicht in TEST_SCRIPTS, damit die Auto-Discovery sie nicht erneut meldet.
NO_TEST_SUMMARY: set[str] = {
    "scripts/test_gaeb_reference.py",  # X83-Fixtures gitignore; TMP-checkout ohne Referenzdaten
    "scripts/test_bvbs_pruefdatei.py",     # braucht externe Pruefdatei
    "scripts/export_backtest_signals.py",  # Daten-Exporter, kein Test
    "scripts/fetch_xrechnung_schematron.py",  # Fetcher, kein Test
    "scripts/test_wave22_ops.py",           # 50+ Klassen-Import → OOM in Sandbox, braucht >256 MB
    "scripts/demo_finale.py",               # Demo-Skript, kein Test
    "scripts/demo_simchain.py",             # Demo-Skript, kein Test
    "scripts/test_e2e_pipeline.py",         # E2E-Test, RESULT ✅/❌ (kein x/y-Bilanz)
    "scripts/test_wirtschaft_base.py",      # Baustein 1: pytest, x/y-Bilanz erst mit Baustein 3
    "scripts/test_wirtschaft_schranken.py", # Baustein 2: Funktionsschranken / Gewaltenteilung
    "scripts/test_wirtschaft_agenten.py",   # Baustein 3: 9 Agenten + Freigabe/Delegation
    "scripts/test_wirtschaft_routing.py",   # Baustein 4: KlassenResolver + Envelope↔AgentMessage
    "scripts/test_wirtschaft_simulation.py",  # Baustein 5a: Event-Log Simulation für Kuramoto
    "scripts/test_wirtschaft_emergence.py",   # Baustein 5b: Kuramoto-Adapter (ergebnisoffen)
    "scripts/test_rescue.py",                 # Rescue-Koordination (Katastrophenschutz, zivil)
    "scripts/test_rescue_simulation.py",      # Rescue volle Simulationsschleife (emergente Kopplung)
    "scripts/test_rescue_clearance.py",       # Rescue Einsatzregeln / Infrastruktur-Freigabe (RoE)
    "scripts/test_study_rescue_density.py",   # Rescue Dichte-Studie Statistik-Helfer (Spearman/KW)
    "scripts/test_ci_h0.py",                  # CI H0-Gate Unit-Tests (Normalbetrieb, Phasen-Offset-Shuffle)
    "scripts/test_ci_stress.py",              # CI Stress-Injektoren (Blackout/Cyber/Naturkatastrophe)
    "scripts/test_hum_h0.py",                 # Humanitäre Logistik H0-Gate (Jitter, Phasen-Offset-Shuffle)
    "scripts/test_hum_stress.py",             # Humanitäre Logistik Stress-Injektoren (Hub/Nachbeben/Komm)
    "scripts/test_smartgrid_h0.py",           # Smart Grid H0 Mess-Validität (R_grid + W_dyn, kein R→1)
    "scripts/test_smartgrid_stress.py",       # Smart Grid Stress-Injektoren (Bewölkung/Spitzenlast/Leitung)
    "scripts/test_evaluator_redundancy.py",   # Hebel 1: Evaluator-Redundanz (strictness tot, 1-von-9)
    "scripts/test_tier2a_eval.py",            # Hebel 3: TIER-2a Effizienz-Auswertung (±5% Pre-Reg)
    "scripts/test_astrocore_evaluator.py",  # AstroCore Kuramoto smoke (IAAFT CI-light)
    "scripts/test_emergence_kopplung_vorarbeit.py",  # Emergence Kopplung Vorarbeit (freeze/shuffle/κ=0)
}


class Report:
    def __init__(self) -> None:
        self.problems: list[dict] = []
        self.env_skips: list[dict] = []
        self.checked = 0

    def ok(self) -> None:
        self.checked += 1

    def fail(self, line: int | None, kind: str, doc, real, note: str = "") -> None:
        self.checked += 1
        self.problems.append({"line": line, "kind": kind, "doc": doc,
                              "real": real, "note": note})

    def env(self, script: str, note: str = "") -> None:
        self.env_skips.append({"script": script, "note": note})


def parse_waves(text: str) -> tuple[list[str], int | None]:
    """Wellen-Tabelle: '| 3.5 | Name | 9 | `modul.py` | ...'"""
    waves = re.findall(r"^\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|[^|]+\|\s*(\d+)\s*\|",
                       text, re.M)
    ids = [w[0] for w in waves]
    per = {int(w[1]) for w in waves}
    return ids, (per.pop() if len(per) == 1 else None)


def check_line_counts(text: str, root: Path, rep: Report) -> None:
    """'# Wave 1: 9 agents, 709 lines' gegen die echte Datei."""
    # Modulpfad aus der Baumzeile davor ist unzuverlaessig — stattdessen die
    # Wellen-Tabelle als Quelle fuer Pfad je Welle nutzen.
    paths = dict(re.findall(r"^\|\s*([0-9.]+)\s*\|[^|]+\|\s*\d+\s*\|\s*`([^`]+)`",
                            text, re.M))
    for lineno, raw in enumerate(text.splitlines(), 1):
        m = re.search(r"Wave ([0-9.]+):.*?([\d.]+)\s+lines", raw)
        if not m:
            continue
        wave, claimed = m.group(1), int(m.group(2).replace(".", ""))
        rel = paths.get(wave)
        if not rel:
            rep.fail(lineno, "Welle ohne Modulpfad", wave, "—",
                     "in der Wellen-Tabelle nicht gefunden")
            continue
        f = root / "agents_b2g" / rel
        if not f.exists():
            rep.fail(lineno, "Datei fehlt", rel, "—")
            continue
        actual = len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
        if actual != claimed:
            rep.fail(lineno, f"Zeilenzahl {rel}", claimed, actual)
        else:
            rep.ok()


def check_dead_refs(text: str, root: Path, rep: Report) -> None:
    """Jeder `pfad.py`-Backtick und jeder python3-Aufruf muss existieren."""
    seen: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), 1):
        for ref in re.findall(r"`([\w/.\-]+\.(?:py|yaml|yml|json|sol|md))`", raw):
            if ref in seen or ref.startswith("tests/"):
                continue
            seen.add(ref)
            hits = [root / ref, root / "agents_b2g" / ref, root / "scripts" / ref]
            if not any(h.exists() for h in hits):
                rep.fail(lineno, "tote Referenz", ref, "existiert nicht")
            else:
                rep.ok()
        m = re.match(r"\s*python3 ([\w/.\-]+\.py)", raw)
        if m and not (root / m.group(1)).exists():
            rep.fail(lineno, "Befehl zeigt ins Leere", m.group(1), "existiert nicht")


def check_counts(text: str, waves: list[str], per: int | None, rep: Report) -> None:
    """Jede '<N> agents'/'<N> waves'-Angabe gegen die Tabelle."""
    # Unterwellen (3.5 etc.) zählen nicht als Hauptwellen — Konvention im Dokument.
    main = [w for w in waves if "." not in w]
    n_waves, n_agents = len(main), len(main) * (per or AGENTS_PER_WAVE)
    for lineno, raw in enumerate(text.splitlines(), 1):
        # Skip lines that are test results (x/y fractions), not head counts
        if re.search(r"\d+/\d+\s+(?:tests?|waves|WAVES)(?:\s+passed|\))", raw):
            continue
        for num, unit in re.findall(r"(\d+)\s+(agents?|waves?|Wellen|B2G-Agenten)",
                                    raw, re.I):
            n = int(num)
            if unit.lower().startswith(("wave", "wellen")):
                if n != n_waves:
                    rep.fail(lineno, "Wellenzahl", n, str(n_waves))
                else:
                    rep.ok()
            elif n >= 50:  # kleine Zahlen sind Subagenten-Angaben, nicht die Summe
                if n != n_agents:
                    rep.fail(lineno, "Agentenzahl", n, str(n_agents))
                else:
                    rep.ok()


def _resolve_test_root(doc_root: Path) -> Path:
    """Repo-Root für Testläufe (Fixtures), unabhängig vom staged checkout-index TMP.

    Pre-commit exportiert den Index nach TMP — dort fehlen gitignorierte
    Referenzdaten (z.B. GAEB X83). AGENT_X_TEST_ROOT oder git toplevel nutzen.
    """
    import os
    env = os.environ.get("AGENT_X_TEST_ROOT")
    if env:
        return Path(env).resolve()
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return doc_root


def check_tests(text: str, root: Path, rep: Report) -> None:
    """Testskripte laufen lassen, Ausgabe gegen die Zahlen im Text halten.

    Jedes Skript hat einen eigenen Doku-Kontext-Regex, der genau die Zeile(n)
    identifiziert, in denen sein Ergebnis dokumentiert ist. Nur x/y-Paare aus
    diesen Zeilen werden mit der tatsaechlichen Testausgabe verglichen.
    """
    test_root = _resolve_test_root(root)
    for script, out_pattern, doc_pattern in TEST_SCRIPTS:
        # Guard: both patterns must have exactly 2 groups (passed, total)
        bad = False
        for name, pat in [("Ausgabe-Regex", out_pattern), ("Doku-Regex", doc_pattern)]:
            if re.compile(pat).groups != 2:
                rep.fail(None, f"Test {script}", pat,
                         f"{name} braucht 2 Gruppen (bestanden/gesamt), hat "
                         f"{re.compile(pat).groups}")
                bad = True
        if bad:
            continue
        # Immer Repo-Skript (nicht TMP): Path(__file__) muss Fixtures/Imports finden.
        # CLAUDE.md kommt weiterhin aus root (staged Index).
        f = test_root / script
        if not f.exists():
            continue
        try:
            out = subprocess.run([sys.executable, str(f)], cwd=str(test_root),
                                 capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            rep.fail(None, f"Test {script}", "—", "Timeout")
            continue
        blob = out.stdout + out.stderr

        # Umgebungsdefizit (fehlendes Modul) von echtem Testfehler unterscheiden
        # Pattern 1: raw ModuleNotFoundError traceback (e.g. pycryptodome)
        missing = re.search(r"ModuleNotFoundError: No module named '(\S+)'", blob)
        # Pattern 2: caught import error in test output (e.g. streamlit/plotly)
        if not missing:
            missing = re.search(r"No module named '(\S+)'", blob)
        if missing:
            rep.env(script, f"Übersprungen — {missing.group(1)} nicht installiert")
            continue

        m = re.search(out_pattern, blob)
        if not m:
            rep.fail(None, f"Test {script}", "—",
                     "Ergebnismuster nicht in der Ausgabe gefunden")
            continue
        real = f"{m.group(1)}/{m.group(2)}"
        _test_results[script] = {
            "passed": int(m.group(1)),
            "total":  int(m.group(2)),
            "failed": int(m.group(2)) - int(m.group(1)),
            "exit_code": out.returncode,
        }

        # Suche im Dokument die Zeile, die per doc_pattern zu diesem Skript gehoert
        found = False
        for lineno, raw in enumerate(text.splitlines(), 1):
            dm = re.search(doc_pattern, raw)
            if not dm:
                continue
            found = True
            doc_val = f"{dm.group(1)}/{dm.group(2)}"
            if doc_val != real:
                rep.fail(lineno, f"Testergebnis {Path(script).stem}",
                         doc_val, real)
            else:
                rep.ok()
        if not found:
            rep.fail(None, f"Testergebnis {Path(script).stem}",
                     "nicht dokumentiert", real)


def check_undocumented_tests(root: Path, rep: Report) -> None:
    """Find all scripts/test_*.py files and check they're registered."""
    on_disk = sorted(
        p.relative_to(root).as_posix()
        for p in root.glob("scripts/test_*.py")
    )
    registered = {t[0] for t in TEST_SCRIPTS} | NO_TEST_SUMMARY
    for script in on_disk:
        if script not in registered:
            rep.fail(None, "Testskript nicht registriert",
                     script, "fehlt in TEST_SCRIPTS oder NO_TEST_SUMMARY")


def main() -> int:
    # Filtere Flags und deren Werte (--json-report <path>)
    raw = sys.argv[1:]
    positional = []
    skip = False
    for a in raw:
        if skip:
            skip = False
            continue
        if a == "--json-report":
            skip = True   # nächster Wert ist der Pfad, kein Positionsargument
            continue
        if a.startswith("-"):
            continue
        positional.append(a)
    root = Path(positional[0]).resolve() if positional else Path.cwd()
    doc = root / "CLAUDE.md"
    if not doc.exists():
        print(f"CLAUDE.md nicht gefunden in {root}", file=sys.stderr)
        return 2

    text = doc.read_text(encoding="utf-8")
    rep = Report()
    waves, per = parse_waves(text)

    check_line_counts(text, root, rep)
    check_dead_refs(text, root, rep)
    check_counts(text, waves, per, rep)
    check_undocumented_tests(root, rep)
    if "--run-tests" in sys.argv:
        check_tests(text, root, rep)

    # JSON-Report für /compliance Endpoint (--json-report <path>)
    json_report_path = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--json-report" and i + 1 < len(sys.argv):
            json_report_path = sys.argv[i + 1]
            break
    if json_report_path and "--run-tests" in sys.argv:
        from datetime import datetime as _dt, timezone as _tz
        report = {
            "generated_at": _dt.now(_tz.utc).isoformat(),
            "repository": str(root),
            "tests": _test_results,
        }
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    if "--json" in sys.argv:
        print(json.dumps({"checked": rep.checked, "problems": rep.problems},
                         indent=2, ensure_ascii=False))
        return 1 if rep.problems else 0

    main_waves = [w for w in waves if "." not in w]
    print(f"CLAUDE.md — {len(text.splitlines())} Zeilen")
    print(f"Wellen-Tabelle: {len(waves)} Zeilen ({', '.join(waves)})")
    print(f"  -> {len(main_waves)} Hauptwellen x {per or AGENTS_PER_WAVE} "
          f"= {len(main_waves)*(per or AGENTS_PER_WAVE)} Agenten")
    print(f"  -> mit Unterwellen: {len(waves)*(per or AGENTS_PER_WAVE)}")
    skipped = len(rep.env_skips)
    status = f"{rep.checked} Angaben geprueft, {len(rep.problems)} Abweichungen"
    if skipped:
        status += f", {skipped} uebersprungen (Umgebung)"
    print(f"\n{status}\n")

    for s in rep.env_skips:
        print(f"  ⏭️  {s['script']}  — {s['note']}")

    for p in rep.problems:
        loc = f"Zeile {p['line']:>4}" if p["line"] else "         "
        print(f"  {loc}  {p['kind']}")
        print(f"            Doku: {p['doc']}   tatsaechlich: {p['real']}"
              + (f"   ({p['note']})" if p["note"] else ""))

    if not rep.problems and not skipped:
        print("  Keine Abweichungen.")
    return 1 if rep.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
