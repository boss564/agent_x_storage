#!/usr/bin/env python3
"""Einwurf-Wächter: prüft am Eingang, nicht im Archiv.

§A-ZZZZ111 (Runde 77): **der Sensorfehler aus Runde 76.**

Runde 76 hat `meldung_digest.py` gebaut und in derselben Meldung
eingeräumt: „die Anhänge liegen nicht auf der Platte". Damit war der
Wächter am **Archiv** angeschlossen (TAG7_ABNAHME.md), während die
Wiederholung durch den **Einwurf** kam. Nach Runde 77 ist das kein
Randhinweis mehr, sondern ein Meßbefund:

    Von 261 echten Nutzermeldungen sind 38 bytegleich.
    Davon 37 mit **identischem Zeitstempel** → doppelte Zustellung.
    Davon  1 mit anderem Zeitstempel        → bewußte Wiederholung.
    Die Wiederholungen liegen zu 16/37 auf gerader Position.
    → **keine systematische Duplizierung, sondern zufällige.**

Daraus folgt die Architektur: der Wächter gehört **vor** die Zustellung,
nicht nach der Buchung. Dieses Skript liest den tatsächlichen
Nachrichtenstrom (Transcript-JSONL), nicht die Akte.

Was es tut:

    --strom <pfad.jsonl>     prüft alle Meldungen, meldet Paare
    --einwurf <textdatei>    prüft eine neue Meldung gegen den Strom

Exit 1 heißt: die Meldung ist eine Wiederholung. Der Aufrufer soll sie
**nicht zustellen**, nicht: sie zustellen und protokollieren.

Grenze, ausdrücklich (Runde 76, unverändert): der Digest erkennt
Wiederholung, nicht Wahrheit. Und: dieses Skript kann nur prüfen, was
es lesen kann. Läuft es nicht **vor** dem Kanal, ist es derselbe
Zeuge-nach-der-Tat wie sein Vorgänger. Die Platzierung ist die Arbeit,
nicht der Code.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

MIN_LAENGE = 400          # kürzere Einträge sind Steuertexte, keine Meldungen

# §A-ZZZZ121b (Runde 81): **die Fieber-Grenze.** Ein Zähler ohne Schwelle
# ist ein Thermometer, das mißt und nicht alarmiert. Ab dieser Zahl
# unparsbarer Zeilen warnt der Lauf — er bleibt Exit 0 (die gültigen
# Zeilen wurden geprüft), aber die Warnung steht auf stderr und ist
# damit nicht übersehbar. Begründung der Zahl: heute 0 am echten Strom;
# 1 wäre ein einzelner beschädigter Schreibvorgang, 10 deutet auf einen
# Formatbruch. Die Schwelle ist Vertragsgegenstand, nicht Code-Gefühl.
JSON_SCHWELLE = 1


class StreamUnlesbar(Exception):
    """Der Stream fehlt oder ist nicht lesbar — Exit 3, nicht Traceback.

    §A-ZZZZ115 (Runde 79): abgegrenzt gegen **defektes Format**. Ein
    kaputtes JSON je Zeile wird übersprungen, nicht abgebrochen —
    Meldungen sind zeilenweise unabhängig. `StreamUnlesbar` meint nur:
    die Datei selbst ist nicht zu öffnen. Ein Zustand, den der Wächter
    nicht verursacht und nicht verhindern kann.
    """
ENVELOPE_MARKER = ("<available_subagent_types>",)


def normalisiere(text: str) -> str:
    """Wie in `meldung_digest.py` — **eine** Normalisierung, zwei Sensoren.

    §A-ZZZZ119 (Runde 80): **der Zeitstempel wird vor dem Hash entfernt.**

    Bis Runde 79 blieb er im Text — mit der Begründung, er trenne
    KANAL-DUPLIKAT von WIEDERHOLUNG. Das war ein Denkfehler mit
    Folgen: gleicher Hash ⇒ gleicher Text ⇒ gleicher Zeitstempel ⇒
    `WIEDERHOLUNG` war **strukturell unerreichbar**. Jede Meldung, die
    ein Absender zweimal mit verschiedenem Zeitstempel sendet, bekam
    einen anderen Hash und galt als neu — die Klasse existierte im
    Vertrag und nicht im Code.

    Der Fall `A,A,B,A` hat es aufgedeckt: Position 4 ist inhaltlich
    identisch mit Position 1, wurde aber nie gemeldet.

    Jetzt wird der Zeitstempel **vor** dem Hash entfernt und **daneben**
    als eigenes Feld geführt. Das Etikett entscheidet sich danach aus
    `(hash_gleich, ts_gleich)`, nicht aus dem Hash allein.
    """
    t = re.sub(r"<timestamp>.*?</timestamp>", "", text, flags=re.DOTALL)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t]+$", "", t, flags=re.MULTILINE)
    # §A-ZZZZ110: erst kollabieren, **dann** trimmen.
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip("\n")


def digest(text: str) -> str:
    return hashlib.sha256(normalisiere(text).encode("utf-8")).hexdigest()


def _text_von(nachricht: object) -> str:
    c = (nachricht or {}).get("content") if isinstance(nachricht, dict) else None
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(x.get("text", "") for x in c
                       if isinstance(x, dict) and x.get("type") == "text")
    return ""


def lese_strom(p: Path) -> list[tuple[str, str]]:
    """(zeitstempel, text) je echter Nutzermeldung, in Reihenfolge.

    §A-ZZZZ115 (Runde 79): **Exit 3 hat eine Stelle, nicht nur eine
    Absicht.** Der Wächter ist stateless — aber ein unlesbarer Stream
    ist ein Zustand, den er nicht verursacht und nicht verhindern kann.
    Die Exception wird hier in `StreamUnlesbar` übersetzt; `main`
    entscheidet über den Exit-Code.

    §A-ZZZZ118 (Runde 80): **was übersprungen wird, wird gezählt.**
    Runde 79 meldete bei defektem Format Exit 0 und schwieg dabei: die
    müllige Zeile wurde nie gehasht, der Lauf sah geprüft aus. Gemessen
    am echten Strom: 0 unparsbare Zeilen — der Befund war ein
    **potentieller**, kein eingetretener. Ein potentieller Befund, der
    als eingetretener gemeldet wird, ist dieselbe Lüge in der anderen
    Richtung. Beides gehört in den Bericht: die Zahl der übersprungenen
    Zeilen, und die Verteilung der Gründe.
    """
    try:
        f = p.open(encoding="utf-8")
    except OSError as e:
        raise StreamUnlesbar(f"Stream nicht lesbar: {e}") from e
    out: list[tuple[str, str]] = []
    skip: dict = {"json": 0, "kurz": 0, "envelope": 0, "json_pos": []}
    # §A-ZZZZ139 (Runde 84): **die unparsbare Zeile hat eine Position.**
    # Sie war ein blosser Zaehler. Ein Konsument, der eine Zeile nicht
    # pruefen konnte, muss sie markieren koennen — dafuer braucht er die
    # Zeilennummer, nicht die Summe.
    with f:
        for nr, line in enumerate(f, start=1):
            try:
                o = json.loads(line)
            except ValueError:
                skip["json"] += 1
                skip["json_pos"].append(nr)
                continue
            if o.get("role") != "user":
                continue
            t = _text_von(o.get("message"))
            if len(t) < MIN_LAENGE:
                skip["kurz"] += 1
                continue
            if t.lstrip().startswith(ENVELOPE_MARKER):
                skip["envelope"] += 1
                continue
            m = re.search(r"<timestamp>(.*?)</timestamp>", t)
            out.append((m.group(1) if m else "?", t))
    LESESTAT.update(skip)
    return out


# §A-ZZZZ118: die Zählung hängt am Modul, nicht am Rückgabewert — der
# Rückgabetyp bleibt `list[tuple[str, str]]`, damit jeder Aufrufer
# unverändert bleibt. Eine Signaturänderung für eine Statistik wäre eine
# Kopplung, die niemand braucht.
LESESTAT: dict[str, int] = {"json": 0, "kurz": 0, "envelope": 0}


def exit_aus_zeilen(bericht: list[str]) -> int:
    """Leitet den Strom-Exit aus den Zeilen-Urteilen ab — die einzige Quelle.

    §A-ZZZZ147 (Runde 85): `UNGEPRUEFT` ist unvollstaendig (4),
    `VERWERFEN` ist ein Befund (1), sonst neu (0). Die Reihenfolge ist
    nicht "hart gewinnt", sondern folgt `aggregiere`.
    """
    urteile = {m.group(1) for z in bericht
               for m in [re.match(r"ZEILE \S+ ([A-Z]+);", z)] if m}
    # WIEDERHOLT ist ein Befund (1), aber KEIN Verwerfen — es stehen
    # beide in der Schwere 1, only die Aktion unterscheidet sich.
    befunde = {"VERWERFEN", "WIEDERHOLT"} & urteile
    return aggregiere(4 if "UNGEPRUEFT" in urteile else 0,
                      1 if befunde else 0)


def _unparsbar_zeilen() -> list[str]:
    """§A-ZZZZ139: Meldungszeilen, die nicht pruefbar waren — als Zeilen."""
    # Unparsbare Zeilen haben keinen Inhalts-Hash (es gibt keinen Inhalt).
    # Ihr Zeiger ist die Position — aber die ist hier eindeutig, weil die
    # Zeile nicht parsebar ist und ein Konsument sie per Zeilennummer
    # markiert, nicht per Hash. Das wird im Vertrag als Ausnahme benannt.
    return [f"ZEILE pos:{n} UNGEPRUEFT;pos={n};"
            for n in LESESTAT.get("json_pos", [])]


def pruefe_strom(strom: list[tuple[str, str]]) -> tuple[int, int, list[str]]:
    """Liefert (paare, kanal_duplikate, bericht).

    `kanal_duplikate` zählt Paare mit **identischem** Zeitstempel: das
    ist Doppelzustellung, nicht Wiederholung durch den Absender. Die
    Unterscheidung ist der eigentliche Befund — wer beides in einen
    Topf wirft, kann die Ursache nicht mehr benennen.
    """
    # §A-ZZZZ138 (Runde 84): **Zaehler sind keine Zeiger.**
    # Der Vertrag sagt "Duplikat -> verwerfen". `KANAL-DUPLIKAT=37` sagt
    # WIEVIELE, nicht WELCHE. Ein Konsument konnte die Aktion nicht
    # ausfuehren. Jetzt traegt jede Zeile ihr Urteil: `ZEILE <n> <urteil>`
    # auf derselben Messachse, mit 1-basierten Positionen wie im Bericht.
    seen: dict[str, int] = {}
    bericht: list[str] = []
    paare = kanal = 0
    for i, (ts, t) in enumerate(strom):
        h = digest(t)
        if h in seen:
            # §A-ZZZZ114 (Runde 79): **Referenz auf den unmittelbaren
            # Vorgänger, nicht auf das erste Vorkommen.** Bei A,A,A
            # meldete die erste Fassung `#211 == #213` — wahr, aber
            # Δ=2. Der Bericht behauptete damit eine Adjazenz, die er
            # nicht hatte, und `seen[h]` nach dem Treffer *nicht* zu
            # aktualisieren ließ jede weitere Kopie auf das erste
            # Vorkommen zeigen. Jetzt: `j` ist der Vorgänger, und der
            # Eintrag wandert mit. Damit ist Δ immer 1 und die Aussage
            # des Berichts deckt sich mit der Messung.
            j = seen[h]
            paare += 1
            gleich_ts = strom[j][0] == ts
            kanal += gleich_ts
            art = "KANAL-DUPLIKAT" if gleich_ts else "WIEDERHOLUNG"
            # §A-ZZZZ142 (Runde 84): **die Detailzeile faellt aus der
            # Messachse heraus.** Vorher hing sie mit `  KANAL-DUPLIKAT #1
            # == #2` an derselben Zeile — ein Konsument, der per `;`
            # trennt, sah `  KANAL-DUPLIKAT #1 == #2` als Schluessel ohne
            # `=`. Jetzt: Marke auf der Messachse, Prosa auf eigener Zeile
            # mit Praefix `#` — grammatisch kein Paar.
            # §A-ZZZZ145 (Runde 85): **der Zeiger traegt Inhalt, nicht
            # nur Position.** `ZEILE 2` ist eine Position in einem Strom,
            # der sich bewegt — kommen vorne Meldungen hinzu, zeigt 2 auf
            # eine andere Meldung. Jetzt traegt der Zeiger den Inhalts-
            # Hash; die Position bleibt als Diagnose daneben (zweites
            # Feld, nicht der Zeiger).
            # §A-ZZZZ149 (Runde 85): **das Urteil traegt die Achse, an
            # der ADJ haengt.** Bis R84 warfen beide Etiketten dasselbe
            # `VERWERFEN` — damit war die Frage, ob eine BEWUSSTE
            # Neusendung blockiert werden darf, durch Auslassung
            # entschieden: der Code sagte "ja", der Betreiber hatte nie
            # zugestimmt. Jetzt ein eigener Zeiger-Fall:
            #   KANAL-DUPLIKAT -> VERWERFEN  (bytegleich, gleicher ts)
            #   WIEDERHOLUNG   -> WIEDERHOLT (Inhalt gleich, ts anders)
            # `WIEDERHOLT` ist ein eigener Verdict-Slot, kein stilles
            # VERWERFEN. Die Aktion dazu entscheidet der Betreiber
            # (ADJ); Default ist heute VERWERFEN, jetzt benannt.
            urteil = "WIEDERHOLT" if not gleich_ts else "VERWERFEN"
            bericht.append(f"ZEILE {h} {urteil};pos={i + 1};art={art};")
            bericht.append(f"  # {art} #{j + 1} == #{i + 1}"
                           f"  Δ={i - j}"
                           f"  {'(gleicher Zeitstempel)' if gleich_ts else '(anderer Zeitstempel)'}"
                           f"  sha {h[:12]}")
        else:
            bericht.append(f"ZEILE {h} ZUSTELLEN;pos={i + 1};")
        seen[h] = i
    # Die unparsbaren Zeilen tragen ihr Urteil, ohne Inhalt zu haben.
    bericht[:0] = [z for z in _unparsbar_zeilen()]
    return paare, kanal, bericht


# §A-ZZZZ129 (Runde 83): **die Schwere-Ordnung als Gesetz, nicht als
# Reihenfolge im Code.** Bis Runde 82 entschied die Stelle, an der ein
# `return` stand, welcher Befund gewann — bei "Duplikat + unparsbar"
# gewann das Duplikat, weil sein `return` zuerst kam. Der Vertrag sagte
# dazu nichts.
#
# Die Achse ist **Sicherheit des Urteils**, nicht Haerte:
#
#   2  kein Urteil ueber die Meldung      (Aufruffehler)
#   3  gar nichts geprueft                 (Stream unlesbar)
#   4  geprueft, aber unvollstaendig       (Meldungsbefund + Luecke)
#   1  vollstaendig geprueft: Duplikat     (Meldungsbefund, kein Zweifel)
#   0  vollstaendig geprueft: neu          (kein Befund)
#
# **Exit-Codes sind nominal, nicht ordinal.** Numerisch ist 1 < 4, aber
# 4 ist das strengere Urteil. Wer `exit > 1` vergleicht, baut falsch.
# Deshalb ist die Rangfolge hier als Tabelle hinterlegt, und genau eine
# Funktion entscheidet — jeder zweite Vergleichsort waere ein Fehler.
_SCHWERE = {0: 0, 1: 1, 4: 2, 3: 3}


def aggregiere(*kandidaten: int) -> int:
    """Der strengste Inhalts-Exit gewinnt. Reihenfolge sonst irrelevant.

    §A-ZZZZ140 (Runde 84): **Exit 2 ist eine eigene Achse.**
    Ein Aufruffehler ist ein Meta-Fehler — das Werkzeug konnte nicht
    laufen — und kein Urteil ueber den Inhalt. Bis R83 stand 2 als
    Schwere 4 in derselben Skala wie 0/1/3/4 und war damit das
    schaerfste Inhalts-Urteil, ohne je eines zu sein. Jetzt terminiert
    2: es gibt kein Inhalts-Urteil, also wird nicht aggregiert.
    """
    if 2 in kandidaten:
        return 2
    return max(kandidaten, key=lambda c: _SCHWERE.get(c, 9))


def achse(paare: int, kanal: int, wieder: int, ueber: int | None = None) -> str:
    """Die Messachse — auf JEDEM Zweig, mit denselben Schluesseln.

    Runde 82 emittierte sie nur dort, wo der Autor sie gerade brauchte.
    Ein Konsument, der `Paare` liest, darf je nach Exit nicht auf None
    stossen.
    """
    u = LESESTAT["json"] if ueber is None else ueber
    return (f"Paare={paare};KANAL-DUPLIKAT={kanal};WIEDERHOLUNG={wieder};"
            f"uebersprungen={u};json={u};")


def main(argv: list[str]) -> int:
    # §A-ZZZZ111a: **`--einwurf` zuerst prüfen.** Die erste Fassung fragte
    # `--strom` zuerst ab, und weil `--einwurf` den Strom als Referenz
    # mitbrachte, lief jeder Einwurf-Test still als Strom-Test — Exit 1
    # kam vom falschen Zweig. Gefunden durch die Gegenprobe, nicht durch
    # Lesen: der Test war grün aus dem falschen Grund.
    if "--einwurf" in argv:
        if "--strom" not in argv:
            print(achse(0, 0, 0), end="")
            # §A-ZZZZ148 (Runde 85): **Exit 2 darf nicht zeilenlos sein.**
            print("ZEILE AUFRUF VERWERFEN;grund=einwurf_ohne_strom;")
            print("--einwurf braucht --strom als Referenz", file=sys.stderr)
            return 2
        try:
            strom = lese_strom(Path(argv[argv.index("--strom") + 1]))
            text = Path(argv[argv.index("--einwurf") + 1]).read_text(
                encoding="utf-8")
        except (StreamUnlesbar, OSError) as e:
            # §A-ZZZZ128 (Runde 83): **das Schema ist ueber alle Urteile
            # invariant.** Runde 82 liess den Exit-3-Zweig ohne Messachse
            # — ein Konsument, der immer `Paare=` liest, stiess hier auf
            # nichts. Jetzt emittiert JEDER Exit die volle Achse, auch
            # wenn alle Werte 0 sind. Ein Feld darf nicht existieren,
            # weil der Exit zufaellig 0 ist.
            print(achse(0, 0, 0), end="")
            print(f"DIE WACHE TRÄGT NICHT: {e}", file=sys.stderr)
            return 3
        h = digest(text)
        # Einwurf-Zeitstempel fuer die Etikett-Entscheidung (ts_gleich).
        _mt = re.search(r"<timestamp>(.*?)</timestamp>", text)
        _ein_ts = _mt.group(1) if _mt else "?"
        for i, (ts, t) in enumerate(strom):
            if digest(t) == h:
                ts_gleich = ts == _ein_ts
                # §A-ZZZZ126 (Runde 82): der Einwurf-Zweig trug keine
                # Messachse. Der Mock-Konsument fragte `Paare==1` und
                # fand nichts — Befund des Konsumenten, nicht des
                # Detektors. Jetzt dieselbe Achse wie der Strom-Lauf.
                # §A-ZZZZ129 (Runde 83): **Aggregation, nicht Maskierung.**
                # Unparsbare Zeilen im referenzierten Strom heben das
                # Urteil auf Exit 4: das Duplikat ist ein Teilbefund, der
                # Gesamtstrom wurde nicht vollstaendig geprueft. Bis
                # Runde 82 verschluckte Exit 1 den Alarm, fuer den Exit 4
                # gebaut wurde. Die Regel ist EINE Funktion (aggregiere),
                # nicht ein Vorrang-If.
                _u = LESESTAT["json"] >= JSON_SCHWELLE
                print(achse(1, 1 if ts_gleich else 0,
                            0 if ts_gleich else 1, LESESTAT["json"]),
                      end="")
                print(f"{'KANAL-DUPLIKAT' if ts_gleich else 'WIEDERHOLUNG'};"
                      f"treffer={i + 1};"
                      f"sha={h[:12]};aktion="
                      f"{'blockieren' if not _u else 'blockieren+marke'}")
                return aggregiere(1, 4 if _u else 1)
        print(achse(0, 0, 0, LESESTAT["json"]), end="")
        print(f"NEU;sha={h[:12]};aktion="
              f"{'zustellen' if LESESTAT['json'] < JSON_SCHWELLE else 'zustellen+marke'}")
        return aggregiere(0, 4 if LESESTAT["json"] >= JSON_SCHWELLE else 0)

    if "--strom" in argv:
        p = Path(argv[argv.index("--strom") + 1])
        try:
            strom = lese_strom(p)
        except StreamUnlesbar as e:
            print(achse(0, 0, 0, 0), end="")
            print(f"DIE WACHE TRÄGT NICHT: {e}", file=sys.stderr)
            return 3
        paare, kanal, bericht = pruefe_strom(strom)
        # §A-ZZZZ121 (Runde 81): **Messung und Annotation in getrennte
        # Spalten.** Bis Runde 80 stand hier `bewußt: {paare - kanal}` —
        # eine Kategorie, die der Detektor nicht messen kann. Er sieht
        # Inhalt und Zeitstempel; Absicht sieht er nicht. Wer Annotation
        # in die Zählachse setzt, wird als Nächstes versuchen, sie
        # ausgeben zu lassen. Deshalb steht links der Detektor-Fakt
        # (`WIEDERHOLUNG: 1`) und rechts, klar abgesetzt, die
        # Interpretation, die ein Mensch später einträgt.
        _us = ""
        # §A-ZZZZ139b: json_pos ist eine Liste, nicht ein Zaehler. Wer
        # alle Werte summiert, zaehlt Listen mit — die Summe ist dann
        # ein Typfehler statt einer Zahl.
        _ue = (LESESTAT["json"] + LESESTAT["kurz"]
               + LESESTAT["envelope"])
        if _ue:
            _us = (f";uebersprungen={_ue};json={LESESTAT['json']};"
                   f"kurz={LESESTAT['kurz']};"
                   f"envelope={LESESTAT['envelope']}")
        # §A-ZZZZ122 (Runde 82): **maschinenlesbar statt Prosa.** Vorher
        # "Meldungen: 259 | Paare: 38 | KANAL-DUPLIKAT: 37". Ein Verbraucher
        # musste Etiketten parsen — jedes Relabel brach den Vertrag
        # (Runde 81: 8/9 rot bei reiner Textaenderung). Jetzt
        # `schluessel=wert;` mit stabilen ASCII-Schluesseln.
        print(f"Meldungen={len(strom)};"
              + achse(paare, kanal, paare - kanal)[:-1]
              + f";kurz={LESESTAT['kurz']};envelope={LESESTAT['envelope']}")
        # §A-ZZZZ121b: **die Schwelle ist Vertrag, nicht Gefühl.**
        if LESESTAT["json"] >= JSON_SCHWELLE:
            print(f"WARNUNG: {LESESTAT['json']} unparsbare Zeile(n) — "
                  f"Schwelle {JSON_SCHWELLE} erreicht. Diese Zeilen "
                  f"wurden nicht geprüft und dürfen nicht als geprüft "
                  f"gelten.", file=sys.stderr)
        for z in bericht:
            print(z)
        # §A-ZZZZ122 (Runde 82): **unvollstaendig ist ein eigener Ausgang.**
        # Bis Runde 81 war die Schwelle stderr-only bei Exit 0 — ein
        # Tor-Verbraucher, der nur den Exit-Code liest, stellte den Inhalt
        # zu und sah die Warnung nie. Exit 3 = gar nicht geprueft,
        # Exit 4 = geprueft, aber nicht vollstaendig.
        # §A-ZZZZ147 (Runde 85): **der Exit folgt aus den Zeilen.**
        # Bis R84 entstanden Strom-Exit und Zeilen-Urteile parallel —
        # zwei Wahrheiten ohne Ableitung. Jetzt leitet genau EINE
        # Funktion den Exit aus den Zeilen-Verdicts ab; die Zaehler
        # sind Telemetrie daneben, nicht die Quelle.
        return exit_aus_zeilen(bericht)

    # §A-ZZZZ148 (Runde 85): **Exit 2 darf nicht zeilenlos sein.**
    # Vorher endete 2 vor jedem Zeilen-Array — der Konsument bekam 2 und
    # eine leere Parse. Jetzt traegt auch der Meta-Fall genau EINE Zeile:
    # Zeiger `AUFRUF` (kein Inhalt, also kein Inhalts-Hash), Urteil
    # VERWERFEN — der Konsument blockiert, alarmiert, handelt nicht.
    print(achse(0, 0, 0, 0), end="")
    print("ZEILE AUFRUF VERWERFEN;grund=kein_modus;")
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
