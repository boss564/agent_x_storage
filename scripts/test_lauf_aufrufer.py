#!/usr/bin/env python3
"""#12 eine Ebene tiefer: die Kette lauf.py -> make -> Shell.

BEFUND aus R101: GNU make normalisiert JEDES Rezept-Exit auf 2.
Ein `make lauf`, das 1 (GEFALLEN) und 2 (BEFUND) unterscheiden soll,
kann das nicht — beide kommen als 2 heraus. Die 0/1/2-Semantik
ueberlebt die make-Grenze nicht.

Diese Suite haelt BEIDES fest:
  A  lauf.py direkt traegt 0/1/2 (Instrument, ehrlich)
  B  make kollabiert 1 und 2 auf 2 (Grenze, dokumentiert)
  C  der Aufrufer darf sein Signal deshalb NICHT aus make beziehen

Waere B eines Tages nicht mehr wahr (z.B. wrapper), wird der Test rot
und zwingt zur Neubewertung. Ein dokumentierter Defekt ist kein
ungedeckter Defekt.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ok = gesamt = 0


def pruefe(name: str, bedingung: bool, detail: str = "") -> None:
    global ok, gesamt
    gesamt += 1
    if bedingung:
        ok += 1
        print(f"ok   {name}")
    else:
        print(f"ROT  {name}  {detail}")


def _make_mit(rc: int, tmp: str) -> int:
    Path(tmp, "p.py").write_text(f"import sys; sys.exit({rc})\n")
    return subprocess.run(["make", "-s"], cwd=tmp, capture_output=True).returncode


def main() -> int:
    # A: das Instrument traegt drei Zustaende
    src = (REPO / "scripts" / "lauf.py").read_text(encoding="utf-8")
    pruefe("A1 lauf.py: GEFALLEN/BEENDET -> 1",
           'return 1' in src and "GEFALLEN" in src)
    pruefe("A2 lauf.py: BEFUND -> 2 (vor dem Gruen-Zweig)",
           src.find('return 2') < src.find('return 0'))

    # B: die make-Grenze kollabiert 1 und 2
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "Makefile").write_text("t:\n\t@python3 p.py\n")
        codes = {rc: _make_mit(rc, tmp) for rc in (0, 1, 2, 9)}
        pruefe("B1 make: Rezept-Erfolg -> 0", codes[0] == 0, str(codes))
        pruefe("B2 make: 1 und 2 kollabieren auf 2 (BEFUND, nicht behoben)",
               codes[1] == codes[2] == 2, str(codes))
        pruefe("B3 make: kein Fehler kommt als 0 heraus (#12-Sorge widerlegt)",
               all(codes[k] != 0 for k in (1, 2, 9)), str(codes))

    # C: die Semantik muss ausserhalb von make verdrahtet werden
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    s = mk.find("\nlauf:")
    e = mk.find("\n.PHONY: lauf", s)
    rez = mk[s:e] if s > 0 and e > s else ""
    pruefe("C1 make lauf ruft scripts/lauf.py (Ort der Wahrheit bleibt)",
           "scripts/lauf.py" in rez)
    pruefe("C2 make lauf deklariert die make-Grenze (meldet 2, nicht 1)",
           "make meldet 2" in rez and "ueberlebt diese Grenze NICHT" in rez
           or "make meldet 2" in rez)

    print(f"\n{ok}/{gesamt} Aufrufer-Ketten-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
