#!/usr/bin/env python3
"""Escaping: freie Textfelder duerfen die Achse nicht zerlegen.

§A-ZZZZ157 (Runde 86): ein Semikolon in einer Fehlermeldung ist kein
Angriff, sondern ein Sonderzeichen — und zerlegt `key=value;` genau so
gut wie ein Schluessel ohne `=`. Der Test betritt den Fall, den niemand
freiwillig baut: Eingabedaten mit `;`, `=`, `%` und Zeilenumbruch.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parent / "einwurf_waechter.py"


def _lauf(zeilen: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "strom.jsonl"
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=td)
        return r.returncode, r.stdout


def main() -> int:
    ok = gesamt = 0
    boese = "kaputt;grund=x=y%zz\nneu"
    code, out = _lauf([boese])
    marken = re.findall(r"ZEILE (pos:\d+) (UNGEPRUEFT);pos=(\d+);", out)
    gesamt += 1
    gut = bool(marken) and code == 4
    print(f"{'ok  ' if gut else 'FAIL'} boese Zeile bleibt parsebar  "
          f"{len(marken)} Marken, exit={code}")
    ok += gut

    gesamt += 1
    # Nur die MASSACHSE zaehlt, nicht stderr: die Warnung darf den
    # Inhalt nennen (sie ist Prosa fuer Menschen), die Achse nicht.
    achse = [z for z in out.splitlines()
             if z.startswith(("Meldungen=", "Paare="))]
    gut = bool(achse) and all("kaputt" not in z for z in achse)
    print(f"{'ok  ' if gut else 'FAIL'} Achse ohne Eingabe-Echo      "
          f"{'sauber' if gut else 'LEAK'}")
    ok += gut

    gesamt += 1
    r = subprocess.run([sys.executable, str(W)], capture_output=True, text=True)
    feld = re.findall(r"grund=([^;]*);", r.stdout)
    gut = bool(feld) and all(";" not in f and "\n" not in f for f in feld)
    print(f"{'ok  ' if gut else 'FAIL'} grund ein Feld              {feld}")
    ok += gut

    print(f"\n{ok}/{gesamt} Escaping-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
