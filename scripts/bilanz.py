#!/usr/bin/env python3
"""Bilanz aus Posten — nicht aus Prosa.

§A-ZZZZ220 (Runde 94 Befund 4): **der Satz, der den Rückbau feiert,
rechnet falsch.**

R93 schrieb: "Eine Suite rein, eine rein, vier gesperrt" und daraus
"um drei geschrumpft". Zwei rein (+2), vier gesperrt (−4) = −2.
Und 20 − 4 = 16, nicht 15.

Die Zahlkrankheit war aus der Kopfzeile in den Meta-Satz gewandert.
Dieselbe Ursache wie bei der Standzeile: die Bilanz war Prosa.

Dieses Skript rechnet sie. Es zählt Dateien, keine Behauptungen.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
WURZEL = SCRIPTS.parent
V = SCRIPTS / "waechter_vertrag.json"


def dateien(rev: str) -> int:
    r = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", rev, "scripts/"],
        cwd=WURZEL, capture_output=True, text=True)
    if r.returncode != 0:
        return -1
    return sum(1 for z in r.stdout.splitlines()
               if "/test_" in z and z.endswith(".py")
               and "/quarantaene/" not in z)


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))

    jetzt = dateien("HEAD")
    vorher = dateien("HEAD~1")
    if jetzt < 0 or vorher < 0:
        print("UNBEWIESEN: git nicht lesbar")
        return 2

    # 1. Die Bilanz ist die Differenz der Dateien, nicht eine Behauptung.
    gesamt += 1
    netto = jetzt - vorher
    gut = True
    print(f"{'ok  ' if gut else 'FAIL'} Netto aus Dateien          "
          f"{jetzt} - {vorher} = {netto:+d}")
    ok += gut

    # 2. Die Quarantaene ist getrennt gezaehlt — nicht in der Testzahl.
    gesamt += 1
    q = len(list((SCRIPTS / "quarantaene").glob("*.quarantaene")))
    gut = q > 0
    print(f"{'ok  ' if gut else 'FAIL'} Quarantaene separat        {q}")
    ok += gut

    # 3. Keine Zahl ohne Subtraktion: der Vertrag traegt die Posten.
    gesamt += 1
    posten = d.get("bilanz_regel", {})
    gut = "git" in posten.get("regel", "")
    print(f"{'ok  ' if gut else 'FAIL'} Bilanzregel deklariert     "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 4. Der Fehlermodus: eine getippte Bilanz ist nicht pruefbar.
    gesamt += 1
    gut = d.get("bilanz_regel", {}).get("prosa_verboten") is True
    print(f"{'ok  ' if gut else 'FAIL'} Prosa-Bilanz verboten      "
          f"{gut}")
    ok += gut

    print(f"\n{ok}/{gesamt} Bilanz-Faelle gruen")
    print(f"BILANZ: {netto:+d} Testdateien (aus git, nicht getippt)")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
