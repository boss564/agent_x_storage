# D37 — Regeneration Messblock (Bestandsaufnahme + Reihenfolge)

Stand: 2026-11-09 · HEAD vor Schreibe: `41bf1026` · Option **C** (SP-838)

## 1. Bestandsaufnahme (gemessen)

| Gegenstand | Wert |
|---|---|
| Werkzeug | `scripts/schreibe_messblock.py` (append-only, guarded_write) |
| Akte | `order_execution_engine/ops/TAG7_ABNAHME.md` |
| Messblöcke in Akte | 10 (`kind=Messung`), Protokoll-Blöcke gesamt 321 |
| Letzter Block Karte | `52390b01dfbe` · Prüfer `d86d5e26e062` |
| Heutige Karte | `d6aa48a83cb8` · Prüfer `fbcbe4c42521` |
| `_akt_block_mismatch` | `Akte-Block: keine Messung zur Karte d6aa48a83cb8 — nicht gemessen` (1) |
| `_kopfzeile_errors` | Prüfer-Vorzustand (1; im Hook quittiert) |
| Code-Blöcke (Zustand) | Block 2794 → heute 2816 |
| Bezug root | Akte = `/Volumes/THX_OS_ULTRA/Users/...` (samefile mit Workspace) |

**Entscheidung:** Option C aus SP-838 — neuen Block **anhängen**, alten belassen.
Kein Ersatz, kein Einzeiler, kein Bypass. `schreibe_messblock.py` ist die kanonische Sequenz.

## 2. Reihenfolge (begründet)

1. Plan versionieren (diese Datei) — Audit vor Schreibe
2. `python3 scripts/schreibe_messblock.py` — Karte → Hash → Suiten → Hash-Stabilität → Append
3. Nachmessung: `_akt_block_mismatch` == [] ; Hook Index-TMP exit:0
4. **Ein** Commit: Akte (+ ggf. vom Schreibe erzeugte Begleitdateien) + dieser Plan
5. Post: `git show --stat`, `git status` leer, `stash@{0}` unberührt

Begründung: SP-838 verbietet mechanisches Überschreiben; Option C = Rundenarbeit am Dokument.
Der Block ist das **letzte** Artefakt (Prüfer-Hash hängt an `scripts/*.py`).

## 3. Nicht im Scope

- `stash@{0}` (D30 TAG7/BERICHT/R29-Review) — **kein** Pop
- D34 G1-content / D35 F-Messung / D36 A6 — eigene Commits
- Push — nur mit Freigabe

## 4. Erwartetes Commit-Ergebnis

- Neuer Abschnitt `### §71.76 — Messblock …` am Dateiende
- Karte im Zaun = `calibration_card()` byte-gleich
- Kopfzeile mit heutigem Prüfer + Vorzustand-Marke falls Selbstbezug

## 5. Messprotokoll (Schritt 2026-11-09)

Eingabe: `python3 scripts/schreibe_messblock.py` auf HEAD `41bf1026`

| Suite | Ergebnis |
|---|---|
| Hash-Eingang … Exit-vor-Stdout (24 Suiten) | Summe **145/151** (bekannte Teilrots: Zeilen-Identitaet 3/4, ADJ 3/4, Projektion-echt 2/3, Kreuz-Record 7/10) |
| Vorblock entfernt | 1 (eigene §71.76-Attrappe) |
| Guard | TAG7 10260 → 10280 Zeilen |
| Prüfer-Hash | `fbcbe4c42521` stabil vor/nach |
| `_kopfzeile_errors` | **[]** |
| `_akt_block_mismatch` | **[]** |
| Index-TMP-Hook | **exit:0**, offen=0, quittiert=0 |

## 6. Commit-Scope (exakt)

```
git add -- order_execution_engine/ops/TAG7_ABNAHME.md \
  protokoll/R29_D37_REGENERATION_PLAN.md
```

Kein Stash-Pop · kein `-A` · kein Push.
