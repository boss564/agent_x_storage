#!/usr/bin/env python3
"""Frist-Gate: Verfall loest eine Buchung aus — oder die Frist ist keine.

§A-ZZZZ175 (Runde 88): **das Frist-Instrument hat einen
Konstruktionsfehler.** Dreimal belegt: ADJ (R84 gesetzt, R84 verfallen,
erst R85/R86 auf externen Befund gebucht), NRM (R85 gesetzt, Frist R86,
R86 und R87 schweigen), Mutationsvarianz (R87 benannt, nicht gebucht).

Eine Frist ohne Verfallskonsequenz ist ein Reminder, kein Gate.
Dieser Test erzwingt:

  1. Jede Frist hat genau einen Endzustand aus
     {bewiesen, entschieden, akzeptiert_mit_neuem_termin}.
  2. Kein Endzustand darf fehlen, wenn die Runde > frist ist.
  3. "Schweigen" ist kein moeglicher Endzustand.
  4. Ein verschobener Termin traegt eine Begruendung.

Die Rundenzahl kommt aus dem Versions-Ledger, nicht aus einer Konstanten.
"""
from __future__ import annotations

import json
from pathlib import Path

V = Path(__file__).resolve().parent / "waechter_vertrag.json"
ENDE = {"bewiesen", "entschieden", "akzeptiert_mit_neuem_termin"}


def main() -> int:
    d = json.loads(V.read_text(encoding="utf-8"))
    runde = max(e["runde"] for e in d["versions_ledger"]
                if isinstance(e.get("runde"), int))
    fristen = d.get("fristen", {})
    ok = gesamt = 0

    for name, f in fristen.items():
        if not isinstance(f, dict) or "frist" not in f:
            continue
        ziel = int(str(f["frist"]).lstrip("R"))
        ende = f.get("endzustand")
        if runde <= ziel:
            continue          # Frist laeuft noch, kein Endzustand noetig
        gesamt += 1
        gut = ende in ENDE
        print(f"{'ok  ' if gut else 'FAIL'} {name}: Frist R{ziel} < R{runde}, "
              f"endzustand={ende!r}")
        ok += gut

        if ende == "akzeptiert_mit_neuem_termin":
            gesamt += 1
            gut = bool(f.get("neuer_termin")) and bool(f.get("begruendung"))
            print(f"{'ok  ' if gut else 'FAIL'} {name}: Verschiebung "
                  f"begruendet      {bool(f.get('begruendung'))}")
            ok += gut

    # Das Instrument selbst ist Normtext, nicht nur Konvention.
    gesamt += 1
    inst = d.get("frist_instrument", {})
    gut = "Schweigen" in inst.get("regel", "")
    print(f"{'ok  ' if gut else 'FAIL'} Instrument benennt 'Schweigen'  "
          f"als verboten")
    ok += gut

    # Und es ist verlinkt — ein Test, der nirgends steht, ist keine Norm.
    gesamt += 1
    gut = inst.get("test") is not None and Path(
        Path(__file__).parent / Path(inst["test"]).name).exists()
    print(f"{'ok  ' if gut else 'FAIL'} Instrument verlinkt seinen Test")
    ok += gut

    print(f"\n{ok}/{gesamt} Frist-Gate-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
