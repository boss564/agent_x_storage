# Widerlegung SP-830 (UTF-8-BOM in CLAUDE.md)

**Stand:** 2026-11-05T18:06Z
**Ergebnis:** **WIDERLEGT — kein BOM. Der Befund war falsch.**

## Messung (nicht Behauptung)

| Quelle | Erste 3 Bytes (hex) | ASCII | BOM? |
|---|---|---|---|
| `CLAUDE.md` Arbeitsbaum | `23 20 41` | `# A` | **nein** |
| `CLAUDE.md` in HEAD (`git show HEAD:CLAUDE.md`) | `23 20 41` | `# A` | **nein** |
| Behauptung SP-830 (`EF BB BF`) | — | — | nicht reproduzierbar |

Erste 64 Bytes Arbeitsbaum (repr):

```
b'# Agent X \xe2\x80\x94 Risk Management & B2G Procurement Platform\n\n6-Klassen-'
```

`\xe2\x80\x94` ist der UTF-8-Gedankenstrich (U+2014) **innerhalb** der Zeile —
kein BOM am Dateianfang. Die Datei ist BOM-frei.

## Objekt-Identität

- `CLAUDE.md` HEAD = Arbeitsbaum = `4a6a4d403fb8` → unverändert, nicht gestaged.
- Der BOM ist damit **auch nicht** durch das Staging entstanden: der Hash ist
  bytegleich zu HEAD, und HEAD trägt keinen BOM.

## Konsequenz für die Reihenfolge

Die von SP-832 vorgesehene Stufe „(2) BOM strippen als verifizierter Commit"
**entfällt** — es gibt nichts zu strippen. Ebenso entfällt „(3) BOM-Check in den
Hook", solange kein BOM-Vorkommen im Repo nachgewiesen ist. Ein Check gegen einen
nicht existierenden Fehler wäre ein Gate, das grün meldet und nichts gemessen hat —
dieselbe Blindheit, die diese Serie aufdeckt.

**Falls** ein BOM-Vorkommen repo-weit existiert, ist es zuerst zu **messen**, dann
zu buchen — nicht umgekehrt.

## Herkunft des Fehlbefunds

Die Behauptung stammte aus dem Wiedereröffnungs-Text, nicht aus einer Messung in
dieser Sitzung. Übernommen wurde sie dort, wo die Methode richtig beschrieben war
(„nur in den Staged Bytes sichtbar") — aber die Zahl war nicht geprüft.
**Die Methode war richtig, der Messwert erfunden.**
