#!/usr/bin/env python3
"""Governance-Gate — Wand, nicht Turm.

§A-ZZZZ221/222 (Runde 94/95): **zum ersten Mal greift eine Regel VOR dem
Verstoss statt danach.**

Die vier R92-Suiten standen eine volle Runde gegen die eigene
Stopp-Bedingung im Baum. Der Rollback kam erst nach externer Kritik.
Dieser Check laeuft an der Commit-Grenze und verkuerzt die Reaktionszeit
von Runden auf Commits.

DREI WEGE (B1, Freigabe R95):
    HARD BLOCK   bekannte Regressionsklassen, und neue Test-Suiten
                 solange kein Eigentuemer existiert — AUSSER der Commit
                 beruehrt nur die Felder, die ihn gruen machen koennen.
    ERLAUBT      Commits, die genau die Besitz-Bedingung erfuellen
                 (EXT-Buch, Eigentuemer, Beweisversuch).
    WARNUNG      Besitz rot, aber kein neuer Test — die Luecke ist
                 DEKLARIERT, nicht versteckt.

B3: lesend, offline, gate-only. Keine Suite, keine Schreibzugriffe, kein Netz.

Was der Hook NICHT kann (und nie koennen wird):
  - die naechste UNBEKANNTE Auspraegung erfinden
  - einen Namen in die Eigentuemer-Spalte schreiben
  - sich selbst uneditierbar machen: dieselbe Hand kann diesen Code aendern.
    Der einzige Backstop ist CI (.github/workflows/governance.yml).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
WURZEL = SCRIPTS.parent
V = SCRIPTS / "waechter_vertrag.json"
Q = SCRIPTS / "quarantaene"

# Commits, die die Besitz-Bedingung ERFUELLEN, nicht umgehen.
BESITZ_PFADE = ("scripts/waechter_vertrag.json",)
BESITZ_SCHLUESSEL = ("eigentuemer", "posten", "beweisversuch",
                     "frist_blocker", "externes_buch")


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=WURZEL,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def staged() -> list[str]:
    return [z for z in _git("diff", "--cached", "--name-only").splitlines()
            if z]


def staged_diff() -> str:
    return _git("diff", "--cached", "-U0")


def neue_tests(gestaged: list[str]) -> list[str]:
    """Gestagte NEUE Dateien unter scripts/test_*.py."""
    neu = _git("diff", "--cached", "--name-status", "--diff-filter=A")
    return [z.split("\t", 1)[1] for z in neu.splitlines()
            if z.endswith(".py") and "scripts/test_" in z]


# Suiten, die die Wand selbst sind (Bootstrap R95). Sie bauen die
# Durchsetzung, nicht den Turm — und duerfen im Installations-Commit
# mitkommen.
WAND_SUITEN = {"scripts/test_governance_gate.py",
               "scripts/test_aufrufbaum.py"}

# R97/R98: Die Ausnahme ist eine DATENSCHICHT, kein Regelbruch. Jede
# Entscheidung ist eine eigene Datei mit geschlossener Liste; verbraucht
# ist sie, wenn alle gelisteten Dateien in HEAD liegen (lesend, B3).
# Neue Wand = neue ENTSCHEIDUNG, nie Berufung auf "Instrument-Reparatur"
# (10. Auspraegung: Ausnahme darf nicht Kategorie werden).
ENTSCH = SCRIPTS / "entscheidung_R97.json"


ENTSCHEIDUNGEN = (SCRIPTS / "entscheidung_R97.json",
                  SCRIPTS / "entscheidung_R98.json")


def _ausnahme(e: dict, gestaged: list[str]) -> tuple[bool, str]:
    """Eine Entscheidung anwenden. Die LOGIK ist fuer alle gleich:
    geschlossene Liste, fremde Datei -> nein, verbraucht -> nein.
    Eine neue Entscheidung erweitert nur ENTSCHEIDUNGEN, nie diese
    Funktion. So kann 'Instrument-Reparatur' nicht zur Kategorie werden.
    """
    liste = set(e.get("dateien_geschlossen", []))
    if not liste:
        return False, f"{e.get('id','?')}: Dateiliste leer — ungültig"
    fremd = [p for p in gestaged if p not in liste]
    if fremd:
        return False, (f"{e['id']} deckt {len(fremd)} fremde Datei(en): "
                       f"{fremd[:3]}")
    # R97-N1: Verbrauch misst den DATEIZUSTAND, nicht den Ledger.
    # R98-N1: Feiner. Eine Datei kann in HEAD liegen UND geaendert werden.
    # "In HEAD" allein ist zu grob (#11: genau diese Verwechslung liess
    # Modifikationen unsichtbar). Massstab ist daher:
    #   baseline_sha256 vorhanden -> verbraucht, wenn HEAD != baseline
    #   sonst                     -> verbraucht, wenn alle Dateien in HEAD
    base = e.get("fix", {}).get("baseline_sha256")
    if base:
        fehlend = [f for f in sorted(liste)
                   if not _git("ls-tree", "--name-only", "HEAD", "--", f).strip()]
        if fehlend:
            return True, (f"{e['id']}: {len(liste)} Dateien, Basis noch nicht im Baum")
        import hashlib as _h
        for f in sorted(liste):
            ist = _h.sha256((SCRIPTS.parent / f).read_bytes()).hexdigest()
            if ist != base:
                return False, (f"{e['id']} verbraucht — {f} weicht von der "
                               f"Baseline ab; neue ENTSCHEIDUNG noetig")
        return True, (f"{e['id']}: {len(liste)} Dateien, Basis identisch, "
                      f"Aenderung gegen Baseline gestattet")
    fehlend = [f for f in sorted(liste)
               if not _git("ls-tree", "--name-only", "HEAD", "--", f).strip()]
    if not fehlend:
        return False, (f"{e['id']} verbraucht — alle Dateien im Baum; "
                       f"neue ENTSCHEIDUNG nötig")
    return True, (f"{e['id']}: {len(liste)} Dateien, geschlossen, einmalig "
                  f"(noch {len(fehlend)} nicht im Baum)")


def ausnahme_aktiv(gestaged: list[str]) -> tuple[bool, str]:
    """Die erste greifende Entscheidung. Reihenfolge = Dateiliste oben."""
    if not gestaged:
        return False, ""
    gruende = []
    for pfad in ENTSCHEIDUNGEN:
        if not pfad.exists():
            continue
        ok, grund = _ausnahme(json.loads(pfad.read_text(encoding="utf-8")),
                              gestaged)
        if ok:
            return True, grund
        gruende.append(grund)
    return False, "; ".join(gruende) if gruende else ""


# R97-N1/B3: Es gibt KEINEN _verbrauche_R97(). Das Gate schreibt nicht.
# Der Verbrauch folgt allein aus dem Dateibaum: sobald die vier Dateien
# in HEAD liegen, verweigert ausnahme_R97() die naechste Ausnahme.


def erfuellt_besitz(gestaged: list[str], diff: str) -> bool:
    """Beruehrt der Commit AUSSCHLIESSLICH Besitz-Felder? (B1 Weg 2)"""
    if not gestaged:
        return False
    if any(p not in BESITZ_PFADE and p not in WAND_SUITEN
           for p in gestaged):
        return False
    # Nur Zeilen, die Besitz-Schluessel tragen, duerfen sich aendern.
    for z in diff.splitlines():
        if not (z.startswith("+") or z.startswith("-")):
            continue
        if z.startswith(("+++", "---")):
            continue
        if not any(k in z for k in BESITZ_SCHLUESSEL):
            # Strukturzeile (Klammern, Kommas) ist erlaubt.
            if z[1:].strip() and z[1:].strip() not in ("{", "}", "},", "],"):
                return False
    return True


def main(argv: list[str]) -> int:
    d = json.loads(V.read_text(encoding="utf-8"))
    e = d.get("enforcement", {})
    q_liste = e.get("quarantaene", [])
    posten = d.get("externes_buch", {}).get("posten", [])
    ohne = [p["id"] for p in posten if not p.get("eigentuemer")]

    gestaged = staged()
    diff = staged_diff()
    hart: list[str] = []
    warnung: list[str] = []

    # --- Bekannte Regressionsklassen: HARD BLOCK ------------------------
    for name in q_liste:
        if (SCRIPTS / f"{name}.py").exists():
            hart.append(f"gesperrte Suite zurueck: scripts/{name}.py")
    for datei in ("Makefile", "scripts/check_claude_md.py"):
        p = WURZEL / datei
        if p.exists():
            t = p.read_text(encoding="utf-8")
            for name in q_liste:
                if name in t:
                    hart.append(f"gesperrte Suite referenziert: {datei}:{name}")
    # Nur AUSGABE-Zeilen pruefen, nicht die Regelliste selbst: sonst
    # verbietet das Gate den Code, der es formuliert (Fehlalarm R95).
    for w in d.get("standzeile", {}).get("verbotene_woerter", []):
        for z in diff.splitlines():
            if not z.startswith("+") or z.startswith("+++"):
                continue
            if "VERBOTEN" in z or w in ("",):
                continue
            # Treffer nur, wenn das Wort als Text ausgegeben/gedruckt wird.
            if ("print(" in z or "f\"" in z or "f'" in z) and w in z.lower():
                hart.append(f"Adels-Wort in der Ausgabe: {w} :: {z.strip()[:60]}")
    if not d.get("bilanz_regel", {}).get("prosa_verboten"):
        hart.append("Bilanzregel fehlt — Prosa-Bilanz erlaubt")

    # --- Stopp-Bedingung: B1 -------------------------------------------
    if ohne:
        neu = neue_tests(gestaged)
        # Wand-Suiten (Bootstrap) sind keine Turm-Suiten.
        turm_neu = [x for x in neu if x not in WAND_SUITEN]
        ok_ausn, grund = ausnahme_aktiv(gestaged) if turm_neu else (False, "")
        if turm_neu and ok_ausn:
            warnung.append(f"R97-Ausnahme aktiv (verbraucht sich mit diesem Commit): {grund}")
            turm_neu = []
        if turm_neu and not erfuellt_besitz(gestaged, diff):
            hart.append(
                f"{len(turm_neu)} neue Test-Suite(n) ohne Eigentuemer "
                f"(EXT offen: {', '.join(ohne)}): {', '.join(turm_neu)}")
        elif neu and not turm_neu:
            warnung.append(
                f"Wand-Suiten im Commit ({len(neu)}) — Bootstrap-Ausnahme")
        elif neu and not erfuellt_besitz(gestaged, diff):
            pass
        elif not neu:
            warnung.append(
                f"Besitz rot ({len(ohne)}/4 ohne Eigentuemer) — "
                "Commit ohne neuen Test erlaubt; Luecke DEKLARIERT")
        else:
            warnung.append("Besitz-Commits erlaubt (B1 Weg 2)")

    if hart:
        print("GOVERNANCE ROT:")
        for r in hart:
            print(f"  - {r}")
        print("\n  Wand, nicht Turm: der Commit wuerde neue Maschinerie")
        print("  bauen, waehrend EXT-1..4 unbeauftragt sind.")
        print("  Erlaubt: Commits, die NUR Eigentuemer/Beweisversuch setzen.")
        return 1
    for w in warnung:
        print(f"GOVERNANCE WARNUNG: {w}")
    print(f"Governance: ok ({len(q_liste)} gesperrt, "
          f"{len(ohne)}/4 EXT offen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
