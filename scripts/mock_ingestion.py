#!/usr/bin/env python3
"""Mock-Ingestion: der fehlende fuenfte Beleg.

§A-ZZZZ125 (Runde 82): **ein Waechter ohne Verbraucher ist eine Wette.**

Runde 82 hat den Exit 4 eingefuehrt, weil Exit 0 + stderr bedeutete:
der Inhalt wurde zugestellt, die Warnung nie gelesen. Aber auch Exit 4
beweist nichts, solange niemand belegt, dass die Ingestion ihn liest.
Dieses Skript ist der Beweis im Kleinen — kein Produktionscode, sondern
die ausfuehrbare Schnittstelle, gegen die die echte Ingestion gebaut
werden MUSS:

    Waechter-Exit   Mock-Aktion
    -------------   -----------
    0  neu          zustellen
    1  duplikat     verwerfen
    2  Aufruffehler alarmieren, NICHT zustellen
    3  ungeprueft   zustellen, markiert UNGEPRUEFT
    4  unvollstaendig  zustellen, markiert UNVOLLSTAENDIG + alarmieren
    sonst           fail-closed: verwerfen + alarmieren

Der Test faehrt alle fuenf Faelle gegen echte Waechter-Laeufe und
assertiert die Aktion. Zusaetzlich liest der Konsument die Messachse
(schluessel=wert;) und prueft, dass die Zahlen zum Fall passen.

Laeuft die echte Ingestion anders, ist DIES hier die Referenz, gegen
die sie abweicht.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

W = Path(__file__).resolve().parent / "einwurf_waechter.py"


def konsumiere(code: int, stdout: str, stderr: str) -> dict:
    """Die Schnittstelle. Aendert sich hier etwas, aendert sich der Vertrag."""
    mess = dict(re.findall(r"(?:^|;)([A-Za-z_\-]+)=(\d+)", stdout))
    if code == 0:
        aktion, marke = "zustellen", None
    elif code == 1:
        aktion, marke = "verwerfen", "DUPLIKAT"
    elif code == 2:
        aktion, marke = "verwerfen", "AUFRUFFEHLER"
    elif code == 3:
        # §A-ZZZZ133 (Runde 83): **3 alarmiert wie 4.** Unter der Achse
        # "Sicherheit des Urteils" ist 3 der Extrempunkt (nichts geprueft),
        # 4 der Mittelpunkt. Vorher trug der Extrempunkt keinen Alarm und
        # der Mittelpunkt schon — Inversion unter der eigenen Achse.
        aktion, marke = "zustellen", "UNGEPRUEFT"
    elif code == 4:
        aktion, marke = "zustellen", "UNVOLLSTAENDIG"
    else:
        aktion, marke = "verwerfen", "UNBEKANNT_FAIL_CLOSED"
    return {"exit": code, "aktion": aktion, "marke": marke,
            "alarm": marke in ("AUFRUFFEHLER", "UNVOLLSTAENDIG",
                               "UNGEPRUEFT", "UNBEKANNT_FAIL_CLOSED"),
            "messung": mess, "warnung": bool(stderr.strip())}


def _lauf(args: list[str], cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run([sys.executable, str(W), *args],
                       capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


def main() -> int:
    ok = 0
    faelle = 0
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        dup = "D" * 500
        zeile = '{"role":"user","message":{"content":"%s"}}' % dup
        neu = "N" * 500
        (d / "strom.jsonl").write_text(zeile + "\n", encoding="utf-8")
        (d / "duplikat.md").write_text(dup, encoding="utf-8")
        (d / "neu.md").write_text(neu, encoding="utf-8")
        (d / "muell.jsonl").write_text(zeile + "\nKEIN JSON\n{kaputt\n",
                                       encoding="utf-8")
        (d / "nurmuell.jsonl").write_text("KEIN JSON\n", encoding="utf-8")

        # §A-ZZZZ132 (Runde 83): **Muell + Duplikat.** Der Fall, den
        # Runde 82 offen liess: Exit 1 verschluckte den Exit-4-Alarm.
        (d / "dupmuell.jsonl").write_text(zeile + "\nKEIN JSON\n",
                                          encoding="utf-8")
        proben = [
            ("muell+duplikat -> 4", ["--einwurf", str(d / "duplikat.md"),
                                     "--strom", str(d / "dupmuell.jsonl")],
             4, "zustellen", "UNVOLLSTAENDIG"),
            ("neu -> zustellen", ["--einwurf", str(d / "neu.md"),
                                  "--strom", str(d / "strom.jsonl")],
             0, "zustellen", None),
            ("duplikat -> verwerfen", ["--einwurf", str(d / "duplikat.md"),
                                       "--strom", str(d / "strom.jsonl")],
             1, "verwerfen", "DUPLIKAT"),
            ("aufruf -> verwerfen", ["--einwurf", str(d / "neu.md")],
             2, "verwerfen", "AUFRUFFEHLER"),
            ("fehlt -> ungeprueft", ["--strom", str(d / "gibtsnicht.jsonl")],
             3, "zustellen", "UNGEPRUEFT"),
            ("muell -> unvollstaendig", ["--strom", str(d / "muell.jsonl")],
             4, "zustellen", "UNVOLLSTAENDIG"),
            ("nur müll -> unvollstaendig",
             ["--strom", str(d / "nurmuell.jsonl")],
             4, "zustellen", "UNVOLLSTAENDIG"),
        ]
        for name, args, exit_soll, aktion_soll, marke_soll in proben:
            faelle += 1
            code, out, err = _lauf(args, d)
            k = konsumiere(code, out, err)
            k_mess = k["messung"]
            gut = (code == exit_soll and k["aktion"] == aktion_soll
                   and k["marke"] == marke_soll)
            # §A-ZZZZ132: Schema-Invarianz — die Achse muss auf JEDEM
            # Exit lesbar sein, nicht nur dort, wo der Autor sie brauchte.
            fehlend = [k for k in ("Paare", "KANAL-DUPLIKAT",
                                   "WIEDERHOLUNG", "uebersprungen", "json")
                       if k not in k_mess]
            if gut and fehlend:
                gut = False
                print(f"     Schema-Luecke auf exit={code}: {fehlend}")
            if gut and code == 4:
                # Die Messachse muss die Unvollstaendigkeit tragen.
                gut = k["messung"].get("json") == "2" or \
                      int(k["messung"].get("json", 0)) >= 1
            if gut and code == 1:
                gut = k["messung"].get("Paare") == "1"
            print(f"{'ok  ' if gut else 'FAIL'} {name:28s} "
                  f"exit={code} aktion={k['aktion']:12s} "
                  f"marke={k['marke']} alarm={k['alarm']}")
            ok += gut

    print(f"\n{ok}/{faelle} Konsumenten-Faelle gruen")
    return 0 if ok == faelle else 1


if __name__ == "__main__":
    raise SystemExit(main())
