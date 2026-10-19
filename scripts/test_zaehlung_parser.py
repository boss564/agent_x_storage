#!/usr/bin/env python3
"""Eichnormal fuer das Messgeraet (R105, P2).

R104: der Parser las 1/1 statt 6/6. Die Zahl konnte lautlos luegen.
Eine Korrektur ist eine Bandage; dieses Fixture-Set ist das Eichnormal.
Jede bekannte Eingabe hat ein bekanntes Soll. Aendert jemand die Lesart,
wird hier rot — nicht im Bericht.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import zaehlung as Z

ok = gesamt = 0


def pruefe(name: str, bedingung: bool, detail: str = "") -> None:
    global ok, gesamt
    gesamt += 1
    ok += bool(bedingung)
    if not bedingung:
        print(f"ROT  {name}  {detail}")


def main() -> int:
    for name, eingabe, soll_a, soll_b in Z.FIXTURES:
        got = Z.summenzeile(eingabe)
        ist = got if got else (0, 0)
        pruefe(f"fixture: {name}", ist == (soll_a, soll_b), f"{ist} != ({soll_a},{soll_b})")

    # Mutation: die alte Lesart (erstes N/M) muss am Eichnormal scheitern
    import re
    alt = "ok (1/2) Teil\nok (2/2) Teil\n\n6/6 gruen\n"
    # alte Lesart: ERSTES N/M im ganzen Text (ohne Wortgrenze) -> (1,2)
    alle = re.findall(r"(\d+)/(\d+)", alt)
    alte_lesart = (int(alle[0][0]), int(alle[0][1]))
    pruefe("mutation: alte Lesart (erstes N/M) liest (1,2) statt (6,6)",
           alte_lesart == (1, 2), str(alte_lesart))
    pruefe("mutation: neue Lesart liest (6,6)", Z.summenzeile(alt) == (6, 6),
           str(Z.summenzeile(alt)))
    # zweite Mutation: N/M NICHT am Zeilenanfang (R105)
    pruefe("mutation: 'Assurance 43/43 | ...' wird gelesen",
           Z.summenzeile("Assurance 43/43 | Charakterisierung 6/6") == (6, 6),
           str(Z.summenzeile("Assurance 43/43 | Charakterisierung 6/6")))

    # Live: der echte Lauf muss eine Summenzeile liefern
    import subprocess
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "zaehlung.py")],
                       cwd=REPO, capture_output=True, text=True)
    pruefe("live: zaehlung.py liefert eine Summenzeile", Z.summenzeile(r.stdout) is not None)
    pruefe("live: RC 0", r.returncode == 0, str(r.returncode))

    print(f"\n{ok}/{gesamt} Eichnormal-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
