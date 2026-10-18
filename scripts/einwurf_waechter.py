#!/usr/bin/env python3
"""Einwurf-Wächter: prüft am Eingang, nicht im Archiv.

§A-ZZZZ111 (Runde 77): **der Sensorfehler aus Runde 76.**

Runde 76 hat `meldung_digest.py` gebaut und in derselben Meldung
eingeräumt: „die Anhänge liegen nicht auf der Platte". Damit war der
Wächter am **Archiv** angeschlossen (TAG7_ABNAHME.md), während die
Wiederholung durch den **Einwurf** kam. Nach Runde 77 ist das kein
Randhinweis mehr, sondern ein Meßbefund:

    Von 261 echten Nutzermeldungen sind 38 bytegleich.
    Davon 37 mit **identischem Zeitstempel** → doppelte Zustellung.
    Davon  1 mit anderem Zeitstempel        → bewußte Wiederholung.
    Die Wiederholungen liegen zu 16/37 auf gerader Position.
    → **keine systematische Duplizierung, sondern zufällige.**

Daraus folgt die Architektur: der Wächter gehört **vor** die Zustellung,
nicht nach der Buchung. Dieses Skript liest den tatsächlichen
Nachrichtenstrom (Transcript-JSONL), nicht die Akte.

Was es tut:

    --strom <pfad.jsonl>     prüft alle Meldungen, meldet Paare
    --einwurf <textdatei>    prüft eine neue Meldung gegen den Strom

Exit 1 heißt: die Meldung ist eine Wiederholung. Der Aufrufer soll sie
**nicht zustellen**, nicht: sie zustellen und protokollieren.

Grenze, ausdrücklich (Runde 76, unverändert): der Digest erkennt
Wiederholung, nicht Wahrheit. Und: dieses Skript kann nur prüfen, was
es lesen kann. Läuft es nicht **vor** dem Kanal, ist es derselbe
Zeuge-nach-der-Tat wie sein Vorgänger. Die Platzierung ist die Arbeit,
nicht der Code.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

MIN_LAENGE = 400          # kürzere Einträge sind Steuertexte, keine Meldungen


class StreamUnlesbar(Exception):
    """Der Stream fehlt oder ist nicht lesbar — Exit 3, nicht Traceback.

    §A-ZZZZ115 (Runde 79): abgegrenzt gegen **defektes Format**. Ein
    kaputtes JSON je Zeile wird übersprungen, nicht abgebrochen —
    Meldungen sind zeilenweise unabhängig. `StreamUnlesbar` meint nur:
    die Datei selbst ist nicht zu öffnen. Ein Zustand, den der Wächter
    nicht verursacht und nicht verhindern kann.
    """
ENVELOPE_MARKER = ("<available_subagent_types>",)


def normalisiere(text: str) -> str:
    """Wie in `meldung_digest.py` — **eine** Normalisierung, zwei Sensoren.

    Der Zeitstempel wird mitgenommen: zwei Zustellungen derselben
    Nachricht haben denselben, zwei bewußte Wiederholungen nicht. Das
    ist der Unterschied zwischen „Kanal dupliziert" und „Mensch
    wiederholt" — er darf nicht wegnormalisiert werden.
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+$", "", t, flags=re.MULTILINE)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip("\n")


def digest(text: str) -> str:
    return hashlib.sha256(normalisiere(text).encode("utf-8")).hexdigest()


def _text_von(nachricht: object) -> str:
    c = (nachricht or {}).get("content") if isinstance(nachricht, dict) else None
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(x.get("text", "") for x in c
                       if isinstance(x, dict) and x.get("type") == "text")
    return ""


def lese_strom(p: Path) -> list[tuple[str, str]]:
    """(zeitstempel, text) je echter Nutzermeldung, in Reihenfolge.

    §A-ZZZZ115 (Runde 79): **Exit 3 hat eine Stelle, nicht nur eine
    Absicht.** Der Wächter ist stateless — aber ein unlesbarer Stream
    ist ein Zustand, den er nicht verursacht und nicht verhindern kann.
    Die Exception wird hier in `StreamUnlesbar` übersetzt; `main`
    entscheidet über den Exit-Code. Vorher wäre ein fehlender Stream
    als Traceback gestorben — genau die Klasse, die zwei Runden
    dominiert hat (PermissionError, Fall 1).
    """
    try:
        f = p.open(encoding="utf-8")
    except OSError as e:
        raise StreamUnlesbar(f"Stream nicht lesbar: {e}") from e
    out: list[tuple[str, str]] = []
    with f:
        for line in f:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("role") != "user":
                continue
            t = _text_von(o.get("message"))
            if len(t) < MIN_LAENGE:
                continue
            if t.lstrip().startswith(ENVELOPE_MARKER):
                continue
            m = re.search(r"<timestamp>(.*?)</timestamp>", t)
            out.append((m.group(1) if m else "?", t))
    return out


def pruefe_strom(strom: list[tuple[str, str]]) -> tuple[int, int, list[str]]:
    """Liefert (paare, kanal_duplikate, bericht).

    `kanal_duplikate` zählt Paare mit **identischem** Zeitstempel: das
    ist Doppelzustellung, nicht Wiederholung durch den Absender. Die
    Unterscheidung ist der eigentliche Befund — wer beides in einen
    Topf wirft, kann die Ursache nicht mehr benennen.
    """
    seen: dict[str, int] = {}
    bericht: list[str] = []
    paare = kanal = 0
    for i, (ts, t) in enumerate(strom):
        h = digest(t)
        if h in seen:
            # §A-ZZZZ114 (Runde 79): **Referenz auf den unmittelbaren
            # Vorgänger, nicht auf das erste Vorkommen.** Bei A,A,A
            # meldete die erste Fassung `#211 == #213` — wahr, aber
            # Δ=2. Der Bericht behauptete damit eine Adjazenz, die er
            # nicht hatte, und `seen[h]` nach dem Treffer *nicht* zu
            # aktualisieren ließ jede weitere Kopie auf das erste
            # Vorkommen zeigen. Jetzt: `j` ist der Vorgänger, und der
            # Eintrag wandert mit. Damit ist Δ immer 1 und die Aussage
            # des Berichts deckt sich mit der Messung.
            j = seen[h]
            paare += 1
            gleich_ts = strom[j][0] == ts
            kanal += gleich_ts
            art = "KANAL-DUPLIKAT" if gleich_ts else "WIEDERHOLUNG"
            bericht.append(f"  {art}: #{j + 1} == #{i + 1}"
                           f"  Δ={i - j}"
                           f"  {'(gleicher Zeitstempel)' if gleich_ts else '(anderer Zeitstempel)'}"
                           f"  sha {h[:12]}")
        seen[h] = i
    return paare, kanal, bericht


def main(argv: list[str]) -> int:
    # §A-ZZZZ111a: **`--einwurf` zuerst prüfen.** Die erste Fassung fragte
    # `--strom` zuerst ab, und weil `--einwurf` den Strom als Referenz
    # mitbrachte, lief jeder Einwurf-Test still als Strom-Test — Exit 1
    # kam vom falschen Zweig. Gefunden durch die Gegenprobe, nicht durch
    # Lesen: der Test war grün aus dem falschen Grund.
    if "--einwurf" in argv:
        if "--strom" not in argv:
            print("--einwurf braucht --strom als Referenz", file=sys.stderr)
            return 2
        try:
            strom = lese_strom(Path(argv[argv.index("--strom") + 1]))
            text = Path(argv[argv.index("--einwurf") + 1]).read_text(
                encoding="utf-8")
        except (StreamUnlesbar, OSError) as e:
            print(f"DIE WACHE TRÄGT NICHT: {e}", file=sys.stderr)
            return 3
        h = digest(text)
        for i, (_, t) in enumerate(strom):
            if digest(t) == h:
                print(f"WIEDERHOLUNG am Einwurf: identisch mit #{i + 1} "
                      f"(sha {h[:12]}) — nicht zustellen.")
                return 1
        print(f"neu am Einwurf (sha {h[:12]})")
        return 0

    if "--strom" in argv:
        p = Path(argv[argv.index("--strom") + 1])
        try:
            strom = lese_strom(p)
        except StreamUnlesbar as e:
            print(f"DIE WACHE TRÄGT NICHT: {e}", file=sys.stderr)
            return 3
        paare, kanal, bericht = pruefe_strom(strom)
        print(f"Meldungen: {len(strom)} | Paare: {paare} "
              f"| davon Kanal-Duplikate: {kanal} | bewußt: {paare - kanal}")
        for z in bericht:
            print(z)
        return 1 if paare else 0

    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
