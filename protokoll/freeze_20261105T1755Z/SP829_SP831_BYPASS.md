# SP-829 / SP-831 — Vorab-Buchung des Hook-Bypasses (Freeze-Commit)

**Gebucht:** 2026-11-05T18:08Z — **vor** dem Lauf (Bedingung 3, SP-831).
**Zweck:** Freeze-Commit des vorbestehenden unsauberen Stands mit `--no-verify`.

## SP-829 — Befund: Pre-Commit-Hook vorbestehend rot

**Kausalität ausgeschlossen.** Der Checker läuft gegen den **alten Anker**
`913af0dc` (via `git archive HEAD`, ohne Freeze-Artefakte im Baum) und liefert
denselben `EXIT=1` wie gegen den Arbeitsbaum.

Beleg mit wörtlicher Ausgabe: `hook_fail_alt_anker.txt`
Reproduktions-Hashes: `repro_hashes.txt`

Befundzeilen (identisch in beiden Läufen):

```
8 gemessen · 1 nicht gemessen · 0 ohne Skript (12 entfernt) — unvollstaendig · Prüfer 842de489e5a7
Harness-Zaun 2/3
Kopfzeile: Prüfer af77393000f8 im Block, 842de489e5a7 heute — Block ist Vorzustand
```

Zwei Teilbefunde:
1. **Harness-Zaun 2/3** — eine Teilprobe ist rot.
2. **Kopfzeilen-Drift** — `af77393000f8` im Block vs. `842de489e5a7` heute
   (`ops/KOPFZEILE.md`, zitiert und quittiert, laut Ausgabe nicht blockierend).

**Status: OFFEN.** Der Bypass dieses Commits erledigt den Befund **nicht**.

## SP-831 — Verfahren: Bypass unter fünf Bedingungen

| # | Bedingung | Nachweis |
|---|---|---|
| 1 | Beweis-Paste liegt im Commit | `hook_fail_alt_anker.txt` (gestaged) |
| 2 | Ausschließlich vorbestehender Zustand, kein Fix | keine Datei inhaltlich korrigiert; BERICHT.md-Diff unverändert aus dem Baum |
| 3 | Vorab gebucht | diese Datei, Zeitstempel **vor** dem Commit |
| 4 | Marker in der Commit-Message | `HOOK-BYPASS GEBUCHT (SP-829/SP-831)` |
| 5 | Hook bleibt OFFEN | SP-829 OFFEN, Fix = SP-832 |

## SP-830 — Widerlegt

Der gemeldete UTF-8-BOM in `CLAUDE.md` existiert **nicht** (`23 20 41` in HEAD
und Arbeitsbaum, Hash bytegleich). Siehe `SP830_WIDERLEGT.md`.
Die Stufe „BOM strippen" aus SP-832 entfällt.

## Reihenfolge

1. **Freeze** (dieser Commit) — gebuchter Bypass.
2. **Hook-Fix** (SP-832) — eigener Commit, ebenfalls gebuchter Bypass
   (Bootstrap: das rote Gate blockiert seinen eigenen Fix).
3. **Ab dann: null Bypässe.**

## Was dieser Bypass verdeckt

**Nichts Eigenes.** Er sichert den Beweis eines fremden, vorbestehenden Fehlers,
bevor der nächste Commit ihn überschreibt. Die entlarvte Sorte wäre: eigener
Fehler, still, ungebucht. Dies ist das Gegenteil.
