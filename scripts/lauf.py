#!/usr/bin/env python3
"""Der eine Lauf — gespeist aus der einen Zaehlung.

§A-ZZZZ224 (Runde 96, neunte Auspraegung): **der richtige Zaehler
existierte, die Verwendung fehlte.**

R95 lief ueber
    for f in scripts/test_*.py scripts/blocker_*.py
und zaehlte `blocker_nrm_injektivitaet.py` (Exit 2 = UNBEWIESEN) als
rot. Der Bericht benannte den Fehler korrekt ("der Glob war falsch,
nicht das Skript") und **reparierte ihn nicht**. Der naechste Lauf
haette denselben Fehler reproduziert.

Dieser Runner ist der Fix. Er definiert NICHT selbst, was ein Test ist —
er fragt `test_zaehlweise.zaehle()`.

DREI EINHEITEN (R96 Buchung 3): "rot" hatte in R95 keine Einheit.
    GEFALLEN     Exit != 0 und nicht als Befund klassifiziert
    BEFUND       Exit 2 (UNBEWIESEN) — absichtlich, kein Ausfall
    BEENDET      Exit 143 (SIGTERM) oder 124 (Timeout)
Jede Zahl im Bericht traegt ihre Einheit. Keine Summe ohne Zerlegung.

KEIN `.git`-ZUGRIFF (R96 Buchung 7): der Runner fasst `.git` nicht an.
Sonst perturbiert der Beobachter das System, das er misst
(index.lock, parallele Commits).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from test_zaehlweise import zaehle  # die EINE Quelle

V = SCRIPTS / "waechter_vertrag.json"
ERGEBNIS = SCRIPTS.parent / "data" / "lauf_letzter.json"


def klassifiziere(rc: int) -> str:
    if rc == 0:
        return "GRUEN"
    if rc == 2:
        return "BEFUND"
    if rc in (124, 143):
        return "BEENDET"
    return "GEFALLEN"


def lauf(dateien: list[str], timeout: int = 180) -> dict:
    erg: list[dict] = []
    # R96: inkrementell schreiben. Ein abgebrochener Lauf darf seinen
    # Fortschritt nicht verlieren — sonst ist der Abbruch unsichtbar
    # (siebte Auspraegung: Befund ohne Wirkung).
    ERGEBNIS.parent.mkdir(parents=True, exist_ok=True)
    for name in dateien:
        p = SCRIPTS / name
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, str(p)],
                               capture_output=True, text=True,
                               timeout=timeout, cwd=SCRIPTS.parent)
            rc = r.returncode
            tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
        except subprocess.TimeoutExpired:
            rc, tail = 124, ["TIMEOUT"]
        erg.append({"datei": name, "exit": rc,
                    "klasse": klassifiziere(rc),
                    "s": round(time.time() - t0, 1),
                    "letzte": tail[0][:120],
                    "ende": (r.stdout or r.stderr).strip().splitlines()[-4:]})
        _schreib(erg, laufend=True)
    return {"erg": erg, "quelle": "test_zaehlweise.zaehle()"}


def _schreib(erg: list[dict], laufend: bool = False) -> None:
    ERGEBNIS.write_text(
        json.dumps({"erg": erg, "laufend": laufend,
                    "quelle": "test_zaehlweise.zaehle()"},
                   indent=1, ensure_ascii=False), encoding="utf-8")


def bericht(d: dict) -> None:
    c = Counter(e["klasse"] for e in d["erg"])
    print(f"Quelle: {d['quelle']}")
    print(f"Dateien: {len(d['erg'])}")
    for k in ("GRUEN", "GEFALLEN", "BEFUND", "BEENDET"):
        print(f"  {k:9} {c.get(k, 0)}")
    if c.get("GEFALLEN") or c.get("BEENDET"):
        print("\nGEFALLEN/BEENDET:")
        for e in d["erg"]:
            if e["klasse"] in ("GEFALLEN", "BEENDET"):
                print(f"  {e['klasse']:9} {e['datei']:38} "
                      f"exit={e['exit']} {e['letzte'][:60]}")
    if c.get("BEFUND"):
        print("\nBEFUND (Exit 2 = unentscheidbar, kein Ausfall):")
        for e in d["erg"]:
            if e["klasse"] == "BEFUND":
                print(f"  {e['datei']:38} {e['letzte'][:70]}")


# R98 (Route A): Das Archiv liegt in einem VERSIONIERTEN Pfad.
# `data/` ist .gitignore:38 — ein Archiv dort waere fluechtig und heilte
# nur das Ueberschreiben, nicht die Archivierbarkeit.
PROTOKOLL = SCRIPTS.parent / "protokoll"
VERTRAG = SCRIPTS / "waechter_vertrag.json"


def _provenienz(modus: str) -> dict:
    """Herkunft, ohne die ein Archiv eine Zahlenkolonne ist (R98 Bedingung 4)."""
    def g(*a: str) -> str:
        try:
            return subprocess.run(["git", *a], capture_output=True,
                                  text=True, cwd=SCRIPTS.parent).stdout.strip()
        except OSError:
            return ""
    try:
        z = json.loads(VERTRAG.read_text(encoding="utf-8"))
        zw = {"n_code": z.get("zaehlweise", {}).get("n_code"),
              "n_gesamt": z.get("zaehlweise", {}).get("n_gesamt"),
              "version": z.get("_version")}
    except (OSError, ValueError):
        zw = {}
    return {
        "commit_hash": g("rev-parse", "HEAD"),
        "commit_dirty": bool(g("status", "--porcelain")),
        "modus": modus,
        "zeitstempel_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "zaehlweise": zw,
        "querverweis": "lauf_R96_ergebnis",
    }


def archivieren(d: dict) -> Path:
    """R98: schreibt nach protokoll/ (versioniert), ISO-Timestamp mit Sekunden."""
    PROTOKOLL.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    ziel = PROTOKOLL / f"vollauf_{ts}.json"
    n = 2
    while ziel.exists():  # Zweitlauf in derselben Sekunde — keine Kollision
        ziel = PROTOKOLL / f"vollauf_{ts}_{n}.json"
        n += 1
    d["provenienz"] = _provenienz(d.get("modus", "?"))
    d["zerlegung"] = dict(sorted(Counter(e["klasse"] for e in d["erg"]).items()))
    d["exitcodes"] = {e["datei"]: e["exit"] for e in d["erg"]}
    ziel.write_text(json.dumps(d, indent=1, ensure_ascii=False),
                    encoding="utf-8")
    return ziel


def main(argv: list[str]) -> int:
    voll = "--voll" in argv
    k = zaehle()
    dateien = sorted(k["code"] + k["nur_vertrag"])
    if voll:
        dateien += sorted(k["aussen"])
    d = lauf(dateien)
    d["modus"] = "voll" if voll else "vertrag"
    ERGEBNIS.parent.mkdir(parents=True, exist_ok=True)
    ERGEBNIS.write_text(json.dumps(d, indent=1, ensure_ascii=False),
                        encoding="utf-8")
    bericht(d)
    print(f"\nArtefakt: {ERGEBNIS}")
    if voll:
        print(f"Archiv:   {archivieren(json.loads(ERGEBNIS.read_text(encoding='utf-8')))}")
    return 0 if not any(e["klasse"] in ("GEFALLEN", "BEENDET")
                        for e in d["erg"]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
