#!/usr/bin/env python3
"""Selbst-begrenzende Records: kein Emittent darf eine Reihenfolge kennen.

§A-ZZZZ209 (Runde 92 Befund 4): **der Reihenfolge-Fix ist das Spiegelbild
des Parser-Bugs aus R88.**

R88 lernte: "Ein Parser, der die Reihenfolge kennt, kennt die Version."
Der zentrale `felder()`-Parser wurde reihenfolge-tolerant.

R91 baute das Gegenteil auf der SCHREIB-Seite:
    "STROM-Zeile MUSS zuerst, sonst klebt sie an der Achse."

Gemessen in R92:
    Zeile 0 endet mit ';'   (STROM ... jsonl';
    Zeile 1 endet mit ';'   (...json=0;)

Beide Zeilen enden mit `;`. Ohne Zeilenumbruch waere `STROM UNLESBAR;...
;Paare=0;...` EIN Feldstrom, in dem die STROM-Zeile nur durch ihre Position
erkennbar ist. Genau das ist die versteckte Version im Emittenten.

Die Architektur-Loesung: jeder Record selbst-begrenzend. Konkret —
jeder Record traegt ein TYP-PRAEFIX am Zeilenanfang (`STROM `, `ZEILE `,
`DEDUP `, `Paare=`). Ein Parser, der nach Praefix trennt, ist
reihenfolge-unabhaengig. Dieser Test prueft, dass das gilt — fuer JEDE
Permutation der Records.
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"
W = SCRIPTS / "einwurf_waechter.py"

PRAEFIXE = ("STROM ", "ZEILE ", "DEDUP ", "Paare=", "AUFRUF ")


def typ(zeile: str) -> str:
    for p in PRAEFIXE:
        if zeile.startswith(p):
            return p.strip()
    return "?"


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    gr = d.get("record_grammatik", {})

    # 1. Jeder Record traegt ein Typ-Praefix — gemessen am echten Bericht.
    with tempfile.TemporaryDirectory() as td:
        fehlt = Path(td) / "x.jsonl"
        r = subprocess.run([sys.executable, str(W), "--strom", str(fehlt)],
                           capture_output=True, text=True)
    zeilen = [z for z in r.stdout.splitlines() if z.strip()]

    gesamt += 1
    ohne = [z[:20] for z in zeilen if typ(z) == "?"]
    gut = not ohne
    print(f"{'ok  ' if gut else 'FAIL'} Jeder Record hat Praefix    "
          f"ohne={ohne}")
    ok += gut

    # 2. Die Praefixe sind untereinander eindeutig (kein Praefix ist
    #    Praefix eines anderen).
    gesamt += 1
    koll = [(a, b) for a, b in itertools.permutations(PRAEFIXE, 2)
            if a.startswith(b) or b.startswith(a)]
    gut = not koll
    print(f"{'ok  ' if gut else 'FAIL'} Praefixe kollisionsfrei    "
          f"{koll or 'ja'}")
    ok += gut

    # 3. Permutation: ein Parser, der nach Praefix trennt, findet die
    #    STROM-Zeile in JEDER Position — nicht nur an Position 0.
    gesamt += 1
    gefunden_ueberall = True
    for perm in itertools.permutations(zeilen):
        idx = [i for i, z in enumerate(perm) if typ(z) == "STROM"]
        if len(idx) != 1:
            gefunden_ueberall = False
            break
    gut = gefunden_ueberall
    print(f"{'ok  ' if gut else 'FAIL'} Praefix-Parser reihenfolge- "
          f"unabhaengig ({len(zeilen)}! Permutationen)")
    ok += gut

    # 4. Der Vertrag deklariert die Grammatik — nicht die Reihenfolge.
    gesamt += 1
    gut = (gr.get("regel") and "praefix" in gr.get("regel", "").lower()
           and "reihenfolge" in gr.get("regel", "").lower())
    print(f"{'ok  ' if gut else 'FAIL'} Grammatik deklariert        "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 5. Der alte Vorrang-Satz ist als BANDAGE markiert, nicht als Norm.
    gesamt += 1
    vor = d.get("exit_taxonomie", {}).get("vorrang_strom_zeile", "")
    gut = "BANDAGE" in vor or "nicht noetig" in vor.lower()
    print(f"{'ok  ' if gut else 'FAIL'} Vorrang als Bandage        "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 6. Ein Record ohne abschliessendes ';' ist erkennbar (Achse endet
    #    mit ';', also ist ein fehlendes ';' ein Terminator-Signal).
    gesamt += 1
    ohne_semi = [z[:14] for z in zeilen if not z.endswith(";")]
    gut = ohne_semi == []
    print(f"{'ok  ' if gut else 'FAIL'} Terminator einheitlich      "
          f"ohne_semi={ohne_semi}")
    ok += gut

    print(f"\n{ok}/{gesamt} Record-Grammatik-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
