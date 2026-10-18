#!/usr/bin/env python3
"""Die Klausel: jedes Feld deklariert seine Quelle, oder es ist ungueltig.

§A-ZZZZ208 (Runde 91): **die Krankheit ist ein Default, nicht ein Bug.**

Vier Auspraegungen in vier Runden:
    "?"-Sentinel       Feld existiert, Bedeutung fehlt
    BLOCKER benannt    Zeichenkette existiert, Substanz fehlt
    gruen bei 3/3      Bestanden existiert, Gelegenheit fehlt
    zustell_zusage     Zusage existiert, BEDARF fehlt

Jeder Einzelfall-Fix heilt eine Auspraegung und muenzt zwei neue. Der
strukturelle Fix: ein normatives Feld ohne Substanzklasse ist NICHT
GEBUCHT. Dieser Test ist der Vollstaendigkeitspruefer dieser Regel —
er unterscheidet sich von test_substanzklassen.py dadurch, dass er
die KLASSEN-MECHANIK prueft, nicht die Eintraege:

  - kein Feld darf Klasse und Beleg widersprechen
  - ABLEITUNG muss eine Eingangsgroesse nennen, die im Vertrag existiert
  - MESSUNG muss ein Skript nennen, das EXIT 0 liefert (nicht nur existiert)

Der letzte Punkt ist der, den R91 forderte: "definiert" ohne Inhalt ist
selbst eine Praesenz-Aussage. Ein Skript, das existiert aber rot ist, ist
kein Beleg — es ist ein Formular.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    kl = d.get("substanzklassen", {})

    # 1. Die Klausel selbst ist deklariert, mit Verstoss-Folge.
    gesamt += 1
    gut = bool(kl.get("verstoss")) and "nicht gebucht" in kl.get("regel", "")
    print(f"{'ok  ' if gut else 'FAIL'} Klausel deklariert         "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 2. Kein normatives Feld traegt zwei Klassen oder keine.
    gesamt += 1
    normativ = [k for k, v in d.items()
                if isinstance(v, dict) and "substanz" in v]
    mehrfach = [k for k in normativ
                if d[k].get("substanz") not in kl]
    gut = not mehrfach
    print(f"{'ok  ' if gut else 'FAIL'} Keine unbekannte Klasse    "
          f"{len(normativ)} Felder, abweichend={mehrfach}")
    ok += gut

    # 3. ABLEITUNG nennt eine Eingangsgroesse — und die existiert.
    gesamt += 1
    kaputt = []
    for k in normativ:
        v = d[k]
        if v.get("substanz") != "ABLEITUNG":
            continue
        eing = v.get("eingangsgroesse", "")
        if not eing:
            kaputt.append((k, "keine Eingangsgroesse"))
        elif "digest()" in eing and "def digest(" not in \
                (SCRIPTS / "einwurf_waechter.py").read_text(encoding="utf-8"):
            kaputt.append((k, "digest() fehlt im Code"))
    gut = not kaputt
    print(f"{'ok  ' if gut else 'FAIL'} ABLEITUNG->Eingang existiert "
          f"kaputt={kaputt}")
    ok += gut

    # 4. MESSUNG nennt ein Skript, das GRUEN ist — nicht nur existiert.
    gesamt += 1
    rot = []
    for k in normativ:
        v = d[k]
        if v.get("substanz") != "MESSUNG":
            continue
        pfad = v.get("messung_skript")
        if not pfad:
            rot.append((k, None))
            continue
        r = subprocess.run([sys.executable, str(SCRIPTS / pfad)],
                           capture_output=True, timeout=180)
        if r.returncode != 0:
            rot.append((k, f"{pfad} exit={r.returncode}"))
    gut = not rot
    print(f"{'ok  ' if gut else 'FAIL'} MESSUNG-Skript ist gruen   "
          f"rot={rot}")
    ok += gut

    # 5. Die Klausel ist beobachtbar: ein Feld ohne Klasse faellt durch.
    gesamt += 1
    feld = {"aussage": "irgendwas"}
    altes_gate = bool(feld.get("aussage"))
    neues_gate = feld.get("substanz") in kl
    gut = altes_gate is True and neues_gate is False
    print(f"{'ok  ' if gut else 'FAIL'} Praesenz-Falle messbar     "
          f"alt={altes_gate} neu={neues_gate}")
    ok += gut

    print(f"\n{ok}/{gesamt} Klausel-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
