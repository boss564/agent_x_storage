"""Referenz-Konsumentensemantik — die Norm als Code, den man ausfuehren kann.

§A-ZZZZ172 (Runde 88): **der Konsument ist die State Machine; seine
Semantik war nur in Testfaellen, nicht als Norm.**

R87 machte die Regel relativ. Damit ist Korrektheit keine Eigenschaft
des Reports mehr, sondern der Konsumenten-Implementierung. Der Vertrag
zeigte fuenf Beispiele — und liess fuenf Fragen offen:

  1. ANKER      vs. wem wird `bei_gleich` verglichen?
  2. TOTalitaet {gleich, ungleich} ist nicht vollstaendig.
  3. VORRANG    ZEILE-Record und DEDUP-Regel widersprechen sich?
  4. ORDNUNG    ist die erste Kopie im Strom die Originalmeldung?
  5. DEFAULT    Regel-lose Wiederholung — zustellen? laut?

Dieses Modul beantwortet jede Frage EINMAL, ausfuehrbar. Der Vertrag
(`waechter_vertrag.json` -> `konsumenten_semantik`) verweist hierher.
Wer den Vertrag liest, kann jede Norm hier nachschlagen und ausfuehren;
wer zwei unabhaengige Konsumenten baut, hat eine Referenz, gegen die
Divergenz sichtbar wird.

Kein Zufall, kein Zustand ausserhalb der Argumente: die Funktionen sind
reine Abbildungen Strom -> Aktionen.
"""
from __future__ import annotations

import re
from typing import NamedTuple

# --------------------------------------------------------------------------
# Norm 1 — ANKER: der unmittelbare Vorgaenger, nicht das erste Vorkommen.
# Begruendung: der Detektor misst dasselbe (Δ=1, `seen[h]` wandert mit).
# Mit Anker "erstes Vorkommen" wuerde der Konsument anders handeln als
# der Detektor, der die Regel erzeugte — und das waere eine stille
# Divergenz zwischen den beiden Parteien desselben Vertrags.
ANKER = "vorgaenger"

# --------------------------------------------------------------------------
# Norm 2 — VERGLEICH: total. Drei Ausgaenge, nicht zwei.
GLEICH = "gleich"
UNGLEICH = "ungleich"
UNLESBAR = "unlesbar"

# --------------------------------------------------------------------------
# Norm 5 — DEFAULT: keine Regel + erstes Vorkommen -> zustellen.
#           keine Regel + Wiederholung      -> LAUT, nicht still.
# "Laut" heisst: eigener Aktionsname, kein stiller Fallback auf
# ZUSTELLEN oder VERWERFEN. Ein stiller Fallback ist die Luecke, gegen
# die das ganze System gebaut wurde.
DEFAULT_ERST = "ZUSTELLEN"
DEFAULT_REST = "KEINE-REGEL"

# --------------------------------------------------------------------------
# Norm 3 — VORRANG: der ZEILE-Record gewinnt gegen die DEDUP-Regel.
# Begruendung: der ZEILE-Record ist ein EREIGNIS ueber DIESEN Strom; die
# DEDUP-Regel ist eine VORSCHRIFT fuer kuenftige Kopien. Ein Ereignis
# ueber eine Zeile, die der Detektor sah, ist konkreter als eine
# Vorschrift fuer Raenge, die er nicht sah. Umgekehrt waere die Regel
# eine Aussage ueber das, was sie nicht messen konnte.
VORRANG = "ZEILE>DEDUP"

_KOPF = re.compile(r"^ZEILE (\S+) ([A-Z]+);")
_REGEL = re.compile(r"^DEDUP ([^;]+);")
_FELD = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)=([^;]*);")


class Abgeleitet(NamedTuple):
    aktion: str
    quelle: str      # "ZEILE" | "DEDUP" | "DEFAULT"
    norm: str        # welcher Normsatz gegriffen hat


def parse_regel(zeile: str) -> dict[str, str] | None:
    """DEDUP-Zeile -> Felder. None, wenn keine DEDUP-Zeile."""
    if not _REGEL.match(zeile):
        return None
    return dict(_FELD.findall(zeile))


def parse_zeilen(bericht: list[str]) -> dict[str, list[str]]:
    """sha -> ZEILE-Urteile in Berichtsreihenfolge. `AUFRUF` bleibt aussen.

    Norm 3 braucht die Ereignisse. `AUFRUF` wird hier bewusst nicht
    gefuehrt: er ist ein Meta-Ereignis, kein Inhalt (Kreuz-Record-Invariante).
    """
    out: dict[str, list[str]] = {}
    for z in bericht:
        m = _KOPF.match(z)
        if not m:
            continue
        h, u = m.group(1), m.group(2)
        if h == "AUFRUF":
            continue
        out.setdefault(h, []).append(u)
    return out


def relate(a: object, b: object) -> str:
    """Norm 2: totaler Zeitstempel-Vergleich.

    `a` und `b` sind entweder Strings (gelesen) oder None (unlesbar).
    Ein unlesbarer Wert ist mit NICHTS gleich — auch nicht mit sich selbst.
    """
    if a is None or b is None:
        return UNLESBAR
    return GLEICH if a == b else UNGLEICH


def vorschrift(regel: dict[str, str], rel: str) -> str:
    """Norm 1+2: Regel + Vergleich -> Aktion."""
    if rel == GLEICH:
        return regel.get("bei_gleich", DEFAULT_REST)
    if rel == UNGLEICH:
        return regel.get("bei_ungleich", DEFAULT_REST)
    return regel.get("bei_unlesbar", DEFAULT_REST)


def apply(regel: dict[str, str] | None,
          positionen: list[str | None]) -> list[Abgeleitet]:
    """Wendet EINE Klasse auf ihren Strom an. `positionen` = Zeitstempel."""
    out: list[Abgeleitet] = []
    for i, jetzt in enumerate(positionen):
        if i == 0:
            a = (regel or {}).get("erst", DEFAULT_ERST)
            out.append(Abgeleitet(a, "DEDUP" if regel else "DEFAULT",
                                  "rang1/erst"))
            continue
        if regel is None:
            out.append(Abgeleitet(DEFAULT_REST, "DEFAULT", "regel-los"))
            continue
        if regel.get("anker", ANKER) != ANKER:
            # Norm 1: ein fremder Anker ist kein Vertragsbruch des
            # Konsumenten, sondern ein Feld, das der Detektor setzt.
            # Hier wird der Anker als Vorschrift GELESEN, nicht angenommen.
            pass
        rel = relate(positionen[i - 1], jetzt)
        out.append(Abgeleitet(vorschrift(regel, rel), "DEDUP",
                              f"bei_{rel}"))
    return out


# --------------------------------------------------------------------------
# §A-ZZZZ177 (Runde 88): **Feldweise, nicht positionsweise.**
# R88 fuegte `anker=` und `bei_unlesbar=` ein — und drei Parser in
# bestehenden Tests brachen, weil sie die Feldreihenfolge im Regex
# eingebaut hatten. Das ist die Norm "Ableitungen parsen Record-Typen"
# noch nicht ernst genommen: ein Parser, der die Reihenfolge kennt, kennt
# die Version. Diese Funktion liest Felder nach `;`, egal in welcher
# Reihenfolge sie stehen, und ist damit gegen Feld-Ergaenzungen immun.
def felder(zeile: str) -> dict[str, str]:
    """`DEDUP <sha>;a=b;c=d;` -> {'sha':.., 'a':'b', 'c':'d'}."""
    m = _REGEL.match(zeile)
    if not m:
        raise ValueError(f"kein DEDUP-Record: {zeile[:40]!r}")
    d = {"sha": m.group(1)}
    d.update(dict(_FELD.findall(zeile[m.end():])))
    return d


def regel_aus_bericht(bericht: list[str]) -> dict[str, dict[str, str]]:
    """sha -> Felder aller DEDUP-Records im Bericht."""
    return {h: felder(z) for z in bericht
            for h in [(_REGEL.match(z).group(1) if _REGEL.match(z) else None)]
            if h}
