#!/usr/bin/env python3
"""Wiedervorlage ist eine Frist, kein Wunschtermin.

§A-ZZZZ216 (Runde 93 Befund 4): **das EXT-Buch liegt ausserhalb der
Frist-Gate-Jurisdiktion — und genau dort greift die Krankheit.**

Das Frist-Gate aus R88/89 hatte gelernt: "ein Gate, das jedes Datum
akzeptiert, ist ein Formular" und "Datum ist Wunschtermin mit
Herleitung". Die Wiedervorlage 2026-11-02 im EXT-Buch trug nichts
davon: keinen Blocker, keinen Beweisversuch, keine Verfallskonsequenz.

Ohne das verfaellt der Termin folgenlos, und das Gate bucht am 02.11.
ein NEUES Datum. Der Wunschtermin aus OFFEN #3, jetzt in der
Governance-Schicht.

Die Antwort ist keine neue Klausel, sondern eine Zustaendigkeits-
erweiterung: dieses Gate wendet die Frist-Regel auf das EXT-Buch an.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    posten = d.get("externes_buch", {}).get("posten", [])
    regeln = d.get("externes_buch", {}).get("gate", {}).get(
        "wiedervorlage_regeln", [])

    # 1. Die Regel existiert im Gate, nicht nur im Bericht.
    gesamt += 1
    gut = len(regeln) >= 3 and any("kein neues" in r.lower()
                                   for r in regeln)
    print(f"{'ok  ' if gut else 'FAIL'} Verfall bucht nicht neu    "
          f"{len(regeln)} Regeln")
    ok += gut

    # 2. Jede Wiedervorlage traegt die drei Frist-Bestandteile.
    gesamt += 1
    unvollstaendig = [p["id"] for p in posten
                      if p.get("wiedervorlage") and not (
                          p.get("frist_blocker")
                          and p.get("beweisversuch") is not None
                          and p.get("frist_verfall"))]
    gut = not unvollstaendig
    print(f"{'ok  ' if gut else 'FAIL'} Blocker+Beweis+Verfall     "
          f"unvollstaendig={unvollstaendig or 'keine'}")
    ok += gut

    # 3. Ein Beweisversuch, der KEINER ist, ist erlaubt — aber er ist
    #    dann der Befund, kein Freibrief. Genau das steht im Feld.
    gesamt += 1
    keiner = [p["id"] for p in posten
              if "KEINER" in str(p.get("beweisversuch", ""))]
    gut = len(keiner) == len(posten)
    print(f"{'ok  ' if gut else 'FAIL'} Beweisversuch ehrlich     "
          f"KEINER bei {len(keiner)}/{len(posten)} — Befund, kein Grund")
    ok += gut

    # 4. Der Verfallstext verweist auf ROT, nicht auf "neues Datum".
    gesamt += 1
    falsch = [p["id"] for p in posten
              if "ROT" not in str(p.get("frist_verfall", ""))]
    gut = not falsch
    print(f"{'ok  ' if gut else 'FAIL'} Verfall -> ROT             "
          f"{falsch or 'alle korrekt'}")
    ok += gut

    # 5. Der Termin liegt in der Zukunft (sonst ist er schon verfallen
    #    und das Gate muesste heute rot sein).
    gesamt += 1
    heute = date.today().isoformat()
    alt = [(p["id"], p["wiedervorlage"]) for p in posten
           if p.get("wiedervorlage") and p["wiedervorlage"] < heute]
    gut = not alt
    print(f"{'ok  ' if gut else 'FAIL'} Termine nicht verfallen    "
          f"{alt or 'ok'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Wiedervorlage-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
