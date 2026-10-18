#!/usr/bin/env python3
"""Kopfzeile: offene Posten statt grüner Suiten.

§A-ZZZZ178 (Runde 88): **„23 Suiten, 0 Befunde" verwischt zwei Groessen.**

Gruene Suite = die Tests, die ich gebaut habe, laufen. Offene Posten =
was der Vertrag noch nicht leistet. R87 meldete die erste Groesse und
liess die zweite aus der Kopfzeile — und die schwersten Funde (12->10,
falscher erster Anlauf) kamen NICHT von der Suite.

Diese Kopfzeile nennt zuerst, was offen ist, und dann, was gruen ist.
Reihenfolge ist aussagend: das Erste, was gelesen wird, ist das
Ungeloeste.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parent / "waechter_vertrag.json"


def main() -> int:
    d = json.loads(V.read_text(encoding="utf-8"))
    # §A-ZZZZ185 (Runde 89): der Stand ist die HOECHSTE Runde im Ledger —
    # keine getippte Versionsnummer. Eine Kopfzeile, die "stand_r88" sagt,
    # waehrend der Vertrag v9 ist, ist die "14 Zahlen"-Krankheit in gruen.
    _op = d["bringschuld"]["offene_posten"]
    _stand = max((k for k in _op if k.startswith("stand_r")),
                 key=lambda k: int(k[7:]))
    op = _op[_stand]
    fristen = {k: v for k, v in d.get("fristen", {}).items()
               if isinstance(v, dict) and v.get("endzustand")}
    print(f"OFFEN ({len(op)})")
    for i, p in enumerate(op, 1):
        print(f"  {i}. {p}")
    print(f"\nFRISTEN erledigt/verschoben: {len(fristen)}")
    for k, v in fristen.items():
        neu = f" -> {v['neuer_termin']}" if v.get("neuer_termin") else ""
        print(f"  {k}: {v['endzustand']}{neu}")
    # §A-ZZZZ207: jede Suite-Zahl liest aus EINER Quelle (zaehlweise).
    _zw = d.get("zaehlweise", {})
    print(f"\nStand: {_stand} | Version: v{d['_version']} | Instanzen: "
          f"{len(d['bringschuld']['instanzen'])} | Ledger: "
          f"{len(d['versions_ledger'])}")
    print(f"Zaehlweise: {_zw.get('n_code')} (Code) + "
          f"{_zw.get('n_nur_vertrag')} (nur Vertrag) = "
          f"{_zw.get('n_gesamt')} — aus test_zaehlweise.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
