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

    # §A-ZZZZ212 (Runde 92): die Achse ist DISTINKTE NORMALFORMEN, nicht
    # Zeilen. i.i.d. Zeilen sind bei geclusterten Stroemen eine falsche
    # Annahme — 1000 Zeilen derselben Sekunde sind EINE Gelegenheit.
    from einwurf_waechter import digest
    hashes: dict[str, tuple[str, str]] = {}   # normform -> (roh, quelle)
    kollisionen = []
    zeilen = 0
    for nr, zeile in enumerate(STROM.read_text(encoding="utf-8").splitlines(), 1):
        if not zeile.strip():
            continue
        zeilen += 1
        h = digest(zeile)                     # die Normalform
        if h in hashes and hashes[h][0] != zeile:
            kollisionen.append((nr, hashes[h][0][:40], zeile[:40]))
        else:
            hashes.setdefault(h, (zeile, "_"))
    if kollisionen:
        print(f"WIDERLEGT: {len(kollisionen)} Kollisionen")
        for nr, a, b in kollisionen[:5]:
            print(f"  Zeile {nr}: {a!r} != {b!r}")
        return 1
    # §A-ZZZZ206/212: die Schwelle folgt aus dem FORMAT-Raum (N_eff), weil
    # Verletzungen an Formatgrenzen liegen — nicht aus der Sekundenzahl.
    import json as _json
    _v = _json.loads((SCRIPTS / "waechter_vertrag.json").read_text(
        encoding="utf-8"))["schwellen_herleitung"]
    import math as _math
    _N = _v["N_herleitung"].get("N_eff")
    _a = _v["alpha"]
    if not _N:
        # §A-ZZZZ213 (Runde 92): N ist NICHT hergeleitet. Dann ist die
        # Probe nicht entscheidbar — und "gruen mit 3 Zeilen" waere die
        # Gelegenheits-Falle tiefer (N_eff=36 ergab n=1).
        print("UNBEWIESEN: N (Normalform-Raum) ist nicht hergeleitet "
              f"({len(hashes)} distinkte Normalformen gelesen). "
              "Die Schwelle hat die richtige Form, aber keinen gueltigen "
              "Eingang — ein zu kleiner Raum macht jede Probe gruen.")
        return 2
    MINDESTENS = _math.ceil(_math.sqrt(
        2.0 * _N * _math.log(1.0 / (1.0 - _a))))
    if len(hashes) < MINDESTENS:
        print(f"UNBEWIESEN: {len(hashes)} distinkte Normalformen < "
              f"{MINDESTENS} (n aus N_eff={_N}, alpha={_a}; {zeilen} Zeilen "
              "gelesen) — gruen aus Mangel an Gelegenheit, nicht aus Beweis")
        return 2
    print(f"BESTANDEN: {len(hashes)} Zeilen, 0 Kollisionen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
