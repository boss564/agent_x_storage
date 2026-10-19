#!/usr/bin/env python3
"""Ledger-Provenienz: Kontiguitaet ist nicht Gleichzeitigkeit.

§A-ZZZZ211 (Runde 92 Befund 7): **ein vollstaendiger, nachtraeglicher
Ledger ist vollstaendig und falsch zugleich.**

Der Kontiguitaetstest fing v13 — aber der Eintrag wurde NACH v14
geschrieben. Rekonstruktion. Von einem zeitgleichen Eintrag ist er ohne
Herkunftsnachweis nicht unterscheidbar.

Die Loesung ist Hash-Verkettung: jeder Eintrag traegt den Hash seines
Vorgaengers. Ein Nachtrag, der zwischen zwei bestehende Eintraege
geschoben wird, bricht die Kette — strukturell sichtbar, nicht durch
Disziplin.

    eintrag[n].vorgaenger_hash == sha256(canonical(eintrag[n-1]))

Und weil Python-Dicts die Reihenfolge erhalten, die JSON-Datei aber von
Hand umsortiert werden kann, wird canonical() explizit nach Schluessel
sortiert — sonst haengt der Hash an der Schreibweise, nicht am Inhalt.

GRENZE (ehrlich): Hash-Verkettung erkennt NACHTRAG, nicht ZEITPUNKT.
Wer e_14 schreibt, dann e_13 korrekt einschiebt und alle Hashes neu
berechnet, erzeugt eine gueltige Kette. Der einzige Schutz dagegen ist
Git-History — und die ist ausserhalb dieses Artefakts.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"

FELDER = ("version", "runde", "aenderung", "gebucht", "rekonstruiert")


def canonical(e: dict) -> str:
    """Stabiler Hash ueber die INHALTLICHEN Felder, sortiert."""
    slim = {k: e.get(k) for k in FELDER if k in e}
    return json.dumps(slim, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def hash_von(e: dict) -> str:
    return hashlib.sha256(canonical(e).encode("utf-8")).hexdigest()


def akzeptiert(ledger: list[dict]) -> list[dict]:
    return sorted((e for e in ledger if isinstance(e.get("version"), int)),
                  key=lambda e: e["version"])


def kette_brechen(ledger: list[dict]) -> list[int]:
    """Versionen, deren vorgaenger_hash nicht zum Vorgaenger passt."""
    aus = akzeptiert(ledger)
    brueche: list[int] = []
    for i, e in enumerate(aus):
        if i == 0:
            continue
        soll = hash_von(aus[i - 1])
        if e.get("vorgaenger_hash") != soll:
            brueche.append(e["version"])
    return brueche


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    L = d["versions_ledger"]
    dok = d.get("ledger_provenienz", {})

    # 1. Die Doktrin ist deklariert, inkl. ihrer Grenze.
    gesamt += 1
    gut = bool(dok.get("regel")) and "NACHTRAG" in dok.get("grenze", "")
    print(f"{'ok  ' if gut else 'FAIL'} Doktrin + Grenze           "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 2. Jeder akzeptierte Eintrag (ausser v1) traegt einen Vorgaenger-Hash.
    gesamt += 1
    ohne = [e["version"] for e in akzeptiert(L) if e["version"] > 1
            and not e.get("vorgaenger_hash")]
    gut = not ohne
    print(f"{'ok  ' if gut else 'FAIL'} Jeder Eintrag verkettet    "
          f"ohne={ohne}")
    ok += gut

    # 3. Die Kette ist unversehrt.
    gesamt += 1
    brueche = kette_brechen(L)
    gut = not brueche
    print(f"{'ok  ' if gut else 'FAIL'} Kette unversehrt           "
          f"brueche={brueche}")
    ok += gut

    # 4. Der v13-Fall ist als REKONSTRUKTION markiert — nicht als Record.
    gesamt += 1
    v13 = next((e for e in akzeptiert(L) if e["version"] == 13), {})
    gut = v13.get("rekonstruiert") is True
    print(f"{'ok  ' if gut else 'FAIL'} v13 als Rekonstruktion     "
          f"{v13.get('rekonstruiert')}")
    ok += gut

    # 5. Ein nachtraeglicher Eintrag BRICHT die Kette — gemessen.
    gesamt += 1
    test = [dict(e) for e in akzeptiert(L)]
    fake = {"version": 13, "runde": 91, "aenderung": "eingeschoben",
            "vorgaenger_hash": "0" * 64}
    test.append(fake)
    gut = 13 in kette_brechen(test)
    print(f"{'ok  ' if gut else 'FAIL'} Einschub bricht Kette      "
          f"{gut}")
    ok += gut

    # 6. canonical() ist reihenfolge-unabhaengig im Dict (sort_keys).
    gesamt += 1
    a = {"version": 1, "runde": 79, "aenderung": "x"}
    b = {"aenderung": "x", "runde": 79, "version": 1}
    gut = canonical(a) == canonical(b)
    print(f"{'ok  ' if gut else 'FAIL'} canonical sortiert         "
          f"{gut}")
    ok += gut

    print(f"\n{ok}/{gesamt} Ledger-Provenienz-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
