#!/usr/bin/env python3
"""Die Schwellen-Herleitung: n aus N und alpha, nicht aus dem Bauch.

§A-ZZZZ206 (Runde 91 Befund 5): **die 1000-Zeilen-Schwelle war eine
magische Zahl — und fuer realistische Zeitstempel-Raeume so leer wie 3.**

Die Probe testet Injektivitaet der Normalisierung. Die Frage lautet:
wie viele Zeilen braucht man, damit eine Kollision mit Konfidenz
`1-alpha` SICHTBAR wird, wenn es eine gibt? Geburtstagsschranke:

    n ~ sqrt(2 * N * ln(1/(1-alpha)))

Das ist die Zahl der Ziehungen, bei denen die Kollisionswahrscheinlichkeit
ueber alpha steigt. Sie ist eine ABLEITUNG aus N (Groesse des
Normalisierungsraums) und alpha (Irrtumswahrscheinlichkeit) — keine Wahl.

Der Befund aus R91: bei N = 10^8 (Sekunden ueber ~3 Jahre) und
alpha = 0.01 ist n ~ 10^4 — die 1000 war zu klein. Bei N = 10^9 waere
n ~ 3*10^4. Die 1000 war nicht nur unhergeleitet, sie war um eine
Groessenordnung zu niedrig.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"


def geburtstag(n_raum: float, alpha: float) -> int:
    """n, ab dem eine Kollision mit W'keit > 1-alpha erwartet wird."""
    return math.ceil(math.sqrt(2.0 * n_raum * math.log(1.0 / (1.0 - alpha))))


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    her = d.get("schwellen_herleitung", {})

    # 1. Die Eingangsgroessen sind benannt — N und alpha, keine Schwelle.
    gesamt += 1
    gut = ("N" in her and "alpha" in her)
    print(f"{'ok  ' if gut else 'FAIL'} N und alpha benannt        "
          f"{sorted(her)[:4]}")
    ok += gut

    # 2. Die Formel steht im Vertrag und ist die Geburtstagsschranke.
    gesamt += 1
    formel = her.get("formel", "")
    gut = "sqrt" in formel and "ln" in formel
    print(f"{'ok  ' if gut else 'FAIL'} Formel = Geburtstagsschranke "
          f"{formel[:44]!r}")
    ok += gut

    # 3. Die Schwelle ist das ERGEBNIS der Formel, nicht eine Zahl.
    gesamt += 1
    n_raum = her.get("N", 0)
    alpha = her.get("alpha", 0)
    n_ergebnis = her.get("n")
    soll = geburtstag(n_raum, alpha) if n_raum and alpha else None
    gut = n_ergebnis == soll and soll is not None
    print(f"{'ok  ' if gut else 'FAIL'} n = geburtstag(N,alpha)    "
          f"n={n_ergebnis} soll={soll} (N={n_raum:.0e}, a={alpha})")
    ok += gut

    # 4. Der alte Wert 1000 war zu klein — gemessen, nicht behauptet.
    gesamt += 1
    alt = her.get("vorher", 1000)
    gut = soll is not None and alt < soll
    print(f"{'ok  ' if gut else 'FAIL'} 1000 war zu klein          "
          f"{alt} < {soll} = {gut}")
    ok += gut

    # 5. Die Probe benutzt den hergeleiteten Wert, nicht die Literale.
    gesamt += 1
    probe = (SCRIPTS / "blocker_nrm_injektivitaet.py").read_text(encoding="utf-8")
    # Zuweisung pruefen, nicht Erwaehnung: der Kommentar DARF die alte
    # Zahl nennen (er erklaert den Fehler). Verboten ist die Literal-Zuweisung.
    import re as _re
    literal = _re.search(r"^\s*MINDESTENS\s*=\s*\d+\s*$", probe,
                         _re.MULTILINE) is not None
    liest = "schwellen_herleitung" in probe
    gut = not literal and liest
    print(f"{'ok  ' if gut else 'FAIL'} Probe liest statt tippt    "
          f"literal={literal} liest={liest}")
    ok += gut

    # 6. Die Achse ist ehrlich: unhergeleitet bleibt UNBEWIESEN.
    gesamt += 1
    gut = "UNBEWIESEN" in her.get("status_regel", "")
    print(f"{'ok  ' if gut else 'FAIL'} Status-Regel deklariert    "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Schwellen-Herleitungs-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
