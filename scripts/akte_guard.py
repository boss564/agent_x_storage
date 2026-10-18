#!/usr/bin/env python3
"""Der Schreib-Guard für die Akte — `menge_neu ⊇ menge` **vor** dem rename.

§A-NS (Runde 52): In Runde 51 wurde `TAG7_ABNAHME.md` beim Ersetzen eines
Blocks von 5.986 auf 177 Zeilen gekürzt. Gefunden hat es `git diff --stat`
— von Hand. Kein Prüfer sah es, weil **alle** gegen committete Bäume
messen und der Verlust im Arbeitsbaum passierte, also im Fenster
**zwischen** zwei Commits.

Die Antwort ist deshalb nicht ein vierter Prüfer über committeten
Bäumen, sondern der Schreibvorgang selbst:

    vorher:  menge := bloecke(datei)
    temp:    schreibe nach datei.tmp
    nachher: menge_neu := bloecke(temp)
             menge_neu ⊇ menge   sonst: kein rename, laut
    rename:  atomar

Das fängt den Fall **vor** dem Commit, im selben Prozess, ohne `git`.
Ein Guard, der nur committete Bäume kennt, ist per Konstruktion einen
Schritt hinter dem Fehler.

Nebenwirkung, benannt: ein Guard, der abbricht, hinterlässt `.tmp` —
`guarded_write` räumt ihn im `finally` weg. Und der Guard schützt nur
Dateien, die ihn rufen; `git diff --stat` bleibt für den Rest nötig.

Rückgabe von `guarded_write`: `(ok, meldung)`. Bei `ok=False` ist die
Datei **unverändert** — das ist die Zusicherung, nicht die Absicht.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

# Dieselbe Blockdefinition wie `check_claude_md._akte_blocks`: eine
# Überschrift `### §71.NN — …` beginnt einen Block. Der Guard darf keine
# eigene Semantik haben — zwei Definitionen von „Block" wären zwei Zahlen.
_BLOCK_RE = re.compile(r"^### (§71\.\d+[a-z]?) — ", re.M)


def blocks(text: str) -> set[str]:
    """Die Menge der Blocküberschriften einer Akte."""
    return set(_BLOCK_RE.findall(text))


def line_count(text: str) -> int:
    return len(text.splitlines())


def check_shrink(old: str, new: str) -> list[str]:
    """Verliert `new` Blöcke oder Zeilen gegen `old`?

    Zwei Regeln, und die zweite ist die aus dem Vorfall:

      1. `bloecke(new) ⊇ bloecke(old)` — kein Block darf verschwinden.
      2. `zeilen(new) >= zeilen(old)` — eine Akte, die schrumpft, ist
         entweder eine Berichtigung (dann als eigener Block) oder ein
         Unfall. Beides ist laut, nicht still.

    Leere `old` (erste Fassung) ist immer in Ordnung — es gibt nichts
    zu verlieren.
    """
    out: list[str] = []
    if not old.strip():
        return out
    gone = blocks(old) - blocks(new)
    for b in sorted(gone):
        out.append(f"Block {b} fehlt — Runde verloren")
    old_n, new_n = line_count(old), line_count(new)
    if new_n < old_n:
        out.append(f"Zeilen {old_n} -> {new_n} — Verlust von {old_n - new_n}")
    return out


def guarded_write(path: Path, new_text: str,
                  whole: bool = True) -> tuple[bool, str]:
    """Schreibt `new_text` nach `path` — nur wenn nichts verloren geht.

    `whole=True`: `new_text` **ersetzt** die Datei; geprüft wird gegen den
    bisherigen Inhalt. `whole=False`: `new_text` wird **angehängt**; die
    Prüfung ist dann strukturell erfüllt (Anhängen kann nichts entfernen),
    wird aber trotzdem gerechnet — ein Anhang, der die Blockmenge
    verändert, ist ein Zeichen für einen falschen Aufruf.

    Ablauf: lesen → prüfen → `.tmp` schreiben → aus `.tmp` zurücklesen und
    erneut prüfen → atomar `os.replace`. Der zweite Lesevorgang ist kein
    Misstrauen gegen sich selbst, sondern gegen die **Codepage**: was auf
    der Platte steht, ist die Wahrheit, was im Speicher steht, die Absicht.
    """
    path = Path(path)
    old = ""
    if path.exists():
        try:
            old = path.read_text(encoding="utf-8")
        except OSError as exc:                       # pragma: no cover
            return False, f"{path}: nicht lesbar ({exc}) — kein Schreiben"
    candidate = (old + new_text) if not whole else new_text
    problems = check_shrink(old, candidate)
    if problems:
        return False, "; ".join(problems)
    tmp: str | None = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                   dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(candidate)
            fh.flush()
            os.fsync(fh.fileno())
        # Zweiter Blick: was auf der Platte steht, nicht was im Speicher stand.
        on_disk = Path(tmp).read_text(encoding="utf-8")
        again = check_shrink(old, on_disk)
        if again:
            return False, "; ".join(again)
        os.replace(tmp, path)
        tmp = None
        return True, f"{path.name}: {line_count(old)} -> {line_count(on_disk)} Zeilen"
    except OSError as exc:                           # pragma: no cover
        return False, f"{path}: Schreiben fehlgeschlagen ({exc})"
    finally:
        # §A-NS: ein abbrechender Guard hinterlässt `.tmp` — sonst wächst
        # der Baum mit jedem Fehlversuch.
        if tmp and Path(tmp).exists():
            try:
                os.unlink(tmp)
            except OSError:                          # pragma: no cover
                pass


def append_block(path: Path, block: str) -> tuple[bool, str]:
    """Hängt einen Block an die Akte an — die Form, die Runde 51 gelernt hat."""
    text = block if block.endswith("\n") else block + "\n"
    return guarded_write(path, "\n" + text, whole=False)


if __name__ == "__main__":                            # pragma: no cover
    import sys
    target = Path(sys.argv[1] if len(sys.argv) > 1
                  else "order_execution_engine/ops/TAG7_ABNAHME.md")
    ok, msg = append_block(target, "### §71.99 — Probe\n\nText.\n")
    print(("OK   " if ok else "ABBR "), msg)
