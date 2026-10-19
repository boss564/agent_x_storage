#!/usr/bin/env python3
"""STANDZEILE — generiert, nicht getippt.

§A-ZZZZ217 (Runde 94, achte Auspraegung): **die Anti-Kern-Regel stand im
Fuß des Berichts, der sie baute.**

R93 buchte: "Zaehlweise 34, KEIN Kern-Filter". Die Standzeile desselben
Berichts lautete: "Waechter-Kern 15/15 gruen". Der verbotene Filter im
sichtbarsten Feld.

Die Ursache ist nicht Nachlaessigkeit, sondern Bauart: die Standzeile war
PROSA. Der Mensch tippt die Zahl, wie er denkt — und er denkt in "Kern",
weil er so viele Runden in dieser Teilmenge gearbeitet hat.

Der Fix ist keine neunte Regel, sondern: diese Datei erzeugt die
Standzeile aus denselben Daten, aus denen die Tests laufen. Kein
Tastaturzugriff auf die Zahl.

WAS HIER NICHT STEHT (und nie stehen darf):
  - keine Teilmenge mit eigenem Namen ("Kern", "kritisch", "relevant")
  - keine zweite Zahl neben der ersten
  - keine gerundete Zahl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_zaehlweise import zaehle  # die EINE Quelle

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"
Q = SCRIPTS / "quarantaene"

# Woerter, die eine Teilmenge adeln. Die Standzeile darf sie nicht tippen.
VERBOTEN = ("kern", "critical", "kritisch", "relevant", "wichtig",
            "ausgewaehlt", "selected")


def zeile() -> str:
    """Die Standzeile. Eine Zahl, eine Quelle, keine Adjektive."""
    d = json.loads(V.read_text(encoding="utf-8"))
    k = zaehle()
    gesamt = sum(len(v) for v in k.values())
    q = len(list(Q.glob("*.quarantaene"))) if Q.is_dir() else 0
    offen = len([p for p in d.get("externes_buch", {}).get("posten", [])
                 if not p.get("eigentuemer")])
    posten = len(d.get("externes_buch", {}).get("posten", []))
    # R96: zwei Einheiten, nie eine Summe ohne Zerlegung.
    #   Testkorpus = zaehle() = code + nur_vertrag + aussen.
    #   Instrumente = Nicht-Test-Skripte, die zaehle() NICHT sieht
    #   (Frist-Gate, Governance-Gate, Kopf-/Standzeile). In R95 unbewertet.
    inst = [x.name for x in SCRIPTS.glob("*.py")
            if not x.name.startswith("test_")]
    return (f"Tests: {gesamt} Dateien "
            f"({len(k['code'])} vertragsbezogen, "
            f"{len(k['nur_vertrag'])} nur Vertrag, "
            f"{len(k['aussen'])} aussen) | "
            f"Instrumente: {len(inst)} Nicht-Test-Skripte "
            f"(ausserhalb des Testkorpus) | "
            f"Quarantaene: {q} | "
            f"Obligationen: {posten} extern, davon {offen} ohne Eigentuemer")


def main() -> int:
    s = zeile()
    low = s.lower()
    treffer = [w for w in VERBOTEN if w in low]
    if treffer:
        print(f"VERBOTEN in Standzeile: {treffer}")
        return 1
    print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
