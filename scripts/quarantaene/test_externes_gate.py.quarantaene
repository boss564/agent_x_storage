#!/usr/bin/env python3
"""Das externe Gate: "keiner" ist kein zulaessiger Eigentuemer-Wert.

§A-ZZZZ210 (Runde 92 Hauptbefund): **die fuenfte Auspraegung steht im Buch,
das die Krankheit schliessen sollte.**

  "?"-Sentinel        Feld existiert, Bedeutung fehlt
  BLOCKER benannt     Zeichenkette existiert, Substanz fehlt
  gruen bei 3/3       Bestanden existiert, Gelegenheit fehlt
  zustell_zusage      Zusage existiert, Bedarf fehlt
  EXT-Buch            Eigentuemer-SPALTE existiert, Eigentuemer fehlt

Der Mechanismus ist derselbe. Die Jurisdiktion ist neu: die Klausel
regiert normative Felder IM VERTRAG. Das EXT-Buch ist kein Vertragsfeld —
es ist Governance. Die Krankheit ist ueber die Grenze gewandert.

Dieses Gate holt sie zurueck. Zulaessig ist NUR:
  (a) Name/Rolle + Datum + Akzeptanzkriterium
  (b) Klassifikation ENTSCHEIDUNG + Begruendung, warum niemand da ist
      + Wiedervorlage-Termin

"keiner", None, "", "TBD", "spaeter" sind KEINE Werte. Sie sehen wie
eine Antwort aus und sind die Abwesenheit einer Antwort.

WAS DIESES GATE NICHT KANN (und nie koennen wird): einen Namen erzeugen.
Es kann nur rot melden. Das ist die Bringschuld, die kein Test schliesst —
und der Grund, warum es ein GATE ist und keine Suite.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"

# Werte, die wie eine Antwort aussehen und keine sind.
PLATZHALTER = {"", "keiner", "keine", "none", "null", "tbd", "offen",
               "spaeter", "?", "n/a", "niemand", "-"}


def gueltig(p: dict) -> tuple[bool, str]:
    """Drei Regeln, alle drei muessen greifen."""
    e = p.get("eigentuemer")
    if isinstance(e, str) and e.strip().lower() in PLATZHALTER:
        return False, f"Platzhalter als Eigentuemer: {e!r}"
    if e is None:
        # Variante (b): ENTSCHEIDUNG mit Begruendung + Wiedervorlage.
        if p.get("klassifikation") != "ENTSCHEIDUNG":
            return False, "kein Eigentuemer und keine ENTSCHEIDUNG"
        if not p.get("begruendung_ohne_eigentuemer"):
            return False, "ENTSCHEIDUNG ohne Begruendung"
        if not p.get("wiedervorlage"):
            return False, "ENTSCHEIDUNG ohne Wiedervorlage"
        return True, "ENTSCHEIDUNG mit Begruendung"
    # Variante (a): Name + Datum + Akzeptanz.
    if isinstance(e, dict):
        if not e.get("name") or not e.get("datum") or not p.get("akzeptanz"):
            return False, "Eigentuemer ohne name/datum/akzeptanz"
        return True, f"benannt: {e['name']}"
    return False, f"unbekannte Form: {type(e).__name__}"


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    buch = d.get("externes_buch", {})
    posten = buch.get("posten", [])
    gate = buch.get("gate", {})

    # 1. Die Regel steht im Vertrag — Platzhalter verboten, zwei Varianten.
    gesamt += 1
    gut = (gate.get("platzhalter_verboten")
           and len(gate.get("zulaessig", [])) == 2)
    print(f"{'ok  ' if gut else 'FAIL'} Gate-Regel deklariert       "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 2. "keiner" ist ausdruecklich UNZULAESSIG — der Befund als Regel.
    gesamt += 1
    gut = "keiner" in [x.lower() for x in gate.get("platzhalter", [])]
    print(f"{'ok  ' if gut else 'FAIL'} 'keiner' verboten           "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 3. Jeder Posten hat einen zulaessigen Eigentuemer ODER Variante (b).
    gesamt += 1
    rot = [(p["id"], gueltig(p)[1]) for p in posten if not gueltig(p)[0]]
    gut = not rot
    print(f"{'ok  ' if gut else 'FAIL'} Eigentuemer zulaessig      "
          f"rot={rot}")
    ok += gut

    # 4. Die Stopp-Bedingung ist deklariert und greift, solange rot.
    gesamt += 1
    st = gate.get("stopp_bedingung", {})
    gut = bool(st.get("regel")) and st.get("greift_bei") == "gate_rot"
    print(f"{'ok  ' if gut else 'FAIL'} Stopp-Bedingung deklariert "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 5. Das Gate kann keinen Namen erzeugen — deklariert, nicht bedauert.
    gesamt += 1
    gut = "nicht erzeugen" in gate.get("grenze", "")
    print(f"{'ok  ' if gut else 'FAIL'} Grenze deklariert          "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 6. Beobachtbar: ein Posten mit "keiner" faellt durch — der Kritiker
    #    sieht denselben Fehlermodus, den er beschrieb.
    gesamt += 1
    fake = {"id": "X", "eigentuemer": "keiner", "akzeptanz": "irgendwas"}
    gut = gueltig(fake)[0] is False
    print(f"{'ok  ' if gut else 'FAIL'} Fehlermodus reproduziert   "
          f"{gueltig(fake)[1]}")
    ok += gut

    # 7. Ein Wiedervorlage-Datum ist nicht in der Vergangenheit.
    gesamt += 1
    alt = [(p["id"], p["wiedervorlage"]) for p in posten
           if p.get("wiedervorlage")
           and p["wiedervorlage"] < date.today().isoformat()]
    gut = not alt
    print(f"{'ok  ' if gut else 'FAIL'} Wiedervorlagen nicht alt   "
          f"{alt or 'ok'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Externes-Gate-Faelle gruen")
    if not posten or any(not gueltig(p)[0] for p in posten):
        print("\nGATE ROT — die Stopp-Bedingung greift: keine neue interne")
        print("Maschinerie, bis jeder Posten einen Namen oder eine")
        print("begruendete ENTSCHEIDUNG mit Wiedervorlage traegt.")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
