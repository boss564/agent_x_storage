#!/usr/bin/env python3
"""Zeilen-Identitaet: der Test, der scheitern MUSS, bevor er grün wird.

§A-ZZZZ137 (Runde 84): **Zähler sind keine Zeiger.**

Der Vertrag sagt „Duplikat → verwerfen". Die Ausgabe der Runde 83 sagte
`KANAL-DUPLIKAT=37`. Ein Konsument weiss damit, DASS 37 Zeilen zu
verwerfen sind — nicht WELCHE. Er kann die vertragliche Aktion nicht
ausführen.

Dieser Test treibt das auf die Spitze: er nimmt einen GEMISCHTEN Strom
(clean + Duplikat + unparsbar), liest die Ausgabe und versucht, die
Aktion zeilenweise auszuführen. Gelingt es nicht, ist das ein Befund
über die Ausgabe — nicht über den Test.

Der Test ist bewusst VOR der Reparatur geschrieben. Sein erster Lauf
war rot. Das ist der Bringschuld-Nachweis: ein Fall, der rot sein
MUSSTE, weil die Ausgabe kein Zeilen-Urteil trägt.
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
C = "C" * 500


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


def _zeilenurteile(out: str) -> dict[int, str]:
    """Position -> Urteil, gelesen aus den `ZEILE <n> <urteil>`-Marken."""
    return {int(n): u for n, u in
            re.findall(r"ZEILE (\d+) ([A-Z\-]+)", out)}


def main() -> int:
    ok = 0
    gesamt = 0

    # Gemischter Strom: Position 1 clean, 2 Duplikat, 3 clean, 4 Duplikat,
    # 5 unparsbar.
    zeilen = [_z("T1", A), _z("T1", A), _z("T2", B), _z("T2", B),
              "KEIN JSON"]
    code, out = _lauf(zeilen)

    gesamt += 1
    print(f"gemischter Strom: exit={code}  "
          f"({'unvollstaendig' if code == 4 else 'FALSCH'})")
    ok += code == 4

    # Der eigentliche Test: kann ein Konsument die Zeilen lokalisieren?
    urteil = _zeilenurteile(out)
    gesamt += 1
    vollstaendig = len(urteil) >= 5
    print(f"{'ok  ' if vollstaendig else 'FAIL'} Zeilen-Identitaet        "
          f"{len(urteil)}/5 Zeilen tragen ein Urteil")
    ok += vollstaendig

    # Und stimmen die Urteile mit der Aktion überein?
    soll = {1: "ZUSTELLEN", 2: "VERWERFEN", 3: "ZUSTELLEN",
            4: "VERWERFEN", 5: "UNGEPRUEFT"}
    gesamt += 1
    stimmt = all(urteil.get(k) == v for k, v in soll.items())
    print(f"{'ok  ' if stimmt else 'FAIL'} Urteil je Zeile          "
          f"soll={soll}  ist={urteil}")
    ok += stimmt

    # Ein Konsument muss allein aus der Ausgabe zustellen können.
    gesamt += 1
    zuzustellen = sorted(k for k, v in urteil.items()
                         if v in ("ZUSTELLEN", "UNGEPRUEFT"))
    erwartet = [1, 3, 5]
    gut = zuzustellen == erwartet
    print(f"{'ok  ' if gut else 'FAIL'} Zustell-Liste            "
          f"{zuzustellen} erwartet {erwartet}")
    ok += gut

    print(f"\n{ok}/{gesamt} Zeilen-Identitaets-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
