#!/usr/bin/env python3
"""Exit 2: Meta-Achse, aber nicht zeilenlos.

§A-ZZZZ148 (Runde 85): **ein Exit ohne Zeilen ist eine leere Parse.**

R84 trennte Exit 2 sauber als Meta-Fehler von den Inhalts-Urteilen — und
liess ihn dann vor jedem Zeilen-Array terminieren. Der Konsument bekam 2
und nichts zu handeln, obwohl der Aufruf syntaktisch gueltig war. Die
Schema-Invarianz (7/7) deckte 0/1/3/4, nicht 2.

Jetzt traegt jeder 2-Zweig genau EINE Zeile mit dem Zeiger `AUFRUF`
(kein Inhalt, also kein Inhalts-Hash) und dem Urteil VERWERFEN. Dieser
Test betritt JEDEN 2-Zweig — kein Zweig bleibt unbetreten.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

W = Path(__file__).resolve().parent / "einwurf_waechter.py"


def _lauf(*argv: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(W), *argv],
                       capture_output=True, text=True)
    return r.returncode, r.stdout


def main() -> int:
    ok = 0
    gesamt = 0
    # Nur ECHTE 2-Zweige: der Aufruf selbst ist falsch. Ein unlesbarer
    # Strom ist Exit 3 (Strom nicht pruefbar) — ein Inhalts-Urteil, kein
    # Meta-Fehler. Dieser Test prueft die 2-Achse, nicht die 3-Achse.
    faelle = [
        ("kein Modus", "grund=kein_modus", ()),
        ("einwurf ohne strom", "grund=einwurf_ohne_strom", ("--einwurf",)),
    ]
    for name, soll, argv in faelle:
        gesamt += 1
        code, out = _lauf(*argv)
        m = re.search(r"ZEILE AUFRUF VERWERFEN;([a-z_]+=[a-z_]+);", out)
        gut = code == 2 and m and m.group(1) == soll
        print(f"{'ok  ' if gut else 'FAIL'} {name:26s} exit={code} "
              f"zeile={'ja' if m else 'FEHLT'} {m.group(1) if m else ''}")
        ok += gut
    # Kein 2-Zweig darf eine Inhaltszeile vortaeuschen.
    gesamt += 1
    _, out = _lauf()
    inhalt = re.findall(r"ZEILE ([0-9a-f]{12,}) ", out)
    gut = not inhalt
    print(f"{'ok  ' if gut else 'FAIL'} kein Inhalts-Hash bei 2      "
          f"{len(inhalt)} erfunden")
    ok += gut
    print(f"\n{ok}/{gesamt} Exit-2-Zeilen-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
