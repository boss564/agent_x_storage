#!/usr/bin/env python3
"""Bedarfs-Inventur: wer liest die Felder, die ZUSTELLEN liefert?

§A-ZZZZ202 (Runde 91 Hauptbefund): **`zustell_zusage` ist eine Zusage ohne
gemessenen Bedarf — die vierte Auspraegung der Krankheit.**

  "?"-Sentinel          Feld existiert, Bedeutung fehlt
  BLOCKER benannt       Zeichenkette existiert, Substanz fehlt
  gruen bei 3/3         Bestanden existiert, Gelegenheit fehlt
  zustell_zusage        Zusage existiert, BEDARF fehlt

Ob der Downstream den Original-Zeitstempel braucht, ist eine EMPIRISCHE
Frage an das Teilsystem hinter der Schnittstelle, keine normative an den
Vertrag. Diese Inventur stellt sie empirisch: sie durchsucht jeden
Nicht-Test-Konsumenten im Baum danach, ob er aus einem Record
(`ZEILE`/`DEDUP`) den Zeitstempel liest.

Ergebnis ist selbst ein Befund: gibt es keinen Leser, ist `zustell_zusage`
ein PROTOKOLL (belegt). Gibt es einen, ist sie eine VERTRAGSAENDERUNG,
die dieser Leser mitzeichnen muss.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
V = SCRIPTS / "waechter_vertrag.json"

# Liest ein Nicht-Test-Skript den Zeitstempel AUS EINEM RECORD?
# Zwei Bedingungen zusammen: ein Record-Praefix im selben Modul UND ein
# Timestamp-Regex. Ein Test-Aufbau, der Strome ERZEUGT, ist kein Leser.
RECORD = re.compile(r"\b(ZEILE |DEDUP |ZUSTELLEN)")
TS = re.compile(r"<timestamp>(.*?)</timestamp>")


def leser() -> tuple[list[str], list[str]]:
    """(leser, ausgeschlossen) — beide explizit, keine stille Filterung."""
    tests = {p for p in SCRIPTS.glob("test_*.py")}
    lesend: list[str] = []
    ausgeschlossen: list[str] = []
    for p in sorted(SCRIPTS.glob("*.py")):
        if p in tests:
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if not (RECORD.search(t) and TS.search(t)):
            continue
        # §A-ZZZZ204: der EMITTENT ist kein Downstream. Er baut die
        # Records — ein Emittent, der als Leser zaehlt, macht die
        # Inventur zu einer Tautologie (er liest immer seinen eigenen Output).
        if re.search(r"def digest\(|bericht\.append\(f\"ZEILE", t):
            ausgeschlossen.append(p.name + " (Emittent)")
            continue
        # ein Modul, das Strome ERZEUGT, liest sie im eigenen Testaufbau
        if re.search(r"def _z\(|json\.dumps\(\{\"role\"", t):
            ausgeschlossen.append(p.name)
            continue
        lesend.append(p.name)
    return lesend, ausgeschlossen


def main() -> int:
    ok = gesamt = 0
    d = json.loads(V.read_text(encoding="utf-8"))
    lesend, ausg = leser()

    # 1. Der Befund: kein Downstream liest den Original-Zeitstempel.
    gesamt += 1
    gut = lesend == []
    print(f"{'ok  ' if gut else 'FAIL'} Kein Downstream liest TS    "
          f"leser={lesend or 'keine'}")
    ok += gut

    # 2. Die Ausschluesse sind benannt, nicht still (kein Filternebel).
    gesamt += 1
    gut = bool(ausg)
    print(f"{'ok  ' if gut else 'FAIL'} Ausschluesse explizit      "
          f"{ausg or 'keine'}")
    ok += gut

    # 3. Die Inventur steht im Vertrag — mit Ergebnis und Datum.
    gesamt += 1
    inv = d.get("bedarfs_inventur", {})
    gut = bool(inv.get("ergebnis")) and inv.get("leser") == [] and lesend == []
    print(f"{'ok  ' if gut else 'FAIL'} Inventur im Vertrag        "
          f"{'ja' if gut else 'nein'}")
    ok += gut

    # 4. Der Status der Zusage folgt aus der Messung, nicht aus dem Dekret.
    gesamt += 1
    gut = inv.get("status") == "PROTOKOLL" and not lesend
    print(f"{'ok  ' if gut else 'FAIL'} Zusage = Protokoll         "
          f"status={inv.get('status')}")
    ok += gut

    # 5. Die Klassen-Regel: jedes normative Feld deklariert seine Quelle.
    gesamt += 1
    kl = d.get("substanzklassen", {})
    gut = all(k in kl for k in ("MESSUNG", "ABLEITUNG", "ENTSCHEIDUNG"))
    print(f"{'ok  ' if gut else 'FAIL'} Substanzklassen            "
          f"{sorted(kl) if kl else 'fehlt'}")
    ok += gut

    print(f"\n{ok}/{gesamt} Bedarfs-Inventur-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
