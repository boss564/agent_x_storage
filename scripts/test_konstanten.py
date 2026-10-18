#!/usr/bin/env python3
"""Konstanten-Test: fängt richtig *geratene* Zahlen, nicht nur falsche.

§A-ZZZZ130 (Runde 83): **ein Fixture-Wert fängt nur falsche Konstanten.**

Der Mutant `KANAL-DUPLIKAT=37` bestand den Vertrag der Runde 82, weil
das einzige Fixture 37 erwartete. 37 == 37. Ein Detektor, der die Zahl
hartkodiert statt zu zaehlen, waere damit zertifiziert worden.

Dieser Test faehrt **drei synthetische Stroeme mit abweichenden
Soll-Werten** gegen den echten Waechter. Erst abweichende Erwartungen
binden die Rechnung an die Eingabe:

    Fixture A: 1 Meldung, 0 Duplikate        -> Paare=0
    Fixture B: 2 identisch + 1 verschieden   -> Paare=1, KANAL-DUPLIKAT=1
    Fixture C: 3 identisch, ts verschieden   -> Paare=2, WIEDERHOLUNG=2

Kein fester Wert kann alle drei bestehen. Die Soll-Werte stammen aus der
Fixture-Konstruktion (ich zaehle, was ich hineinlege), nicht aus der
Ausgabe des Prueflings — sonst ratifizierte der Vertrag einen
systematischen Zaehlfehler.

Der Live-Strom-Snapshot (38/37/1) ist bewusst **nicht** hier: er wandert
mit jeder neuen Meldung und wuerde CI rot faerben, ohne dass ein Defekt
vorliegt.
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


def _achse(stdout: str) -> dict[str, int]:
    return {k: int(v) for k, v in re.findall(r"(?:^|;)([A-Za-z_\-]+)=(\d+)", stdout)}


def main() -> int:
    ok = 0
    faelle = [
        ("A: 1 Meldung, 0 Duplikate",
         [_z("T1", A)],
         {"Paare": 0, "KANAL-DUPLIKAT": 0, "WIEDERHOLUNG": 0}),
        ("B: 2 identisch + 1 verschieden",
         [_z("T1", A), _z("T1", A), _z("T2", B)],
         {"Paare": 1, "KANAL-DUPLIKAT": 1, "WIEDERHOLUNG": 0}),
        ("C: 3 identisch, ts verschieden",
         [_z("T1", A), _z("T2", A), _z("T3", A)],
         {"Paare": 2, "KANAL-DUPLIKAT": 0, "WIEDERHOLUNG": 2}),
    ]
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for name, zeilen, soll in faelle:
            f = d / "strom.jsonl"
            f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                               capture_output=True, text=True, cwd=d)
            ist = _achse(r.stdout)
            gut = all(ist.get(k) == v for k, v in soll.items())
            diff = {k: (v, ist.get(k)) for k, v in soll.items()
                    if ist.get(k) != v}
            print(f"{'ok  ' if gut else 'FAIL'} {name:32s} "
                  f"{' '.join(f'{k}={v}' for k, v in soll.items())}"
                  + (f"  ABWEICHUNG soll/ist {diff}" if diff else ""))
            ok += gut
    print(f"\n{ok}/{len(faelle)} Konstanten-Proben gruen")
    print("Kein fester Wert besteht alle drei — die Zahl folgt der Eingabe.")
    return 0 if ok == len(faelle) else 1


if __name__ == "__main__":
    raise SystemExit(main())
