#!/usr/bin/env python3
"""Holt den R106-Payload byte-exakt aus dem Transkript (R110).

Anlass: In R109 wurde die R106-Kette von Hand in einen Test getippt --
und dabei der eigene R108-Text ('Veetragsscope') als vermeintliche
Quelle uebernommen. Der Diff lief dann gegen eine Fixture, die den zu
widerlegenden Fehler selbst enthielt.

Regel (R110): Kein Test und kein Bericht darf die R106-Kette als
Literal enthalten. Sie wird zur Laufzeit aus dem Transkript gelesen.

Kriterium: die Zeile mit dem R106-Payload ist eine assistant-Nachricht,
die mit 'Hier sind die Bytes' beginnt. Der Base64-Block darin ist die
Lieferung. Die Fixture-Zeilen aus R109 tragen diese Ueberschrift nicht.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# §SP-832 (2026-11-05): **der Harness-Zaun hat recht gehabt, nicht die Ausnahme.**
# Bis hier stand der Live-Transcript hart kodiert in scripts/ -- genau das,
# was der Zaun verbietet (Anlass R85: eine Suite, die den Live-Strom liest,
# teilt dessen Blindheit). Der Fix ist NICHT eine Ausnahme in AUSNAHMEN,
# sondern der Pfad wird zur Laufzeit hereingereicht:
#
#   1. `--transkript <pfad>`  (explizit, fuer den Menschen)
#   2. Env `AGENTX_TRANSKRIPT` (fuer Test/Harness, ohne Argument)
#
# Kein Default auf einen Live-Pfad: fehlt beides, bricht der Aufruf mit
# einer benannten Meldung ab. Ein stiller Fallback waere derselbe Defekt
# in neuer Form. Der Gegenstand dieses Skripts -- der R106-Payload -- ist
# byte-exakt (SHA unten) und damit unabhaengig vom Zieldatei-Pfad.

def _transkript_aus_umgebung() -> Path:
    """Pfad aus Argument oder Env. Kein Live-Default (Zaun §SP-832)."""
    for i, a in enumerate(sys.argv):
        if a == "--transkript" and i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1])
    env = os.environ.get("AGENTX_TRANSKRIPT")
    if env:
        return Path(env)
    raise SystemExit(
        "Transkript nicht gesetzt: --transkript <pfad> oder AGENTX_TRANSKRIPT. "
        "Kein Live-Default (Harness-Zaun).")

MARKER = "Hier sind die Bytes"
MUSTER = re.compile(r"CUBlY2hvICL[A-Za-z0-9+/=]{200,}")
# Die Lieferung ist 439 Byte: 588 Base64-Zeichen. Die R107-Prosa
# (440 Byte, 'Vertragsscope' im Header) ist auch 588 lang -- deshalb
# unterscheidet der Marker, nicht die Laenge.
ERWARTETE_SHA = "30257636d107f7019074d85de4742e119f0faa24ddcf6340e0741d4ce7b00b52"


def hole(pfad: Path | None = None) -> str:
    if pfad is None:
        pfad = _transkript_aus_umgebung()
    treffer = []
    for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), 1):
        if MARKER not in zeile:
            continue
        for m in MUSTER.finditer(zeile):
            treffer.append((nr, m.group(0)))
    if not treffer:
        raise SystemExit("R106-Payload nicht gefunden (Marker fehlt?)")
    if len(treffer) > 1:
        raise SystemExit(f"Mehrdeutig: {len(treffer)} Kandidaten "
                         f"in Zeilen {[t[0] for t in treffer]}")
    nr, b64 = treffer[0]
    roh = base64.b64decode(b64)
    sha = hashlib.sha256(roh).hexdigest()
    if sha != ERWARTETE_SHA:
        raise SystemExit(f"Zeile {nr}: sha {sha} != erwartet {ERWARTETE_SHA}")
    return b64


def main() -> int:
    b64 = hole()
    roh = base64.b64decode(b64)
    print(f"len={len(roh)} sha={hashlib.sha256(roh).hexdigest()}")
    print(b64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
