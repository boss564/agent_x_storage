#!/usr/bin/env python3
"""N und alpha herleiten — und die Probe auf das messen, was sie meint.

§A-ZZZZ212 (Runde 92 Befund 5): **die Magie ist von 1000 auf N und alpha
gewandert.**

Die Arithmetik n=1418 stimmt. Aber N=1e8 und alpha=0.01 sind selbst
Entscheidungen. Und das Modell passt nicht zum Strom:

  Geburtstagsschranke setzt voraus:  uniforme, unabhaengige Ziehungen
  Realer Strom:                      geclustert (Bursts, gleiche Sekunde),
                                     Verletzungen an FORMATGRENZEN
                                     ("01.02." vs "1.2." vs "2024-02-01")

FOLGE: Die Schranke ist weder Garantie noch Schaetzung. Sie ist ein
Mindest-Evidenz-Floor in Formelverkleidung.

DIE ZWEI HERLEITUNGEN, DIE NOETIG SIND:

1. N: nicht "Sekunden ueber 3 Jahre", sondern der tatsaechliche
   NORMALFORM-RAUM. Verletzungen liegen an Formatgrenzen, also zaehlt
   die Zahl der Format-Varianten, nicht die Zahl der Sekunden:
       N_eff = distinkte_trennzeichen x distinkte_breiten x ...
   Das ist kleiner als 1e8 — und genau der Raum, in dem die Probe
   Verletzungen finden KANN.

2. alpha: eine Anforderung, kein Policy-Default. Wer traegt das
   Restrisiko von 1%? Das ist keine Frage an den Autor.

DIE MESSAXIS-UMSTELLUNG: Die Probe samplet heute ZEILEN. i.i.d. Zeilen
sind bei geclusterten Stroemen eine falsche Annahme. Richtig ist:
distinkte NORMALFORMEN zaehlen, nicht Zeilen.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    h = d.get("schwellen_herleitung", {})
    n_h = h.get("N_herleitung", {})
    a_h = h.get("alpha_herleitung", {})

    # 1. N ist hergeleitet, nicht gesetzt — aus dem Format-Raum.
    gesamt += 1
    # Der Raum muss der FORMAT-Raum sein — erkennbar an den Faktoren,
    # nicht am Wort "format" (das steht im Feld `warum`, nicht `formel`).
    gut = ("trennzeichen" in n_h.get("formel", "")
           and "feldbreiten" in n_h.get("formel", ""))
    print(f"{'ok  ' if gut else 'FAIL'} N aus Format-Raum          "
          f"{n_h.get('formel', 'fehlt')[:46]}")
    ok += gut

    # 2. §A-ZZZZ213: N_eff ist NICHT gesetzt — der zu kleine Wert ist als
    #    Befund gebucht. Ein gesetztes N_eff waere die Gelegenheits-Falle
    #    tiefer (36 -> n=1 -> "BESTANDEN" mit 3 Zeilen).
    gesamt += 1
    n_eff = n_h.get("N_eff")
    zu_klein = n_h.get("N_eff_zu_klein_befund", "")
    gut = n_eff is None and "n=1" in zu_klein
    print(f"{'ok  ' if gut else 'FAIL'} N_eff bewusst offen        "
          f"N_eff={n_eff} Befund gebucht={'ja' if zu_klein else 'nein'}")
    ok += gut

    # 3. alpha ist eine ANFORDERUNG mit einer benannten Stelle.
    gesamt += 1
    gut = (a_h.get("stelle") and a_h.get("frage")
           and a_h.get("status") == "anforderung")
    print(f"{'ok  ' if gut else 'FAIL'} alpha als Anforderung      "
          f"stelle={a_h.get('stelle', 'fehlt')}")
    ok += gut

    # 4. Die i.i.d.-Annahme ist als VERLETZT deklariert, nicht still.
    gesamt += 1
    gut = h.get("annahme_verletzt") is True and bool(h.get("modell"))
    print(f"{'ok  ' if gut else 'FAIL'} i.i.d.-Verletzung benannt   "
          f"{h.get('annahme_verletzt')}")
    ok += gut

    # 5. Die Messachse ist umgestellt: distinkte Normalformen, nicht Zeilen.
    gesamt += 1
    gut = d.get("messachse_norm") == "distinkte_normalformen"
    print(f"{'ok  ' if gut else 'FAIL'} Messachse umgestellt       "
          f"{d.get('messachse_norm')}")
    ok += gut

    # 6. Die Schranke ist als FLOOR deklariert, nicht als Garantie.
    gesamt += 1
    gut = "garantie" in h.get("status", "").lower() and \
        "floor" in h.get("status", "").lower()
    print(f"{'ok  ' if gut else 'FAIL'} Status = Floor, keine Garantie "
          f"{h.get('status', 'fehlt')[:40]}")
    ok += gut

    print(f"\n{ok}/{gesamt} Schwellen-Eingaenge-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
