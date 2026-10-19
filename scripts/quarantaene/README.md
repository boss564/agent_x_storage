# Quarantäne (Runde 93)

Hier liegen die vier Suiten, die in **Runde 92 gegen die eigene Stopp-Bedingung**
gebaut wurden. Sie sind nicht gelöscht und nicht grün — sie sind **gesperrt**.

## Warum

Die Stopp-Bedingung aus v15 lautet: *solange EXT-1..4 keinen Eigentümer haben,
keine neue interne Maschinerie.* Sie wurde in derselben Runde überfahren, in der
sie beschlossen wurde. Die Konsequenz war eine Buchung, kein Rollback.

Eine Regel, deren Bruch nur den Ledger ändert und nicht den Baum, ist keine
Regel — sie ist eine Beobachtung mit Sanktionsvokabular.

## Was gesperrt ist

| Datei | Warum sie hier liegt |
|---|---|
| `test_record_grammatik.py` | Baut eine Fähigkeit, die kein Abnehmer abruft (`parse_zeilen()` hat keinen Aufrufer) |
| `test_externes_gate.py` | Grün aus **Form** (4× ENTSCHEIDUNG), nicht aus Besetzung |
| `test_ledger_provenienz.py` | Erkennt Nachtrag, nicht Zeitpunkt; Git-Zeuge als „außerhalb" deklariert |
| `test_schwelle_eingaenge.py` | Misst eine Herleitung, deren Eingang `None` ist |

## Freigabe

`test_enforcement.py` prüft, dass sie **nicht** zurückkehren, solange
`freigabe_bei: alle_posten_mit_eigentuemer` nicht erfüllt ist.

Die Freigabe hängt an einem **Namen in der Eigentümer-Spalte**, nicht an einem
Datum. Kein Gate, keine Suite und kein Commit kann diesen Namen erzeugen.
