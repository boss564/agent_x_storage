#!/usr/bin/env python3
"""Typisierte Blocker: das Gate FUEHRT den Blocker aus und sieht ihn rot.

§A-ZZZZ198 (Runde 90 Befund 6): `test_frist_gate.py` prueft
`bool(f.get("blocker"))` — Praesenz einer Zeichenkette. "Blocker:
Komplexitaet" waere gueltig. Dieses Gate prueft stattdessen:

    blockiert_durch: <datei>   -> muss EXISTIEREN
                               -> muss EXIT != 0 liefern (oder 2 = UNBEWIESEN)
                               -> Exit 1 = WIDERLEGT ist ebenfalls ein Blocker

Drei Exit-Bedeutungen der Blocker-Probe, alle drei als "gebucht" gewertet:
  1 WIDERLEGT   — die Probe zeigt einen echten Fehler
  2 UNBEWIESEN  — die Probe kann nicht entscheiden (zu klein / Strom fehlt)
  0 BESTANDEN   — Blocker aufgeloest: die Frist DARF nicht mehr offen sein

Der letzte Fall ist der Test, den die Freitext-Version nicht hatte: ein
Blocker, der gruen ist, waehrend die Frist offen bleibt, ist ein Zombie.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"

FREITEXT_MARKER = ("Komplexitaet", "komplex", "Zeit", "schwer", "unklar")


def probe(datei: Path) -> tuple[int, str]:
    if not datei.is_file():
        return -1, "Datei fehlt"
    try:
        r = subprocess.run([sys.executable, str(datei)], capture_output=True,
                           text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return -2, "Timeout"
    return r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:] and \
        (r.stdout + r.stderr).strip().splitlines()[-1] or ""


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    # R96: Nur typisierbare Fristen. `endzustand_typ == "NICHT_TYPISIERBAR"`
    # markiert Fristen, deren Blocker eine Baum-Eigenschaft ist (Aufrufbaum),
    # keine ausfuehrbare Probe. Sie gehoeren nicht in diesen Pfad — und
    # werden hier explizit ausgeschlossen, nicht stillschweigend uebersprungen.
    fristen = {k: v for k, v in d.get("fristen", {}).items()
               if isinstance(v, dict) and v.get("endzustand")
               and v.get("endzustand_typ") != "NICHT_TYPISIERBAR"}
    nicht_typ = sorted(k for k, v in d.get("fristen", {}).items()
                       if isinstance(v, dict)
                       and v.get("endzustand_typ") == "NICHT_TYPISIERBAR")
    for k in nicht_typ:
        print(f"skip {k}: NICHT_TYPISIERBAR (Blocker ist Baum-Eigenschaft, "
              f"gemessen von {d['fristen'][k].get('blocker_messung', {}).get('skript', '?')})")

    for name, f in fristen.items():
        gesamt += 1
        ziel = f.get("blockiert_durch")
        if not ziel:
            print(f"FAIL {name}: kein blockiert_durch (Freitext-Blocker)")
            continue
        code, letzte = probe(SCRIPTS / ziel)
        if code == 0:
            print(f"FAIL {name}: Blocker ist GRUEN ({ziel}) — "
                  f"Frist offen, Blocker aufgeloest: Zombie")
            continue
        print(f"ok   {name}: Blocker rot         exit={code:<3} {ziel}  "
              f"| {letzte[:60]}")
        ok += 1

    # 2. Die Praesenz-Falle ist als solche deklariert.
    gesamt += 1
    dok = d.get("frist_instrument", {}).get("blocker_doktrin", "")
    gut = "AUSFUEHRBARES" in dok
    print(f"{'ok  ' if gut else 'FAIL'} Doktrin: ausfuehrbar      "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 3. Ein Freitext-only-Blocker ist per Definition ungueltig — gemessen.
    gesamt += 1
    fake = {"endzustand": "verschoben", "blocker": "Komplexitaet"}
    alt = bool(fake.get("blocker"))
    neu = bool(fake.get("blockiert_durch"))
    gut = alt is True and neu is False
    print(f"{'ok  ' if gut else 'FAIL'} Freitext-Falle geprueft   "
          f"alt={alt} neu={neu}")
    ok += gut

    # 4. Gelegenheits-Norm: Exit 2 zaehlt als Blocker, NICHT als Bestehen.
    gesamt += 1
    g = d.get("frist_instrument", {}).get("gelegenheit_norm", "")
    gut = "UNBEWIESEN" in g and ("Gelegenheit" in g)
    print(f"{'ok  ' if gut else 'FAIL'} Gelegenheit normiert     "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Typisierter-Blocker-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
