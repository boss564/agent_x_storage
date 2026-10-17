"""Testinvokation dieses Pakets: kein Bytecode, damit die Probe nicht lügt.

Warum diese Datei existiert
---------------------------
In der Schwellen-Probe (TAG7_ABNAHME.md §5.4e) war der erste Lauf bei
Schwelle 3 *und* 5 grün. Ursache war ein veralteter ``.pyc`` im
Ladepfad: pytest maß gegen Bytecode von vor der Änderung. Erst
``__pycache__`` leeren ließ die Probe greifen.

Das ist derselbe Mechanismus wie in §5.4d, diesmal als Messfehler in der
Messung selbst — und in der einzigen Richtung, die niemand bemerkt:
**grün**. Eine Probe, die bei jeder Eingabe dasselbe sagt, sagt nichts.

``-B`` beim Dienst verlangt einen Neustart aus falschem Anlaß und ist
deshalb nach der Abnahme gebucht. ``-B`` beim Testlauf verlangt gar
nichts: hier gibt es keinen laufenden Prozeß, dessen Bytecode sich
ändert. Deshalb steht es hier, und nicht als Merksatz im Kopf.

Benutzung::

    PYTHONPATH=. python3 order_execution_engine/run_tests.py
    PYTHONPATH=. python3 order_execution_engine/run_tests.py -k threshold

Die Umgebungsvariable ``PYTHONDONTWRITEBYTECODE`` wird **vor** dem Import
von pytest gesetzt — pytest selbst lädt beim Start Module aus dem Paket.
Ein ``export`` in der Shell wäre gleichwertig, aber nicht erzwingbar;
hier ist es Teil der Invokation.
"""

from __future__ import annotations

import os
import pathlib

# Vor jedem Import aus dem Paket: kein Bytecode schreiben.
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
# sys.dont_write_bytecode greift auch für bereits laufende Interpreter —
# die Umgebungsvariable allein wirkt nur beim Start neuer Prozesse.
import sys  # noqa: E402

sys.dont_write_bytecode = True

# Das Repo-Wurzelverzeichnis muss auf sys.path stehen, sonst findet pytest
# `order_execution_engine` nicht, egal von wo es gestartet wird. Auch das
# gehört in die Invokation, nicht in ein `export` im Kopf des Ausführenden.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest  # noqa: E402

if __name__ == "__main__":
    here = pathlib.Path(__file__).resolve().parent
    # cwd auf das Paket setzen: einige Tests lesen Quellen über relative
    # Pfade. Ohne das hängt das Ergebnis davon ab, wer den Test startet —
    # dieselbe Form von Abhängigkeit, die diese Akte elf Runden beschäftigt.
    os.chdir(_ROOT)
    argv = [
        str(here / "tests"),
        "-q",
        # Kein pytest-Cache: `lastfailed` überlebt sonst Schwellen-Änderungen
        # und ändert, welche Tests laufen.
        "-p", "no:cacheprovider",
        *sys.argv[1:],
    ]
    raise SystemExit(pytest.main(argv))
