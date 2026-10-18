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


def block_bodies(text: str) -> dict[str, str]:
    """`{§71.NN: Blockkörper}` — der Text zwischen zwei Überschriften."""
    marks = list(_BLOCK_RE.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m.group(1)] = text[m.end():end]
    return out


def _body_hash(body: str) -> str:
    import hashlib
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def block_hashes(text: str) -> dict[str, str]:
    """`{§71.NN: sha256(Blockkörper)}` — die Identität je Block (§A-ZE).

    `zeilen >= vorher` ist eine **Zahl**, nicht eine **Menge**: zwei
    gelöscht, zwei hinzugefügt ist grün, und der Verlust steht still in
    der Akte. Die Kopfzeile fängt es nicht, weil sie den Block sieht; die
    Zeilenzahl fängt es nicht, weil sie nur zählt.

    Der Hash fängt es: ein Block, dessen Körper sich ändert, hat einen
    anderen Hash. Er ist **strikt** — auch eine gewollte Berichtigung ist
    rot, und muß als eigener Block geschrieben werden, nicht als stille
    Korrektur. Das ist derselbe Vertrag wie bei `bloecke`, nur eine Ebene
    tiefer: die Akte ist append-only, nicht „append-with-edits".
    """
    return {b: _body_hash(t) for b, t in block_bodies(text).items()}


def line_count(text: str) -> int:
    return len(text.splitlines())


def check_shrink(old: str, new: str) -> list[str]:
    """Verliert `new` Blöcke, Zeilen oder **Blockinhalte** gegen `old`?

    Drei Regeln, und die dritte ist die aus Runde 53:

      1. `bloecke(new) ⊇ bloecke(old)` — kein Block darf verschwinden.
      2. `zeilen(new) >= zeilen(old)` — eine Akte, die schrumpft, ist
         entweder eine Berichtigung (dann als eigener Block) oder ein
         Unfall. Beides ist laut, nicht still.
      3. **`hash(block, new) == hash(block, old)`** für jeden Block, der
         in beiden steht — sonst hat sich der Blockkörper geändert und
         die Zeilenzahl hat es nicht gemerkt.

    **§A-ZE (Runde 53, nach dem ersten Selbsttest):** Regel 3 in der
    ersten Fassung war **zu streng**. `append_block` hängt an `new` an —
    und der letzte Block der Akte hat dann keinen Endmarker mehr, also
    wächst *sein* Körper um den Anhang. Ergebnis: `Anhaengen wurde
    verweigert`. Der Fix ist keine Ausnahme, sondern die richtige Regel:
    **Präfix-Treue.** Ein Block darf nur **am Ende** wachsen; wer ihm
    vorne oder in der Mitte etwas nimmt oder ersetzt, verändert das
    Präfix. Das ist `new_body.startswith(old_body)` — und es erlaubt
    Anhängen, während `Text.` → `Text! ` (gleiche Länge, anderes Präfix)
    rot bleibt.

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
    old_b, new_b = block_bodies(old), block_bodies(new)
    for b in sorted(set(old_b) & set(new_b)):
        if not new_b[b].startswith(old_b[b]):
            out.append(f"Block {b} geändert ({_body_hash(old_b[b])} -> "
                       f"{_body_hash(new_b[b])})"
                       " — Berichtigung als neuer Block, nicht still")
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
