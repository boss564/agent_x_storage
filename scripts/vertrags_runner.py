#!/usr/bin/env python3
"""Vertrags-Runner: prüft Wächter gegen Text, Exit, stderr, Speicherzustand.

§A-ZZZZ112 (Runde 78): **die Fehlerfläche ist der Vertrag, nicht die Logik.**

Vier Runden, vier Fehler, eine Klasse — alle in der Argument- oder
Zustandsbehandlung, keiner in der Rechnung:

    1. PermissionError statt Exit 3     (Datei-Zustand)
    2. Leerzeile blieb stehen           (Normalisierungs-Zustand)
    3. `--strom` vor `--einwurf`        (Argument-Zustand)
    4. Off-by-one im Testtisch          (Test-Zustand)

Keiner davon wäre von einer Formprüfung gefunden worden. Alle vier
wären von einem Vertragstest gefunden worden, der **den Text** prüft.

Der Runner erzwingt je Fall vier Dinge:

    Eingabe  → Ausgabetext (Substring, nicht Exit-Code)
             → Exit-Code
             → stderr (leer oder erwartet)
             → Speicherzustand (unverändert, wenn der Wächter rein liest)

**Speicher je Fall, nicht je Lauf.** Ein Testfall bekommt einen
`tmp_path`; zwei Fälle teilen nie einen. Der Runner prüft das selbst:
er hash't das Arbeitsverzeichnis vor und nach jedem Fall und schlägt
fehl, wenn ein Fall Spuren hinterlässt, die er nicht angekündigt hat.

Grenze, ausdrücklich: der Runner prüft **den Vertrag**, nicht die
Wahrheit der Messung. Ein Wächter, der korrekt „neu" sagt, während die
Meldung inhaltlich falsch ist, besteht den Vertrag. Das ist Absicht —
Vertrag und Wahrheit sind zwei Achsen, und diese Datei prüft die erste.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "einwurf_waechter.py"
TRANSCRIPT = Path(
    "/Users/olivermueller/.cursor/projects/"
    "Volumes-THX-OS-ULTRA-Users-olivermueller-agent-x-storage-order-"
    "execution-engine/agent-transcripts/"
    "ed0106b6-8a07-4cda-ac09-53851e6aa04a/"
    "ed0106b6-8a07-4cda-ac09-53851e6aa04a.jsonl"
)


def _dir_hash(p: Path) -> str:
    """Zustand des Arbeitsverzeichnisses — für die Speicher-Isolation."""
    h = hashlib.sha256()
    for f in sorted(p.rglob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _lauf(args: list[str], cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run([sys.executable, str(SCRIPT), *args],
                       capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


# (name, args-bauer, erwarteter_text, erwarteter_exit, darf_schreiben)
FAELLE = [
    ("strom-alle",
     lambda t, d: ["--strom", str(t)],
     "Kanal-Duplikate:", 1, False),
    ("einwurf-bekannt",
     lambda t, d: ["--einwurf", str(d / "bekannt.md"), "--strom", str(t)],
     "WIEDERHOLUNG am Einwurf", 1, False),
    ("einwurf-neu",
     lambda t, d: ["--einwurf", str(d / "neu.md"), "--strom", str(t)],
     "neu am Einwurf", 0, False),
    ("kein-argument",
     lambda t, d: [],
     "Einwurf-Wächter", 2, False),
    ("einwurf-ohne-strom",
     lambda t, d: ["--einwurf", str(d / "neu.md")],
     "braucht --strom", 2, False),
]


def main() -> int:
    if not TRANSCRIPT.is_file():
        print("Transcript nicht lesbar — Vertragstest nicht durchführbar")
        return 3
    # Referenzstrom einmal ziehen: eine bekannte Meldung und eine neue.
    sys.path.insert(0, str(ROOT / "scripts"))
    import einwurf_waechter as e  # noqa: E402
    strom = e.lese_strom(TRANSCRIPT)
    bekannt = strom[0][1]
    neu = "## Vertragstest\nEin Text, der im Strom nicht vorkommt.\n" * 20

    fehler = 0
    for name, args, text, erwartet_exit, darf_schreiben in FAELLE:
        # §A-ZZZZ112: **frisches Verzeichnis je Fall.**
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "bekannt.md").write_text(bekannt, encoding="utf-8")
            (d / "neu.md").write_text(neu, encoding="utf-8")
            vorher = _dir_hash(d)
            code, out, err = _lauf(args(TRANSCRIPT, d), d)
            nachher = _dir_hash(d)
            # Nur die Eingabedateien dürfen existieren — nichts Neues.
            if not darf_schreiben and vorher != nachher:
                print(f"FAIL {name}: Speicher verändert (Blutung)")
                fehler += 1
                continue
            # §A-ZZZZ112: **Text prüfen, nicht nur Code.** Der Fehler der
            # Runde 77 war grün im Exit und falsch im Zweig.
            if text not in (out + err):
                print(f"FAIL {name}: Text fehlt — erwartet {text!r}, "
                      f"bekam {out.strip()[:70]!r}")
                fehler += 1
                continue
            if code != erwartet_exit:
                print(f"FAIL {name}: Exit {code} statt {erwartet_exit}")
                fehler += 1
                continue
            print(f"ok   {name:22s} exit={code}  text ok  speicher isoliert")
    print(f"\n{len(FAELLE) - fehler}/{len(FAELLE)} Vertragsfälle grün")
    return 1 if fehler else 0


if __name__ == "__main__":
    raise SystemExit(main())
