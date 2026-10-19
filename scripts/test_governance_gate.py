#!/usr/bin/env python3
"""Fehlermodus-Tests fuer das Governance-Gate (B1).

§A-ZZZZ223 (Runde 95): **ein Hook, den kein Test rot machen kann, ist ein
Formular an der Commit-Grenze.**

Die Freigabe B1 verlangt DREI Wege:
    HARD BLOCK  neue Suite ohne Eigentuemer
    ERLAUBT     Commit, der nur Besitz-Felder setzt
    WARNUNG     Besitz rot, kein neuer Test

Getestet wird die ENTSCHEIDUNGSLOGIK, nicht git: die Funktionen werden
mit synthetischen Eingaben gerufen. Ein echter Commit im Test waere ein
Schreibzugriff (B3 verbietet das).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def lade():
    spec = importlib.util.spec_from_file_location(
        "gov", SCRIPTS / "governance_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ok = gesamt = 0
    G = lade()

    # 1. Neue Suite ohne Eigentuemer + fremder Pfad => HARD BLOCK.
    gesamt += 1
    gut = not G.erfuellt_besitz(
        ["scripts/test_neu.py", "scripts/waechter_vertrag.json"],
        '+    "scripts/test_neu.py",\n')
    print(f"{'ok  ' if gut else 'FAIL'} Neue Suite => block        "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 2. Nur Besitz-Felder => ERLAUBT.
    gesamt += 1
    d = ('+       "eigentuemer": {"name": "M. Mueller", "datum": "2026-10-19"},\n'
         '+       "beweisversuch": "Anfrage an ING am 19.10.",\n')
    gut = G.erfuellt_besitz(["scripts/waechter_vertrag.json"], d)
    print(f"{'ok  ' if gut else 'FAIL'} Besitz-Commit => erlaubt    "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 3. Besitz-Pfad, aber fremde Aenderung => NICHT erlaubt.
    gesamt += 1
    gut = not G.erfuellt_besitz(
        ["scripts/waechter_vertrag.json"],
        '+  "record_grammatik": {"regel": "neu"},\n')
    print(f"{'ok  ' if gut else 'FAIL'} Fremdfeld im Besitzpfad    "
          f"{'blockiert' if gut else 'durchgelassen'}")
    ok += gut

    # 4. Zwei Pfade, einer davon fremd => nicht erlaubt (Pfad-Whitelist).
    gesamt += 1
    gut = not G.erfuellt_besitz(
        ["scripts/waechter_vertrag.json", "scripts/test_x.py"],
        '+       "eigentuemer": {"name": "x"},\n')
    print(f"{'ok  ' if gut else 'FAIL'} Zweiter Pfad => block      "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 5. Die bestehende Quarantaene wird erkannt (Rueckkehr => rot).
    gesamt += 1
    d2 = json.loads((SCRIPTS / "waechter_vertrag.json").read_text(
        encoding="utf-8"))
    q = d2["enforcement"]["quarantaene"]
    zurueck = [n for n in q if (SCRIPTS / f"{n}.py").exists()]
    gut = not zurueck and len(q) == 4
    print(f"{'ok  ' if gut else 'FAIL'} Quarantaene intakt         "
          f"{len(q)} gesperrt, zurueck={zurueck or 'keine'}")
    ok += gut

    # 6. B3: das Gate schreibt nicht und liest kein Netz.
    gesamt += 1
    t = (SCRIPTS / "governance_gate.py").read_text(encoding="utf-8")
    verboten = [w for w in ("write_text", "open(", "requests", "urllib",
                            "socket") if w in t]
    gut = not verboten
    print(f"{'ok  ' if gut else 'FAIL'} B3: lesend, offline        "
          f"{verboten or 'ja'}")
    ok += gut

    # 7. B2: getrackter Installer + CI vorhanden.
    gesamt += 1
    inst = (SCRIPTS / "install_hook.sh").exists()
    ci = (SCRIPTS.parent / ".github/workflows/governance.yml").exists()
    gut = inst and ci
    print(f"{'ok  ' if gut else 'FAIL'} B2: Installer + CI        "
          f"installer={inst} ci={ci}")
    ok += gut

    print(f"\n{ok}/{gesamt} Gate-Fehlermodus-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
