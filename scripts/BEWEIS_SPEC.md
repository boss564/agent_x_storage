# BEWEIS-SPEC v1 — Kanonisierung des Zitat-Payloads

Ein SHA-256 ist nur dann cross-party reproduzierbar, wenn die exakte
Byte-Sequenz spezifiziert ist. R104 hat den Digest geliefert und die
Rahmung verschwiegen. Diese Datei ist die Rahmung.

## 1. Was gehasht wird

Gehasht wird **genau** die Nutzlast `payload` — der Text zwischen der
Markerzeile `sha256=… datei=… zeilen=…` und der Schlusszeile `BEWEIS>>>`.
Markerzeilen sind **nicht** Teil des Payloads.

## 2. Byte-Kanonisierung (verbindlich)

| Regel | Wert |
|---|---|
| Zeilenende | `\n` (LF), **niemals** CRLF |
| Letztes Byte | genau **ein** `\n` am Ende; kein zusätzliches |
| Tabs | **byte-exakt aus der Quelle**, nicht expanded |
| Backslash-Fortsetzung | **Literal** — `\` + LF bleiben Zeichen im Payload |
| Encoding | UTF-8, ohne BOM |
| Trailing Whitespace | **exakt aus der Quelle**, nicht getrimmt |
| Zeilennummerierung | 1-basiert, `von`..`bis` **inklusiv** |

## 3. Rechenweg für einen Dritten (ohne Werkzeug)

    # payload.txt = exakt die Bytes laut §1 und §2
    sha256sum payload.txt
    # vergleiche mit dem sha256= im Block

Referenzimplementierung, falls kein Textfile vorhanden ist (Python-Kern):

    python3 -c "import json,sys,hashlib; e=json.load(open(sys.argv[1])); \
    print(hashlib.sha256(e['text'].encode('utf-8')).hexdigest())" beleg.json

## 4. Die zwei Bindungen — getrennt deklariert

| Feld | Bindet | Rolle im `check --strict` |
|---|---|---|
| `sha256` (Region) | `von`..`bis` | **Beweisbindung. MUSS stimmen.** |
| `sha256_datei` (Datei) | ganze Datei | **Provenienz.** Darf abweichen (Versionszeiger). |
| `zeilen` | Zeilenzahl der Datei | Provenienz, Hinweis auf Umfang |

Begründung: R104 erzwang beide und hätte damit jeden historischen Beleg
entwertet, sobald irgendwo im Makefile etwas geändert wird. Das Zitat
bleibt wahr; die Datei bewegt sich. Beweisbindung ≠ Versionierung.

`check --strict` prüft **Region + Wortlaut + Zeilenbereich**.
Weicht `sha256_datei` ab, meldet `check` **PROVENIENZ-DRIFT** (sichtbar,
nicht blockierend) — außer mit `--provenienz-streng`.

## 5. Historie

| v | Runde | Änderung |
|---|---|---|
| 1 | R105 | Erste Fassung. Ersetzt die ungeschriebene Kanonisierung aus R103/R104. |
