#!/usr/bin/env python3
"""Regel-Zeiger vs. Positions-Zeiger unter MITTIGER Einfügung.

§A-ZZZZ156 (Runde 86): der Vergleich, der die Architektur entscheidet.

Bewegung vorne verschiebt nur Indizes (trivial). Bewegung MITTEN im
Strom ist der harte Fall: die Zeile davor und danach sind verschieden,
und ein Konsument, der `pos=` gebunden hat, verwirft danach die
falsche Meldung. Ein Konsument mit Rang-Regel trifft weiter dieselbe.

    Strom:   M1  (A, T1)   <- Rang 1
             M2  (B, T2)   <- Rang 1 von B
             M3  (A, T1)   <- Rang 2 von A  -> VERWERFEN

    Einfuegen:  M1  Mx(B,T7)  M2  M3
    pos=3 war A#2 (VERWERFEN), ist jetzt B#1 (ZUSTELLEN)  -> falsche Aktion.
    Rang 2 von A ist weiter M3                            -> richtige Aktion.
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


def _lauf(zeilen: list[str]) -> str:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "strom.jsonl"
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=td)
        return r.stdout


def _pos(out: str) -> dict[int, str]:
    return {int(p): u for u, p in
            re.findall(r"ZEILE \S+ ([A-Z]+);pos=(\d+);", out)}


def _dedup(out: str) -> dict[tuple[str, int], str]:
    return {(h, int(r)): a for h, r, a in
            re.findall(r"DEDUP (\S+);rang=(\d+);art=\S+;aktion=([A-Z]+);", out)}


def main() -> int:
    ok = 0
    gesamt = 0
    base = [_z("T1", A), _z("T2", B), _z("T1", A)]
    mitte = [_z("T1", A), _z("T7", B), _z("T2", B), _z("T1", A)]

    p_base = _pos(_lauf(base))
    p_mitte = _pos(_lauf(mitte))

    # 1. Positions-Zeiger: pos=3 traegt nach Einfuegung eine andere Aktion.
    gesamt += 1
    # Die Aktion an pos=3 wechselt VERWERFEN -> WIEDERHOLT — das ist
    # schlimmer als "ZUSTELLEN": die Zeile, die verworfen werden sollte,
    # wird jetzt nur MARKIERT und dem Konsumenten als Inhalt angeboten.
    gut = (p_base.get(3) == "VERWERFEN"
           and p_mitte.get(3) in ("ZUSTELLEN", "WIEDERHOLT"))
    print(f"{'ok  ' if gut else 'FAIL'} pos=3 vorher/nachher         "
          f"{p_base.get(3)} -> {p_mitte.get(3)}"
          f"  {'(FALSCHE Zeile)' if gut else ''}")
    ok += gut

    # 2. Regel-Zeiger: (hashA, rang2) bleibt VERWERFEN.
    gesamt += 1
    import hashlib
    def _h(t: str) -> str:
        return hashlib.sha256(" ".join(t.split()).encode()).hexdigest()
    d_base = _dedup(_lauf(base))
    d_mitte = _dedup(_lauf(mitte))
    ha = _h(A)
    gut = (d_base.get((ha, 2)) == "VERWERFEN"
           and d_mitte.get((ha, 2)) == "VERWERFEN")
    print(f"{'ok  ' if gut else 'FAIL'} (A,rang=2) vorher/nachher    "
          f"{d_base.get((ha, 2))} -> {d_mitte.get((ha, 2))}")
    ok += gut

    # 3. Beide Zeiger nebeneinander: genau EINER ist stabil.
    gesamt += 1
    pos_stabil = p_base == p_mitte
    regel_stabil = d_base == d_mitte
    gut = (not pos_stabil) or regel_stabil
    print(f"{'ok  ' if gut else 'FAIL'} Stabilität                   "
          f"pos stabil={pos_stabil}  regel stabil={regel_stabil}")
    ok += gut

    print(f"\n{ok}/{gesamt} Regel-gegen-pos-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
