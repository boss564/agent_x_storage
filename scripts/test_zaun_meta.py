#!/usr/bin/env python3
"""Zaun-Meta-Test: prüft die Prüfung, nicht die Skripte.

§A-ZZZZ144 (Runde 84): **ein Zaun ohne Meta-Test prüft nur die reparierte
Fassung.**

Der Slash-Filter-Bug (`count("/") == 2`, während `scripts/x.py` einen
hat) wurde durch manuelles Bemerken gefunden, nicht durch einen Test.
Die nachgereichte Probe (`touch zz.py`) lief NACH dem Fix und hätte die
erste Fassung nicht gefangen. Damit hatte der Zaun dieselbe Krankheit
wie die Wache: er bewies Detektion, nicht Funktion.

Dieser Test prüft den Zaun gegen synthetische Bäume — in `tempfile`,
ohne das echte Repository anzufassen:

    A  leerer scripts/-Ordner           -> muss "zu wenig" melden
    B  flacher Ordner, 60 Dateien       -> muss alle sehen
    C  verschachtelt                      -> muss auch tiefe Dateien sehen
    D  unbekannte Datei                   -> muss sie melden
    E  Datei in der Baseline              -> darf sie NICHT melden

Fall A ist der Zen-Test: eine Prüfung, die nichts sieht, darf nicht
"0 Befunde" melden.

Der Test importiert `check_undocumented_tests` direkt und sammelt die
Befunde über ein Stub-Report-Objekt. Er fasst keinen echten Pfad an.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_claude_md as c  # noqa: E402


class StubReport:
    def __init__(self) -> None:
        self.befunde: list[tuple] = []

    def fail(self, *a) -> None:  # noqa: D401
        self.befunde.append(a)

    def ok(self) -> None:
        pass


def _bau(root: Path, dateien: list[str]) -> None:
    for rel in dateien:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# synthetisch\n", encoding="utf-8")


def main() -> int:
    ok = 0
    gesamt = 0

    # A: leerer Baum -> "Zaun sieht zu wenig"
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "scripts").mkdir()
        r = StubReport()
        c.check_undocumented_tests(root, r)
        gesamt += 1
        gut = any("Zaun sieht zu wenig" in str(b) for b in r.befunde)
        print(f"{'ok  ' if gut else 'FAIL'} A leerer Baum            "
              f"{len(r.befunde)} Befund(e)")
        ok += gut

    # B: flach, 60 Dateien, alle in der Baseline -> kein Befund
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        namen = [f"scripts/s{i:02d}.py" for i in range(60)]
        _bau(root, namen)
        (root / "scripts" / ".skript_baseline.json").write_text(
            "[" + ",".join(f'"{n}"' for n in namen) + "]", encoding="utf-8")
        r = StubReport()
        c.check_undocumented_tests(root, r)
        gesamt += 1
        gut = not r.befunde
        print(f"{'ok  ' if gut else 'FAIL'} B 60 Dateien, baselined   "
              f"{len(r.befunde)} Befund(e)")
        ok += gut

    # C: verschachtelt -> tiefe Dateien müssen gesehen werden
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        flach = [f"scripts/a{i:02d}.py" for i in range(55)]
        tief = ["scripts/sub/deep/x.py"]
        _bau(root, flach + tief)
        (root / "scripts" / ".skript_baseline.json").write_text(
            "[" + ",".join(f'"{n}"' for n in flach) + "]", encoding="utf-8")
        r = StubReport()
        c.check_undocumented_tests(root, r)
        gesamt += 1
        gut = any("deep" in str(b) for b in r.befunde)
        print(f"{'ok  ' if gut else 'FAIL'} C verschachtelt          "
              f"tiefe Datei {'gemeldet' if gut else 'ÜBERSEHEN'}")
        ok += gut

    # D: unbekannte Datei -> gemeldet
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        flach = [f"scripts/b{i:02d}.py" for i in range(55)]
        _bau(root, flach + ["scripts/neu.py"])
        (root / "scripts" / ".skript_baseline.json").write_text(
            "[" + ",".join(f'"{n}"' for n in flach) + "]", encoding="utf-8")
        r = StubReport()
        c.check_undocumented_tests(root, r)
        gesamt += 1
        gut = any("neu.py" in str(b) for b in r.befunde)
        print(f"{'ok  ' if gut else 'FAIL'} D neue Datei             "
              f"{'gemeldet' if gut else 'DURCHGELASSEN'}")
        ok += gut

    # E: Baseline-Datei -> NICHT gemeldet
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _bau(root, [f"scripts/d{i:02d}.py" for i in range(55)])
        alle = [f"scripts/d{i:02d}.py" for i in range(55)]
        (root / "scripts" / ".skript_baseline.json").write_text(
            "[" + ",".join(f'"{n}"' for n in alle) + "]", encoding="utf-8")
        r = StubReport()
        c.check_undocumented_tests(root, r)
        gesamt += 1
        gut = not r.befunde
        print(f"{'ok  ' if gut else 'FAIL'} E Baseline respektiert    "
              f"{len(r.befunde)} Befund(e)")
        ok += gut

    print(f"\n{ok}/{gesamt} Zaun-Meta-Faelle gruen")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
