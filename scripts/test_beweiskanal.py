#!/usr/bin/env python3
"""#14 (P0): Der Beweiskanal muss selbst beweisbar sein.

Wenn der Kanal, der Zitate pruefbar macht, ungeprueft ist, ist er
die naechste Attrappe. Vier Faelle:

  1  beweis cite erzeugt einen Block, der check besteht
  2  check meldet SHA-Drift, wenn das Artefakt sich aendert
  3  ein gekuerztes Zitat kann nicht bestehen (Wortlaut-Pruefung)
  4  der Ledger ist nicht leer und traegt die drei R102-Streitpunkte

Fall 3 ist der Kern: R99/R100/R101 zitierten gekuerzt und niemand
merkte es. Hier kann ein gekuerzter Block nicht gruen werden.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import beweis as B

ok = gesamt = 0


def pruefe(name: str, bedingung: bool, detail: str = "") -> None:
    global ok, gesamt
    gesamt += 1
    if bedingung:
        ok += 1
        print(f"ok   {name}")
    else:
        print(f"ROT  {name}  {detail}")


def main() -> int:
    block = B.zitiere("Makefile", 56, 63)
    pruefe("1a cite erzeugt Block", block.startswith("<<<BEWEIS") and block.endswith("BEWEIS>>>"))
    m = B.MUSTER.search(block)
    pruefe("1b Block ist maschinell lesbar", bool(m))
    if m:
        defekt = B.pruefe_block(m["a"], int(m["v"]), int(m["b"]), m["h"], m["t"])
        pruefe("1c frischer Block besteht check", defekt == "", defekt)

        # 2 SHA-Drift: gleicher Block, aber falscher Text -> Wortlaut-Pruefung
        kaputt = m["t"].replace("Vertragsscope", "VERTRAGSCOPE")
        d2 = B.pruefe_block(m["a"], int(m["v"]), int(m["b"]), m["h"], kaputt)
        pruefe("2a geaenderter Wortlaut -> Defekt", bool(d2), d2)

        # 3 gekuerztes Zitat
        kurz = "\n".join(m["t"].splitlines()[:3])
        d3 = B.pruefe_block(m["a"], int(m["v"]), int(m["b"]), m["h"], kurz)
        pruefe("3a gekuerztes Zitat -> Defekt", bool(d3), d3)

    # 4 Ledger
    zeilen = [z for z in B.LEDGER.read_text(encoding="utf-8").splitlines() if z.strip()]
    pruefe("4a Ledger nicht leer", len(zeilen) >= 3, str(len(zeilen)))
    artefakte = {json.loads(z)["artefakt"] for z in zeilen}
    pruefe("4b die drei Streitpunkte sind belegt",
           {"Makefile", "scripts/entscheidung_R101.json"} <= artefakte,
           str(artefakte))

    r = subprocess.run([sys.executable, str(REPO / "scripts" / "beweis.py"), "check", "--strict"],
                       cwd=REPO, capture_output=True, text=True)
    pruefe("5a check --strict gruen (keine Drift)", r.returncode == 0, r.stdout[-200:])

    print(f"\n{ok}/{gesamt} Beweiskanal-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
