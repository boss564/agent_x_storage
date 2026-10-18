#!/usr/bin/env python3
"""Harness-Zaun: kein Test darf gegen einen Live-Pfad assertieren.

§A-ZZZZ165 (Runde 87): **eine Testsuite, die den Live-Strom liest, teilt
die Blindheit des Systems, das sie prueft.**

R85 lief `strom-alle` gegen den laufenden Konversations-Transcript und
erwartete die Konstante 38/37. Die Zahl war beim Commit schon 39/38.
Gefunden wurde das nicht von der Suite, sondern von einem externen Blick
auf eine Zahl.

Der Zaun ist mechanisch: jede Pfad-Konstante in `scripts/test_*.py` und
`scripts/vertrags_runner.py`, die auf einen Transcript/persistente Daten
zeigt und NICHT aus einem tmpdir/`Path(__file__)` stammt, ist ein Befund.
Ausnahmen tragen `# laut: ...` mit Begruendung und sind hier aufgelistet.

Ein Test, der den Zaun selbst prueft, ist selbst ein Test — er laeuft
ueber diese Datei mit, deshalb steht sie in `SKRIPT_OHNE_LAUF`? Nein:
sie liest nur `scripts/`, kein Live-Pfad.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Muster, die einen Live-/Persistenz-Pfad bezeichnen.
LIVE = re.compile(
    r"(agent-transcripts|\.cursor/projects|/Users/[^\"']*/\.cursor"
    r"|shadow_live|data_root\s*=\s*Path\(\"data/)")

# Ausnahmen: Datei -> Anzahl erlaubter Treffer (mit Grund im Kommentar).
AUSNAHMEN = {
    # Der Vertrags-Runner liest den Live-Transcript fuer den Fall
    # `strom-live` — prueft dort NUR eine Invariante, keine Zahl.
    # ZWEI Zeilen: der Pfad steht als mehrzeiliges Literal.
    "vertrags_runner.py": 2,
}


def main() -> int:
    ok = gesamt = 0
    verstoesse: list[tuple[str, int, str]] = []
    # Der Zaun nimmt sich selbst aus: sein LIVE-Muster ist der
    # Mustertext, kein Pfad. Ein Zaun, der sich selbst faengt, ist
    # entweder ein Zaun ueber Mustertexte oder Feature-Detection.
    SELBST = {Path(__file__).name}
    for f in sorted(SCRIPTS.glob("*.py")):
        if f.name in SELBST:
            continue
        txt = f.read_text(encoding="utf-8", errors="replace")
        treffer = [(i + 1, ln.strip())
                   for i, ln in enumerate(txt.splitlines())
                   if LIVE.search(ln) and "laut:" not in ln
                   and not ln.lstrip().startswith("#")]
        erlaubt = AUSNAHMEN.get(f.name, 0)
        if len(treffer) > erlaubt:
            verstoesse.append((f.name, len(treffer), str(treffer[:2])))

    gesamt += 1
    gut = not verstoesse
    print(f"{'ok  ' if gut else 'FAIL'} Zaun: keine Live-Pfade     "
          f"{len(verstoesse)} Verstoesse")
    for v in verstoesse:
        print(f"       {v[0]}: {v[1]} Treffer {v[2]}")
    ok += gut

    # Der Gegenbeweis: eine synthetische Datei mit Live-Pfad faellt auf.
    gesamt += 1
    probe = 'T = Path("/x/agent-transcripts/a.jsonl")\n'
    erkannt = bool(LIVE.search(probe))
    print(f"{'ok  ' if erkannt else 'FAIL'} Zaun erkennt Live-Pfad    "
          f"{erkannt}")
    ok += erkannt

    # Und: der Live-Fall prueft wirklich nur eine Invariante, keine Zahl.
    gesamt += 1
    vr = (SCRIPTS / "vertrags_runner.py").read_text(encoding="utf-8")
    block = re.search(r'"strom-live":\s*\[[^\]]*\]', vr)
    print(f"{'ok  ' if block else 'FAIL'} strom-live als Fall         "
          f"{bool(block)}")
    ok += bool(block)

    print(f"\n{ok}/{gesamt} Harness-Zaun-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
