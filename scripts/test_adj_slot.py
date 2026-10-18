#!/usr/bin/env python3
"""ADJ: bewusste Neusendung hat einen eigenen Verdict-Slot.

§A-ZZZZ149 (Runde 85): **eine Auslassung ist eine Entscheidung.**

Das Zeilen-Vokabular hatte drei Werte {ZUSTELLEN, VERWERFEN, UNGEPRUEFT},
der Detektor vier Etiketten (sauber, KANAL-DUPLIKAT, WIEDERHOLUNG,
ungeprueft). Zwischen Detektor und Aktionsschicht fiel eine
Unterscheidung weg — und zwar genau die, deren Adjudikation (ADJ) der
Betreiber nie entschieden hat: darf eine BEWUSSTE Neusendung blockiert
werden? Wer `WIEDERHOLUNG -> VERWERFEN` abbildet, entscheidet "ja"
durch Code. Das ist kein Default, das ist ein Vorgriff.

Jetzt:
    KANAL-DUPLIKAT -> VERWERFEN   (bytegleich, gleicher Zeitstempel)
    WIEDERHOLUNG   -> WIEDERHOLT  (Inhalt gleich, anderer Zeitstempel)

Beide heben den Exit auf 1 (Befund), aber nur VERWERFEN ist eine
Aktion. WIEDERHOLT ist der Slot, den der Betreiber mit ADJ fuellt.
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


def main() -> int:
    ok = 0
    gesamt = 0

    # 1. Kanal-Duplikat: gleicher Inhalt, gleicher ts -> VERWERFEN.
    gesamt += 1
    code, out = _lauf([_z("T1", A), _z("T1", A)])
    gut = code == 1 and re.search(r"ZEILE \S+ VERWERFEN;pos=2;art=KANAL-DUPLIKAT;", out)
    print(f"{'ok  ' if gut else 'FAIL'} Kanal-Duplikat -> VERWERFEN   exit={code}")
    ok += bool(gut)

    # 2. Bewusste Neusendung: gleicher Inhalt, ANDERER ts -> WIEDERHOLT.
    gesamt += 1
    code, out = _lauf([_z("T1", A), _z("T2", A)])
    gut = code == 1 and re.search(r"ZEILE \S+ WIEDERHOLT;pos=2;art=WIEDERHOLUNG;", out)
    print(f"{'ok  ' if gut else 'FAIL'} Neusendung   -> WIEDERHOLT  exit={code}")
    ok += bool(gut)

    # 3. Das Vokabular hat vier Etiketten — und vier Verdicts moeglich.
    gesamt += 1
    _, out = _lauf([_z("T1", A), _z("T1", A), _z("T2", A), "KEIN JSON"])
    verdicts = {u for u in re.findall(r"ZEILE \S+ ([A-Z]+);", out)}
    gut = {"ZUSTELLEN", "VERWERFEN", "WIEDERHOLT", "UNGEPRUEFT"} <= verdicts
    print(f"{'ok  ' if gut else 'FAIL'} vier Etiketten -> vier Verdicts  {sorted(verdicts)}")
    ok += gut

    # 4. Kein WIEDERHOLT darf als VERWERFEN erscheinen (Auslassung).
    gesamt += 1
    # Nur ZEILE-Saetze zaehlen: seit R86 traegt auch DEDUP das Wort
    # WIEDERHOLT, und ein zaehlender Regex ueber beide Achsen sah 2
    # wo 1 gemeint war — der Befund der Runde, im Kleinen.
    n_w = len(re.findall(r"ZEILE \S+ WIEDERHOLT;", out))
    n_v = len(re.findall(r"ZEILE \S+ VERWERFEN;", out))
    gut = n_w == 1 and n_v == 1
    print(f"{'ok  ' if gut else 'FAIL'} keine Vermischung             "
          f"WIEDERHOLT={n_w} VERWERFEN={n_v}")
    ok += gut

    print(f"\n{ok}/{gesamt} ADJ-Slot-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
