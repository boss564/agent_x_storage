#!/usr/bin/env python3
"""Die Ask-Liste — Pflicht-Output der R97-Ausnahme (§4).

R97 §4: "Die Wand macht den Turm sichtbar; die Prokrastination misst,
um nicht zu fragen." Ohne diese Liste war die Ausnahme Verschwendung.

Jeder EXT-Posten hat in `externes_buch` den Beweisversuch "KEINER —
niemand wurde gefragt". Das ist der Befund. Diese Liste macht aus
der Messung die Anfrage: wen fragen, was fragen, wann.

Kein Posten wird als erledigt gefuehrt, solange `eigentuemer` leer ist.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"

# Wer kann die Frage beantworten? Abgeleitet aus `zugang` + `akzeptanz`.
EMPF = {
    "EXT-1": ("Integrator/Team ausserhalb dieses Repos (ING-Schnittstelle)",
              "Kann jemand VERGLEICH aus der Tafel nachbauen und Exit 4 "
              "korrekt lesen, ohne die Python-Tests zu kennen?"),
    "EXT-2": ("betreibende Stelle des Produktions-Downstreams",
              "Liest Ihr System den Original-Zeitstempel? Bitte Mitzeichnung "
              "von zustell_zusage."),
    "EXT-3": ("Dateneigner eines eingefrorenen NRM-Stroms (>=1418 Zeilen)",
              "Koennt Ihr einen eingefrorenen Strom liefern, der den "
              "Harness-Zaun einhaelt?"),
    "EXT-4": ("zweite Hand (nicht der Autor des '?'-Bugs)",
              "Bestaetigen Sie die drei Ausgaenge aus der Semantik der "
              "Wahrheitstafel?"),
}


def main() -> int:
    d = json.loads(V.read_text(encoding="utf-8"))
    posten = d.get("externes_buch", {}).get("posten", [])
    offen = [p for p in posten if not p.get("eigentuemer")]
    print(f"ASK-LISTE — {len(offen)} von {len(posten)} Posten ohne Eigentuemer\n")
    for p in offen:
        pid = p["id"]
        empf, frage = EMPF.get(pid, ("?", "?"))
        print(f"{pid}  {p['posten']}")
        print(f"  fragen:  {empf}")
        print(f"  was:     {frage}")
        print(f"  wann:    bis {p.get('wiedervorlage', '?')} "
              f"(Verfall: {p.get('frist_verfall', '?')[:60]}...)")
        print(f"  beweis:  {str(p.get('beweisversuch', '?'))[:80]}")
        print()
    if not offen:
        print("alle Posten haben einen Eigentuemer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
