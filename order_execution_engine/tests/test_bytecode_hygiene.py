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
    """Kein ``__pycache__`` im Paket nach dem Lauf."""
    leaked = _bytecode_dirs()
    assert not leaked, (
        "Bytecode im Paket nach dem Testlauf: "
        f"{[str(p.relative_to(_PKG)) for p in leaked]}. "
        "Der Lauf hat gegen .pyc gemessen, nicht gegen den Quelltext — "
        "Ergebnisse dieses Laufs sind nicht belastbar. "
        "Starte ihn über order_execution_engine/run_tests.py oder mit "
        "PYTHONDONTWRITEBYTECODE=1 / python3 -B."
    )


def test_bytecode_disabled_for_this_process() -> None:
    """``sys.dont_write_bytecode`` ist gesetzt — oder es ist bereits zu spät.

    Wenn dieses Modul selbst importiert wurde und sein ``.pyc`` existiert,
    hat der Interpreter schon geschrieben, bevor der Test laufen konnte.
    Der Test kann das nicht heilen, nur benennen: er schlägt zusammen mit
    ``test_no_bytecode_leaks_from_this_suite`` fehl, und der Autor sieht
    beide Male dieselbe Ursache.
    """
    if sys.dont_write_bytecode:
        return
    leaked = _bytecode_dirs()
    assert not leaked, (
        "sys.dont_write_bytecode ist False UND es liegt Bytecode im Paket — "
        "der Lauf hat gegen kompilierten Stand gemessen."
    )
    # Kein Bytecode geschrieben, obwohl das Flag aus ist: dann ist die
    # Umgebung sauber (z.B. PYTHONPYCACHEPREFIX auf /tmp). Das ist kein
    # Befund, nur ein Hinweis — der Lauf bleibt belastbar.
