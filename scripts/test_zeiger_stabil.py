#!/usr/bin/env python3
"""Zeiger-Stabilität: trifft `ZEILE <n>` die Zeile, die gemeint ist?

§A-ZZZZ145 (Runde 85): **ein Zeiger in ein bewegtes Ziel ist keine Identität.**

R84 machte aus Zählern Zeiger: `ZEILE 2 VERWERFEN`. Aber 2 ist eine
POSITION in einem Strom, und der Strom bewegt sich. Kommen zwischen
Messung und Handlung drei Meldungen vorne hinzu, ist `ZEILE 2` eine
andere Meldung — eine legitime wird verworfen, die zu verwerfende
zugestellt. Datenverlust und Blindheit in einem Zug.

Warum kein Fixture das sieht: Fixtures sind per Konstruktion
eingefroren. Dieses Skript simuliert Bewegung, indem es den Strom
zwischen zwei Läufen VERÄNDERT und prüft, ob das Urteil der gemeinten
Meldung folgt.

Zwei Vertragsformen sind zulässig (beide werden geprüft):

    inhaltlich   ZEILE <sha256> <urteil>   — Bewegung irrelevant
    positions    ZEILE <n> <urteil> + INPUT_SHA <hash>  — eingefroren

Fehlt beides, ist der Zeiger instabil und der Test rot.
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


def _verdicts(out: str) -> dict[str, str]:
    """Urteil je Zeiger. Schluessel ist, was der Zeiger traegt."""
    v: dict[str, str] = {}
    for zeiger, u in re.findall(r"ZEILE (\S+) ([A-Z]+)", out):
        v[zeiger] = u
    return v


def main() -> int:
    ok = 0
    gesamt = 0

    # Ausgangslage: A, A, B, B  -> A#2 und B#4 sind Duplikate.
    base = [_z("T1", A), _z("T1", A), _z("T2", B), _z("T2", B)]
    _, out1 = _lauf(base)
    v1 = _verdicts(out1)

    # Bewegung: drei Meldungen werden VORNE eingefuegt.
    bewegt = [_z("T9", C), _z("T8", "D" * 500), _z("T7", "E" * 500)] + base
    _, out2 = _lauf(bewegt)
    v2 = _verdicts(out2)

    # 1. Traegt der Zeiger Inhalt (Hash) oder Position?
    gesamt += 1
    inhaltlich = any(re.fullmatch(r"[0-9a-f]{12,64}", k) for k in v1)
    print(f"{'ok  ' if inhaltlich else 'FAIL'} Zeiger-Form             "
          f"{'inhaltlich (sha)' if inhaltlich else 'nur Position'}")
    ok += inhaltlich

    # 2. Folgt das Urteil der GEMEINTEN Meldung unter Bewegung?
    #    Der erste A-Block ist in base Position 2, in bewegt Position 5.
    gesamt += 1
    if inhaltlich:
        # Inhaltlicher Zeiger: derselbe Hash muss dasselbe Urteil tragen.
        gemeinsam = set(v1) & set(v2)
        stabil = all(v1[k] == v2[k] for k in gemeinsam)
        print(f"{'ok  ' if stabil else 'FAIL'} Urteil unter Bewegung   "
              f"{len(gemeinsam)} gemeinsame Zeiger, stabil={stabil}")
        ok += stabil
    else:
        # Positionszeiger: er MUSS als instabil erkannt werden, ausser
        # der Input ist eingefroren (INPUT_SHA in der Ausgabe).
        eingefroren = "INPUT_SHA" in out1
        print(f"{'ok  ' if eingefroren else 'FAIL'} Urteil unter Bewegung   "
              f"Position {'eingefroren (INPUT_SHA)' if eingefroren else 'STABIL BEHAUPTET, ABER BEWEGLICH'}")
        ok += eingefroren

    # 3. Der Beweis der Instabilitaet: dieselbe Position, anderes Urteil.
    gesamt += 1
    pos1 = {k: u for k, u in v1.items() if k.isdigit()}
    pos2 = {k: u for k, u in v2.items() if k.isdigit()}
    if pos1 and pos2:
        drift = [k for k in pos1 if k in pos2 and pos1[k] != pos2[k]]
        gut = bool(drift) and inhaltlich
        print(f"{'ok  ' if gut else 'FAIL'} Positions-Drift         "
              f"{len(drift)} Positionen wechseln das Urteil — "
              f"{'durch Inhalts-Zeiger kompensiert' if inhaltlich else 'NICHT kompensiert'}")
        ok += gut
    else:
        # Kein Positionszeiger mehr: die Drift ist strukturell unmoeglich.
        print("ok   Positions-Drift         entfaellt (kein Positionszeiger)")
        ok += 1

    print(f"\n{ok}/{gesamt} Zeiger-Stabilitaets-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
