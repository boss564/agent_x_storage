#!/usr/bin/env python3
"""Konformitaet: die Ausgabe muss gegen den VERTRAG passen, nicht gegen
die eigene Tokenisierung.

§A-ZZZZ141 (Runde 84): **Code, Mock und Vertrag stimmten ueberein, weil
Code und Mock denselben Parser-Fehler teilten.**

Der Befund der Runde 83: `KANAL-DUPLIKAT` enthaelt einen Bindestrich,
der Parser-Regex `[A-Za-z_]+` zerlegte ihn in `DUPLIKAT`. Alle
Konsumenten-Tests liefen gruen, waehrend der vertragliche Schluessel
NIE gelesen wurde. Kein Test schlug den Schluessel im Vertrag nach.

Dieser Test liest die Schluessel aus `waechter_vertrag.json` (die
Grammatik), sucht sie WOERTLICH in der Ausgabe und prueft die
Zeichenklasse der Schluessel. Ein Bindestrich-Schluessel mit einem
Parser ohne Bindestrich wird hier rot — bevor ein Konsument ihn
verfehlt.

Die Grammatik steht im Vertrag, nicht im Test. Aendert sich die
Grammatik, aendert sich der Test von selbst.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parent / "einwurf_waechter.py"
V = Path(__file__).resolve().parent / "waechter_vertrag.json"
A = "A" * 500
B = "B" * 500


def _z(ts: str, txt: str) -> str:
    return json.dumps({"role": "user", "message": {
        "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
        ensure_ascii=False)


def main() -> int:
    ok = 0
    gesamt = 0
    v = json.loads(V.read_text(encoding="utf-8"))
    gram = v.get("ausgabe_grammatik", {})
    schluessel_muster = gram.get("schluessel_zeichen", "[A-Za-z_][A-Za-z0-9_-]*")
    erlaubte = [k for k in gram.get("messachse", [])]

    # Ein Strom mit allen Urteilen, damit jede Marke vorkommt.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        f = d / "strom.jsonl"
        f.write_text("\n".join([_z("T1", A), _z("T1", A), _z("T2", B),
                                "KEIN JSON"]) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=d)
        out = r.stdout

    # 1. Die Grammatik erlaubt den Bindestrich.
    gesamt += 1
    bindestrich_ok = "-" in schluessel_muster
    print(f"{'ok  ' if bindestrich_ok else 'FAIL'} Grammatik Bindestrich   "
          f"{schluessel_muster!r}")
    ok += bindestrich_ok

    # 2. Jeder Vertrags-Schluessel steht WOERTLICH in der Ausgabe.
    for k in erlaubte:
        gesamt += 1
        # Wortgrenze per Grammatik, nicht per Bauchgefuehl.
        treffer = re.search(rf"(?:^|;){re.escape(k)}=", out)
        gut = treffer is not None
        print(f"{'ok  ' if gut else 'FAIL'} Vertrags-Schluessel      "
              f"{k} {'gefunden' if gut else 'FEHLT WOERTLICH'}")
        ok += gut

    # 3. Jeder Schluessel in der Ausgabe passt zur Grammatik.
    gesamt += 1
    # Prosa-Zeilen (Praefix "#") sind ausgenommen — sie sind Praesentation.
    messzeilen = [z for z in out.splitlines() if not z.lstrip().startswith("#")]
    ist_schluessel = re.findall(r"(?:^|;)([^=;]+)=", "\n".join(messzeilen))
    verstoesse = [s for s in ist_schluessel
                  if not re.fullmatch(schluessel_muster, s)]
    gut = not verstoesse
    print(f"{'ok  ' if gut else 'FAIL'} Ausgabe-Grammatik        "
          f"{len(ist_schluessel)} Schluessel, {len(verstoesse)} Verstoesse"
          + (f" {verstoesse}" if verstoesse else ""))
    ok += gut

    # 4. Zeilen-Marken mit gueltiger Position.
    gesamt += 1
    zeilen = re.findall(r"ZEILE (\d+) ([A-Z]+)", out)
    gut = bool(zeilen) and all(int(n) >= 1 for n, _ in zeilen)
    print(f"{'ok  ' if gut else 'FAIL'} Zeilen-Marken            "
          f"{len(zeilen)} Marken, Positionen >= 1")
    ok += gut

    print(f"\n{ok}/{gesamt} Konformitaets-Pruefungen gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
