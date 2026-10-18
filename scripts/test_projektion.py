#!/usr/bin/env python3
"""Projektion: der Strom-Exit muss aus den Zeilen-Urteilen folgen.

§A-ZZZZ147 (Runde 85): **zwei Wahrheiten ohne Ableitung driften.**

R84 erzeugte zwei Ausgabe-Ebenen: den Strom-Exit (Gesamturteil) und die
Zeilen-Urteile (Gesetz). Der Vertrag sagt nicht, wie die eine aus der
anderen folgt. Ein Strom mit einer UNGEPRUEFT-Zeile koennte Exit 0
tragen — dann faellt jeder Exit-lesende Konsument in die alten
Datenverlust-Modi zurueck, waehrend die Zeilen-Ebene das Richtige sagt.

Dieser Test leitet den Exit aus den Zeilen ab und assertiert Gleichheit:

    Exit = aggregiere(4 wenn eine UNGEPRUEFT-Zeile, 1 wenn eine
                      VERWERFEN-Zeile, sonst 0)

Zusaetzlich: ein Strom ohne VERWERFEN und ohne UNGEPRUEFT MUSS Exit 0
tragen. Sonst ist der Exit nicht Telemetrie, sondern Zufall.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parent / "einwurf_waechter.py"
A = "A" * 500
B = "B" * 500


def _z(ts: str, txt: str) -> str:
    return json.dumps({"role": "user", "message": {
        "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
        ensure_ascii=False)


def _lauf(zeilen: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "strom.jsonl"
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=td)
        return r.returncode, r.stdout


def _erwartet_exit(out: str) -> int:
    u = re.findall(r"ZEILE \S+ ([A-Z]+);", out)
    if "UNGEPRUEFT" in u:
        return 4
    if "VERWERFEN" in u:
        return 1
    return 0


def main() -> int:
    ok = 0
    gesamt = 0
    faelle = [
        ("nur neu", [_z("T1", A), _z("T2", B)], 0),
        ("ein Duplikat", [_z("T1", A), _z("T2", B), _z("T1", A)], 1),
        ("nur Muell", ["KEIN JSON"], 4),
        ("Duplikat + Muell", [_z("T1", A), _z("T1", A), "KEIN JSON"], 4),
        ("alles drei", [_z("T1", A), _z("T1", A), _z("T2", B), "KEIN JSON"], 4),
    ]
    for name, zeilen, soll in faelle:
        gesamt += 1
        code, out = _lauf(zeilen)
        abgeleitet = _erwartet_exit(out)
        gut = code == abgeleitet == soll
        print(f"{'ok  ' if gut else 'FAIL'} {name:20s} exit={code} "
              f"aus_zeilen={abgeleitet} soll={soll}")
        ok += gut
    print(f"\n{ok}/{gesamt} Projektions-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
