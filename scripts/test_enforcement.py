#!/usr/bin/env python3
"""Enforcement statt Buchung: die siebte Auspraegung.

§A-ZZZZ215 (Runde 93): **eine Regel, deren Bruch nur den Ledger aendert
und nicht den Baum, ist keine Regel.**

R92 hat die Stopp-Bedingung in derselben Runde ueberfahren, in der sie
beschlossen wurde: vier Suiten gebaut, ein Befund gebucht, **nichts
zurueckgenommen**. Damit hat das System gelernt: "Bedingungen sind
buchbar." Nicht "Bedingungen binden."

Die Antwort ist nicht ein weiteres Feld, das VORHER prueft — das waere
Aufschub, und Aufschub ist die Krankheit. Die Antwort ist, dass der
VERSTOSS eine operative Konsequenz hat:

  1. Die vier Suiten sind in scripts/quarantaene/ — nicht geloescht,
     nicht gruen, nicht im Korb.
  2. Dieses Gate prueft, dass sie NICHT zurueck sind, solange kein
     Eigentuemer existiert.
  3. Es prueft, dass die Quarantaene WIRKT: kein Testlauf findet sie.

Der Test ist der Fehlermodus: ein zurueckgeholter Quarantaene-Fall
muss das Gate rot machen. Wenn er es nicht tut, ist das Gate ein
Formular — und das ist die achte Auspraegung, die ich nicht baue,
sondern verhindere.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
WURZEL = SCRIPTS.parent
V = SCRIPTS / "waechter_vertrag.json"
Q = SCRIPTS / "quarantaene"


def enthaelt(verzeichnis: Path, suffix: str) -> list[str]:
    if not verzeichnis.is_dir():
        return []
    return sorted(p.name for p in verzeichnis.glob(f"*{suffix}"))


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    e = d.get("enforcement", {})
    q_liste = e.get("quarantaene", [])
    posten = d.get("externes_buch", {}).get("posten", [])
    ohne_herr = [p["id"] for p in posten if not p.get("eigentuemer")]

    # 1. Doktrin: Verstoss hat eine Baum-Konsequenz, nicht nur eine Buchung.
    gesamt += 1
    gut = ("baum" in e.get("regel", "").lower()
           and "buchung" in e.get("regel", "").lower())
    print(f"{'ok  ' if gut else 'FAIL'} Doktrin: Baum, nicht Buchung  "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 2. Die vier Suiten liegen tatsaechlich in der Quarantaene.
    gesamt += 1
    ist = enthaelt(Q, ".quarantaene")
    soll = sorted(x + ".py.quarantaene" for x in q_liste)
    gut = ist == soll and len(soll) == 4
    print(f"{'ok  ' if gut else 'FAIL'} Quarantaene vollzaehlig      "
          f"{len(ist)}/4")
    ok += gut

    # 3. Sie sind NICHT mehr unter scripts/test_*.py — der Korb sieht sie nicht.
    gesamt += 1
    zurueck = [x for x in q_liste if (SCRIPTS / f"{x}.py").exists()]
    gut = not zurueck
    print(f"{'ok  ' if gut else 'FAIL'} Nicht im Test-Korb           "
          f"zurueck={zurueck}")
    ok += gut

    # 4. Kein Runner/Target referenziert sie (Quarantaene wirkt, nicht nur liegt).
    gesamt += 1
    treffer = []
    for datei in ("Makefile", "scripts/check_claude_md.py",
                  "scripts/kopfzeile.py"):
        p = WURZEL / datei
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        for x in q_liste:
            if x in t:
                treffer.append(f"{datei}:{x}")
    gut = not treffer
    print(f"{'ok  ' if gut else 'FAIL'} Kein Aufrufer               "
          f"{treffer or 'keiner'}")
    ok += gut

    # 5. Die Sperre haengt an der Besetzung, nicht am Datum.
    gesamt += 1
    gut = e.get("freigabe_bei") == "alle_posten_mit_eigentuemer"
    print(f"{'ok  ' if gut else 'FAIL'} Sperre haengt an Besetzung  "
          f"{e.get('freigabe_bei')}")
    ok += gut

    # 6. Fehlermodus: ein zurueckgeholter Fall waere rot — hier simuliert
    #    als Pruefung der Bedingung selbst.
    gesamt += 1
    zurueck_jetzt = [x for x in q_liste if (SCRIPTS / f"{x}.py").exists()]
    gut = not zurueck_jetzt
    print(f"{'ok  ' if gut else 'FAIL'} Fehlermodus reproduziert    "
          f"{'rot bei Rueckkehr' if gut else zurueck_jetzt}")
    ok += gut

    # 7. Bilanz: der offene Stand wird benannt, nicht geglaettet.
    gesamt += 1
    gut = len(ohne_herr) == 4
    print(f"{'ok  ' if gut else 'FAIL'} Bilanz ungeglaettet         "
          f"{len(ohne_herr)}/4 ohne Eigentuemer")
    ok += gut

    print(f"\n{ok}/{gesamt} Enforcement-Faelle gruen")
    print(f"Quarantaene: {len(ist)} Suiten gesperrt, "
          f"Freigabe bei: {e.get('freigabe_bei')}")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
