#!/usr/bin/env python3
"""Meldungs-Digest: kein neuer Befund ohne neue Bytes.

**DEPRECATED seit Runde 79 — ersetzt durch `scripts/einwurf_waechter.py`.**
Grund: dieser Wächter liest die **Akte**, nicht den **Einwurf**. Er war
nie verdrahtet (grep auf Makefile/CI/hooks leer) und hätte den Fall
(3)==(4) nicht gesehen, weil er den Eingangskanal nicht liest.
Ein Wächter, ein Name: wer hier etwas verdrahtet, verdrahtet den
falschen. Der Nachfolger prüft Text, Exit, stderr und Speicherzustand
gegen `scripts/waechter_vertrag.json` (`make werktest`).

§A-ZZZZ109 (Runde 76): **die Wiederholung als Prüfgegenstand.**

Runde 75 hat einen Fall offengelegt, den keine Regel dieser Akte bisher
kannte: eine Meldung, deren Inhalt identisch mit der vorigen ist, während
nur der Index fortschreitet. Für den Code gibt es die Regel längst —
„kein Grün ohne erstes Rot". Für Prosa fehlte sie.

Die Wache ist billig und lokal:

    python3 scripts/meldung_digest.py --neu <datei>
    python3 scripts/meldung_digest.py --alle

`--neu` rechnet `sha256` über den **normalisierten** Text (Whitespace am
Rand entfernt, Zeilenenden vereinheitlicht, Leerzeilenfolgen kollabiert),
vergleicht gegen `.meldung-digests.json` und bricht mit Exit 1 ab, wenn
der Digest bereits vorkommt. Nicht normalisiert würde ein einzelnes
Leerzeichen am Ende den Test umgehen.

Warum normalisiert: der Befund lautet „derselbe Inhalt, anderer
Dateiname". Ein Byte-Vergleich fängt das nur, wenn wirklich jedes Byte
gleich ist. Ein Vergleich nach Normalisierung fängt es auch dann, wenn
jemand die Datei neu abschreibt.

Grenze, ausdrücklich: der Digest erkennt **Wiederholung**, nicht
**Wahrheit**. Eine neue Runde mit falschem Inhalt hat einen neuen
Digest — und ist trotzdem falsch. Die Wache schließt genau eine Lücke,
nicht alle.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGESTS = ROOT / ".meldung-digests.json"


def normalisiere(text: str) -> str:
    """Was übrig bleibt, wenn man Schreibweisen-Unterschiede wegnimmt.

    Bewußt **konservativ**: nur Whitespace, Zeilenenden und Leerzeilen.
    Kein Lowercasing, keine Wortumsortierung — sonst würde der Digest
    auch inhaltlich verschiedene Meldungen als gleich melden, und die
    Wache wäre schlimmer als ihr Fehlen.
    """
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+$", "", t, flags=re.MULTILINE)
    # §A-ZZZZ110: erst kollabieren, **dann** trimmen. Die erste Fassung
    # ließ eine Leerzeile dort, wo keine war — `A\nB` und `A\n\n\nB`
    # ergaben verschiedene Digests, und die Wache war blind gegen genau
    # die Schreibweisen-Drift, für die sie gebaut ist.
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip("\n")


def digest(text: str) -> str:
    return hashlib.sha256(normalisiere(text).encode("utf-8")).hexdigest()


def _lade() -> dict[str, str]:
    try:
        return json.loads(DIGESTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _speichere(d: dict[str, str]) -> bool:
    """Schreibt die Digests. Ein Fehler ist ein Befund, kein Traceback.

    §A-ZZZZ110 (Runde 76): der erste Lauf dieses Skripts scheiterte mit
    `PermissionError` als Stacktrace — derselbe Fehler, den Runde 72 an
    `.selftest-exit` repariert hat, hier neu gebaut. Ein Kanal, der nicht
    schreiben kann, ist ein Befund (die Wache trägt nicht) und keine
    Ausnahme, die den Aufrufer erschlägt.
    """
    try:
        DIGESTS.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
        return True
    except OSError:
        return False


def main(argv: list[str]) -> int:
    d = _lade()
    if "--alle" in argv:
        # Rückwärts, damit der jüngste Eintrag den Namen trägt.
        inv: dict[str, list[str]] = {}
        for name, h in sorted(d.items()):
            inv.setdefault(h, []).append(name)
        doppelt = {h: n for h, n in inv.items() if len(n) > 1}
        if doppelt:
            print(f"Wiederholungen: {len(doppelt)}")
            for h, namen in doppelt.items():
                print(f"  {h[:16]}: {', '.join(namen)}")
            return 1
        print(f"keine Wiederholung unter {len(d)} Meldungen")
        return 0

    if "--neu" not in argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    i = argv.index("--neu")
    if i + 1 >= len(argv):
        print("--neu braucht einen Dateipfad", file=sys.stderr)
        return 2
    p = Path(argv[i + 1])
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        print(f"nicht lesbar: {e}", file=sys.stderr)
        return 2
    h = digest(text)
    vorher = {k: v for k, v in d.items() if v == h}
    if vorher:
        print(f"WIEDERHOLUNG: {p.name} hat den Inhalt von "
              f"{', '.join(sorted(vorher))} (sha256 {h[:16]})")
        print("  Kein neuer Befund ohne neue Bytes. Die Meldung wird nicht "
              "als Runde gezählt.")
        return 1
    d[p.name] = h
    if not _speichere(d):
        print(f"BEFUND: Digest für {p.name} nicht schreibbar — die Wache "
              f"trägt nicht, die Wiederholungsprüfung ist für diesen Lauf "
              f"unwirksam (sha256 {h[:16]})", file=sys.stderr)
        return 3
    print(f"neu: {p.name} (sha256 {h[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
