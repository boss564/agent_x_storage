#!/usr/bin/env python3
"""Naht-Beweis: der Konsument handelt auf Kopien, die der Detektor nie sah.

§A-ZZZZ163 (Runde 87): **der Katalog war ein Schnappschuss; die Vorschrift
ist es nicht.**

Der Detektor misst S_T. Der Konsument haelt S_{T+Δ} — mehr oder weniger
Zeilen. Bisher (R86) brach jeder Unterschied die Zuordnung: `rang=n+1`
hatte keine Regel. Jetzt traegt die Regel keinen Rang mehr, sondern eine
Vorschrift:

    erst=ZUSTELLEN
    rest_art=zeitstempel
    bei_gleich=VERWERFEN
    bei_ungleich=WIEDERHOLT

Der Konsument wendet sie auf seinen eigenen Strom an. Dieser Test fuehrt
genau das aus: Regeln vom Detektor, Aktion auf einem Strom, den der
Detektor nie sah.

`gesehen=` steht daneben und wird bewusst NICHT benutzt — es ist
Telemetrie ueber die Messung, keine Autoritaet.
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


def _regeln(out: str) -> dict[str, dict[str, str]]:
    return {h: {"erst": e, "gleich": g, "ungleich": u}
            for h, e, g, u in re.findall(
                r"DEDUP (\S+);erst=([A-Z]+);rest_art=zeitstempel;"
                r"bei_gleich=([A-Z]+);bei_ungleich=([A-Z]+);", out)}


def konsumiere(strom: list[str], regeln: dict[str, dict[str, str]]) -> list[str]:
    import hashlib
    rang: dict[str, int] = {}
    ts: dict[str, str] = {}
    out: list[str] = []
    for zeile in strom:
        try:
            txt = json.loads(zeile)["message"]["content"]
        except (ValueError, KeyError, TypeError):
            out.append("UNGEPRUEFT")
            continue
        m = re.search(r"<timestamp>(.*?)</timestamp>", txt)
        jetzt = m.group(1) if m else "?"
        norm = " ".join(re.sub(r"<timestamp>.*?</timestamp>", "", txt).split())
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        rang[h] = rang.get(h, 0) + 1
        r = regeln.get(h)
        if r is None:
            out.append("KEINE-REGEL")
        elif rang[h] == 1:
            out.append(r["erst"])
        else:
            out.append(r["gleich"] if ts[h] == jetzt else r["ungleich"])
        ts[h] = jetzt
    return out


def main() -> int:
    ok = gesamt = 0
    regeln = _regeln(_lauf([_z("T1", A), _z("T1", A)]))   # Detektor sah 2

    # A: Konsument sieht DREI (dritte kam nach der Messung).
    gesamt += 1
    a = konsumiere([_z("T1", A), _z("T1", A), _z("T1", A)], regeln)
    gut = a == ["ZUSTELLEN", "VERWERFEN", "VERWERFEN"]
    print(f"{'ok  ' if gut else 'FAIL'} A  dritte Kopie               {a}")
    ok += gut

    # A': dritte Kopie mit ANDEREM Zeitstempel -> Wiederholung, nicht Duplikat.
    gesamt += 1
    a2 = konsumiere([_z("T1", A), _z("T1", A), _z("T9", A)], regeln)
    gut = a2 == ["ZUSTELLEN", "VERWERFEN", "WIEDERHOLT"]
    print(f"{'ok  ' if gut else 'FAIL'} A' Neusendung nach Messung     {a2}")
    ok += gut

    # B: Konsument sah die Klasse NIE -> Regel existiert trotzdem nicht
    #    (anderer Inhalt). Erwartet: KEINE-REGEL, laut, nicht still.
    gesamt += 1
    b = konsumiere([_z("T1", A), _z("T1", A), _z("T1", "B" * 500)], regeln)
    gut = b[-1] == "KEINE-REGEL"
    print(f"{'ok  ' if gut else 'FAIL'} B  unbekannte Klasse          {b[-1]}")
    ok += gut

    # C: Konsument sieht WENIGER (Detektor 3, Konsument 1) -> kein Riss.
    gesamt += 1
    regeln3 = _regeln(_lauf([_z("T1", A), _z("T1", A), _z("T1", A)]))
    c = konsumiere([_z("T1", A)], regeln3)
    gut = c == ["ZUSTELLEN"] and regeln3 == _regeln(_lauf([_z("T1", A)]))
    print(f"{'ok  ' if gut else 'FAIL'} C  weniger gesehen            {c}")
    ok += gut

    # D: `gesehen=` wird nicht konsultiert — der Test faelscht es.
    gesamt += 1
    gefaelscht = {h: dict(r, gesehen="999") for h, r in regeln.items()}
    d = konsumiere([_z("T1", A), _z("T1", A), _z("T1", A)], gefaelscht)
    gut = d == a
    print(f"{'ok  ' if gut else 'FAIL'} D  gesehen= ohne Wirkung      {d == a}")
    ok += gut

    print(f"\n{ok}/{gesamt} Naht-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
