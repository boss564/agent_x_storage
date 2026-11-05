# SP-832 Phase 1 — Hook-Fix: Fix belegt, Gate bleibt rot (dritte Ursache)

**Messung:** 2026-11-05T18:25Z · **Anker vor Fix:** `3031a8d4`

## Was gefixt wurde (2 Änderungen)

### 1. `scripts/hole_r106_aus_transkript.py` — Live-Pfad entfernt

**Befund:** Der Helfer trug den Live-Transcript hart kodiert in `scripts/` — der
einzige von drei Harness-Zaun-Verstößen. `test_harness_zaun.py` meldete `2/3`.

**Fix:** Pfad wird zur Laufzeit hereingereicht (`--transkript <pfad>` oder Env
`AGENTX_TRANSKRIPT`). **Kein Default auf einen Live-Pfad** — fehlt beides, bricht
der Aufruf mit benannter Meldung ab. Bewusst **keine** neue Ausnahme in
`AUSNAHMEN`: Die Ausnahme wäre die Vertuschung, die der Zaun verhindern soll.

**Begründung, warum der Zaun recht hatte:** Das Skript ist *kein Test* (0 `def test_`,
0 `assert`). Sein Gegenstand — der R106-Payload — ist byte-exakt über `ERWARTETE_SHA`.
Die Prüfung ist damit **unabhängig vom Zieldatei-Pfad**. Der Live-Pfad war
Bequemlichkeit, nicht Notwendigkeit.

### 2. `scripts/check_claude_md.py` — Doppelnennung im Korb

`scripts/beweis.py` stand **zweimal** im Korb (Z. 5940/5941, gleiches Skript, zwei
Kommentare). Entfernt, Begründung inline.

## Messung (vorher → nachher)

| Prüfung | vorher | nachher |
|---|---|---|
| `test_harness_zaun.py` | **2/3** (FAIL) | **3/3** (ok) |
| Zaun: Live-Pfad-Verstöße | 1 | **0** |
| `hole_r106` ohne Env | (Default = Live) | **bricht benannt ab** (EXIT=1) |
| `hole_r106` mit Env | `len=439 sha=3025…` | `len=439 sha=3025…` (identisch) |
| `test_beleg_export.py` | EXIT=0 | **EXIT=0** (Regression grün) |
| Checker `Harness-Zaun` | 2/3 | **3/3** |
| Checker `Harness-Zaun` (Regression, Anker) | 2/3 | **3/3** |

## Befund, der sich NICHT erledigt hat — dritte Ursache

`Harness-Zaun 2/3 → 3/3` ist erledigt. **Der Checker bleibt `EXIT=1`.**

Gegen den Anker (`3031a8d4`) ist die Ausgabe **bytegleich** zur Vor-Fix-Ausgabe,
bis auf die Zaun-Zeile:

```
Harness-Zaun 2/3   ->   3/3
```

Der Befund ist damit **reproduzierbar und baumunabhängig** — aber eine **zweite,
unabhängige Ursache** hält das Gate rot:

```
Prüfblock: 9 gemessen · 0 nicht gemessen · Prüfer 3b7240aaeaba · 0 offen
Block:     Kopfzeile: Prüfer af77393000f8 im Block — Block ist Vorzustand
```

Der Prüfblock bei `TAG7_ABNAHME.md:7828` (`af77393000f8`) ist **kein redaktioneller
Tippfehler**. Er wird vom Checker aus dem laufenden Baum gerechnet
(`sha256:50fff349`, `Baum 678da9d6+dirty`) — und der Baum hat sich seither geändert.
Der Prüfer-Hash über `_pruefer_hash()` war schlicht für einen anderen Baumstand.

**Folgerung:** Der „Kopfzeilen-Drift" ist **kein Fix am Text**, sondern ein
**Regenerations-Auftrag**: Der Block muss gegen den heutigen Baum neu gerechnet
werden. Ein Einfrieren in den Fix-Commit würde ihn als *Vorzustand* fortschreiben —
genau das, was `_kopfzeile_errors` mit der Meldung „Block ist Vorzustand" benennt.

## Konsequenz für SP-833 (zweiter Bypass)

Der zweite Bypass ist **zulässig und nötig** — aber er landet **einen Teilfix**,
kein grünes Gate. Die Buchung lautet deshalb präzise:

- **erledigt:** Harness-Zaun-Verstoß (inhaltlich, mit Regression belegt)
- **offen:** Kopfzeilen-Regeneration (SP-836 neu) → danach soll der Checker grün sein
- **Bypass-Zahl danach:** **3**, nicht 2 (Freeze, Nachtrag, Hook-Fix)

Ein Fix, der das Gate rot lässt, ist ein Fix der ersten Ursache — nicht der zweiten.
Wer das als „repariert" verbucht, begeht die Fehlerklasse, die diese Serie aufdeckt.

## Herkunft der Zahlen (Paste)

```
$ python3 scripts/test_harness_zaun.py
ok   Zaun: keine Live-Pfade     0 Verstoesse
ok   Zaun erkennt Live-Pfad    True
ok   strom-live als Fall         True
3/3 Harness-Zaun-Faelle gruen

$ python3 scripts/hole_r106_aus_transkript.py
Transkript nicht gesetzt: --transkript <pfad> oder AGENTX_TRANSKRIPT.
Kein Live-Default (Harness-Zaun).          [EXIT=1]

$ AGENTX_TRANSKRIPT=… python3 scripts/hole_r106_aus_transkript.py
len=439 sha=30257636d107f7019074d85de4742e119f0faa24ddcf6340e0741d4ce7b00b52

$ python3 scripts/check_claude_md.py . --run-tests   [EXIT=1]
… Harness-Zaun 3/3 …
Kopfzeile: Prüfer af77393000f8 im Block, 3b7240aaeaba heute — Block ist Vorzustand
```
