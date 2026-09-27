# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> Zentrales Ledger für das Agent-X-Ökosystem. Alle Statusangaben hier sind verbindlich.
> Änderungen nur nach verifizierter Messung + Git-Anker.
> **Maßgeblich:** nur `agent_x_storage/SCHWARM_STATUS.md`. Keine Spiegel-Kopien (Downloads/claude.ai = Staging, nicht SSOT).

---

## 0. Dokument-Metadaten

| Feld | Wert |
|---|---|
| SSOT-Version | **0.3.0** |
| Messstand (Host) | **27.09.2026** (Wächter-Paste 03:45 UTC; PolySentinel-Fixtures 26.09. 18:32 UTC) |
| Buchungsdatum | **27.09.2026** |
| Nächster geplanter Check | Wächter-Timer → **28.09.2026, 03:45 UTC** |
| Betriebsstatus | Betrieb läuft. **Befund des Tages: Wächter-03:45-Lauf erstmals Exit 0 im regulären Timer-Pfad** (Erwartung war Exit 3 / `skip 1`) — Offsite hash-bestätigt. **Gegenbefund: PolySentinel läuft ungated, Gate defekt** (Fail-Closed verletzt, §5.4). B4 ⚪ zurückgestellt; B6/B7 neu eröffnet. |

---

## 1. Schwarm-Architektur (Zielbild v1.3)

```
┌─────────────────────────────────────────────┐
│  AGENT X  — Steuerungs-/Daten-Hub           │
│  Hetzner-Deploy · v1.3 Schema · Compose-DB  │
│  (FalkorDB ≠ Hub → newsagent / B4 ⚪)       │
│  SSOT 0.3.0                                 │
└───────┬───────────────────┬─────────────────┘
        │                   │
  ┌─────▼─────┐       ┌─────▼──────────┐       ┌──────────────────┐
  │PolySentinel│      │ NewsAgent /    │       │ Weitere geplante │
  │ Polymarket │      │ Wächter        │       │ Satelliten:      │
  │ CLOB WS    │      │ Multi-Feed     │       │ · Trading Exec.  │
  │ Monitor    │      │ Ingestion      │       │ · Risiko-Mgmt    │
  │ Fail-Closed│      │ v1.3 Schema    │       │ · Sentiment      │
  │ 10/10 Pre- │      │ Exit-Kontrakt  │       │                  │
  │ flight     │      │ 0/1/2/3        │       │                  │
  └────────────┘      └────────────────┘       └──────────────────┘
```

> **Ist-Abweichung zum Zielbild (27.09.):** PolySentinel läuft derzeit **ungated** — das Fail-Closed-Gate ist defekt. Details §2, §3.3, §6.

---

## 2. Modul-Status

| Modul | Commit-Anker | Status | Bemerkung |
|---|---|---|---|
| **Agent X (Hub)** | `d96031d5` | 🟢 aktiv | Gemessen 27.09. 03:45 UTC (`rev-parse` aus dem Wächter-Lauf); `81502319` → historischer Anker |
| **PolySentinel** | `66be8def` | 🔴 **läuft ungated — Gate defekt** | Frisch belegt via Fixtures `deploy/hetzner/fixtures/polysentinel_*20260926T183216Z*` (26.09. 18:32 UTC); `d567966` → historischer Anker. Fail-Closed (§5.4) derzeit **nicht gewährleistet**; Ursachenzuordnung zu B6/B7 offen. Fixtures-Commit angeordnet (§7) |
| **NewsAgent / Wächter** | `677c49f` | 🟢 aktiv | Gemessen 27.09. 03:45 UTC @ `/root/apps/newsagent`; HEAD weiter als `eec4c50` |

### 2.1 Anker-Kette NewsAgent (Fortschreibung B3-Protokoll)
- Kette: `d2990d3` (Ticket, hist.) → `3b8ada8` (Ist-Anker 0.2.8) → `eec4c50` (Ist-Anker 0.2.9) → **`677c49f` (Ist-Anker 0.3.0)**.
- Regel unverändert: Ledger-Anker folgt dem gemessenen Ist-HEAD; Vorgänger bleiben als historische Referenz erhalten.

### 2.2 Anker-Kette Hub (nachträglich formalisiert)
- Kette: `5a5985c5` (hist.) → `81502319` (Ist-Anker 0.2.9) → **`d96031d5` (Ist-Anker 0.3.0)**.

---

## 3. Verifikationslauf 27.09.2026 — Messprotokoll

### 3.1 Wächter-Lauf 27.09. 03:45 UTC — Exit 0 (Abweichung von der Erwartung)

> **Prominente Buchung:** Erwartet war Exit 3 / `skip 1` (Muster der 03:45-Läufe 24.–26.09.). Gemessen wurde **Exit 0 / `skip 0`** — erster Vollprüfungs-Grünlauf im regulären Timer-Pfad.

| Feld | Messwert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, `Result=success`) |
| Zähler | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` |
| Timer | LAST `2026-09-27 03:45:00 UTC` · NEXT `2026-09-28 03:45:00 UTC` |
| Hook-Drift | `[OK] Hook-Drift: RC=0, kein Drift` (Exit-0-Pfad) |
| Offsite | **hash-bestätigt** — 230 Dateien, Beleg-Alter 84300 s (≈ 23,4 h) |
| Hub `rev-parse` | `d96031d5` (`d96031d53fab836f7166bc39a51ababf761878c1`) |
| NewsAgent `rev-parse` | `677c49f` (`677c49f15ec7dad84720971545c0a5eedcdf8917`) @ `/root/apps/newsagent` |

### 3.2 Observability-Fußnote (explizit kein Befund)
- Der Diff-Block des Laufs enthält die Zeile „DRIFT ERKANNT", der Lauf endet jedoch mit `RC=0, kein Drift` (Summary, Exit-0-Pfad).
- **Ledger-maßgeblich ist die Summary-Zeile.** Der Diff-Lärm wird nicht als Befund gewertet.
- Folgeaktion (nicht blockierend): Ausgabe-Hygiene / Dashboard-FP (Log-Tail) — §9.

### 3.3 PolySentinel-Beleg 26.09. 18:32 UTC

| Feld | Messwert |
|---|---|
| HEAD | `66be8def` |
| Fixtures | `deploy/hetzner/fixtures/polysentinel_*20260926T183216Z*` |
| Befund | **läuft ungated — Gate defekt** (Fail-Closed-Prinzip §5.4 verletzt) |
| Maßnahme | Fixtures + SSOT 0.3.0 mitcommitten (Go erteilt); resultierender Commit-Anker → Nachbuchung **0.3.1** |

### 3.4 Wächter-Serie 24.09.–27.09. (03:45-Timer-Pfad + manuell)

| Wann | Exit | Zähler | Bewertung |
|---|---|---|---|
| 24.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` (Offsite übersprungen) | kontrakt-konform: WARN, OnFailure ok |
| 25.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` (Offsite übersprungen) | kontrakt-konform: WARN, OnFailure ok |
| 26.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` (Offsite übersprungen) | kontrakt-konform: WARN, OnFailure ok |
| 26.09. 11:11 UTC (manuell) | 0 | `geprüft 2 · skip 0` · Hook-Drift OK | ✅ sauber (Vollprüfung, manueller Pfad) |
| **27.09. 03:45 UTC** | **0** | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` | ✅ **erster Exit 0 im Timer-Pfad**; Offsite hash-bestätigt (230 Dateien) |

### 3.5 Archiv — Verifikationslauf 26.09.2026 (0.2.9)
| Prüfung | Ergebnis |
|---|---|
| NewsAgent HEAD / Bare | `eec4c50` (weiter als `3b8ada8`) |
| Hub | `81502319` (nicht mehr nur `5a5985c5`) |
| Korrektur zu 0.2.8 | „Positivlauf 24.09." war Exit-3/Skip, kein Grün; erster Grünlauf war 26.09. 11:11 UTC (manuell) |

### 3.6 Archiv — Verifikationslauf 23.09.2026 (0.2.8)
| Schritt | Prüfung | Ergebnis |
|---|---|---|
| 2 | Bare-Repo | `d2990d3` existiert; Bare-HEAD = `3b8ada8` |
| 3 | Host-Sync | HEAD `3b8ada8` == origin; `d2990d3` = Ancestor ✅ |
| 4 | Wächter-Timer | enabled + active, next run 24.09. 03:45 UTC |
| 5 | B3-Anker | Host-Ist-Anker = `3b8ada8` (nicht exakt `d2990d3`) |

---

## 4. Baustellen-Tracker (B-Tracks)

**Legende:** ✅ geschlossen · 🟢 i. O. · 🟡 Beobachtung läuft · 🔴 offen / kritisch · ⬛ keine Messung · ⚪ zurückgestellt (kein Blocker, kein aktiver Fokus in diesem Intervall)

| ID | Thema | Status | Anker/Detail |
|---|---|---|---|
| B1 | — | ✅ geschlossen | Ergebnis: `not-found` (damit erledigt) |
| B3 | Host-Anker-Verifikation | ✅ abgeschlossen | Fortgeschrieben: Ist-Anker `677c49f` (27.09.) |
| **B4** | **FalkorDB-Integration** | ⚪ **zurückgestellt** | Kein aktiver Fokus im 0.3.0-Intervall; Graph-Layer bleibt v1.3-Zielbild. Key-Rotationstermin hängt weiter an B4 (§7) und rückt entsprechend |
| **B6** | **venv-Defekt** | 🔴 **offen (neu)** | Fix angeordnet, nicht blockierend für 0.3.0; Detailbeleg folgt mit Fix-Commit |
| **B7** | **`[OPS]`-Alert-Pfad** | 🔴 **offen (neu)** | Fix angeordnet, nicht blockierend für 0.3.0; Detailbeleg folgt mit Fix-Commit |
| **Track 12** | **`--self-test`** | 🔴 **offen** | Erweitert: **Exit-Inventur** (Simulation aller Codes 0/1/2/3 je Satellit) als Teilaufgabe; nicht blockierend |
| **m2** | **EXEC-Repeater** | 🟡 **wirkt behoben** | Messbeleg 26.09. 16:00 UTC unverändert (live-monitor `success`, Median-Lag ~36 min); keine neue Messung im 0.3.0-Intervall — Beobachtung läuft |
| B5 | Wächter-Exit-3-Kontrakt | ✅ **geschlossen (27.09.)** | **Kontrakt-Ist ist 0/1/2/3** (`waechter_lauf.sh` §3.2). Exit 3 = Teilprüfung mit Skip → WARN / OnFailure ok, **kein CRIT**. Der 0.2.9-Entwurf hatte fälschlich eine Vertragslücke behauptet — False Claim, vor Commit korrigiert. Der 27.09.-Lauf (Exit 0) liegt im bestätigten Kontrakt |

---

## 5. Schnittstellen-Verträge (v1.3)

### 5.1 Vertragsprinzipien
- Strikte JSON-Schemas; jede Nachricht mit `schema_version`, `agent_id`, `ts_utc`.
- Unbekannte Felder: Satelliten ignorieren (forward-compatible), Hub verwirft bei Pflichtfeld-Fehlern (fail-closed am Hub).

### 5.2 Pflichtfelder (alle Satelliten-Nachrichten)
```json
{
  "schema_version": "1.3",
  "agent_id": "<modul-id>",
  "ts_utc": "<ISO-8601 UTC>",
  "msg_type": "<event|alert|heartbeat|ops>",
  "payload": { }
}
```

### 5.3 NewsAgent/Wächter — v1.3 Erweiterungen
- **`detection_lag`**: Pflichtfeld in Sekunden (Feed-Ereignis → Detektion).
- **Exit-Kontrakt `0/1/2/3`** (Ist-Stand, `waechter_lauf.sh` §3.2):
  - `0` = sauberer Exit, Vollprüfung (kein Follow-up nötig)
  - `1` = Exit mit Warnung (Hub loggt `[OPS]` WARN)
  - `2` = harter Fehler (Hub eskaliert, Satellit als degraded markiert)
  - `3` = Teilprüfung mit Skip (z. B. Offsite übersprungen) → `[OPS]` **WARN**; systemd-`OnFailure` ist akzeptiertes Verhalten, **kein CRIT**
- **Doku-Historie:** SSOT 0.2.8 dokumentierte nur `0/1/2`; mit 0.2.9 auf den realen Kontrakt `0/1/2/3` nachgezogen (B5); mit 0.3.0 Erstnachweis **Exit 0 im regulären Timer-Pfad** (27.09. 03:45 UTC).
- **Optionaler Betrieb — Zwischenstand 27.09.:** Ziel (03:45-Läufe tendenziell Exit 0) im 27.09.-Lauf erstmalig erreicht — Offsite hash-bestätigt. **Erwartungsmanagement:** Ein Grünlauf hebt das Skip-Muster nicht strukturell auf; Exit 3 bleibt kontrakt-konform. Messreihe fortsetzen, bevor das Erwartungsbild umgestellt wird.

### 5.4 PolySentinel — Operational Safety
- **Fail-Closed**: Bei Preflight-Fehler startet der Monitor nicht (kein blindes Monitoring).
- **10/10 Preflight**: Alle 10 Checks müssen bestanden sein.
- **Reconnect-Grenzen**: Max. Reconnects definiert; Überschreitung → `[OPS]`-Alert + kontrollierter Prozess-Exit (Exit-Kontrakt analog).
- **⚠ Ist-Abweichung (27.09.):** Gate defekt — Monitor **läuft ungated**; Fail-Closed derzeit nicht gewährleistet. Bis zur Wiederherstellung: Betrieb als bekanntes Risiko führen, `[OPS]`-Überwachung priorisieren (B7).

### 5.5 `[OPS]`-Alert-Format
```
[OPS] <severity> <agent_id> <ts_utc> <code> <msg>
severity: INFO | WARN | CRIT
```

---

## 6. Operational Safety — Wächter

| Komponente | Zustand | Detail |
|---|---|---|
| Wächter-Systemd-Timer | 🟢 enabled + active | LAST 27.09. 03:45 UTC · NEXT **28.09. 03:45 UTC** |
| 03:45-Lauf 27.09. | 🟢 **Exit 0 — Vollprüfung** | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0`; Offsite hash-bestätigt (230 Dateien); Hook-Drift RC=0 |
| Skip-Muster 24.–26.09. | ✅ durchbrochen (27.09.) | Erwartung Exit 3 widerlegt — Einzelmessung, Serie weiter beobachten |
| **PolySentinel-Gate** | 🔴 **defekt** | Monitor läuft ungated; Fail-Closed (§5.4) verletzt; Klärung via B6/B7 |
| Reconnect-Grenzen | 🟡 definiert (PolySentinel) | Wirksamkeit im ungated Zustand unklar — Neumessung zusammen mit Gate-Fix |
| Prozess-Exits | 🟢 Exit-Kontrakt 0/1/2/3 aktiv | Erneut bestätigt durch 27.09.-Lauf (Exit 0) |

**Regel (unverändert):** Jeder Exit **außerhalb** des Kontrakts 0/1/2/3 wird als CRIT-`[OPS]`-Alert geführt und im nächsten SSOT-Update als Incident dokumentiert.

---

## 7. Audit-Pfade & Zero-Trust

| Prüfpfad | Stand |
|---|---|
| Commit-Verifikation Agent X (Hub) | `d96031d5` ✅ gemessen 27.09. 03:45 UTC (Voll-Hash §3.1); Kette `5a5985c5` → `81502319` → `d96031d5` |
| Commit-Verifikation PolySentinel | `66be8def` ✅ belegt via Fixtures 26.09. 18:32 UTC; `d567966` hist. — ⬛ aufgelöst |
| Commit-Verifikation NewsAgent | `677c49f` ✅ gemessen 27.09. 03:45 UTC @ `/root/apps/newsagent`; Kette `d2990d3` → `3b8ada8` → `eec4c50` → `677c49f` |
| **Fixtures-Hygiene (neu)** | PolySentinel-Fixtures liegen **untracked im Repo-Arbeitsbaum** (`deploy/hetzner/fixtures/polysentinel_*20260926T183216Z*`); nicht „nur auf dem Host“. **Commit angeordnet (Go im 0.3.0-Schnitt erteilt)** — resultierender Commit-Anker → Nachbuchung 0.3.1 |
| SSOT-Hygiene | SSOT 0.3.0 liegt im Repo-Arbeitsbaum (Schnitt 27.09.); **Commit-Anker noch offen** bis nach diesem Commit — Nachbuchung 0.3.1 schließt den Zero-Trust-Pfad |
| Key-Rotation | nächste Rotation: nach B4-Abschluss festlegen (B4 ⚪ — Termin rückt entsprechend) |
| Zero-Trust-Audit-Pfad | jede SSOT-Änderung erfordert Messbeleg + Commit-Anker |

---

## 8. Änderungsprotokoll 0.2.9 → 0.3.0

| Thema | 0.2.9 (26./27.09.) | 0.3.0 (27.09.) |
|---|---|---|
| Hub-Anker | `81502319` | `d96031d5` |
| NewsAgent-Anker | `eec4c50` | `677c49f` |
| PolySentinel | ⬛ keine frische Messung (`d567966`, 23.09.) | 🔴 `66be8def` + Fixtures (26.09. 18:32 UTC) — **läuft ungated, Gate defekt** |
| Wächter 03:45-Pfad | Muster: Exit 3 / `skip 1` (3×) | **Exit 0 / `skip 0`** — Offsite hash-bestätigt (230 Dateien, Beleg 84300 s); Erwartung widerlegt |
| B4 FalkorDB | 🔴 offen | ⚪ zurückgestellt |
| B6 / B7 | — | 🔴 neu: venv-Defekt / `[OPS]`-Alert-Pfad |
| Track 12 | 🔴 offen | 🔴 offen, + Exit-Inventur als Teilaufgabe |
| Fixtures | — | Beleg verifiziert, **Commit angeordnet** |
| SSOT-Hygiene | Commit angeordnet | Anker weiter ausstehend → Nachbuchung |

**Archiv-Hinweis:** Die in 0.2.9 dokumentierte False-Claim-Korrektur (Exit-Kontrakt `0/1/2/3`) ist mit B5 geschlossen und bleibt in §4/§5.3 nachvollziehbar.

---

## 9. Nächste Schritte (Priorität)

1. **Fixtures-Commit** (Go erteilt im 0.3.0-Schnitt): `deploy/hetzner/fixtures/polysentinel_*20260926T183216Z*` committen; Anker → Nachbuchung **0.3.1**.
2. **SSOT-Commit** (Go erteilt): `SCHWARM_STATUS.md` 0.3.0 committen; Anker → Nachbuchung **0.3.1** (schließt Zero-Trust-Pfad).
3. **PolySentinel-Gate wiederherstellen** (Fail-Closed): höchste Satelliten-Priorität — bis dahin ungated-Betrieb als bekanntes Risiko führen; Verzahnung mit B6 (venv) / B7 (`[OPS]`) klären.
4. **B6-Fix (venv)** und **B7-Fix (`[OPS]`)**: nicht blockierend für 0.3.0, aber vor der nächsten PolySentinel-Neumessung.
5. **Wächter-Lauf 28.09. 03:45 UTC** abwarten: Erwartung offen — Exit 0 und Exit 3 sind beide kontrakt-konform; die Serie entscheidet, ob das Skip-Muster strukturell überwunden ist.
6. **m2 — Beobachtung abschließen**: nächster live-monitor-Beleg bestätigt Behebung → dann ✅ schließen.
7. **Backlog (nicht blockierend):** Dashboard-FP (Log-Tail; u. a. Diff-Lärm „DRIFT ERKANNT" vs. Summary), `alpha-pipeline` Scope-Zeile, Track-12 Exit-Inventur, B4-Schema-Design (⚪).

---

*SSOT 0.3.0 · Messstand 27.09.2026 (Wächter 03:45 UTC; PolySentinel-Fixtures 26.09. 18:32 UTC) · gebucht 27.09.2026 · verifizierte Messwerte, keine Annahmen.*
