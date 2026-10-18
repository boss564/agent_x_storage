#!/usr/bin/env python3
"""Beweis: Reorder tauscht das Etikett, nicht den Inhalt.

§A-ZZZZ190 (Runde 90 Hauptbefund): Die Messung in R89 lief auf der
Etiketten-Achse. Die Behauptung "Norm 1 vs. Norm 4 widersprechen sich"
ist im Payload keiner, weil `digest()` den Zeitstempel VOR dem Hash
entfernt. Dieser Test misst BEIDE Achsen getrennt:

    Etiketten-Achse: verschieden unter Reorder   (R89 hat das gemessen)
    Inhalts-Achse:   konstant Null               (R89 hat das uebersprungen)

Der Vertragssatz `zustell_zusage` sagt: ZUSTELLEN garantiert Inhalt,
nicht Original-Zeitstempel. Der Test prueft, dass diese Zusage exakt
das beschreibt, was der Code tut — nicht mehr und nicht weniger.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from einwurf_waechter import digest  # noqa: E402

V = SCRIPTS / "waechter_vertrag.json"
A = "A" * 500
T1, T2 = "2026-10-18T21:00:00Z", "2026-10-18T21:00:07Z"


def text(ts: str | None) -> str:
    return f"<timestamp>{ts}</timestamp>\n{A}" if ts else A


def hash_ohne_ts() -> str:
    """Hash des Inhalts OHNE jeden Zeitstempel."""
    return hashlib.sha256(digest(A).encode()).hexdigest()


def main() -> int:
    ok = gesamt = 0

    # 1. Der Hash ist zeitstempel-frei: drei Zeitstempel, ein Hash.
    gesamt += 1
    h = {digest(text(t)) for t in (T1, T1, T2, None)}
    gut = len(h) == 1
    print(f"{'ok  ' if gut else 'FAIL'} Hash ist TS-frei            "
          f"{len(h)} verschiedene Hashes fuer 4 Zeitstempel")
    ok += gut

    # 2. Der Beweis aus dem Vertrag ist wahr: waere der TS im Hash,
    #    koennte bei_ungleich=WIEDERHOLT nie feuern.
    gesamt += 1
    gut = digest(text(T1)) == digest(text(T2))
    print(f"{'ok  ' if gut else 'FAIL'} Neusendung == Original-Hash  "
          f"{gut} (sonst kein WIEDERHOLT moeglich)")
    ok += gut

    # 3. Inhalts-Achse: unter beiden Ordnungen wird derselbe Inhalt
    #    genau einmal zugestellt.
    for name, strom, erwartet_ts in (
        ("korrekt", [T1, T1, T2], T1),
        ("reorder", [T2, T1, T1], T2),
    ):
        gesamt += 1
        gesehen: dict[str, str] = {}
        zugestellt: list[tuple[str, str]] = []
        for t in strom:
            d = digest(text(t))
            if d not in gesehen:
                gesehen[d] = t
                zugestellt.append((d, t))
        inhalt_genau_einmal = len(zugestellt) == 1
        gut = inhalt_genau_einmal and zugestellt[0][1] == erwartet_ts
        print(f"{'ok  ' if gut else 'FAIL'} {name:<8} Inhalt genau einmal  "
              f"inhalt={len(zugestellt)} ts={zugestellt[0][1] if zugestellt else '-'}")
        ok += gut

    # 4. Die Inhalts-Achse ist unter Reorder konstant — das ist die
    #    Achse, die R89 uebersprungen hat.
    gesamt += 1
    a = {digest(text(t)) for t in [T1, T1, T2]}
    b = {digest(text(t)) for t in [T2, T1, T1]}
    gut = a == b
    print(f"{'ok  ' if gut else 'FAIL'} Inhalts-Achse konstant      "
          f"symmetrische Differenz={len(a ^ b)}")
    ok += gut

    # 5. Die Etiketten-Achse divergiert — das IST gemessen, nicht bestritten.
    gesamt += 1
    def etiketten(strom: list[str]) -> list[str]:
        seen: dict[str, str] = {}
        out = []
        for t in strom:
            d = digest(text(t))
            out.append("ZUSTELLEN" if d not in seen else
                       ("VERWERFEN" if seen[d] == t else "WIEDERHOLT"))
            seen[d] = t
        return out
    e1, e2 = etiketten([T1, T1, T2]), etiketten([T2, T1, T1])
    gut = e1 != e2 and e1[0] == e2[0] == "ZUSTELLEN"
    print(f"{'ok  ' if gut else 'FAIL'} Etiketten-Achse divergiert  "
          f"{e1} vs {e2}")
    ok += gut

    # 6. Die Zusage im Vertrag beschreibt genau das.
    gesamt += 1
    z = json.loads(V.read_text(encoding="utf-8"))["zustell_zusage"]
    gut = ("INHALT" in z["satz"] and "NICHT den Zeitstempel" in z["satz"]
           and "ERSTEN" in z["folge_unter_reorder"])
    print(f"{'ok  ' if gut else 'FAIL'} Zusage deckt Befund         "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Reorder-Payload-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
