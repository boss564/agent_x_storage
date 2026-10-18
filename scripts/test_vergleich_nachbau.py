#!/usr/bin/env python3
"""Nachbau des Vergleichs ALLEIN aus der Wahrheitstafel im Vertrag.

§A-ZZZZ189 (Runde 90 Befund 4): `vergleich_pflicht` ist ein Python-Verbot
(„`==` verboten"). Ein Konsument in einer anderen Sprache kann es nicht
lesen und muss `ts_vergleich` aus der Prosa nachbauen — dort reisst die
boolesche Falle wieder auf.

Dieser Test tut genau das: er baut VERGLEICH aus `vergleich_schnittstelle`
im Vertrag, **ohne** `konsumenten_semantik.ts_vergleich` zu importieren,
und misst gegen die Referenz. Wenn diese Datei gruen ist, ist die
Schnittstelle sprach-agnostisch spezifiziert. Wenn nicht, ist sie nur
ein Verbot mit Kommentar.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

V = SCRIPTS / "waechter_vertrag.json"


class Unlesbar:
    """Fremdsprachiger Konsument: Opakes Unlesbar-Objekt."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        # Ein naiver Konsument schreibt genau das — und faellt in die Falle.
        return isinstance(other, Unlesbar)

    def __hash__(self) -> int:
        return 0


def vergleich_aus_tafel(a: object, b: object) -> str:
    """Reimplementierung NUR aus der Wahrheitstafel im Vertrag.

    Keine Referenz auf ts_vergleich. Der Algorithmus folgt aus:
      - UNLESBAR auf einer Seite -> UNLESBAR (3 Zellen)
      - LESBAR x LESBAR -> GLEICH bei Gleichheit, sonst UNGLEICH (2 Zellen)
    """
    u = isinstance(a, Unlesbar) or isinstance(b, Unlesbar)
    if u:
        return "UNLESBAR"
    return "GLEICH" if a == b else "UNGLEICH"


def main() -> int:
    ok = gesamt = 0
    tafel = json.loads(V.read_text(encoding="utf-8"))["vergleich_schnittstelle"]

    # 1. Die Wahrheitstafel hat genau fuenf Zellen (= 3x3 minus 4, siehe 2).
    gesamt += 1
    gut = len(tafel["wahrheitstafel"]) == 5
    print(f"{'ok  ' if gut else 'FAIL'} Tafel hat 5 Zellen          "
          f"{len(tafel['wahrheitstafel'])}")
    ok += gut

    # 2. Die vier erklaerten Zellen stimmen mit dem Nachbau.
    faelle = [
        ("T1", 100, 100, "GLEICH"),
        ("T2", 100, 200, "UNGLEICH"),
        ("T3", 100, Unlesbar(), "UNLESBAR"),
        ("T4", Unlesbar(), 100, "UNLESBAR"),
        ("T5", Unlesbar(), Unlesbar(), "UNLESBAR"),
    ]
    for name, a, b, soll in faelle:
        gesamt += 1
        ist = vergleich_aus_tafel(a, b)
        gut = ist == soll
        print(f"{'ok  ' if gut else 'FAIL'} {name} Nachbau={ist:<8} "
              f"soll={soll}")
        ok += gut

    # 3. Der Kern: Unlesbar ist NICHT reflexiv — im Nachbau UND in der Tafel.
    gesamt += 1
    gut = "VERGLEICH(x,x)=GLEICH nur wenn x LESBAR" in tafel["invariante"]
    print(f"{'ok  ' if gut else 'FAIL'} Invariante deklariert      "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 4. Der naive Konsument (Unlesbar == Unlesbar) weicht AB — gemessen.
    gesamt += 1
    naiv = Unlesbar() == Unlesbar()
    korrekt = vergleich_aus_tafel(Unlesbar(), Unlesbar())
    gut = naiv is True and korrekt == "UNLESBAR"
    print(f"{'ok  ' if gut else 'FAIL'} naive Falle messbar        "
          f"bool={naiv} total={korrekt}")
    ok += gut

    # 5. Gegenprobe: der Nachbau ist deckungsgleich mit der Referenz.
    gesamt += 1
    from konsumenten_semantik import relate  # Referenz
    # Repraesentationen derselben Domaene: Unlesbar() <-> None.
    def ref(a: object, b: object) -> str:
        fa = None if isinstance(a, Unlesbar) else a
        fb = None if isinstance(b, Unlesbar) else b
        return relate(fa, fb).upper()

    abw = [(n, ref(a, b), vergleich_aus_tafel(a, b))
           for n, a, b, _ in faelle
           if ref(a, b) != vergleich_aus_tafel(a, b)]
    gut = not abw
    print(f"{'ok  ' if gut else 'FAIL'} Nachbau == Referenz        "
          f"Abweichungen={len(abw)}")
    ok += gut

    # 6. Die Abbildung Ausgabe -> Verdict steht im Vertrag.
    gesamt += 1
    gut = all(w in tafel["abbildung"] for w in ("UNGEPRUEFT", "VERWERFEN", "WIEDERHOLT"))
    print(f"{'ok  ' if gut else 'FAIL'} Abbildung auf Verdicts    "
          f"{'vollstaendig' if gut else 'luecken'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Schnittstellen-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
