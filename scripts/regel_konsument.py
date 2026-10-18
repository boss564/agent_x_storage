#!/usr/bin/env python3
"""Ein Konsument, der DEDUP-REGELN exekutiert — nicht Positionen.

§A-ZZZZ155 (Runde 86): **der Beweis, den nur ein Regel-Konsument führen
kann.** R85 band die Handlung an `pos=`. Dieser Konsument liest die
Regeln und zählt den Rang **auf seinem eigenen Strom** — er kennt die
Detektor-Positionen nicht. Genau deshalb ist Bewegung irrelevant: die
Entscheidung hängt am Inhalt und am lokalen Rang, nicht an einem Index,
der beim Detektor galt.

Auch dieser Konsument ist ein Fixture-Konsument (kein ING-Ersatz) — aber
er ist der erste, der ohne `pos=` handeln kann.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import subprocess
from pathlib import Path

W = Path(__file__).resolve().parent / "einwurf_waechter.py"


def _z(ts: str, txt: str) -> str:
    return json.dumps({"role": "user", "message": {
        "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
        ensure_ascii=False)


def _regeln(out: str) -> dict[tuple[str, int], str]:
    return {(h, int(r)): a for h, r, a in
            re.findall(r"DEDUP (\S+);rang=(\d+);art=\S+;aktion=([A-Z]+);", out)}


def _lauf(zeilen: list[str]) -> str:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "strom.jsonl"
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=td)
        return r.stdout


def konsumiere(strom: list[str], regeln: dict[tuple[str, int], str]) -> list[str]:
    """Ordnet jeder ÄUSSEREN Zeile die Aktion zu — per lokalem Rang.

    Der lokale Rang wird auf dem Strom gezählt, den der Konsument selbst
    hält. Vorangestellte Meldungen verschieben den Index, aber nicht
    den Rang einer Zeile *innerhalb ihrer Klasse*.
    """
    import hashlib
    rang: dict[str, int] = {}
    aktionen: list[str] = []
    for zeile in strom:
        try:
            txt = json.loads(zeile)["message"]["content"]
        except (ValueError, KeyError, TypeError):
            aktionen.append("UNGEPRUEFT")
            continue
        norm = re.sub(r"<timestamp>.*?</timestamp>", "", txt)
        norm = " ".join(norm.split())
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        rang[h] = rang.get(h, 0) + 1
        aktionen.append(regeln.get((h, rang[h]), "KEINE-REGEL"))
    return aktionen


def main() -> int:
    A = "A" * 500
    B = "B" * 500
    ok = 0
    gesamt = 0

    # Bewegung = neue MELDUNGEN, die dieselben Klassen in anderer
    # Reihenfolge/Anzahl tragen. `T0=B` allein waere falsch: B kommt
    # dann im shift-Strom zweimal vor, A dreimal — die Klassen sind
    # nicht mehr dieselben, und der Test prueft dann nicht Bewegung,
    # sondern einen anderen Strom. Genau diese Verwechslung hat der
    # erste Entwurf gemacht.
    base = [_z("T1", A), _z("T1", A), _z("T2", A), _z("T3", B)]
    shift = [_z("T0", B), _z("T9", A), _z("T8", B)] + base

    r_base = _regeln(_lauf(base))
    r_shift = _regeln(_lauf(shift))

    # 1. Die Regelmenge ist unter Bewegung NICHT identisch — und das ist
    #    korrekt: ein anderer Strom hat andere Klassen/Anzahlen. Der
    #    Test prueft daher nicht Gleichheit der Mengen, sondern die
    #    Eigenschaft, auf der alles beruht: **die Aktion einer Meldung
    #    haengt nur an (Inhalt, lokaler Rang) — nie an pos=.** Die
    #    fruehere Form `r_base == r_shift` war falsch UND hat einen
    #    zweiten Fehler verdeckt: sie haette Gleichheit verlangt, wo
    #    ein anderer Strom andere Regeln haben muss.
    gesamt += 1
    gut = bool(r_base) and bool(r_shift)
    print(f"{'ok  ' if gut else 'FAIL'} Regeln je Strom vorhanden    "
          f"base={len(r_base)} shift={len(r_shift)} (Mengen duerfen "
          f"abweichen, weil der Strom abweicht)")
    ok += gut

    # 2. Der INVARIANTE Kern: Rang 1 jeder Klasse ist ZUSTELLEN, jeder
    #    hoehere Rang ist nie ZUSTELLEN. Das gilt in JEDEM Strom, weil
    #    es eine Regel ueber Raenge ist, keine Aussage ueber Positionen.
    gesamt += 1
    def _rang1_zustellbar(regeln):
        return all(regeln[(h, 1)] == "ZUSTELLEN" for h, _ in regeln)
    def _kein_rang_gt1_zustellbar(regeln):
        return all(a != "ZUSTELLEN" for (h, r), a in regeln.items() if r > 1)
    gut = (_rang1_zustellbar(r_base) and _rang1_zustellbar(r_shift)
           and _kein_rang_gt1_zustellbar(r_base)
           and _kein_rang_gt1_zustellbar(r_shift))
    print(f"{'ok  ' if gut else 'FAIL'} Rang-Invariante              "
          f"rang1=ZUSTELLEN in beiden, rang>1 nie ZUSTELLEN")
    ok += gut

    # 3. Die Klassenaktion ist inhaltlich richtig.
    gesamt += 1
    a_base = konsumiere(base, r_base)
    soll = ["ZUSTELLEN", "VERWERFEN", "WIEDERHOLT", "ZUSTELLEN"]
    gut = a_base == soll
    print(f"{'ok  ' if gut else 'FAIL'} Klassenaktion korrekt        {a_base}")
    ok += gut

    # 4. Keine Position ist noetig: die Regeln tragen kein pos=.
    gesamt += 1
    out = _lauf(base)
    dedup_ohne_pos = not re.search(r"DEDUP [^;]+;[^;]*pos=", out)
    gut = dedup_ohne_pos and bool(r_base)
    print(f"{'ok  ' if gut else 'FAIL'} Regeln ohne Position        pos im DEDUP={not dedup_ohne_pos}")
    ok += gut

    print(f"\n{ok}/{gesamt} Regel-Konsumenten-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
