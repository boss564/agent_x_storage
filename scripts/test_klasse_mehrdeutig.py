#!/usr/bin/env python3
"""Klassen-Identität: derselbe Hash, drei Urteile, keine physische Bindung.

§A-ZZZZ153 (Runde 86): **der Inhalts-Hash ist eine Klasse, keine Zeile.**

R85 ersetzte `ZEILE <n>` durch `ZEILE <sha>`. Aber das System existiert
genau für den Fall, in dem Inhalt sich wiederholt: Original, Duplikat,
Wiederholung — derselbe Hash. Der Konsument findet drei Datensätze mit
einem Schlüssel und drei einander widersprechenden Anweisungen.

Dieser Test misst die Mehrdeutigkeit direkt:

  1. Fixture Original + Duplikat + Wiederholung -> ein Hash, drei Urteile.
  2. Eine Zeile gleichen Inhalts VORNE einfuegen (Bewegung).
  3. Der Konsument muss die Verwerfen-Entscheidung an die richtige
     physische Zeile binden koennen.

Eine Aufloesung ist nur zulaessig, wenn der Zeiger je Zeile eindeutig
ist (Regel-Zeiger oder frozen-object-Hash). `pos=` ist KEINE Aufloesung
— es ist das Feld, das unter Bewegung driftet.

Exit 0 = mehrdeutig erkannt und als mehrdeutig AUSGEWIESEN (Vertrag
erlaubt es nur, wenn der Konsument die Regel kennt).
Exit 1 = mehrdeutig und stillschweigend auf pos= aufgeloest.
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


def _lauf(zeilen: list[str]) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "strom.jsonl"
        f.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=td)
        return r.returncode, r.stdout


def _saetze(out: str) -> list[tuple[str, str, str]]:
    """(zeiger, urteil, pos) je Zeilen-Satz."""
    return [(z, u, p) for z, u, p in
            re.findall(r"ZEILE (\S+) ([A-Z]+);pos=(\d+);", out)]


def main() -> int:
    ok = 0
    gesamt = 0
    base = [_z("T1", A), _z("T1", A), _z("T2", A)]
    code, out = _lauf(base)
    s = _saetze(out)

    # 1. Ein Hash, drei Urteile — das ist die Klasse.
    gesamt += 1
    hashes = {z for z, _, _ in s}
    urteile = {u for _, u, _ in s}
    gut = len(hashes) == 1 and len(urteile) == 3
    print(f"{'ok  ' if gut else 'FAIL'} ein Hash, drei Urteile     "
          f"{len(hashes)} Hash, {len(urteile)} Urteile")
    ok += gut

    # 2. Der Zeiger unterscheidet die Zeilen NICHT — der Hash ist gleich.
    gesamt += 1
    unterscheidbar = len(hashes) == len(s)
    gut = not unterscheidbar
    print(f"{'ok  ' if gut else 'FAIL'} Zeiger trennt Zeilen?      "
          f"{'ja' if unterscheidbar else 'NEIN — Klasse, nicht Zeile (erwartet)'}")
    ok += gut

    # 3. Bewegung: gleiche Meldung vorne -> pos-Verschiebung.
    be = [_z("T0", A)] + base
    _, out2 = _lauf(be)
    s2 = _saetze(out2)
    gesamt += 1
    # Bewegung AENDERT DIE ZEILENMENGE (hier 3 -> 4), nicht nur die
    # Indizes. Ein zip ueber beide Listen verglich dann Zeile 3 von drei
    # mit Zeile 3 von vier und sah nichts. Gemessen wird der echte
    # Befund: die Aktion an einer festen pos= wechselt.
    mpa = {p: u for u, p in re.findall(r"ZEILE \S+ ([A-Z]+);pos=(\d+);", out)}
    mpb = {p: u for u, p in re.findall(r"ZEILE \S+ ([A-Z]+);pos=(\d+);", out2)}
    drift = sorted((p, mpa[p], mpb[p]) for p in mpa if p in mpb and mpa[p] != mpb[p])
    gut = bool(drift)
    print(f"{'ok  ' if gut else 'FAIL'} pos driftet unter Bewegung "
          f"{len(drift)} von {len(mpa)} Positionen: {drift[:2]}")
    ok += gut

    # 4. Der eigentliche Befund: gibt es eine zeilen-eindeutige Loesung?
    #    Zulaessig: ein Regel-Zeiger (z.B. eine Dedup-Regel samt
    #    Vorkommens-Rang) ODER ein frozen-object-Hash. Verboten: alles,
    #    was ueber pos= aufgeloest werden muss.
    gesamt += 1
    # §A-ZZZZ161: die Aufloesung ist jetzt eine VORSCHRIFT je Klasse
    # (erst/rest_art), nicht eine Rang-Tabelle. `rang=` war der
    # Schnappschuss und ist entfallen.
    regel_zeiger = re.search(
        r"DEDUP \S+;erst=\S+;rest_art=zeitstempel;bei_gleich=\S+;"
        r"bei_ungleich=\S+;", out) is not None
    frozen = re.search(r"INPUT_SHA=|objekt=", out) is not None
    aufgeloest = regel_zeiger or frozen
    gut = aufgeloest
    print(f"{'ok  ' if gut else 'FAIL'} Mehrdeutigkeit aufgeloest   "
          f"regel={bool(regel_zeiger)} frozen={bool(frozen)}")
    ok += gut

    print(f"\n{ok}/{gesamt} Klassen-Mehrdeutigkeits-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
