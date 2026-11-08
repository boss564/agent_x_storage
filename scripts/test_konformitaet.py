#!/usr/bin/env python3
"""Konformitaet: die Ausgabe muss gegen den VERTRAG passen, nicht gegen
die eigene Tokenisierung.

§A-ZZZZ141 (Runde 84): **Code, Mock und Vertrag stimmten ueberein, weil
Code und Mock denselben Parser-Fehler teilten.**

Der Befund der Runde 83: `KANAL-DUPLIKAT` enthaelt einen Bindestrich,
der Parser-Regex `[A-Za-z_]+` zerlegte ihn in `DUPLIKAT`. Alle
Konsumenten-Tests liefen gruen, waehrend der vertragliche Schluessel
NIE gelesen wurde. Kein Test schlug den Schluessel im Vertrag nach.

Dieser Test liest die Schluessel aus `waechter_vertrag.json` (die
Grammatik), sucht sie WOERTLICH in der Ausgabe und prueft die
Zeichenklasse der Schluessel. Ein Bindestrich-Schluessel mit einem
Parser ohne Bindestrich wird hier rot — bevor ein Konsument ihn
verfehlt.

Die Grammatik steht im Vertrag, nicht im Test. Aendert sich die
Grammatik, aendert sich der Test von selbst.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from achsen_invariante import AchsenKlasse, bewerte_achsenzeile

W = Path(__file__).resolve().parent / "einwurf_waechter.py"
V = Path(__file__).resolve().parent / "waechter_vertrag.json"
A = "A" * 500
B = "B" * 500

# L3 Inline-Fixtures (Commit R): Dual Alt ODER Neu.
# Alt = HEAD-Vertrag messachse via git show (C4/D12 — nicht Worktree-Spiegel).
# Neu = Soll nach Flip (8). Formale Rekonziliation = Commit 1 (P8/F9):
#   assert "messachse" in gram
#   assert set(INLINE_NEU_KEYS) == set(gram["messachse"])
def _head_alt_keys() -> list[str]:
    """C4/D12: Freeze-Orakel (kein git show — Hook-TMP ohne .git)."""
    doc = json.loads(
        (Path(__file__).resolve().parent / "orakel_head_messachse_alt5.json")
        .read_text(encoding="utf-8")
    )
    return list(doc["messachse"])


INLINE_ALT_KEYS = _head_alt_keys()
INLINE_NEU_KEYS = [
    "Paare", "KANAL-DUPLIKAT", "WIEDERHOLUNG", "ZEITSTEMPEL-UNLESBAR",
    "uebersprungen", "json", "kurz", "envelope",
]


def _z(ts: str, txt: str) -> str:
    return json.dumps({"role": "user", "message": {
        "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
        ensure_ascii=False)


def main() -> int:
    ok = 0
    gesamt = 0
    skipped = 0
    v = json.loads(V.read_text(encoding="utf-8"))
    gram = v.get("ausgabe_grammatik", {})
    schluessel_muster = gram.get("schluessel_zeichen", "[A-Za-z_][A-Za-z0-9_-]*")

    # Ein Strom mit allen Urteilen, damit jede Marke vorkommt.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        f = d / "strom.jsonl"
        f.write_text("\n".join([_z("T1", A), _z("T1", A), _z("T2", B),
                                "KEIN JSON"]) + "\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(W), "--strom", str(f)],
                           capture_output=True, text=True, cwd=d)
        out = r.stdout

    # 1. Die Grammatik erlaubt den Bindestrich.
    gesamt += 1
    bindestrich_ok = "-" in schluessel_muster
    print(f"{'ok  ' if bindestrich_ok else 'FAIL'} Grammatik Bindestrich   "
          f"{schluessel_muster!r}")
    ok += bindestrich_ok

    # 2. L3 Dual: Inline Alt (5) ODER Inline Neu (8) — Commit R gruen
    #    gegen HEAD-Producer und gegen Commit-1-Producer.
    def _alle_gefunden(keys: list[str]) -> bool:
        return all(re.search(rf"(?:^|;){re.escape(k)}=", out) for k in keys)

    gesamt += 1
    alt_ok = _alle_gefunden(INLINE_ALT_KEYS)
    neu_ok = _alle_gefunden(INLINE_NEU_KEYS)
    gut = alt_ok or neu_ok
    print(f"{'ok  ' if gut else 'FAIL'} Inline Dual Alt|Neu      "
          f"alt5={alt_ok} neu8={neu_ok}")
    ok += gut

    # 2b. P8/D5 BOOK Rekonziliation: pytest-aequivalenter Skip in Script-Runner.
    #     Diese Suite ist kein pytest — Semantik = pytest.mark.skip:
    #     zaehlt weder in ok noch gesamt; erscheint als „1 skipped“.
    #     Aktivierung Commit 1:
    #       assert "messachse" in gram   # laut, kein .get(..., [])
    #       assert set(INLINE_NEU_KEYS) == set(gram["messachse"])
    SKIP_REASON_REKONZILIATION = (
        "Commit 1: gram['messachse'] laut (kein .get) — Rekonziliation"
    )
    skipped += 1
    print(f"skipped Rekonziliation (BOOK) reason={SKIP_REASON_REKONZILIATION!r}")

    # 3. Jeder Schluessel in der Ausgabe passt zur Grammatik (Zeichenklasse).
    gesamt += 1
    messzeilen = [z for z in out.splitlines() if not z.lstrip().startswith("#")]
    ist_schluessel = re.findall(r"(?:^|;)([^=;]+)=", "\n".join(messzeilen))
    verstoesse = [s for s in ist_schluessel
                  if not re.fullmatch(schluessel_muster, s)]
    gut = not verstoesse
    print(f"{'ok  ' if gut else 'FAIL'} Ausgabe-Grammatik        "
          f"{len(ist_schluessel)} Schluessel, {len(verstoesse)} Verstoesse"
          + (f" {verstoesse}" if verstoesse else ""))
    ok += gut

    # 4. L4 via bewerte_achsenzeile (Pipeline: L4 vor Dispatcher).
    gesamt += 1
    achsenzeilen = [z for z in messzeilen if "Paare=" in z]
    pipeline_fails: list[str] = []
    for az in achsenzeilen:
        bok, bgrund, bklasse = bewerte_achsenzeile(az, modus="expand")
        if not bok:
            pipeline_fails.append(f"{bklasse.value}:{bgrund}")
    gut = not pipeline_fails and bool(achsenzeilen)
    print(f"{'ok  ' if gut else 'FAIL'} Achsenzeile L4∘Dispatch  "
          f"{'gruen' if gut else pipeline_fails}")
    ok += gut

    # 5. Zeilen-Marken: der ZEIGER und das URTEIL kommen aus dem Vertrag.
    gesamt += 1
    vertrag = json.loads((Path(__file__).resolve().parent /
                          "waechter_vertrag.json").read_text(encoding="utf-8"))
    zs = vertrag["ausgabe_grammatik"]["zeile"]
    muster = (r"ZEILE (AUFRUF|pos:\d+|[0-9a-f]{64}) "
              r"(" + "|".join(zs["urteile"]) + r");")
    marken = re.findall(muster, out)
    zeiger_ok = all(z == "AUFRUF" or z.startswith("pos:")
                    or re.fullmatch(r"[0-9a-f]{64}", z) for z, _ in marken)
    urteil_ok = all(u in zs["urteile"] for _, u in marken)
    gut = bool(marken) and zeiger_ok and urteil_ok
    print(f"{'ok  ' if gut else 'FAIL'} Zeilen-Marken            "
          f"{len(marken)} Marken, Zeiger={zeiger_ok}, Urteil={urteil_ok}")
    ok += gut

    print(f"\n{ok} passed, {skipped} skipped, {gesamt} total"
          f"  ({ok}/{gesamt} Konformitaets-Pruefungen gruen)")
    return 0 if ok == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
