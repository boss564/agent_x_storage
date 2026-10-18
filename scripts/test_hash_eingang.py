#!/usr/bin/env python3
"""Hash-Eingangs-Test: was darf in den Hash, was nicht.

§A-ZZZZ123 (Runde 82): **"leer erfuellt" ist keine Mauer.**

Der Identitaets-Audit der Runde 81 belegte, welche Felder heute in den
Hash gehen — und dass heute kein weiteres Diagnose-Feld im Schema
liegt. Das ist eine Messung der Gegenwart, kein Schutz der Zukunft:
fuegt jemand morgen ein Sequenz- oder Kanal-Feld hinzu, ist der
Zeitstempel-Fehler von Runde 79 wieder da, ohne dass ein Test schreit.

Dieser Test assertiert den Eingang mechanisch:

    1. digest() nimmt GENAU einen Argument (text) — kein zweiter Parameter
       kann stillschweigend mitgehasht werden.
    2. normalisiere() entfernt den Zeitstempel, bevor gehasht wird.
    3. Zwei Texte, die sich NUR im Zeitstempel unterscheiden, haben
       denselben Hash.
    4. Zwei Texte, die sich im Inhalt unterscheiden, haben verschiedene
       Hashes — auch bei gleichem Zeitstempel.
    5. _text_von() projiziert message.content und ignoriert jedes andere
       Feld des Envelopes.

Faellt einer der Punkte, ist die Invariante "Identitaet = Inhalt"
verletzt, und das ist ein Befund, kein Testfehler.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import einwurf_waechter as w  # noqa: E402

FEHLER: list[str] = []


def pruefe(name: str, ok: bool, detail: str) -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name:34s} {detail}")
    if not ok:
        FEHLER.append(name)


def main() -> int:
    # 1. Signatur von digest: genau ein Parameter.
    sig = inspect.signature(w.digest)
    pruefe("digest-signatur",
           list(sig.parameters) == ["text"],
           f"Parameter={list(sig.parameters)} — erwartet ['text']")

    # 2. Zeitstempel wird vor dem Hash entfernt.
    a = "<timestamp>T1</timestamp>\nInhalt A"
    b = "<timestamp>T2</timestamp>\nInhalt A"
    pruefe("normalisiere-entfernt-ts",
           "<timestamp>" not in w.normalisiere(a),
           "kein <timestamp> im normalisierten Text")

    # 3. Identischer Inhalt, verschiedener Zeitstempel => gleicher Hash.
    pruefe("ts-egal-fuer-hash",
           w.digest(a) == w.digest(b),
           f"{w.digest(a)[:12]} == {w.digest(b)[:12]}")

    # 4. Verschiedener Inhalt, gleicher Zeitstempel => anderer Hash.
    c = "<timestamp>T1</timestamp>\nInhalt C"
    pruefe("inhalt-bestimmt-hash",
           w.digest(a) != w.digest(c),
           f"{w.digest(a)[:12]} != {w.digest(c)[:12]}")

    # 5. _text_von projiziert nur content, nicht role/type/status/id.
    env = {"role": "user", "type": "message", "status": "sent",
           "id": "abc", "message": {"content": "X" * 500}}
    pruefe("_text_von-nur-content",
           w._text_von(env["message"]) == "X" * 500,
           f"len={len(w._text_von(env['message']))}, erwartet 500")

    # 5b. Ein zusaetzliches Feld IM message-Objekt darf nichts beitragen.
    env2 = {"content": "X" * 500, "seq": 99, "channel": "y"}
    pruefe("_text_von-ignoriert-extra",
           w._text_von(env2) == w._text_von({"content": "X" * 500}),
           "seq/channel tragen nichts bei")

    print(f"\n{6 - len(FEHLER)}/6 Hash-Eingangs-Pruefungen gruen")
    return 0 if not FEHLER else 1


if __name__ == "__main__":
    raise SystemExit(main())
