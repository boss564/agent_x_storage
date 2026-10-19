#!/usr/bin/env python3
"""Vertragsschnittstelle mit durable Adresse (R105, P3-Anteil).

Befund seit R102: data/lauf_letzter.json ist zur Schnittstelle erklaert
und liegt unter .gitignore 'data/'. Governance bewachte den Produzenten
(lauf.py), nicht das Produkt. Ein Vertrag auf eine Datei, die niemand
eincheckt, ist ein Vertrag auf Sand.

Loesung (nicht Bandage — Ausnahme, nicht Glob-Aufweichung):
  * data/ bleibt ignoriert (Laufzeit ist keine Historie)
  * dieser Befehl schreibt eine VERSIONIERTE Kopie
    vertrag/vertrag_<utc-ts>.json mit Provenienz (Quellpfad, SHA,
    Zeilenzahl, Entstehungszeit)
  * latest.json ist ein ZEIGER: {snapshot, sha256}, nie der Inhalt
    selbst — sonst waere der Zeiger wieder ein Zustand, kein Verweis.

    python3 scripts/vertrag_snapshot.py          # Snapshot ziehen
    python3 scripts/vertrag_snapshot.py --check   # Zeiger vs. Snapshot
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
QUELLE = REPO / "data" / "lauf_letzter.json"
ZIEL = REPO / "vertrag"
ZEIGER = ZIEL / "latest.json"


def main(argv: list[str]) -> int:
    ZIEL.mkdir(exist_ok=True)
    if "--check" in argv:
        if not ZEIGER.exists():
            print("kein Zeiger — Vertrag hat keine durable Adresse")
            return 1
        z = json.loads(ZEIGER.read_text(encoding="utf-8"))
        p = ZIEL / z["snapshot"]
        if not p.exists():
            print(f"Zeiger zeigt ins Leere: {z['snapshot']}")
            return 1
        ist = hashlib.sha256(p.read_bytes()).hexdigest()
        if ist != z["sha256"]:
            print(f"Snapshot manipuliert: {ist[:16]} != {z['sha256'][:16]}")
            return 1
        print(f"ok  {z['snapshot']} sha256={ist[:16]}…")
        return 0

    if not QUELLE.exists():
        print(f"keine Quelle: {QUELLE.relative_to(REPO)}")
        return 1
    roh = QUELLE.read_bytes()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"vertrag_{ts}.json"
    (ZIEL / name).write_bytes(roh)
    sha = hashlib.sha256(roh).hexdigest()
    ZEIGER.write_text(json.dumps({
        "snapshot": name, "sha256": sha,
        "quelle": "data/lauf_letzter.json",
        "zeilen": len(roh.decode("utf-8").splitlines()),
        "gezogen_utc": ts,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Snapshot: {name} sha256={sha[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
