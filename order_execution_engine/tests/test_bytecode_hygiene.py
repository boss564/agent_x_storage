"""Zeuge gegen den Bytecode, der die Probe fälscht.

Warum dieser Test existiert
----------------------------
Bei der Schwellen-Probe (TAG7_ABNAHME.md §5.4e) war der Lauf bei Schwelle 3
*und* 5 grün. Ursache: ein veralteter ``.pyc`` im Ladepfad — pytest maß
gegen Bytecode von vor der Änderung. Erst das Leeren von ``__pycache__``
ließ die Probe greifen.

Das ist ein Messfehler **in der Messung selbst**, und zwar in der einzigen
Richtung, die niemand bemerkt: **grün**. Eine Probe, die bei jeder Eingabe
dasselbe sagt, sagt nichts.

Dieser Test ist der Zeuge dafür. Er prüft nicht den Code, sondern den Lauf:
Liegt nach der Suite Bytecode im Paket, war der Lauf nicht aussagekräftig —
egal ob 0 oder 100 Tests grün waren.

Grenze, ausdrücklich: der Test sieht nur, was beim Start des Prozesses
geschrieben wurde. Er kann ``sys.dont_write_bytecode`` nicht nachträglich
setzen. Deshalb ist er ein Zeuge und keine Abhilfe; die Abhilfe steht in
``run_tests.py`` und in der Konvention ``python3 -B -m pytest``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent


def _bytecode_dirs() -> list[Path]:
    return sorted(p for p in _PKG.rglob("__pycache__") if p.is_dir())


def test_no_bytecode_leaks_from_this_suite() -> None:
    """Kein ``__pycache__`` im Paket nach dem Lauf — mit Grund, nicht mit Artefakt.

    Ein Test, der "Datei liegt da" meldet, meint "unter einem anderen
    Einstieg gestartet" und niemand liest ihn. Deshalb wird zuerst die
    Ursache geprüft: ``sys.dont_write_bytecode`` — gesetzt von
    ``run_tests.py``. Ist es aus, lautet der Befund "direkt gestartet",
    nicht "Datei vorhanden".
    """
    leaked = _bytecode_dirs()
    if leaked:
        assert sys.dont_write_bytecode, (
            "direkt gestartet (pytest statt run_tests.py): "
            "PYTHONDONTWRITEBYTECODE ist nicht gesetzt, also hat der "
            "Interpreter Bytecode in das Paket geschrieben "
            f"({[str(p.relative_to(_PKG)) for p in leaked]}). Der Lauf ist "
            "nicht belastbar. Einstieg: "
            "`python3 order_execution_engine/run_tests.py` oder "
            "`python3 -B -m pytest`."
        )
        assert False, (
            "Bytecode im Paket trotz dont_write_bytecode: "
            f"{[str(p.relative_to(_PKG)) for p in leaked]} — Reste eines "
            "früheren Laufs. `find order_execution_engine -name __pycache__ "
            "-exec rm -rf {} +` und wiederholen."
        )


def test_bytecode_disabled_for_this_process() -> None:
    """``sys.dont_write_bytecode`` ist gesetzt — oder der Starter ist der falsche.

    Zusicherung statt Divergenz: bricht mit dem Grund (Starter), nicht mit
    dem Artefakt (Datei). Die Abhängigkeit vom Einstieg ist damit sichtbar
    und benannt, und sie bleibt bestehen: ``PYTHONDONTWRITEBYTECODE`` wirkt
    vor dem Interpreterstart und läßt sich von ``pytest.ini`` nicht setzen.
    """
    if sys.dont_write_bytecode:
        return
    assert not _bytecode_dirs(), (
        "sys.dont_write_bytecode ist False und es liegt Bytecode im Paket — "
        "der Lauf hat gegen kompilierten Stand gemessen. Einstieg: "
        "`python3 order_execution_engine/run_tests.py`."
    )
    # Flag aus, aber nichts geschrieben: die Umgebung ist trotzdem sauber
    # (z. B. PYTHONPYCACHEPREFIX auf /tmp). Kein Befund, nur ein Hinweis.
