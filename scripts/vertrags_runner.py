#!/usr/bin/env python3
"""Vertrags-Runner: prüft Wächter gegen Text, Exit, stderr, Speicherzustand.

§A-ZZZZ112 (Runde 78): **die Fehlerfläche ist der Vertrag, nicht die Logik.**
§A-ZZZZ116 (Runde 79): **die Fallzahl wird gerendert, nicht getippt.**

Fünf Runden, fünf Fehler, eine Klasse — alle in der Argument- oder
Zustandsbehandlung, keiner in der Rechnung:

    1. PermissionError statt Exit 3     (Datei-Zustand)
    2. Leerzeile blieb stehen           (Normalisierungs-Zustand)
    3. `--strom` vor `--einwurf`        (Argument-Zustand)
    4. Off-by-one im Testtisch          (Test-Zustand)
    5. Heredoc scheiterte still, NameError in der Reparatur (Bau-Zustand)

**Die Fälle stehen nicht mehr in dieser Datei, sondern in
`scripts/waechter_vertrag.json`.** Der Grund ist der Altposten 4/8:
eine Zahl, die im Code getippt ist, wandert nicht, wenn die
Wirklichkeit wandert. Wird ein Fall ergänzt, ändert sich die Zahl im
Bericht — weil sie aus dem Vertrag kommt, nicht aus einer Zeile, die
jemand anfassen muß.

**Mutation je Vertragsfeld** (`--mutation`): Text, Exit, stderr und
Isolation werden nicht durch Handbeweis belegt, sondern durch
eingebaute Fehler, die der Runner fangen muß. Ohne diese Suite
zertifiziert „7/7 grün" einen Runner, dessen eigene Prüfung nicht
regressionsgeschützt ist.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "einwurf_waechter.py"
VERTRAG = ROOT / "scripts" / "waechter_vertrag.json"
TRANSCRIPT = Path(
    "/Users/olivermueller/.cursor/projects/"
    "Volumes-THX-OS-ULTRA-Users-olivermueller-agent-x-storage-order-"
    "execution-engine/agent-transcripts/"
    "ed0106b6-8a07-4cda-ac09-53851e6aa04a/"
    "ed0106b6-8a07-4cda-ac09-53851e6aa04a.jsonl"
)


def lade_vertrag() -> dict:
    return json.loads(VERTRAG.read_text(encoding="utf-8"))


def _dir_hash(p: Path) -> str:
    """Zustand des Arbeitsverzeichnisses — für die Speicher-Isolation."""
    h = hashlib.sha256()
    for f in sorted(p.rglob("*")):
        if f.is_file():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def _lauf(args: list[str], cwd: Path, script: Path = SCRIPT,
          seed: str | None = None) -> tuple[int, str, str]:
    # §A-ZZZZ184 (Runde 89): **Umgebungsvarianz, kein Zufall im Detektor.**
    # R88 schrieb als offenen Punkt "Zufallsquelle im DETEKTOR fehlt" —
    # das ist der falsche Fix: Nichtdeterminismus in Produktionscode ist
    # genau der Defekt, den ein robustes System nicht haben darf. Was
    # fehlt, ist Harness-Varianz: PYTHONHASHSEED aendert die
    # Set-/Dict-Iterationsreihenfolge. Ein Mutant, der nur darunter
    # entkommt, ist dann sichtbar.
    import os
    env = dict(os.environ)
    if seed is not None:
        env["PYTHONHASHSEED"] = seed
    r = subprocess.run([sys.executable, str(script), *args],
                       capture_output=True, text=True, cwd=cwd, env=env)
    return r.returncode, r.stdout, r.stderr


def _args(name: str, t: Path, d: Path) -> list[str] | None:
    """Argumente je Fallname. `None` heißt: unbekannter Fall → Befund."""
    return {
        # §A-ZZZZ159: eingefrorenes Fixture statt Live-Transcript.
        "strom-alle": ["--strom", str(d / "fest.jsonl")],
        "strom-live": ["--strom", str(t)],
        "einwurf-bekannt": ["--einwurf", str(d / "bekannt.md"), "--strom", str(t)],
        "einwurf-neu": ["--einwurf", str(d / "neu.md"), "--strom", str(t)],
        "kein-argument": [],
        "einwurf-ohne-strom": ["--einwurf", str(d / "neu.md")],
        "strom-fehlt": ["--strom", str(d / "gibtsnicht.jsonl")],
        # Dreiergruppe: drei identische Meldungen hintereinander. Erwartet
        # werden ZWEI Duplikat-Ereignisse, beide mit Δ=1 zum Vorgänger.
        "dreiergruppe": ["--strom", str(d / "dreier.jsonl")],
        "aaba": ["--strom", str(d / "aaba.jsonl")],
        "uebersprung": ["--strom", str(d / "muell.jsonl")],
        "uebersprung-allein": ["--strom", str(d / "nurmuell.jsonl")],
    }.get(name)


def _saat(d: Path, strom: list, neu_text: str) -> None:
    (d / "bekannt.md").write_text(strom[0][1], encoding="utf-8")
    (d / "neu.md").write_text(neu_text, encoding="utf-8")
    # Dreiergruppe als eigener Strom: A,A,A — mit Zeitstempeln.
    zeile = json.dumps({"role": "user",
                        "message": {"content": strom[0][1]}},
                       ensure_ascii=False)
    (d / "dreier.jsonl").write_text("\n".join([zeile] * 3) + "\n",
                                    encoding="utf-8")
    # A,A,B,A — der Fall, der die Referenzsemantik beobachtbar macht.
    def _z(ts: str, txt: str) -> str:
        return json.dumps({"role": "user", "message": {
            "content": f"<timestamp>{ts}</timestamp>\n{txt}"}},
            ensure_ascii=False)
    a, b = "A" * 500, "B" * 500
    (d / "aaba.jsonl").write_text(
        "\n".join([_z("T1", a), _z("T1", a), _z("T2", b), _z("T3", a)]) + "\n",
        encoding="utf-8")
    # Zwei unparsbare Zeilen — die Uebersprung-Zahl muss im Bericht stehen.
    (d / "muell.jsonl").write_text(
        zeile + "\nKEIN JSON\n{kaputt\n", encoding="utf-8")
    # Nur Muell, keine gueltige Meldung — dann ist Exit 4 zwingend und
    # nicht durch ein Duplikat (Exit 1) maskiert.
    (d / "nurmuell.jsonl").write_text(
        "KEIN JSON\n{kaputt\n", encoding="utf-8")
    # §A-ZZZZ159 (Runde 86): **`strom-alle` lief gegen den LIVE-Transcript.**
    # Der Test war damit selbst ein `pos=`: seine Erwartung 38/37 war an
    # einen Strom gebunden, der mit jeder Konversationszeile waechst. Die
    # Zahl war bei der Abnahme 39 — im Commit stand trotzdem "10/10".
    # Jetzt: ein eingefrorenes Fixture mit BEKANNTER Zahl. Der Live-Strom
    # wird separat nur ueber eine INVARIANTE geprueft (Paare <=
    # Meldungen, Exit folgt aus Zeilen) — nie ueber eine Konstante.
    # Zeitstempel explizit: `zeile` aus dem Live-Strom hat keinen, und
    # ohne ts sind ALLE Vorkommen '?'-gleich, also immer KANAL-DUPLIKAT.
    zeilen = [_z("T1", a), _z("T1", a),                        # 1 KANAL-DUPLIKAT
              _z("T2", b), _z("T2", b),                       # 1 KANAL-DUPLIKAT
              _z("T3", a)]                                    # 1 WIEDERHOLUNG
    (d / "fest.jsonl").write_text("\n".join(zeilen) + "\n",
                                  encoding="utf-8")


def fahre(script: Path, vertrag: dict, strom: list,
          neu_text: str, seed: str | None = None) -> tuple[int, int, list[str]]:
    """Führt alle Vertragsfälle aus. Liefert (ok, gesamt, meldungen)."""
    ok = 0
    gesamt = 0
    meldungen: list[str] = []
    for fall in vertrag["vertragsfaelle"]:
        gesamt += 1
        name = fall["name"]
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            _saat(d, strom, neu_text)
            a = _args(name, TRANSCRIPT, d)
            if a is None:
                meldungen.append(f"FAIL {name}: Fall im Vertrag, aber kein "
                                 f"Argument-Bauer im Runner")
                continue
            vorher = _dir_hash(d)
            code, out, err = _lauf(a, d, script, seed=seed)
            nachher = _dir_hash(d)
            if vorher != nachher:
                meldungen.append(f"FAIL {name}: Speicher verändert (Blutung)")
                continue
            if fall["text"] not in (out + err):
                meldungen.append(
                    f"FAIL {name}: Text fehlt — erwartet {fall['text']!r}, "
                    f"bekam {(out + err).strip()[:70]!r}")
                continue
            if code != fall["erwarteter_exit"]:
                meldungen.append(f"FAIL {name}: Exit {code} statt "
                                 f"{fall['erwarteter_exit']}")
                continue
            # Dreiergruppe: zwei Ereignisse, beide Δ=1.
            if name == "dreiergruppe":
                if out.count("Δ=1") != 2:
                    meldungen.append(
                        f"FAIL {name}: {out.count('Δ=1')} Δ=1-Ereignisse, "
                        f"erwartet 2 (Vorgänger-Semantik)")
                    continue
            ok += 1
            meldungen.append(f"ok   {name:22s} exit={code}  text ok  "
                             f"speicher isoliert")
    return ok, gesamt, meldungen


# §A-ZZZZ116: **eine Mutation je Vertragsfeld.** Jede verändert eine
# Kopie des Wächters so, daß genau ein Feld brechen muß. Wird sie nicht
# gefangen, ist der Runner selbst defekt — und das ist ein Befund.
#
# Erste Fassung: die Text-Mutation ersetzte `nicht zustellen.")` durch
# `")` — die Ausgabe blieb dieselbe, weil der Satz davor stehenblieb.
# Und die stderr-Mutation traf den Quelltext von `main`, aber der
# `strom-fehlt`-Fall liest den Text aus stderr — beide Meldungen
# erschienen weiter. Beide Mutationen waren **wirkungslos** und der
# Runner meldete „nicht gefangen", obwohl er recht hatte: er konnte
# nichts fangen, was nicht kaputt war. Jetzt greifen sie den Satz
# selbst an, den ein Fall prüft.
MUTATIONEN = [
    # §A-ZZZZ124 (Runde 82): die Muster zeigen jetzt auf die MESSACHSE.
    # Nach dem Umbau auf `schluessel=wert;` trafen die alten Prosa-Muster
    # nichts mehr und der Runner meldete "Muster nicht gefunden" — ein
    # Mutationsloch, kein gruener Lauf. Das ist Runde 79 eine Etage hoeher.
    ("Text", "KANAL-DUPLIKAT={kanal}", "KANAL-DUPLIKAT=0"),      # Zaehler stumm
    # §A-ZZZZ130 (Runde 83): **die Konstante, die richtig raet.** Der
    # Mutant setzt den Zaehler auf 37 statt zu zaehlen. Er besteht jedes
    # Fixture, das 37 erwartet — und muss an test_konstanten.py
    # scheitern, wo Fixture A 0 und B 1 verlangt.
    ("Konstante", "KANAL-DUPLIKAT={kanal}", "KANAL-DUPLIKAT=37"),
    # Die Exit-Mutation prueft, dass ein Duplikat wirklich blockiert:
    # der Strom-Zweig muss ohne Duplikat 0 liefern.
    # §A-ZZZZ152 (Runde 85): die Mutation zielt jetzt auf die EINE
    # Ableitung. "4 if LESESTAT..." existiert nicht mehr — der Exit folgt
    # aus den Zeilen (exit_aus_zeilen). Eine Mutation auf entfallenen
    # Code ist kein Fangerfolg, sondern ein Textmuster ohne Ziel.
    ("Exit", "return exit_aus_zeilen(bericht)",
     "return 0 if not any('VERWERFEN' in z for z in bericht) else 1"),
    ("Exit4", '4 if "UNGEPRUEFT" in urteile else 0', "0"),
    ("stderr", "DIE WACHE TRÄGT NICHT", "WACHE LAEUFT"),         # Wort weg
    ("Zweig", None, None),  # Reihenfolge, s. _mutiere_zweig
]


def _mutiere(feld: str, src: str) -> str | None:
    if feld == "Zweig":
        i = src.index('    if "--einwurf" in argv:')
        j = src.index('    if "--strom" in argv:')
        z = src.index('    print(__doc__.strip()', j)
        return src[:i] + src[j:z] + src[i:j] + src[z:]
    for name, alt, neu in MUTATIONEN:
        if name == feld and alt:
            # §A-ZZZZ116b: **alle Vorkommen ersetzen.** Die erste Fassung
            # nutzte `replace(alt, neu, 1)` und traf bei der stderr-Mutation
            # nur eine von zwei `print`-Stellen — die zweite feuerte im
            # geprüften Fall, und der Runner meldete „nicht gefangen",
            # obwohl die Mutation nur halb war. Eine halbe Mutation ist
            # kein Beweis über den Runner, sondern über ihre eigene
            # Reichweite.
            return src.replace(alt, neu) if alt in src else None
    return None


def _konstanten_probe(script: Path) -> bool:
    """True, wenn der Mutant die drei Konstanten-Proben NICHT besteht."""
    import tempfile as _tf
    with _tf.TemporaryDirectory() as td:
        d = Path(td)
        t = d / "konst.py"
        t.write_text(
            (ROOT / "scripts" / "test_konstanten.py").read_text(encoding="utf-8")
            .replace('Path(__file__).resolve().parent / "einwurf_waechter.py"',
                     f'Path({str(script)!r})'), encoding="utf-8")
        r = subprocess.run([sys.executable, str(t)], capture_output=True,
                           text=True, cwd=d)
        return r.returncode != 0


def _laeufe_pro_mutant() -> int:
    try:
        return max(1, min(20, int(os.environ.get("MUTANT_LAEUFE", "3"))))
    except ValueError:
        return 3


def _varianz_strom(strom: list, saat: int) -> list:
    """§A-ZZZZ176 (Runde 88): **Input-Varianz statt Wiederholung.**

    R87 lief jeden Mutanten dreimal — auf byte-gleichem Input. Bei einer
    Pipeline ohne Zufallsquelle sind drei Laeufe identisch: die Zahl war
    "1 Lauf, dreimal gezaehlt". Dieser Helfer variiert den STROM:
    Reihenfolge der Meldungen, Doppelungen, ein eingestreuter Muell-Satz.
    Ein Mutant, der nur unter einer Ordnung entkommt, wird jetzt sichtbar.
    """
    import random
    rnd = random.Random(saat)
    v = list(strom)
    if not v:
        return v
    # `_saat` liest strom[0] als Kopf — den Vorgaenger nicht wegshuffeln.
    kopf, rest = v[0], v[1:]
    rnd.shuffle(rest)
    v = [kopf] + rest
    v.append(v[rnd.randrange(len(v))])       # spaete Kopie
    return v


def mutationssuite(vertrag: dict, strom: list, neu_text: str) -> tuple[int, int, list[str]]:
    ok = 0
    meldungen: list[str] = []
    quelle = SCRIPT.read_text(encoding="utf-8")

    # §A-ZZZZ120 (Runde 80): **Negativkontrolle zuerst.** Die
    # unveränderte Quelle muß volles Grün ergeben. Tut sie das nicht,
    # ist jeder Mutationsbefund wertlos — der Fehler läge im Gate, nicht
    # im Mutanten. Das war Anlauf 3 der Runde 79: der Runner tadelte
    # den Prüfling für seinen eigenen Defekt. Ein falsch-positives Gate
    # blockiert gültige Arbeit und wird deshalb ignoriert — schlimmer
    # als ein stilles.
    nok, nges, _ = fahre(SCRIPT, vertrag, strom, neu_text)
    if nok != nges:
        meldungen.append(f"FAIL Negativkontrolle: unveränderte Quelle "
                         f"{nok}/{nges} — Gate defekt, Mutationen wertlos")
        return 0, len(MUTATIONEN), meldungen
    meldungen.append(f"ok   Negativkontrolle     {nok}/{nges} grün "
                     f"(unverändert)")

    # §A-ZZZZ166 (Runde 87): **ein Lauf pro Mutant ist keine Messung.**
    # Ein Mutant, der nur gelegentlich entkommt (Zeit, Ordnung, Seed),
    # wurde mit einem Lauf als "deterministisch gefangen" verbucht. Jetzt
    # N Laeufe; nur wenn JEDER faengt, gilt er als gefangen. Ein Mutant,
    # der mal faengt und mal nicht, wird als INSTABIL gemeldet — das ist
    # eine eigene Klasse, schlimmer als "entkommen", weil sie sich als
    # fangbar tarnt.
    N = _laeufe_pro_mutant()
    for feld, _, _ in MUTATIONEN:
        mutiert = _mutiere(feld, quelle)
        if mutiert is None or mutiert == quelle:
            meldungen.append(f"FAIL Mutation {feld}: Muster nicht gefunden "
                             f"— die Mutation prüft nichts")
            continue
        # §A-ZZZZ120b: **Mutanten-Validität.** Eine Mutation, die keine
        # vom Vertrag assertierte Ausgabe ändert, ist äquivalent — sie
        # kann nicht gefangen werden und darf nicht als Beweis zählen.
        # Sie wird hier *nicht* als „gefangen" verbucht, sondern als
        # ungültig gemeldet. Die zwei Anläufe der Runde 79 (Text-Mutation
        # traf einen ungeprüften Satz, stderr-Mutation traf eine von
        # zwei Stellen) wären damit als **unbeobachtbar** klassifiziert
        # worden, statt den Runner zu tadeln.
        with tempfile.TemporaryDirectory() as td:
            kopie = Path(td) / "waechter_mutiert.py"
            kopie.write_text(mutiert, encoding="utf-8")
            nok, nges, nmsg = fahre(kopie, vertrag, strom, neu_text)
            # §A-ZZZZ131 (Runde 83): **zwei Fixtures statt einer.** Der
            # Konstanten-Mutant besteht jeden Vertragsfall, der nur 1
            # erwartet. Er scheitert erst an abweichenden Soll-Werten.
            _konst_rot = _konstanten_probe(kopie)
            _gefangen = (nok != nges) or _konst_rot
            # §A-ZZZZ166: N-1 weitere Laeufe. Ergebnis muss identisch sein,
            # sonst ist der Mutant instabil — und eine instabile Probe
            # zaehlt nicht als gefangen.
            _instabil = False
            _SEEDS = [None, "0", "1", "12345"]
            for _i in range(N - 1):
                _v = _varianz_strom(strom, saat=(hash(feld) ^ _i) & 0xFFFF)
                _n2, _g2, _ = fahre(kopie, vertrag, _v, neu_text,
                                    seed=_SEEDS[(_i + 1) % len(_SEEDS)])
                _gef2 = (_n2 != _g2) or _konstanten_probe(kopie)
                if _gef2 != _gefangen:
                    _instabil = True
                    break
            if _instabil:
                meldungen.append(
                    f"FAIL Mutation {feld}: **INSTABIL** — faengt in "
                    f"{N} Laeufen nicht immer; N=1 haette sie als gefangen "
                    f"verbucht")
                continue
            if not _gefangen:
                # Verändert der Mutant überhaupt eine assertierte Ausgabe?
                if not any(m.startswith("FAIL") for m in nmsg):
                    meldungen.append(
                        f"FAIL Mutation {feld}: **unbeobachtbar** — keine "
                        f"assertierte Ausgabe verändert, Mutant ungültig")
                    continue
                meldungen.append(f"FAIL Mutation {feld}: nicht gefangen "
                                 f"({nok}/{nges} grün)")
                continue
        ok += 1
        _wie = (f"{nok}/{nges} grün" if nok != nges
                else "Vertrag grün, Konstanten-Probe rot")
        meldungen.append(f"ok   Mutation {feld:9s} gefangen ({_wie})")
    return ok, len(MUTATIONEN), meldungen


def main(argv: list[str]) -> int:
    if not TRANSCRIPT.is_file():
        print("Transcript nicht lesbar — Vertragstest nicht durchführbar")
        return 3
    vertrag = lade_vertrag()
    sys.path.insert(0, str(ROOT / "scripts"))
    import einwurf_waechter as e  # noqa: E402
    strom = e.lese_strom(TRANSCRIPT)
    neu_text = "## Vertragstest\nEin Text, der im Strom nicht vorkommt.\n" * 20

    ok, gesamt, meldungen = fahre(SCRIPT, vertrag, strom, neu_text)
    for m in meldungen:
        print(m)
    print(f"\n{ok}/{gesamt} Vertragsfälle grün")

    rc = 0 if ok == gesamt else 1
    if "--mutation" in argv:
        mok, mges, mm = mutationssuite(vertrag, strom, neu_text)
        for m in mm:
            print(m)
        print(f"\n{mok}/{mges} Mutationen gefangen")
        if mok != mges:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
