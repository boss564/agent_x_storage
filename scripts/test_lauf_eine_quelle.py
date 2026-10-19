#!/usr/bin/env python3
"""Prueft, dass die Messung aus der EINEN Quelle gespeist wird — R96.

Die neunte Auspraegung war: der richtige Zaehler existierte, die
Verwendung fehlte. Diese Suite ist der Abnehmer, der den Unterschied
zwischen einem Befund und einer Wirkung sieht.

Fuenf Faelle:
  1  lauf.py importiert `zaehle` (keine eigene Dateiliste)
  2  lauf.py enthaelt KEINEN Glob auf test_*/blocker_* im Laufpfad
  3  die vier Einheiten sind definiert (GRUEN/GEFALLEN/BEFUND/BEENDET)
  4  Exit 2 wird als BEFUND, nicht als GEFALLEN klassifiziert
  5  lauf.py fasst .git nicht an
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
LAUF = SCRIPTS / "lauf.py"
# Die Registrierung ist mechanisch: zaehle() erkennt Vertragsbezug am
# Quelltext (waechter_vertrag.json). Eine Suite, die den Vertrag prueft,
# aber nicht liest, landet in "aussen" und wird nie als Vertragssuite
# gezaehlt -- genau der R93-Verstoss. Der Import ist die Verdrahtung.
V = SCRIPTS / "waechter_vertrag.json"


def main() -> int:
    ok = gesamt = 0
    src = LAUF.read_text(encoding="utf-8") if LAUF.exists() else ""

    def pruefe(name: str, bedingung: bool) -> None:
        nonlocal ok, gesamt
        gesamt += 1
        print(f"{'ok  ' if bedingung else 'FAIL'} {name}")
        ok += int(bool(bedingung))

    pruefe("lauf.py existiert", bool(src))
    vertrag = json.loads(V.read_text(encoding="utf-8"))
    pruefe("Vertrag nennt lauf_eine_quelle",
           "lauf_eine_quelle" in vertrag)
    pruefe("speist aus test_zaehlweise.zaehle()",
           bool(re.search(r"from test_zaehlweise import zaehle", src)))
    # Der Laufpfad darf keine eigene Dateiliste per Glob bauen.
    globs = re.findall(r"glob\(\s*[\"'](?:test_|blocker_)", src)
    pruefe(f"kein test_*/blocker_*-Glob im Laufpfad ({len(globs)})", not globs)
    pruefe("vier Einheiten definiert",
           all(k in src for k in ("GRUEN", "GEFALLEN", "BEFUND", "BEENDET")))
    # Exit 2 -> BEFUND, in der Funktion, nicht in einem Kommentar.
    bedingung_2 = re.search(r"if\s+rc\s*==\s*2\s*:\s*\n\s*return\s*[\"']BEFUND", src)
    pruefe("Exit 2 -> BEFUND (nicht GEFALLEN)", bool(bedingung_2))
    # Nur ausfuehrbarer Code zaehlt — ein Docstring, der ".git" nennt,
    # ist eine Behauptung, kein Zugriff (R93: Registrierung vs. Verdrahtung).
    import ast
    baum = ast.parse(src)
    for n in ast.walk(baum):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            if (n.body and isinstance(n.body[0], ast.Expr)
                    and isinstance(n.body[0].value, ast.Constant)
                    and isinstance(n.body[0].value.value, str)):
                n.body = n.body[1:] or [ast.Pass()]
    code = ast.unparse(baum)
    pruefe("kein .git-Zugriff im ausfuehrbaren Code", ".git" not in code)

    print(f"\n{ok}/{gesamt} Mess-Instrument-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
