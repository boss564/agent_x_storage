#!/usr/bin/env python3
"""Die 94 "aussen" enumerieren — R96 Buchung 5.

R95: "94 aussen-Dateien nie bewertet" war ein Befund ohne Zerlegung.
R96: `aussen` wird in **Partitionen** zerlegt, jede mit Definition.

Die Partitionen werden NICHT aus Dateinamen geraten (R96: "der Glob war
falsch, nicht das Skript" — dieselbe Falle waere, Kategorien aus
Namensmustern zu raten). Definitionen sind mechanisch:

    GOVERNANCE   importiert `waechter_vertrag`, `test_zaehlweise`,
                 `kopfzeile`, `standzeile` oder liest den Vertrag
    INFRA        braucht NATS/Z3/Netz/Docker/Anvil (Marker im Quelltext)
    STUDIE       Mess-/Simulationslauf (rescue, ci, hum, wirtschaft,
                 smartgrid, astrocore, simchain, multichain)
    REGRESSION   test_* ohne Governance-Marker (Produkttests)
    SONSTIG      Rest — wird NAMENTLICH gelistet, nie stillschweigend

Regel: keine Partition darf namenlos sein. `SONSTIG` bleibt sichtbar.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from test_zaehlweise import zaehle

GOV_MARKER = ("waechter_vertrag", "test_zaehlweise", "kopfzeile",
              "standzeile", "governance_gate", "bilanz")
INFRA_MARKER = ("nats", "localhost:8222", "anvil", "8545", "z3_solver",
                "127.0.0.1:")
# Negativ-Marker: Dienst wird nur ERWAEHNT (Assertion), nicht VERBUNDEN.
KEIN_DIENST = re.compile(
    r"(kein[e]?\s+(nats|netz|docker|server|z3)|"
    r"ohne\s+(nats|netz|docker|server)|"
    r"assert[^\n]*(not\s+)?(docker|web3)[^\n]*(in|not in))", re.I)
STUDIEN = ("rescue", "ci_", "hum_", "wirtschaft", "smartgrid",
           "astrocore", "simchain", "multichain", "h0", "stress_study")


def quelle(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def einordnen(name: str) -> tuple[str, str]:
    p = SCRIPTS / name
    q = quelle(p).lower()
    if any(m in q for m in GOV_MARKER):
        return "GOVERNANCE", "liest Vertrag/Zaehler/Instrument"
    # R96: "docker"/"web3" allein sind zu breit — sie treffen Produkttests.
    # INFRA nur, wenn der Test sich mit einem laufenden Dienst verbinden will.
    if KEIN_DIENST.search(q):
        return "REGRESSION", "erwaehnt Dienst nur als Assertion"
    if any(m in q for m in INFRA_MARKER):
        return "INFRA", "braucht Dienst/Netz"
    if any(m in name for m in STUDIEN):
        return "STUDIE", "Mess-/Simulationslauf"
    if name.startswith("test_"):
        return "REGRESSION", "Produkttest ohne Governance-Marker"
    return "SONSTIG", "keine mechanische Zuordnung"


def main(argv: list[str]) -> int:
    nur = "--json" in argv
    k = zaehle()
    zeilen = []
    for n in sorted(k["aussen"]):
        kl, grund = einordnen(n)
        zeilen.append({"datei": n, "klasse": kl, "grund": grund})
    c = Counter(z["klasse"] for z in zeilen)
    if nur:
        print(json.dumps({"aussen": len(zeilen), "klassen": c.most_common(),
                          "eintraege": zeilen}, indent=1, ensure_ascii=False))
        return 0
    print(f"aussen: {len(zeilen)} Dateien -> {len(c)} Klassen")
    for kl, n in c.most_common():
        print(f"  {kl:11} {n}")
    for kl in ("SONSTIG", "GOVERNANCE"):
        if not c.get(kl):
            continue
        print(f"\n{kl}:")
        for z in zeilen:
            if z["klasse"] == kl:
                print(f"  {z['datei']:42} {z['grund']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
