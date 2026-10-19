#!/usr/bin/env python3
"""Publikations-Pipeline: ein Bericht ist erst publiziert, wenn er das
Prosa-Gate besteht (R105, P1 — Gate nicht mehr opt-in).

    python3 scripts/publiziere.py <bericht.md>

Prueft in dieser Reihenfolge, bricht beim ersten Defekt ab:
  1 Belege:   check --strict (Region + Wortlaut)
  2 Prosa:    jede datei:zeile / L<n> muss ein Beleg sein
  3 Publikation: kopiert die PUBLIC-Datei byte-exakt nach publiziert/

Exit 1 = nicht publiziert. Es gibt keinen Warn-Modus: ein Bericht, der
sein eigenes Gate nicht besteht, wird nicht veroeffentlicht.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    bericht = Path(argv[0]).resolve()
    if not bericht.exists():
        print(f"kein Bericht: {bericht}")
        return 1
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "beweis.py"),
                        "check", "--strict", "--prosa", str(bericht)],
                       cwd=REPO, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print("NICHT PUBLIZIERT — der Bericht besteht sein eigenes Gate nicht.")
        return 1
    ziel = REPO / "publiziert" / bericht.name
    ziel.parent.mkdir(exist_ok=True)
    shutil.copyfile(bericht, ziel)
    print(f"publiziert: {ziel.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
