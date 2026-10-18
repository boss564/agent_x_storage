#!/usr/bin/env python3
"""Zahlen aus dem Vertrag generieren — nicht tippen.

§A-ZZZZ167 (Runde 87): **das Zaehlen ist der Bug.**

R86 hatte 18 = 18 (korrekt) und 291 vs 283 (falsch) in derselben Runde.
Zwei Zaehlfehler bei zwei Zahlen: die Zahl wurde getippt, nicht
abgeleitet. Zusatz: `zweig_ledger` wurde als "12 Zweige" zitiert, mein
erster Zaehler las `len(zweig_ledger)==3` — er zaehlte die Schluessel
der Huelle statt der Eintraege. Genau der Fehler, den dieser Bericht
seit drei Runden bemaengelt.

Dieses Skript liest nur den Vertrag und gibt ab, was drinsteht. Es
rechnet nichts, was nicht im Artefakt steht — kein Aggregat, das den
Vertrag "versteht".
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

V = Path(__file__).resolve().parent / "waechter_vertrag.json"


def pfad(d: object, *keys: str) -> object:
    """Expliziter Pfad — kein 'irgendwo drin'. Wirft statt zu raten."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            raise KeyError(f"Pfad fehlt: {'/'.join(keys)}")
        cur = cur[k]
    return cur


def main() -> None:
    raw = V.read_bytes()
    d = json.loads(raw)
    z: list[tuple[str, object, str]] = [
        ("Version", pfad(d, "_version"), "_version"),
        ("Versions-Ledger", len(pfad(d, "versions_ledger")),
         "len(versions_ledger)"),
        ("Vertragsfälle", len(pfad(d, "vertragsfaelle")),
         "len(vertragsfaelle)"),
        ("Invarianten", len(pfad(d, "invarianten")), "len(invarianten)"),
        ("Zweige", len(pfad(d, "zweig_ledger", "zweige")),
         "len(zweig_ledger.zweige)"),
        ("Zweige latent ohne Test", len(pfad(d, "zweig_ledger",
                                            "latent_ohne_test")),
         "len(zweig_ledger.latent_ohne_test)"),
        ("Bringschuld-Instanzen", len(pfad(d, "bringschuld", "instanzen")),
         "len(bringschuld.instanzen)"),
        ("Exit-Codes", len(pfad(d, "exit_codes")), "len(exit_codes)"),
        ("Normalisierungsgrenzen",
         len(pfad(d, "normalisierungs_grenze")),
         "len(normalisierungs_grenze)"),
        ("Grammatikregeln", len(pfad(d, "ausgabe_grammatik")),
         "len(ausgabe_grammatik)"),
    ]
    print(f"# generiert aus {V.name} — sha256:{hashlib.sha256(raw)
                                                   .hexdigest()[:16]}")
    for name, wert, quelle in z:
        print(f"{name:26s} {str(wert):>4s}   <- {quelle}")
    n_mit_test = z[4][1] - z[5][1]
    # §A-ZZZZ193 (Runde 90 Befund 7): "27 Suiten" war eine bare Zahl in
    # der Prosa. Jetzt gezaehlt — und zwar die RICHTIGE Menge: nur die
    # Tests, die den Waechter-Vertrag beruehren. `glob(test_*.py)` liefert
    # das GANZE Repo (118) und misst nicht, was gemeint war.
    import re as _re
    waechter: list[str] = []
    for p in sorted(V.parent.glob("test_*.py")):
        if _re.search(r"waechter_vertrag|einwurf_waechter|konsumenten_semantik",
                      p.read_text(encoding="utf-8", errors="replace")):
            waechter.append(p.name)
    print(f"{'Zweige mit Test':26s} {n_mit_test:>4d}   "
          f"<- Zweige - latent_ohne_test")
    print(f"{'Waechter-Suiten':26s} {len(waechter):>4d}   "
          f"<- test_*.py mit Vertragsbezug")
    print(f"{'Repo-Tests gesamt':26s} "
          f"{len(list(V.parent.glob('test_*.py'))):>4d}   "
          f"<- glob(test_*.py)")


if __name__ == "__main__":
    main()
