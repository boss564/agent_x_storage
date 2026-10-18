#!/usr/bin/env python3
"""Der Ledger ist die einzige Versionswahrheit.

§A-ZZZZ192 (Runde 90 Befund 7, vierte Wiederholung): R87 nannte v7,
R89 nannte v9 — v8 stand im Ledger, wurde aber nie in der Prosa genannt.
Die Prosa hat die Version GETIPPT statt GELESEN. Der Befund ist damit
nicht geloest, sondern viermal wiederholt.

Dieser Test prueft drei Dinge, die das kuenftig verhindern:
  1. `_version` == hoechste AKZEPTIERTE Ledger-Version (nicht getippt)
  2. keine Luecke in 1.._version (jedes akzeptierte v hat einen Eintrag)
  3. `kopfzeile.py` liest `_version`, es tippt sie nicht
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"


def akzeptiert(ledger: list[dict]) -> list[int]:
    out = []
    for e in ledger:
        v = e.get("version")
        if isinstance(v, int):
            out.append(v)
    return sorted(out)


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    vs = akzeptiert(d["versions_ledger"])

    # 1. _version ist abgeleitet, nicht getippt.
    gesamt += 1
    gut = d["_version"] == max(vs)
    print(f"{'ok  ' if gut else 'FAIL'} _version == max(Ledger)     "
          f"{d['_version']} == {max(vs)}")
    ok += gut

    # 2. Keine Luecke: 1..n lueckenlos.
    gesamt += 1
    fehlend = [v for v in range(1, max(vs) + 1) if v not in vs]
    gut = not fehlend
    print(f"{'ok  ' if gut else 'FAIL'} Kontiguitaet 1..{max(vs):<12}    "
          f"fehlend={fehlend}")
    ok += gut

    # 3. Verworfenen Eintraege zaehlen NICHT fuer die Kontiguitaet —
    #    sonst maskiert ein '-verworfen' eine echte Luecke.
    gesamt += 1
    verw = [e["version"] for e in d["versions_ledger"]
            if not isinstance(e.get("version"), int)]
    gut = len(verw) >= 1
    print(f"{'ok  ' if gut else 'FAIL'} Verworfene separat           "
          f"{len(verw)} nicht-numerisch")
    ok += gut

    # 4. Die Doktrin ist im Vertrag deklariert.
    gesamt += 1
    dok = d.get("version_doktrin", {})
    gut = bool(dok.get("regel")) and bool(dok.get("pruefbar"))
    print(f"{'ok  ' if gut else 'FAIL'} Doktrin deklariert          "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 5. kopfzeile.py liest `_version`, statt eine Zahl zu enthalten.
    gesamt += 1
    kopf = (SCRIPTS / "kopfzeile.py").read_text(encoding="utf-8")
    liest = "d['_version']" in kopf or 'd["_version"]' in kopf
    getippt = re.search(r"Version: v\d", kopf) is not None
    gut = liest and not getippt
    print(f"{'ok  ' if gut else 'FAIL'} kopfzeile liest statt tippt "
          f"liest={liest} getippt={getippt}")
    ok += gut

    # 6. Jeder Ledger-Eintrag traegt Runde + Aenderung (kein nackter Stand).
    gesamt += 1
    nackt = [e.get("version") for e in d["versions_ledger"]
             if isinstance(e.get("version"), int)
             and not (e.get("runde") and e.get("aenderung"))]
    gut = not nackt
    print(f"{'ok  ' if gut else 'FAIL'} Eintraege vollstaendig      "
          f"nackt={nackt}")
    ok += gut

    print(f"\n{ok}/{gesamt} Versions-Ledger-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
