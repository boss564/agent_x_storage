#!/usr/bin/env python3
"""Zeilen-Konsistenz der Messachse — kein Bodenwahrheits-Orakel.

Schichten (V6, dokumentiert unter einem Modul):
  1. parse_messachse   — kanonischer Achsen-Parser (re.M); Referenz fuer
                         jeden Konsumenten (mock_ingestion = Vertrags-Referenz,
                         keine zweite Produktions-Ingestion im Repo)
  2. hat_kurz_und_envelope / zeile_intern_*  — Shape + Zeilen-Konsistenz
  3. _klassifiziere    — privat (D3); Dispatcher ohne L4-Guard
  4. achsenzeile_fremdkeys / bewerte_achsenzeile — L4 vor Dispatcher (V4)

Oeffentliche API fuer Verdicts: bewerte_achsenzeile / erste_achsenzeile /
parse_messachse / hat_kurz_und_envelope / zeile_intern_* /
achsenzeile_fremdkeys / akzeptiert_expand / akzeptiert_contract.

Pipeline (bindend, D7c):
  Parser → Shape → SCHEMA_KERN_ALT5 → Fremd-Keys → Dispatcher → Verdict

Key-Anzahl-Entscheidung (D1): L4 erzwingt KEINE exakte Kardinalitaet
(meta≠6 / strom≠9 als Count). L4 = Membership: Keys ⊆ erlaubt.
  - Extra-Key → FREMD_KEYS
  - Fehlender Kernkey (SCHEMA_KERN_ALT5) → SCHEMA_LUECKE
  - meta-6 (genau ACHSEN_META_6) → fremdkeys leer → META

Commit R (Expand): akzeptiert meta-6, HEAD-strom-Alias und Soll-Summe.
Commit T (Contract): lehnt Alias ab; Summe und meta bleiben gruen.

P6: Dispatcher-Zweig „sonst“ = Wert-Relations-Fehler (kurz+envelope
vorhanden, aber weder Alias noch Summe). Key-Anzahl / Fremd-Keys
ausschliesslich L4 / bewerte_achsenzeile.

F8/D6d: Parser-Dict meta=6 (kein Meldungen), strom=9 (Meldungen+8).
`hat_kurz_und_envelope` = Subset-Check (keine Count-Pruefung).
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Mapping

# --- D6a L4-Vokabel (wörtlich; Abgleich gegen Vertrag siehe Docstring) ---
# WT gram["messachse"] (8) = ACHSEN_STROM_8.
# ACHSEN_META_6 = STROM_8 ohne {kurz, envelope}.
# HEAD gram["messachse"] hat nur 5 (ohne ZEITSTEMPEL-UNLESBAR) — Producer
# emittiert ZEITSTEMPEL-UNLESBAR trotzdem; META_6 folgt der Emission.
ACHSEN_META_6 = frozenset({
    "Paare", "KANAL-DUPLIKAT", "WIEDERHOLUNG", "ZEITSTEMPEL-UNLESBAR",
    "uebersprungen", "json",
})
ACHSEN_STROM_8 = frozenset({
    "Paare", "KANAL-DUPLIKAT", "WIEDERHOLUNG", "ZEITSTEMPEL-UNLESBAR",
    "uebersprungen", "json", "kurz", "envelope",
})
# D6d: Meldungen NUR auf strom-Pfad (kurz∧envelope). meta → 6, strom → 9.
ERLAUBT_STROM_KEYS = ACHSEN_STROM_8 | frozenset({"Meldungen"})
ERLAUBT_META_KEYS = ACHSEN_META_6  # kein Meldungen (D6d)
# Verdict-Tail: gleiche physische Zeile wegen end="" — NIEMALS kurz/envelope
# (D6c: sonst maskiert stray kurz den meta-Zweig).
VERDICT_TAIL_KEYS = frozenset({"treffer", "sha", "aktion", "grund"})
assert ACHSEN_STROM_8 == ACHSEN_META_6 | frozenset({"kurz", "envelope"})
assert not ({"kurz", "envelope"} & VERDICT_TAIL_KEYS)

# Kanonischer Parser. re.M: Achse auf rc=3 steht in Zeile 2 (nach
# STROM UNLESBAR;…). Regex enthaelt kein `$` — Zeilenende-Semantik unberührt.
#
# D4 Scoping: parse_messachse liest den gesamten Text (Messung/Telemetrie
# darf Nicht-Achsen-`Key=Zahl` am Zeilenanfang mitziehen). L4/Verdict
# scopen ausschliesslich ueber erste_achsenzeile / bewerte_achsenzeile
# auf die Paare=-Zeile — dort greift Membership, nicht der volle stdout.
_MESS_RE = re.compile(r"(?:^|;)([A-Za-z_\-]+)=(\d+)", re.MULTILINE)

# D7b — sechste Konstante: Pflicht-Kern = HEAD-Alt5 / Dual-Alt5-Intersektion.
# ZEITSTEMPEL-UNLESBAR ist in META_6 erlaubt, aber NICHT kern-pflichtig —
# sonst stuerbe HEAD-Alias-Alt5 (5 Keys) als SCHEMA_LUECKE und der Satz
# „Reader akzeptiert HEAD-Alias“ waere falsch.
SCHEMA_KERN_ALT5 = frozenset({
    "Paare", "KANAL-DUPLIKAT", "WIEDERHOLUNG", "uebersprungen", "json",
})
_SCHEMA_KERN = tuple(sorted(SCHEMA_KERN_ALT5))  # stabile Reihenfolge in Meldungen
assert SCHEMA_KERN_ALT5 <= ACHSEN_META_6
assert SCHEMA_KERN_ALT5 == ACHSEN_META_6 - {"ZEITSTEMPEL-UNLESBAR"}


class AchsenKlasse(str, Enum):
    META = "meta"                         # kein kurz/envelope
    ALIAS = "alias"                       # zeile_intern_alias ∧ ¬summe
    SUMME = "summe"                       # zeile_intern_summe (inkl. Null-Kollaps)
    WERT_RELATION_FEHLER = "wert_relation_fehler"  # P6
    FREMD_KEYS = "fremd_keys"             # L4 only
    SCHEMA_LUECKE = "schema_luecke"       # Kernkeys fehlen


def parse_messachse(text: str) -> dict[str, int]:
    """Kanonischer Achsen-Parser — einzige re.M-Quelle im Repo.

    mock_ingestion.konsumiere und test_konstanten._achse delegieren hierher.
    Es gibt keine zweite Produktions-Ingestion mit eigenem Regex; die
    Vertrags-Referenz (mock_ingestion) IST der verbindliche Konsumenten-Parser.

    D4: Ueber-Extraktion im vollen stdout ist fuer `messung` akzeptiert;
    L4-Scoping = erste_achsenzeile / bewerte_achsenzeile.
    """
    return {k: int(v) for k, v in _MESS_RE.findall(text)}


def hat_kurz_und_envelope(mess: Mapping[str, object]) -> bool:
    """Shape-Guard: kurz und envelope vorhanden (Subset, keine Count-Prüfung)."""
    return {"kurz", "envelope"} <= set(mess.keys())


def zeile_intern_alias(mess: Mapping[str, int]) -> bool:
    """Zeilen-Konsistenz HEAD-strom: uebersprungen == emittiertes json-Feld.

    Keine Bodenwahrheit — mess['json'] kann Alias-u sein.
    Nur nach hat_kurz_und_envelope aufrufen (sonst KeyError).
    """
    return int(mess["uebersprungen"]) == int(mess["json"])


def zeile_intern_summe(mess: Mapping[str, int]) -> bool:
    """Zeilen-Konsistenz Soll: uebersprungen == json+kurz+envelope (emittiert)."""
    return int(mess["uebersprungen"]) == (
        int(mess["json"]) + int(mess["kurz"]) + int(mess["envelope"])
    )


def _klassifiziere(mess: Mapping[str, int]) -> AchsenKlasse:
    """Privat (D3). Dispatcher ohne L4-Guard — nur via bewerte_achsenzeile.

    Kennt KEINE Fremd-Keys (P6). Fremd-Keys entscheidet nur
    bewerte_achsenzeile / achsenzeile_fremdkeys VOR diesem Aufruf.
    """
    if not hat_kurz_und_envelope(mess):
        return AchsenKlasse.META
    alias = zeile_intern_alias(mess)
    summe = zeile_intern_summe(mess)
    if summe:
        # Null-Kollaps (0,0,0,0): alias ∧ summe → SUMME (beide wahr; Contract gruen)
        return AchsenKlasse.SUMME
    if alias:
        return AchsenKlasse.ALIAS
    # P6: kurz+envelope da, aber weder Alias noch Summe → Wert-Relation, nicht Key-Zahl
    return AchsenKlasse.WERT_RELATION_FEHLER


def akzeptiert_expand(klasse: AchsenKlasse) -> bool:
    """Commit R / Expand: Alias und Summe und meta."""
    return klasse in (AchsenKlasse.META, AchsenKlasse.ALIAS, AchsenKlasse.SUMME)


def akzeptiert_contract(klasse: AchsenKlasse) -> bool:
    """Commit T / Contract: Alias explizit abgelehnt; Summe und meta ok.

    G4: F-Alias (1,1,1,1) → rot; F-Summe (6,1,2,3) → gruen;
    F-Null (0,0,0,0) → beidseitig gruen (ununterscheidbar).
    """
    return klasse in (AchsenKlasse.META, AchsenKlasse.SUMME)


def achsenzeile_fremdkeys(achsen_keys: set[str], *, hat_meldungen: bool) -> set[str]:
    """L4 Extra-Keys: `achsen_keys - erlaubt` (nur Überschuss, nie Fehlen).

    Membership, keine exakte Kardinalitaet:
      strom (kurz∧envelope): ERLAUBT_STROM_KEYS oder ACHSEN_STROM_8
      meta  (sonst):         ERLAUBT_META_KEYS  — D6d: kein Meldungen
      plus VERDICT_TAIL_KEYS (ohne kurz/envelope, D6c)

    Fehlende Keys → nicht hier; siehe bewerte_achsenzeile (SCHEMA_LUECKE).
    """
    if {"kurz", "envelope"} <= achsen_keys:
        erlaubt = ERLAUBT_STROM_KEYS if hat_meldungen else ACHSEN_STROM_8
    else:
        # D6d: Meldungen auf meta = Fremd (strom-only).
        erlaubt = ERLAUBT_META_KEYS
    erlaubt = erlaubt | VERDICT_TAIL_KEYS
    return achsen_keys - erlaubt


def bewerte_achsenzeile(
    zeile: str, *, modus: str = "expand"
) -> tuple[bool, str, AchsenKlasse]:
    """Pipeline: Parser → Shape → Kern → Fremd → Dispatcher (D7c).

    Praezedenz (vereinheitlicht, D7c):
      1. Partial shape (kurz xor envelope) → SCHEMA_LUECKE
      2. Fehlende SCHEMA_KERN_ALT5        → SCHEMA_LUECKE
      3. Extra-Keys (fremdkeys)           → FREMD_KEYS
      4. _klassifiziere + expand/contract

    Begruendung: strukturelle Vollstaendigkeit (Shape/Kern) vor Fremd-Vokabel,
    damit derselbe Defekt (fehlender Kern) immer SCHEMA_LUECKE ist — auch
    wenn zufaellig ein Fremd-Key danebensteht. fremdkeys sieht Fehlen nie
    (`achsen_keys - erlaubt`).
    """
    mess = parse_messachse(zeile)
    keys = set(mess.keys())

    # 1) D6c: kurz ohne envelope (oder umgekehrt) → SCHEMA_LUECKE.
    hat_kurz = "kurz" in keys
    hat_envelope = "envelope" in keys
    if hat_kurz != hat_envelope:
        fehl = "envelope" if hat_kurz else "kurz"
        return (
            False,
            f"Schema-Luecke: partial shape (fehlt {fehl})",
            AchsenKlasse.SCHEMA_LUECKE,
        )

    # 2) D6b/D7b: fehlende Kernkeys (iteriert _SCHEMA_KERN == sorted(SCHEMA_KERN_ALT5)).
    fehlend = [k for k in _SCHEMA_KERN if k not in mess]
    if fehlend:
        return False, f"Schema-Luecke: {fehlend}", AchsenKlasse.SCHEMA_LUECKE

    # 3) L4 Extra-Keys (nur Überschuss). D7a: meta ohne Meldungen-Grant.
    fremd = achsenzeile_fremdkeys(keys, hat_meldungen="Meldungen" in keys)
    if fremd:
        return False, f"Fremd-Keys: {sorted(fremd)}", AchsenKlasse.FREMD_KEYS

    # 4) Dispatcher — nur Achsen-Felder; Verdict-Tail abstreifen.
    achse = {k: v for k, v in mess.items()
             if k not in VERDICT_TAIL_KEYS}
    klasse = _klassifiziere(achse)
    ok_fn = akzeptiert_expand if modus == "expand" else akzeptiert_contract
    if not ok_fn(klasse):
        if klasse is AchsenKlasse.WERT_RELATION_FEHLER:
            return False, "Wert-Relations-Fehler: weder Alias noch Summe", klasse
        return False, f"Achsenklasse abgelehnt: {klasse.value}", klasse
    return True, klasse.value, klasse


def erste_achsenzeile(stdout: str) -> str | None:
    """Erste Zeile mit Paare= — Achsenzeile, nicht ZEILE-Record (D4-Scope)."""
    for z in stdout.splitlines():
        if "Paare=" in z:
            return z
    return None
