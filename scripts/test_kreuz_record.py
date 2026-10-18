#!/usr/bin/env python3
"""Kreuz-Record-Invarianten: Formen je Zeile sind nicht genug.

§A-ZZZZ164 (Runde 87): **deklariert ist nicht erzwungen.**

Der Vertrag sagt: `AUFRUF` darf nur allein auftreten. Die
Schema-Invarianz prueft Feldformen je Record, nicht die Komposition.
Ebenso steht nirgends mechanisch, dass `UNGEPRUEFT` existiert und der
Exit daraus ableitbar bleibt.

Dieser Test prueft die Komposition:
  1. `AUFRUF` schliesst jeden Inhalts-Record aus.
  2. `UNGEPRUEFT` hat einen Record-Typ bei JEDEM Exit 4.
  3. Der Exit ist aus den Records allein ableitbar (kein internes Wissen).
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


def _z(ts: str, txt: str) -> str:
    return json.dumps({"role": "user", "message": {
        "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
        ensure_ascii=False)


def _lauf(args: list[str]) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(W), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout


def _strom(zeilen: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "strom.jsonl"
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        return _lauf(["--strom", str(f)])


def ableitung(out: str) -> int:
    """Exit NUR aus den Records — keine internen Zustaende."""
    u = set(re.findall(r"ZEILE \S+ ([A-Z]+);", out))
    if "UNGEPRUEFT" in u:
        return 4
    if "VERWERFEN" in u:
        return 1
    # §A-ZZZZ164b: `bei_gleich`/`bei_ungleich` sind eine VORSCHRIFT fuer
    # kuenftige Kopien, kein Befund ueber diesen Strom. Nur wenn der
    # Detektor tatsaechlich eine Kopie SAH (gesehen>=2), ist daraus ein
    # Befund ableitbar. Ein Konsument, der die Vorschrift als Ereignis
    # liest, meldet bei einer einzigen Meldung ein Duplikat — genau der
    # Fehler, den dieser Test beim ersten Lauf selbst gemacht hat.
    for g, in re.findall(r"DEDUP \S+;erst=\S+;rest_art=\S+;"
                         r"bei_gleich=\S+;bei_ungleich=\S+;gesehen=(\d+);", out):
        if int(g) >= 2:
            return 1
    return 0


def main() -> int:
    ok = gesamt = 0

    # 1. AUFRUF nur allein.
    for name, args in (("kein Modus", []),
                       ("einwurf ohne strom", ["--einwurf"])):
        gesamt += 1
        code, out = _lauf(args)
        hat_aufruf = "ZEILE AUFRUF " in out
        hat_inhalt = bool(re.search(r"ZEILE (?!AUFRUF)\S+ ", out)) or \
            "DEDUP " in out
        gut = code == 2 and hat_aufruf and not hat_inhalt
        print(f"{'ok  ' if gut else 'FAIL'} {name:22s} AUFRUF={hat_aufruf} "
              f"Inhalt={hat_inhalt}")
        ok += gut

    # 2. UNGEPRUEFT hat einen Record bei jedem Exit 4.
    for name, zeilen in (("nur muell", ["MUELL"]),
                         ("dup + muell", [_z("T1", A), _z("T1", A), "MUELL"]),
                         ("neu + muell", [_z("T1", A), "MUELL"])):
        gesamt += 1
        code, out = _strom(zeilen)
        hat = bool(re.search(r"ZEILE pos:\d+ UNGEPRUEFT;", out))
        gut = code == 4 and hat
        print(f"{'ok  ' if gut else 'FAIL'} {name:22s} exit={code} "
              f"UNGEPRUEFT-Record={hat}")
        ok += gut

    # 3. Exit aus Records allein.
    for name, zeilen, soll in (
            ("neu", [_z("T1", A)], 0),
            ("dup", [_z("T1", A), _z("T1", A)], 1),
            ("wiederholung", [_z("T1", A), _z("T2", A)], 1),
            ("muell", ["MUELL"], 4),
            ("dup+muell", [_z("T1", A), _z("T1", A), "MUELL"], 4)):
        gesamt += 1
        code, out = _strom(zeilen)
        ab = ableitung(out)
        gut = code == ab
        print(f"{'ok  ' if gut else 'FAIL'} Ableitung {name:14s}  "
              f"exit={code} aus_records={ab}")
        ok += gut

    print(f"\n{ok}/{gesamt} Kreuz-Record-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
