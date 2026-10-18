#!/usr/bin/env python3
"""Substanzklassen: jedes normative Feld deklariert seine Quelle.

§A-ZZZZ203 (Runde 91): **die Krankheit ist ein Default, kein Bug.**

    "?"-Sentinel       Feld existiert, Bedeutung fehlt
    BLOCKER benannt    Zeichenkette existiert, Substanz fehlt
    gruen bei 3/3      Bestanden existiert, Gelegenheit fehlt
    zustell_zusage     Zusage existiert, BEDARF fehlt

Jeder Einzelfall-Fix heilt EINE Auspraegung und muenzt zwei neue. Der
generische Fix: ein Feld ohne Substanzklasse ist nicht gebucht. Diese
Pruefung ist bewusst STRUKTURELL, nicht inhaltlich — sie kann nicht
wissen, ob ein Satz wahr ist, aber sie kann wissen, ob er sagt, WORAUS
er stammt.

Drei Klassen, drei Belegpflichten:
  MESSUNG      -> Skriptpfad, das ausgefuehrt werden kann
  ABLEITUNG    -> Formel + Eingangsgroessen im Vertrag
  ENTSCHEIDUNG -> Bedarfsartefakt oder Mitzeichnungspflicht

Was hier NICHT geprueft wird (ehrlich): ob die Messung richtig misst.
Das ist die Grenze der Selbstverifikation, nicht ein Fehler dieses Tests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"

# Abschnitte, die als normativ gelten und eine Klasse tragen MUESSEN.
# Bewusst als Liste: ein neuer Abschnitt muss hier eingetragen werden,
# und das ist sichtbar im Diff — nicht still per Praefix-Muster.
NORMATIV = [
    "exit_taxonomie", "zustell_zusage", "vergleich_schnittstelle",
    "version_doktrin", "bedarfs_inventur", "hash_vertrag",
    "vokabular_abbildung", "konsumenten_semantik", "kreuz_record_invarianten",
]


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    kl = d.get("substanzklassen", {})

    # 1. Die drei Klassen existieren mit Definition + Belegpflicht.
    gesamt += 1
    gut = all(kl.get(k, {}).get("belegpflicht") for k in
              ("MESSUNG", "ABLEITUNG", "ENTSCHEIDUNG"))
    print(f"{'ok  ' if gut else 'FAIL'} Drei Klassen mit Belegpflicht "
          f"{sorted(k for k in kl if k.isupper())}")
    ok += gut

    # 2. Jeder normative Abschnitt traegt eine gueltige Klasse.
    gesamt += 1
    ohne = []
    ungueltig = []
    for name in NORMATIV:
        sec = d.get(name)
        if not isinstance(sec, dict):
            ohne.append(name)
            continue
        k = sec.get("substanz")
        if k not in ("MESSUNG", "ABLEITUNG", "ENTSCHEIDUNG"):
            ohne.append(name) if k is None else ungueltig.append((name, k))
    gut = not ohne and not ungueltig
    print(f"{'ok  ' if gut else 'FAIL'} Alle normativen Felder      "
          f"ohne={ohne} ungueltig={ungueltig}")
    ok += gut

    # 3. MESSUNG-Felder referenzieren ein ausfuehrbares Skript.
    gesamt += 1
    kaputt = []
    for name in NORMATIV:
        sec = d.get(name) or {}
        if sec.get("substanz") != "MESSUNG":
            continue
        pfad = sec.get("messung_skript")
        if not pfad or not (SCRIPTS / pfad).is_file():
            kaputt.append((name, pfad))
    gut = not kaputt
    print(f"{'ok  ' if gut else 'FAIL'} MESSUNG -> Skript existiert  "
          f"kaputt={kaputt}")
    ok += gut

    # 4. ENTSCHEIDUNG-Felder tragen ein Bedarfsartefakt ODER eine
    #    Mitzeichnungspflicht. Ohne beides: vierte Auspraegung.
    gesamt += 1
    nackt = []
    for name in NORMATIV:
        sec = d.get(name) or {}
        if sec.get("substanz") != "ENTSCHEIDUNG":
            continue
        if not (sec.get("bedarfsartefakt") or sec.get("mitzeichnung")):
            nackt.append(name)
    gut = not nackt
    print(f"{'ok  ' if gut else 'FAIL'} ENTSCHEIDUNG -> Bedarf      "
          f"nackt={nackt}")
    ok += gut

    # 5. Die Klasse ist BEOBACHTBAR: der Test kennt den Unterschied.
    gesamt += 1
    feld_ohne = {"satz": "irgendwas zugesagt"}
    altes_gate = bool(feld_ohne.get("satz"))
    neues_gate = feld_ohne.get("substanz") in kl
    gut = altes_gate is True and neues_gate is False
    print(f"{'ok  ' if gut else 'FAIL'} Praesenz-Falle messbar      "
          f"alt={altes_gate} neu={neues_gate}")
    ok += gut

    # 6. Die Regel benennt ihren eigenen Verstoss — nicht nur die Klassen.
    gesamt += 1
    gut = "Zusage ja, Bedarf nein" in kl.get("verstoss", "")
    print(f"{'ok  ' if gut else 'FAIL'} Verstoss benannt           "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Substanzklassen-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
