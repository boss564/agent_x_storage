#!/usr/bin/env python3
"""Publikations-Pipeline: ein Bericht ist erst publiziert, wenn er das
Prosa-Gate besteht (R105, P1 — Gate nicht mehr opt-in).

    python3 scripts/publiziere.py <bericht.md>

Prueft in dieser Reihenfolge, bricht beim ersten Defekt ab:
  1 Belege:   check --strict (Region + Wortlaut)
  2 Prosa:    jede datei:zeile / L<n> muss ein Beleg sein
  3 Publikation: kopiert die PUBLIC-Datei byte-exakt nach publiziert/

Exit 1 = nicht publiziert. Es gibt keinen Warn-Modus: ein Bericht, der
sein eigenes Gate nicht besteht, wird nicht veroeffentlicht.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    bericht = Path(argv[0]).resolve()
    if not bericht.exists():
        print(f"kein Bericht: {bericht}")
        return 1
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "beweis.py"),
                        "check", "--strict", "--prosa", str(bericht)],
                       cwd=REPO, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print("NICHT PUBLIZIERT — der Bericht besteht sein eigenes Gate nicht.")
        return 1
    # Buchung 2 (R106): Pfad+Länge+Digest sind drei Zeilen desselben
    # Dokuments. Die BYTES muessen mit. Jeder Beleg wird base64 in den
    # Bericht geschrieben — 587 Zeichen statt eines Pfads, den der
    # Auditor nicht lesen kann.
    import base64
    belege = [json.loads(z) for z in (REPO / "scripts" / "beweis_ledger.jsonl")
              .read_text(encoding="utf-8").splitlines() if z.strip()]
    kanal = ["", "## Belege — Bytes zum Selbstrechnen", "",
             "    base64 -d | sha256sum   (muss den sha256 unten ergeben)", ""]
    sys.path.insert(0, str(REPO / "scripts"))
    import beweis as B
    for e in belege:
        pfad = (REPO / "publiziert" / f"{e['artefakt'].replace('/', '__')}"
                f"_{e['von']}-{e['bis']}.payload.txt")
        # R106-Selbstbefund: nicht jeder Ledger-Beleg war je publiziert.
        # Die Pipeline ERZEUGT die Bytes aus der Quelle, statt sie zu erwarten.
        if not pfad.exists():
            pfad.parent.mkdir(exist_ok=True)
            pfad.write_bytes(B.kanonisch(e["text"]))
        roh = pfad.read_bytes()
        kanal += [f"### {e['artefakt']}:{e['von']}-{e['bis']}", "",
                  "```", base64.b64encode(roh).decode(), "```", "",
                  f"sha256 = `{e['sha256']}`", ""]
    # Buchung 7 (R106): die Negation darf nicht still verschwinden.
    # Solange die Quelle ungoverned ist, steht die Grenze im Bericht —
    # erzeugt von der Pipeline, nicht vom Gedaechtnis des Autors.
    grenze = ["", "## Was nicht behauptet wird (erzeugt, nicht erinnert)", "",
              "| | Status |", "|---|---|",
              "| Produkt bewacht (Quelle `data/lauf_letzter.json`) | **nein** — die Kopie in `vertrag/` ist eine Projektion |",
              "| Wand `--no-verify`-fest | **nein** — lokal umgehbar; CI existiert, Ergebnis hier unbelegt |",
              "| Regeln/Ledger getrennt | **nein** |", "| per-Datei-Zustand | **nein** |", ""]
    bericht.write_text(bericht.read_text(encoding="utf-8")
                       + "\n".join(kanal) + "\n".join(grenze),
                       encoding="utf-8")
    ziel = REPO / "publiziert" / bericht.name
    ziel.parent.mkdir(exist_ok=True)
    shutil.copyfile(bericht, ziel)
    print(f"publiziert: {ziel.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
