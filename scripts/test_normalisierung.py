#!/usr/bin/env python3
"""Normalisierungs-Grenze: die zweite Flanke der Identitaet.

§A-ZZZZ134 (Runde 83): **eine Mauer, die nur eine Seite schuetzt.**

`test_hash_eingang.py` prueft die erste Flanke — zu wenig normalisiert:
ein Metadatum (Zeitstempel, Sequenz) leckt in den Hash, ein echtes
Duplikat wird als neu zugestellt. Kosten: Redundanz.

Die zweite Flanke ist **zu viel normalisiert**: ein Inhaltsunterschied
verschwindet, zwei verschiedene Meldungen kollidieren, die zweite wird
verworfen. Kosten: **Inhalt, irreversibel.** Ein falsches Duplikat ist
teurer als ein verpasstes.

Dieser Test zieht die Grenze explizit: drei Kollisionen sind gewollt
und werden assertiert, fuenf Trennungen sind gewollt und werden
assertiert. Was dazwischen liegt, ist kein Zufall, sondern Vertrag.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import einwurf_waechter as w  # noqa: E402

FEHLER: list[str] = []

# (Name, a, b, soll_kollidieren, begruendung)
FAELLE = [
    ("Leerzeilen 1x vs 3x", "A\nB", "A\n\n\nB", True,
     "Zeilenumbrueche sind Formatierung"),
    ("Trailing spaces", "A \nB", "A\nB", True,
     "folgenlos am Zeilenende"),
    ("CRLF vs LF", "A\r\nB", "A\nB", True,
     "Transportformat"),
    ("Tab vs Space", "A\tB", "A B", False,
     "in Code/Tabellen bedeutungstragend"),
    ("Gross-/Kleinschreibung", "Absatz A", "absatz a", False,
     "Namen und Pfade unterscheiden sich darin"),
    ("Satzzeichen", "Ist das wahr?", "Ist das wahr", False,
     "Satz vs Frage ist Bedeutung"),
    ("Wortstellung", "A verklagt B", "B verklagt A", False,
     "Rollen sind Bedeutung"),
]


def pruefe(name: str, a: str, b: str, kollidiert: bool, warum: str) -> None:
    ist = w.digest(a) == w.digest(b)
    gut = ist == kollidiert
    erwartet = "KOLLISION" if kollidiert else "getrennt"
    print(f"{'ok  ' if gut else 'FAIL'} {erwartet:9s} {name:24s} {warum}")
    if not gut:
        FEHLER.append(name)


def main() -> int:
    for name, a, b, k, warum in FAELLE:
        pruefe(name, a, b, k, warum)
    gesamt = len(FAELLE) + 1
    # Beide Richtungen in EINEM Test: der Test ist nur gueltig, wenn er
    # sowohl eine Kollision als auch eine Trennung assertiert. Ein Test,
    # der nur Kollisionen fordert, wuerde eine zu aggressive
    # Normalisierung befuerworten.
    hat_koll = any(k for _, _, _, k, _ in FAELLE)
    hat_tren = any(not k for _, _, _, k, _ in FAELLE)
    pruefe("beide Richtungen geprueft",
           "x", "y" if hat_koll and hat_tren else "x", False,
           "Test enthaelt Kollisions- UND Trennungsfaelle")
    print(f"\n{gesamt - len(FEHLER)}/{gesamt} Normalisierungs-Grenzen gruen")
    return 0 if not FEHLER else 1


if __name__ == "__main__":
    raise SystemExit(main())
