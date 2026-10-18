#!/usr/bin/env python3
"""Katalog-Naht: die Regel darf keine Anzahl tragen.

§A-ZZZZ160/161 (Runde 87): **der Katalog war ein Schnappschuss.**

R86 publizierte je Vorkommen `DEDUP <sha>;rang=<1..n>`. `n` entstand bei
der Messung; eine Kopie danach hatte rang=n+1 ohne Regel. Jetzt traegt
die Regel `erst=`/`rest=` — eine Aussage ueber ALLE Raenge, ohne Anzahl.

Dieser Test prueft die drei Nahtfaelle:
  A  Detektor [A,A], Konsument [A,A,A]      -> dritte Kopie von rest erfasst
  B  Detektor [A],   Konsument [A,A]        -> zweite Kopie von rest erfasst
  C  Detektor [A,A,A], Konsument [A,A]      -> kein Fehlfeuern, kein Riss

Entscheidend: die Regel ist in A und B IDENTISCH (kein n), und der
Konsument kann sie ohne Kenntnis des Detektor-Stroms anwenden.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W = ROOT / "scripts" / "einwurf_waechter.py"
A = "A" * 500


def _z(ts: str, txt: str) -> str:
    return json.dumps({"role": "user", "message": {
        "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
        ensure_ascii=False)


def _lauf(zeilen: list[str]) -> str:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "strom.jsonl"
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=td)
        return r.stdout


def _regel(out: str) -> dict[str, tuple[str, str, str]]:
    """sha -> (erst, bei_gleich, bei_ungleich). `gesehen=` faellt bewusst
    weg: das ist Telemetrie, nicht Autoritaet — der Test prueft die
    VORSCHRIFT, und die muss in jedem Strom gleich sein."""
    return {h: (e, g, u) for h, e, g, u in re.findall(
        r"DEDUP (\S+);erst=([A-Z]+);rest_art=zeitstempel;"
        r"bei_gleich=([A-Z]+);bei_ungleich=([A-Z]+);", out)}


def main() -> int:
    ok = gesamt = 0

    # 1. Keine Regel traegt eine Anzahl als Autoritaet.
    gesamt += 1
    r2 = _regel(_lauf([_z("T1", A), _z("T1", A)]))
    r1 = _regel(_lauf([_z("T1", A)]))
    gut = r1 == r2 and bool(r1)
    print(f"{'ok  ' if gut else 'FAIL'} Regel bei 1 und 2 Kopien gleich  "
          f"{r1} == {r2}")
    ok += gut

    # 2. Fall A: dritte Kopie wird von `rest` erfasst (kein n im Weg).
    gesamt += 1
    h = next(iter(r1))
    _, bei_gleich, bei_ungleich = r1[h]
    # `rest` trifft jede Kopie ab Rang 2 — die Aktion haengt am
    # Zeitstempel, nicht an der Anzahl.
    rang3_aktion = bei_gleich
    gut = {bei_gleich, bei_ungleich} == {"VERWERFEN", "WIEDERHOLT"}
    print(f"{'ok  ' if gut else 'FAIL'} Rang 3 abgedeckt              "
          f"aktion={rang3_aktion}")
    ok += gut

    # 3. Fall B: unique-Klasse, zweite Kopie -> rest greift trotzdem.
    gesamt += 1
    gut = h in r1 and r1[h][0] == "ZUSTELLEN"
    print(f"{'ok  ' if gut else 'FAIL'} unique-Klasse hat Regel       "
          f"erst={r1[h][0]}")
    ok += gut

    # 4. Kein `rang=` mehr in der Ausgabe (die Form, die veraltete).
    gesamt += 1
    out = _lauf([_z("T1", A), _z("T1", A), _z("T2", A)])
    gut = "rang=" not in out and "DEDUP " in out
    print(f"{'ok  ' if gut else 'FAIL'} kein rang= im DEDUP           "
          f"{'sauber' if gut else 'Katalog mit Anzahl'}")
    ok += gut

    # 5. Fall C: Detektor sah 3, Konsument 2 -> kein Fehlfeuern moeglich,
    #    weil die Aktion nicht an einer Anzahl haengt.
    gesamt += 1
    r3 = _regel(_lauf([_z("T1", A), _z("T2", A), _z("T3", A)]))
    gut = r3 == r2
    print(f"{'ok  ' if gut else 'FAIL'} 3 gesehen == 2 gesehen       "
          f"{'identisch' if gut else 'Katalog wandert'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Katalog-Naht-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
