#!/usr/bin/env python3
"""Projektion ist keine Tautologie — als Test, nicht als Behauptung.

§A-ZZZZ158 (Runde 86): nach Entfernen der Parallelrechnung kann
`assert exit == exit_aus_zeilen(...)` nur Determinismus beweisen. Der
Wahrheitstest ist: pruefen, DASS `test_projektion.py` hartkodierte
Erwartungen traegt und die Ableitung nicht importiert. Zwei Zeilen im
Repo, nicht im Bericht.
"""
from __future__ import annotations

import re
from pathlib import Path

T = Path(__file__).resolve().parent / "test_projektion.py"


def main() -> int:
    src = T.read_text(encoding="utf-8")
    ok = gesamt = 0

    gesamt += 1
    importiert = bool(re.search(r"^\s*(from|import)\s+einwurf_waechter", src, re.M))
    gut = not importiert
    print(f"{'ok  ' if gut else 'FAIL'} Ableitung nicht importiert  importiert={importiert}")
    ok += gut

    gesamt += 1
    soll = re.findall(r'^\s*\("([^"]+)",\s*\[.*?\],\s*(\d+)\),', src, re.M)
    gut = len(soll) >= 5
    print(f"{'ok  ' if gut else 'FAIL'} Soll-Werte hartkodiert      "
          f"{len(soll)} Fixtures: {[s[1] for s in soll]}")
    ok += gut

    gesamt += 1
    gut = "exit_aus_zeilen" not in src
    print(f"{'ok  ' if gut else 'FAIL'} keine Selbstableitung       "
          f"{'rein' if gut else 'liest eigenen Ausgang'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Projektions-Echtheits-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
