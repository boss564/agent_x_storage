# SP-841 — Befund, Beleg, Schließung (2026-11-05)

Buchung: **Befund** (nicht Notiz). Die Lücke war real, unabhängig von der
Regeneration, und sie verändert den Beweiswert jedes grünen Laufs.

## 1. Befund

`_akt_block_mismatch` prüfte den Zahlenkopf (`total=…`), die `Bezug:`-Zeile
(`root`, `CLAUDE.md sha256`) — und **nicht** die `Zustand:`-Zeile des
zitierten Messblocks. Ein Block, dessen Zustandszeile nicht mehr zur
Messung paßte, konnte grün durchgehen.

## 2. Beleg (Vorher, mutationsbasiert)

Der ziterte Block wurde im Speicher verändert — `Zustand: 4/8 Meßblöcke` →

    Zustand: 99/99 FALSCH-Absichtlich …

und gegen den Lauf verglichen. Ergebnis **vor** dem Fix: `_compare_block`
lieferte **keine** Meldung (0 Befunde). Die Mutation war unsichtbar.

## 3. Reparatur (O3, nachhaltig)

`_compare_block` vergleicht jetzt zusätzlich die **Struktur** der
`Zustand:`-Zeile: `_zustand_symbol()` ersetzt jeden Zahlenwert durch `#`,
der so maskierte Satz muß gleich sein. Ziffern bleiben Sache der Karte
(Fingerprint), die **Struktur** — Einheiten, Feldnamen, Feldzahl — wird
damit selbst geprüft. Ein Einheitenwechsel oder ein fehlendes Feld
schlägt an, eine reine Zahlenverschiebung nicht (sie ist Karten-Drift und
wird dort gefangen).

Gegenlauf im Selbsttest (`_self_test_akt_block`): der Block wird auf
`Zustand: 99/99 FALSCH` mutiert; kommt keine Meldung mit `Zustand`, ist
der Test rot. Fehlt das Muster selbst, ist der Test ebenfalls rot (sonst
würde eine Prozedur, die nichts trifft, als grün gelten).

## 4. Nachher

    BELEG Akte-Mismatch=[]

Der geschriebene Block (`§71.76` in `TAG7_ABNAHME.md`) ist mit dem
heutigen Lauf deckungsgleich — Kopf, `Bezug:`, `Zustand:`, `Karte:`.

## 5. Was diese Runde zusätzlich gefunden hat (nicht verschwiegen)

Am geschriebenen Block sichtbar geworden und mitgemessen, statt es
später als „bekannte Lücke" zu führen:

| Fund | Wirkung | Behandlung |
|---|---|---|
| Blocktext-Herkunft | Das Werkzeug schrieb Kopf + Karte + Lab-Landkarte als eigenen Text — der Vergleich liest aber die **erste Zeile** als `total=`-Kopf. Ergebnis war `total None zitiert, 0 gemessen` bei einem Block, der den Wert enthält. | Blocktext ist jetzt `calibration_card()` byte-gleich, ohne Zusatz |
| Block ohne eigene Überschrift | Der Anhang landete unter `### 9. Stand` und wurde von `split_blocks` als Teil eines Vorzustands gelesen | eigener Abschnitt `### §71.76 — Messblock …` |
| Fixture-Sollbruch | `check_fixtures._akt_block` ersetzte `total=1 `, die Fixture-Karte trägt aber `total=0` → `0 vs 0`, „Wirkung" war rot, ohne daß etwas kaputt war | Ersatz per `re.sub(r"^total=\d+", …)`; Wirkung jetzt `1 vs 0` |
| `check_counts`-Selbsttest | Mehrere Befunde: Prosa-Zahlen ohne Herkunft, `root` nicht durchgereicht, Literal-Regel feuerte auf die berechnete Toleranz, `_akt_block_mismatch` mit `0 vs 0` | Zahlen benannt oder entfernt, `root`-Name eingeführt, `differenz` benannt, Fixture repariert |
| Meßbereich-Zuwachs | Alle Dateien ohne Bereich, darunter `scripts/schreibe_messblock.py`; der Zähler meldete den Zuwachs, aber keine der Dateien war zugewiesen | Ist-Stand als Bereich `unzugewiesen` eingetragen — **Zuordnung, keine Prüfung**; der Zähler `pruefe_messbereich` hat jetzt einen Fixture-Gegenlauf (`2 vs 0`) |

## 6. Selbstbezug — die letzte Kante

`Prüfer <hash>` in der Karte hängt an `scripts/*.py`. Jede Änderung an
`schreibe_messblock.py` oder `check_claude_md.py` verschiebt ihn; der
Block ist deshalb **das letzte** Artefakt der Runde, nicht das erste.
Geprüft wird im Werkzeug selbst: Hash vor dem Anhängen, Hash nach dem
Anhängen, Gleichheit — sonst kein Block.

## 7. Grenze, benannt

`check_messbereich` zählt **Dateien**, nicht ob eine Datei geprüft wird.
Die neue Zuordnung macht den Zuwachs meßbar; sie behauptet nicht, daß
diese Dateien eine Meßkette haben. Das steht so im Code-Kommentar und
hier — eine Zahl ohne diese Grenze wäre größer, als sie ist.
