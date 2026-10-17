"""Testinvokation dieses Pakets: kein Bytecode, damit die Probe nicht lügt.

Warum diese Datei existiert
---------------------------
In der Schwellen-Probe (TAG7_ABNAHME.md §5.4e) war der erste Lauf bei
Schwelle 3 *und* 5 grün. Ursache war ein veralteter ``.pyc`` im
Ladepfad: pytest maß gegen Bytecode von vor der Änderung.

Das ist derselbe Mechanismus wie in §5.4d, diesmal als Messfehler in der
Messung selbst — und in der einzigen Richtung, die niemand bemerkt:
**grün**.

Was hier steht und was nicht
----------------------------
``PYTHONDONTWRITEBYTECODE`` **muss** hier gesetzt werden: die Variable wirkt
vor dem Interpreterstart und kann von ``pytest.ini`` nicht gesetzt werden.
Alles andere ist inzwischen woanders und damit launcher-unabhängig:

======================  =========================================
Importierbarkeit        ``pytest.ini`` → ``pythonpath = .``
Cache-Verzeichnis       ``pytest.ini`` → ``cache_dir``
Relative Testpfade      ``Path(__file__).parent`` im Test
======================  =========================================

Frühere Fassungen dieser Datei setzten zusätzlich ``sys.path`` und
``os.chdir``. Beides waren **Bandagen**: sie machten den Lauf unter diesem
Starter grün und verdeckten, dass direktes ``pytest`` brach (11
Collection-Fehler, ``FileNotFoundError``). Wer sie entfernt, sieht den
Fehler — und behebt ihn dort, wo er sitzt.

Benutzung::

    python3 order_execution_engine/run_tests.py
    python3 order_execution_engine/run_tests.py -k threshold

Gleichwertig, ohne diesen Starter::

    PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest order_execution_engine/tests
"""

from __future__ import annotations

import os

# Vor jedem Import aus dem Paket: kein Bytecode schreiben.
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
# sys.dont_write_bytecode greift auch für den bereits laufenden Interpreter;
# die Umgebungsvariable allein wirkt nur beim Start neuer Prozesse.
import sys  # noqa: E402

sys.dont_write_bytecode = True

import pathlib  # noqa: E402

import pytest  # noqa: E402

if __name__ == "__main__":
    here = pathlib.Path(__file__).resolve().parent
    argv = [
        str(here / "tests"),
        "-q",
        *sys.argv[1:],
    ]
    raise SystemExit(pytest.main(argv))
