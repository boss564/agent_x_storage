#!/usr/bin/env python3
"""Per-Code-stdout: der Bericht muss auf stdout SAGEN, was er bedeutet.

§A-ZZZZ205 (Runde 91 Befund 4): **"stdout ist immer definiert" ist selbst
eine Praesenz-ohne-Inhalt-Aussage — definiert, aber nicht spezifiziert.**

R90 normierte `stdout_ist_bericht=true` fuer alle Codes. Das kassiert
rueckwirkend die R88-Diagnose: wenn stdout immer der Bericht ist, dann
war ein LEERER stdout bei Exit 3 kein Lese-Fehler des Tests, sondern
ein EMITTIER-Fehler des Waechers. R88 fixte den relativen Pfad
(Harness); der Vertrag sagt bis heute nicht, WAS Exit 3 liefern muss.

Gemessen in R91 vor diesem Test:
    exit=3  stdout='Paare=0;KANAL-DUPLIKAT=0;...'
            stderr='DIE WACHE TRAEGT NICHT: Stream nicht lesbar: ...'

Ein Konsument, der nur stdout liest (weil der Vertrag es erlaubt),
sieht `Paare=0` und meldet "keine Ereignisse". Die Fehlerbeschreibung
steht auf stderr — dort, wo laut Vertrag niemand liest.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
W = SCRIPTS / "einwurf_waechter.py"
V = SCRIPTS / "waechter_vertrag.json"


def lauf(*args: str) -> tuple[int, str, str]:
    r = subprocess.run([sys.executable, str(W), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    tax = d["exit_taxonomie"]["je_code"]

    with tempfile.TemporaryDirectory() as td:
        fehlt = Path(td) / "gibt_es_nicht.jsonl"

        # 1. Exit 3 bei fehlendem Strom — und stdout traegt die Ursache.
        gesamt += 1
        code, out, err = lauf("--strom", str(fehlt))
        traegt = "UNLESBAR" in out.upper() or "NICHT LESBAR" in out.upper()
        gut = code == 3 and traegt
        print(f"{'ok  ' if gut else 'FAIL'} Exit 3 stdout nennt Ursache "
              f"exit={code} stdout_traegt={traegt}")
        ok += gut

        # 2. Der Bericht ist NICHT still: eine Achse aus lauter Nullen
        #    bei Exit 3 ist die Falle, die R88 schon einmal gestellt hat.
        gesamt += 1
        still = ("Paare=0" in out and "UNLESBAR" not in out.upper())
        gut = not still
        print(f"{'ok  ' if gut else 'FAIL'} Exit 3 nicht still         "
              f"still={still}")
        ok += gut

    # 3. Fuer JEDEN Code ist nicht nur "definiert", sondern der INHALT
    #    deklariert: mindestens ein Pflicht-Feld.
    gesamt += 1
    ohne = [c for c, v in tax.items() if not v.get("stdout_pflicht")]
    gut = not ohne
    print(f"{'ok  ' if gut else 'FAIL'} Per-Code-Inhalt deklariert   "
          f"ohne={ohne}")
    ok += gut

    # 4. Exit 3 verlangt ausdruecklich eine Fehlerbeschreibung.
    gesamt += 1
    p3 = tax.get("3", {}).get("stdout_pflicht", "")
    gut = "UNLESBAR" in p3.upper()
    print(f"{'ok  ' if gut else 'FAIL'} Exit 3 fordert Fehlertext   "
          f"{p3[:50]!r}")
    ok += gut

    # 5. Die R88-Falle kehrt nicht zurueck: ein Konsument, der stdout
    #    liest, darf bei Exit 3 NICHT "keine Ereignisse" schliessen.
    gesamt += 1
    konsument_sieht_ereignisse = ("Paare=0" in out and not traegt)
    gut = not konsument_sieht_ereignisse
    print(f"{'ok  ' if gut else 'FAIL'} R88-Falle geschlossen      "
          f"False-Positiv={konsument_sieht_ereignisse}")
    ok += gut

    print(f"\n{ok}/{gesamt} Per-Code-stdout-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
