#!/usr/bin/env python3
"""Aufrufbaum-Gate: eine spezifizierte Funktion braucht einen Abnehmer.

§A-ZZZZ218 (Runde 94 Befund 5): **der Consumer-Strang verifiziert einen
Abnehmer, der nicht existiert.**

Gemessen in R93:
    rg konsumenten_semantik  ->  test_klasse_mehrdeutig
                                 test_konsument_kongruenz
                                 test_regel_gegen_pos
    Produktionsaufrufer       ->  keiner

Der gesamte Consumer-Strang — R88-Falle, Exit-Taxonomie, STROM-vor-Achse,
Praefix-Grammatik — schuetzt eine Funktion, die niemand in Produktion
aufruft. Ein Spiegelkabinett, das einen leeren Raum beleuchtet.

Dieses Gate misst den AUFRUFBAUM, nicht die Spezifikation. Es fragt
nicht "ist die Faehigkeit beschrieben", sondern "wird die Funktion
gerufen".

ZWEI KLASSEN, keine dritte:
    BESTAND      mindestens ein Nicht-Test-Aufrufer
    SPEKULATIV   kein Produktionsaufrufer — ehrlich etikettiert

"Spekulativ" ist kein Fehler. Es ist ein Etikett, das verhindert, dass
Tests fuer eine Faehigkeit als Beweis fuer ein System gelesen werden.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
WURZEL = SCRIPTS.parent
V = SCRIPTS / "waechter_vertrag.json"

# Aus check_claude_md.py — Dateien, die Tests sind, ohne test_* zu heissen.
KORB = {"regel_konsument.py"}


def aufrufer(modul: str) -> tuple[list[str], list[str]]:
    """(Produktion, nur-Tests). Scannt alle .py ausser diesem Verzeichnis-Test."""
    prod, test = [], []
    for p in WURZEL.rglob("*.py"):
        if p.resolve() == Path(__file__).resolve():
            continue
        if any(part in ("node_modules", ".git", "quarantaene", "lib")
               for part in p.parts):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if not re.search(rf"^\s*(import|from)\s+{modul}\b", t, re.M):
            continue
        rel = str(p.relative_to(WURZEL))
        # §A-ZZZZ219 (R93 Fund, hier bestaetigt): "test_*" ist NICHT die
        # einzige Testform. `regel_konsument.py` ist ein Fixture-Konsument
        # (4/4 im Korb) und heisst nicht test_*. Deshalb zaehlt auch der
        # Korb in check_claude_md.py als Testindikator.
        ist_test = (
            p.name.startswith("test_")
            or "/tests/" in rel
            or p.name in KORB
        )
        (test if ist_test else prod).append(rel)
    return sorted(prod), sorted(test)


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    reg = d.get("aufrufbaum", {})
    module = reg.get("module", [])

    # 1. Die Regel ist deklariert, inkl. der zwei Klassen.
    gesamt += 1
    gut = (len(klassen := reg.get("klassen", [])) == 2
           and "SPEKULATIV" in klassen)
    print(f"{'ok  ' if gut else 'FAIL'} Zwei Klassen, keine dritte   "
          f"{klassen}")
    ok += gut

    # 2. Jedes registrierte Modul hat eine Klasse, die zur Messung passt.
    gesamt += 1
    falsch = []
    for m in module:
        prod, test = aufrufer(m["name"])
        soll = "BESTAND" if prod else "SPEKULATIV"
        if m.get("klasse") != soll:
            falsch.append((m["name"], m.get("klasse"), soll))
    gut = not falsch
    print(f"{'ok  ' if gut else 'FAIL'} Klasse == Messung           "
          f"{falsch or 'alle korrekt'}")
    ok += gut

    # 3. Kein SPekulativ-Modul wird als Beweis gezaehlt.
    gesamt += 1
    spek = [m["name"] for m in module if m.get("klasse") == "SPEKULATIV"]
    gut = all(m.get("beweiskraft") == "KEINE" for m in module
              if m.get("klasse") == "SPEKULATIV")
    print(f"{'ok  ' if gut else 'FAIL'} Spekulativ ohne Beweiskraft "
          f"{spek}")
    ok += gut

    # 4. Der Befund steht im Klartext — nicht als Zahl versteckt.
    gesamt += 1
    gut = "konsumenten_semantik" in spek
    print(f"{'ok  ' if gut else 'FAIL'} konsumenten_semantik etikettiert "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    for m in module:
        prod, test = aufrufer(m["name"])
        print(f"     {m['name']:26} {m.get('klasse'):11} "
              f"prod={len(prod)} test={len(test)}")

    print(f"\n{ok}/{gesamt} Aufrufbaum-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
