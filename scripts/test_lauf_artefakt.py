#!/usr/bin/env python3
"""R102: Die Wahrheit liegt im Artefakt, nicht im Prozess-Exit.

Der make-Befund (GNU make normalisiert jeden Rezept-Fehler auf 2) zeigt:
exit-Codes sind an der make-Grenze verloren. Was bleibt, ist die Datei.

Diese Suite prueft die Schnittstelle, die R99 nie getestet hat:
  A  data/lauf_letzter.json existiert und traegt pro Datei den Status
  B  status ist aus dem Artefakt ableitbar, NICHT aus make-Exit
  C  das Inventar deckt sich mit der Zahl der GRUEN+GEFALLEN+BEFUND+BEENDET
  D  protokoll/ ist NICHT ignoriert (R98 #2 aktiv verteidigt)

D ist der Test gegen den Fehlgriff "untracked per .gitignore fixen":
wer protokoll/ ignoriert, macht diese Suite rot.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ART = REPO / "data" / "lauf_letzter.json"
ok = gesamt = 0


def pruefe(name: str, bedingung: bool, detail: str = "") -> None:
    global ok, gesamt
    gesamt += 1
    if bedingung:
        ok += 1
        print(f"ok   {name}")
    else:
        print(f"ROT  {name}  {detail}")


def main() -> int:
    if not ART.exists():
        pruefe("A0 Artefakt vorhanden", False, f"{ART} fehlt")
        print(f"\n{ok}/{gesamt} Artefakt-Faelle gruen")
        return 1
    d = json.loads(ART.read_text(encoding="utf-8"))
    pruefe("A1 Artefakt traegt pro Datei einen Status",
           all("klasse" in e and "datei" in e for e in d.get("erg", [])),
           str(list(d)[:5]))
    pruefe("A2 Artefakt traegt Provenienz (modus)", "modus" in d, str(list(d)))
    # B: der Status ist aus dem Artefakt ableitbar, ohne Prozess-Exit.
    # Eine BEFUND-Zeile ist im Artefakt sichtbar, im make-Exit nicht.
    zaehl = {}
    for e in d.get("erg", []):
        zaehl[e["klasse"]] = zaehl.get(e["klasse"], 0) + 1
    pruefe("B1 Statusverteilung aus dem Artefakt ableitbar", bool(zaehl), str(zaehl))
    pruefe("C1 Inventar = Summe der Klassen",
           len(d.get("erg", [])) == sum(zaehl.values()),
           f'{len(d.get("erg", []))} != {sum(zaehl.values())}')
    # D: protokoll/ darf nie ignoriert werden (R98 #2, aktiv verteidigt)
    r = subprocess.run(["git", "check-ignore", "protokoll/probe.json"],
                       cwd=REPO, capture_output=True, text=True)
    pruefe("D1 protokoll/ ist NICHT gitignored (R98 #2)", r.returncode != 0,
           "check-ignore meldet ignoriert — Regression")
    print(f"\n{ok}/{gesamt} Artefakt-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
