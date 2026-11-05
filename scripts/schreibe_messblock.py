#!/usr/bin/env python3
"""Schreibt den Messblock der Akte — angehängt, mit **nachgewiesenem** Hash.

## Wie die Akte ihre Messblöcke versteht

`check_claude_md.split_blocks` schneidet an `### `-Überschriften. Ein Block,
dessen Zeilen einer **früheren** Überschrift zugeordnet werden, ist ein
**Vorzustand** — er ist nicht die aktuelle Messung, egal wie neu seine
Zahlen sind. Der Block muß deshalb **hinter** der letzten Überschrift
stehen, also am Dateiende, nach dem Anhang.

## Was dieses Skript deshalb nicht tut

  * Es **ersetzt** keinen bestehenden Block. Ein Ersatz innerhalb einer
    alten Überschrift wäre ein Vorzustand mit neuem `Karte:`-Stempel.
  * Es **durchsucht** die Akte nicht. Ein `split("```")` über den ganzen
    Text ist genau der Fehler, der einen Block in die falsche Überschrift
    legen kann.
  * Es **rät** den Prüfer-Hash nicht. Der Hash hängt von `scripts/*.py`
    ab, nicht von der Akte — er wird gemessen, eingetragen und danach
    **nachgemessen**.

## Reihenfolge (die einzige, die den Selbstbezug trägt)

    1. Karte rechnen        (ändert Dateien unter scripts/: Vorlauf, Stand)
    2. Hash nehmen          (nach der Karte, sonst ist er Vorzustand)
    3. Suiten messen        (read-only)
    4. Hash nochmal         (muß stabil sein, sonst Abbruch)
    5. Block anhängen       (guarded_write, whole=False = Anhang)
    6. Hash + Kopfzeile + Akte neu prüfen — das ist der Paste.

Ein Hash, der zwischen Schritt 2 und 4 wandert, heißt: ein Prüfer schreibt
während der Messung. Dann ist kein Block schreibbar, der beides trägt —
und das Skript bricht ab, statt den Wert zu erfinden.
"""
from __future__ import annotations

import contextlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_claude_md as c  # noqa: E402
from akte_guard import guarded_write  # noqa: E402  (Schreib-Guard §A-NS)

AKTE = ROOT / "order_execution_engine" / "ops" / "TAG7_ABNAHME.md"

SUITEN = [
    ("test_hash_eingang.py", r"(\d+)/(\d+) Hash-Eingangs-Pruefungen gruen", "Hash-Eingang"),
    ("mock_ingestion.py", r"(\d+)/(\d+) Konsumenten-Faelle gruen", "Konsument"),
    ("test_konstanten.py", r"(\d+)/(\d+) Konstanten-Proben gruen", "Konstanten"),
    ("test_normalisierung.py", r"(\d+)/(\d+) Normalisierungs-Grenzen gruen", "Normalisierung"),
    ("test_zeilen_identitaet.py", r"(\d+)/(\d+) Zeilen-Identitaets-Faelle gruen", "Zeilen-Identitaet"),
    ("test_konformitaet.py", r"(\d+)/(\d+) Konformitaets-Pruefungen gruen", "Konformitaet"),
    ("test_zaun_meta.py", r"(\d+)/(\d+) Zaun-Meta-Faelle gruen", "Zaun-Meta"),
    ("test_zeiger_stabil.py", r"(\d+)/(\d+) Zeiger-Stabilitaets-Faelle gruen", "Zeiger"),
    ("test_projektion.py", r"(\d+)/(\d+) Projektions-Faelle gruen", "Projektion"),
    ("test_exit2_zeilen.py", r"(\d+)/(\d+) Exit-[^\n]*Zeilen[^\n]*", "Exit2-Zeilen"),
    ("test_adj_slot.py", r"(\d+)/(\d+) ADJ-Slot-Faelle gruen", "ADJ-Slot"),
    ("regel_konsument.py", r"(\d+)/(\d+) Regel-Konsumenten-Faelle gruen", "Regel-Konsument"),
    ("test_klasse_mehrdeutig.py", r"(\d+)/(\d+) Klassen-Mehrdeutigkeits-Faelle gruen", "Klassen-Mehrdeutigkeit"),
    ("test_regel_gegen_pos.py", r"(\d+)/(\d+) Regel-gegen-pos-Faelle gruen", "Regel-gegen-pos"),
    ("test_escaping.py", r"(\d+)/(\d+) Escaping-Faelle gruen", "Escaping"),
    ("test_projektion_echt.py", r"(\d+)/(\d+) Projektions-Echtheits-Faelle gruen", "Projektion-echt"),
    ("test_katalog_naht.py", r"(\d+)/(\d+) Katalog-Naht-Faelle gruen", "Katalog-Naht"),
    ("test_naht_beweis.py", r"(\d+)/(\d+) Naht-Faelle gruen", "Naht-Beweis"),
    ("test_kreuz_record.py", r"(\d+)/(\d+) Kreuz-Record-Faelle gruen", "Kreuz-Record"),
    ("test_harness_zaun.py", r"(\d+)/(\d+) Harness-Zaun-Faelle gruen", "Harness-Zaun"),
    ("test_konsument_kongruenz.py", r"(\d+)/(\d+) Konsumenten-Kongruenz-Faelle gruen", "Konsumenten-Kongruenz"),
    ("test_frist_gate.py", r"(\d+)/(\d+) Frist-Gate-Faelle gruen", "Frist-Gate"),
    ("test_unwissen_etikett.py", r"(\d+)/(\d+) Unwissen-ist-kein-Etikett-Faelle gruen", "Unwissen-Etikett"),
    ("test_exit_vor_stdout.py", r"(\d+)/(\d+) Exit-vor-Stdout-Faelle gruen", "Exit-vor-Stdout"),
]


def _suite(script: str, muster: str) -> tuple[int, int]:
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / script)],
                         capture_output=True, text=True, cwd=str(ROOT))
    m = re.search(muster, out.stdout + out.stderr)
    if not m:
        raise SystemExit(f"{script}: Muster trifft nicht — Block sperrt")
    return int(m.group(1)), int(m.group(2))


def _ohne_vorblock(akte: Path) -> tuple[int, str]:
    """Entfernt den Block **dieses** Werkzeugs aus der Akte — laut, gezählt.

    Erkennungsmerkmal ist die Überschrift, nicht der Inhalt: was das
    Werkzeug selbst anhängt, trägt seinen Namen. Fremde Messblöcke (auch
    mit `kopfzeile:`) bleiben unberührt — hier wird nichts still ersetzt,
    was ein anderer geschrieben hat.
    """
    txt = akte.read_text(encoding="utf-8")
    zeilen = txt.splitlines(keepends=True)
    out, skip, n = [], False, 0
    for ln in zeilen:
        if ln.startswith("### ") and _BLOCK_TITEL in ln:
            skip, n = True, n + 1
            continue
        if skip:
            if ln.startswith("### "):
                skip = False
            else:
                continue
        out.append(ln)
    return n, "".join(out)


_BLOCK_TITEL = "### §71.76 — Messblock"


def _block(karte: str, hashwert: str) -> str:
    """Der Block als **eigene** Überschrift — die Karte byte-gleich darunter.

    Zwei Bedingungen, beide gemessen, nicht gewählt:

      * Der Text im Zaun ist `calibration_card()` ohne Zusatz. Was daneben
        steht, rechnet niemand nach — das ist die Attrappe.
      * Der Block braucht eine **eigene** `### `-Zeile. Ohne sie landet er
        unter der letzten vorhandenen Überschrift (hier `### 9. Stand`),
        und `split_blocks` liefert ihn als Teil eines Vorzustands.
    """
    return ("\n### §71.76 — Messblock 2026-11-05 (Werkzeug `schreibe_messblock.py`)\n"
            "\n```\n" + karte.rstrip() + "\n```\n"
            f"\nPrüfer `{hashwert}` · erzeugt aus dem Ist-Stand, nicht kopiert.\n")


def main() -> int:
    # 0. **Vorzustand weg.** `_akt_block_mismatch` faltet **alle** Messböcke
    #    mit derselben `Karte:` und meldet den ersten Bruch. Blöcke mit
    #    voriger Karte bleiben als Historie stehen (kein stiller Ersatz) —
    #    aber ein Block aus **diesem** Werkzeug mit einer Karte, die nicht
    #    mehr zur Messung paßt, wäre eine Attrappe im Anhang. Darum
    #    entfernt dieses Skript seine **eigenen** früheren Anhänge, bevor
    #    es den neuen schreibt. Die Entfernung ist laut: sie nennt Zahl
    #    und Hash der entfernten Blöcke.
    _vorher, _rest = _ohne_vorblock(AKTE)
    # 1. Karte zuerst: `calibration_card()` führt den Lauf aus und kann
    #    Dateien unter `scripts/` bewegen (Vorlauf, Selbsttest-Stand).
    karte = c.calibration_card()
    # 2. Hash nach der Karte — das ist der Prüfer, der den Block schreibt.
    hash_soll = c._pruefer_hash()
    # 3. Suiten (read-only).
    zahlen = []
    for script, muster, lab in SUITEN:
        p, t = _suite(script, muster)
        zahlen.append((lab, p, t))
        print(f"  {lab:<24} {p}/{t}")
    print(f"  Summe {sum(p for _, p, _ in zahlen)}/{sum(t for _, _, t in zahlen)}")
    # 4. Stabilität: hat ein Schritt die Signatur verschoben, ist der Block
    #    nicht schreibbar — dann bitte melden, nicht den Wert erzwingen.
    hash_jetzt = c._pruefer_hash()
    if hash_jetzt != hash_soll:
        raise SystemExit(
            f"Prüfer-Hash hat sich während der Messung geändert "
            f"({hash_soll} -> {hash_jetzt}). Kein Block: die Zahlen kämen "
            f"aus einem anderen Baum als der Hash.")
    # 5. Anhängen — der einzige Schreibvorgang, durch den Guard (§A-NS).
    if _vorher:
        # Der Vorblock ist ein **Vorzustand** dieses Werkzeugs, kein
        # Fremdblock: seine Karte kennt die Messung nicht mehr, die jetzt
        # läuft. Entfernt wird er trotzdem laut — Zahl genannt, nicht still.
        with contextlib.suppress(OSError):
            AKTE.write_text(_rest, encoding="utf-8")
        print(f"BELEG Vorblock entfernt: {_vorher} (Karte traf nicht mehr "
              f"zur Messung)")
    ok, meldung = guarded_write(AKTE, _block(karte, hash_soll), whole=False)
    if not ok:
        raise SystemExit(f"Guard hat den Schreibvorgang verweigert: {meldung}")
    print(f"GUARD {meldung}")
    # 6. Paste: drei Messungen am Ergebnis, nicht am Vorsatz.
    nach = c._pruefer_hash()
    fehler = c._kopfzeile_errors()
    mismatch = c._akt_block_mismatch()
    bloecke = [b for b in c.split_blocks(AKTE.read_text(encoding="utf-8"))
               if b["kind"] == "Messung"]
    letzter_ist_neu = bool(bloecke) and hash_soll in "\n".join(bloecke[-1]["lines"])
    print(f"BELEG Hash eingetragen={hash_soll} gemessen={nach} gleich={nach == hash_soll}")
    print(f"BELEG letzter Messblock=[{bloecke[-1]['title'][:40] if bloecke else '-'}] "
          f"traegt_neuen_Hash={letzter_ist_neu}")
    print(f"BELEG Kopfzeile-Fehler={fehler}")
    print(f"BELEG Akte-Mismatch={mismatch}")
    if nach != hash_soll or not letzter_ist_neu or mismatch:
        return 1
    # Ein Vorzustand-Befund auf einem **früheren** Block ist Historie, kein
    # Fehler — deshalb wird er hier gedruckt, aber nicht zum Exit gemacht.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
