#!/usr/bin/env python3
"""NRM-Blocker: ist die Normalisierung injektiv?

§A-ZZZZ195 (Runde 90 Befund 6): Der Frist-Termin NRM (R85 -> R90) hatte
einen Freitext-Blocker ("Die Injektivitaetsprobe braucht den ECHTEN
Strom"). Dieses Skript IST die Probe — und es ist ROT, solange sie
nicht existiert. Damit ist der Blocker typisiert: das Gate fuehrt diese
Datei aus und sieht Exit != 0.

WAS GEPRUEFT WIRD:
  digest(x) == digest(y)  =>  inhalt(x) == inhalt(y)
Anders formuliert: die Normalisierung darf zwei INHALTLICH
VERSCHIEDENE Nachrichten nicht auf denselben Hash abbilden. Sonst
wuerde eine davon als Kanal-Duplikat verworfen — stiller Datenverlust.

STATUS: ROT ist hier der korrekte Zustand. Die Probe braucht einen
echten Strom (Charter: keine Live-Transkripte). Solange kein
eingefrorener, ausreichend grosser Strom vorliegt, ist die Aussage
UNBEWIESEN — nicht `False`, nicht `True`.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

STROM = SCRIPTS / "fixtures" / "nrm_injektivitaet.jsonl"


def main() -> int:
    # Die Probe selbst ist der Blocker: ohne eingefrorenen Strom ist
    # Injektivitaet nicht entscheidbar. Exit 2 = UNBEWIESEN (nicht
    # "bestanden", nicht "widerlegt").
    if not STROM.is_file():
        print("UNBEWIESEN: eingefrorener NRM-Strom fehlt "
              f"({STROM.relative_to(SCRIPTS)})")
        print("Blocker fuer Frist NRM bleibt offen — Probe nicht ausfuehrbar.")
        return 2

    from einwurf_waechter import digest
    hashes: dict[str, str] = {}
    kollisionen = []
    for nr, zeile in enumerate(STROM.read_text(encoding="utf-8").splitlines(), 1):
        if not zeile.strip():
            continue
        h = digest(zeile)
        if h in hashes and hashes[h] != zeile:
            kollisionen.append((nr, hashes[h][:40], zeile[:40]))
        hashes[h] = zeile
    if kollisionen:
        print(f"WIDERLEGT: {len(kollisionen)} Kollisionen")
        for nr, a, b in kollisionen[:5]:
            print(f"  Zeile {nr}: {a!r} != {b!r}")
        return 1
    # §A-ZZZZ196: eine 3-Zeilen-Probe ist keine Injektivitaetsprobe.
    # Zufaellige Kollisionen sind bei 3 Zeilen unwahrscheinlich; der
    # Test waere gruen aus Mangel an Gelegenheit. Mindestgroesse noetig.
    MINDESTENS = 1000
    if len(hashes) < MINDESTENS:
        print(f"UNBEWIESEN: {len(hashes)} Zeilen < {MINDESTENS} — "
              "gruen aus Mangel an Gelegenheit, nicht aus Beweis")
        return 2
    print(f"BESTANDEN: {len(hashes)} Zeilen, 0 Kollisionen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
