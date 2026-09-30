# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> Zentrales Ledger für das Agent-X-Ökosystem. Alle Statusangaben hier sind verbindlich.
> Änderungen nur nach verifizierter Messung + Git-Anker.
> **Pflege-Regel:** Kein Audit-Pfad-Abschluss ohne Messbeleg. Key-Rotation schließt nur mit Rotation + Beleg (Datum, Scope, Backup-Nachweis).

---

## 0. Dokument-Metadaten

| Feld | Wert |
|---|---|
| SSOT-Version | **0.3.5** |
| Messstand (Host) | **28.09.2026** Wächter 03:45 UTC (Paste) · PolySentinel Lauf-`rev-parse` **30.09.2026T18:11:54Z** · Sync-FF **30.09.2026T18:18:46Z** `3c7ebc1b`→`b8f66d9d` |
| Buchungsdatum | **30.09.2026** |
| Nächster geplanter Check | Wächter-Timer → **01.10.2026, 03:45 UTC** (Serienpunkt 6) |
| Betriebsstatus | Betrieb läuft. **Serienpunkt 5** (27.+28.09. Exit 0). **Laufzeit-Anker Hub `3c7ebc1b`** · Docs-Tip `b8f66d9d`. PolySentinel Live-HEAD `66be8def`. Zero-Trust SSOT ✅. Key-Rotation 🔴 offen. Gate 🔴 (B6/B7). |

---

## 1. Schwarm-Architektur (Zielbild v1.3)

```
┌─────────────────────────────────────────────┐
│  AGENT X  — Steuerungs-/Daten-Hub           │
│  Hetzner-Deploy · v1.3 Schema · Compose-DB  │
│  (FalkorDB ≠ Hub → newsagent / B4 ⚪)       │
│  SSOT 0.3.5                                 │
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

> **Ist-Abweichung zum Zielbild:** PolySentinel läuft **ungated** — Fail-Closed-Gate defekt (§2, §3.3, §5.4, §6).

### 1.1 SSOT- und Scope-Regeln (verbindlich)

| Regel | Stand |
|---|---|
| **Maßgeblich-nur-Repo** | Einzige SSOT: `agent_x_storage/SCHWARM_STATUS.md`. Downloads / claude.ai / Chat = **Staging**, nie Ledger. |
| **FalkorDB ≠ Hub** | Graph-Layer → **newsagent** (B4 ⚪). Kein Hub-Schema. |
| **Fixtures repo-getrackt** | `deploy/hetzner/fixtures/polysentinel_*20260926T183216Z*` — Anker **`b97bb551`** ✅ |
| **Daten-Weg (Wächter-Paste)** | **Option 2 = Standard:** Host schreibt Summary nach Repo/`logs/` (oder Offsite-Sync); abgeschottete Wakes lesen Datei, erfinden nichts. Option 1 (manuell einfügen) = Fallback. Option 3 (SSH-Keys in geteiltem Ordner) = abgelehnt. |
| **Docs-Tip ≠ Laufzeit-Anker** | SSOT-Commits erzeugen einen **Docs-Tip**; der **Laufzeit-Anker Hub** bleibt der zuletzt gemessene Deploy-/Wächter-`rev-parse`. Nächster `rev-parse`-Lauf nicht gegen Docs-Tip false-positive/negative werten. |

---

## 2. Modul-Status

| Modul | Commit-Anker | Status | Bemerkung |
|---|---|---|---|
| **Agent X (Hub)** | **`3c7ebc1b`** (Laufzeit) | 🟢 aktiv | **Laufzeit-Anker** = Wächter-28.09.-`rev-parse` + 0.3.3-FF. Docs-Tip `b8f66d9d` (0.3.4-SSOT) ≠ Laufzeit. Remote-Sync-Abschluss @ `8edb44f1`. |
| **PolySentinel** | `66be8def` | 🔴 **läuft ungated — Gate defekt** | **Lauf-`rev-parse` 30.09.T18:11:54Z** @ `/opt/polysentinel`; Service active seit 26.09. 15:39:27Z PID 384439; Fixtures `b97bb551`. `d567966` = Vorgänger (`merge-base --is-ancestor` YES) — archiviert, kein Ist-HEAD |
| **NewsAgent / Wächter** | `677c49f` | 🟢 aktiv | **Lauf-Messung 28.09. 03:45 UTC** @ `/root/apps/newsagent` (nicht späterer Tip) |

### 2.1 Anker-Kette NewsAgent
- Kette: `d2990d3` → `3b8ada8` → `eec4c50` → **`677c49f` (Ist / Wächter-Lauf 28.09.)**.
- Regel: Ledger-Anker = gemessener Ist-HEAD am Lauf; spätere Tips ohne Paste nicht nachziehen.

### 2.2 Anker-Kette Hub + Selbstanker-Regel
- **Laufzeit-Kette:** `5a5985c5` → `81502319` → `d96031d5` → `8edb44f1` → `c77febc8` → **`3c7ebc1b` (Laufzeit-Anker / Wächter-28.09.-`rev-parse`)**.
- **Docs-/Ledger-Kette:** `32771676` → `8edb44f1` → `c77febc8` → `3c7ebc1b` → **`b8f66d9d` (Docs-Tip / 0.3.4-Commit, FF 18:18:46Z)**.
- **Selbstanker-Regel:** Commit-Anker der *aktuellen* Version entsteht erst mit ihrem Commit → Nachbuchung im Folge-Schnitt als „Tip gemeldet", keine Ledger-Lücke. (0.3.5 bucht Docs-Tip `b8f66d9d`; eigener Commit = Tip bis 0.3.6.)
- **Unterscheidung:** Docs-Tip für Sync/SSOT-Hygiene; Laufzeit-Anker für Deploy- und Wächter-`rev-parse`-Vergleiche.

---

## 3. Verifikationsprotokolle

### 3.1 Wächter-Lauf 28.09. 03:45 UTC — Exit 0 (Serienpunkt 5)

> Paste gemessen ~03:50Z (diese Session, SSH). Exit **0** → regulär, kein CRIT.

| Feld | Messwert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, `Result=success`) |
| Zähler | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` |
| Timer | LAST `2026-09-28 03:45:02 UTC` · NEXT `2026-09-29 03:45:00 UTC` |
| Hook-Drift | `[OK] Hook-Drift: RC=0, kein Drift` (Summary; Diff-Lärm kein Befund) |
| Offsite | **hash-bestätigt** — 230 Dateien, Beleg-Alter **84302 s** |
| Hub `rev-parse` | `3c7ebc1b` (`3c7ebc1b6493657c228745e883fda5c0da964e2c`) — **Laufzeit-Anker** |
| NewsAgent `rev-parse` | `677c49f` (`677c49f15ec7dad84720971545c0a5eedcdf8917`) @ `/root/apps/newsagent` |
| `[OPS]` | keine |

### 3.2 Observability-Fußnote (explizit kein Befund)
- Diff-Block kann „DRIFT ERKANNT" zeigen; **ledger-maßgeblich ist die Summary-Zeile** (`RC=0, kein Drift`).
- Folgeaktion: Ausgabe-Hygiene / Dashboard-FP — §9.

### 3.3 PolySentinel — Fixtures 26.09. + Lauf-`rev-parse` 30.09.

| Feld | Messwert |
|---|---|
| HEAD (Fixtures 26.09. 18:32 UTC) | `66be8def` |
| HEAD (Lauf 30.09. 18:11:54Z) | **`66be8def`** — unverändert, Live bestätigt |
| Fixtures-Anker | **`b97bb551`** ✅ |
| `d567966` | Vorgänger, `merge-base --is-ancestor` YES — **archiviert** |
| Service | active seit `2026-09-26T15:39:27Z`, PID 384439 |
| Befund | **läuft ungated — Gate defekt** (Fail-Closed §5.4 verletzt) |

### 3.4 Wächter-Serie 03:45-Timer (+ manuell) — Serienpunkt 5

| # | Wann | Exit | Zähler | Bewertung |
|---|---|---|---|---|
| 1 | 24.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` | WARN, OnFailure ok |
| 2 | 25.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` | WARN, OnFailure ok |
| 3 | 26.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` | WARN, OnFailure ok |
| — | 26.09. 11:11 UTC (manuell) | 0 | `geprüft 2 · skip 0` | Vollprüfung, manueller Pfad |
| 4 | 27.09. 03:45 UTC | 0 | `geprüft 2 · … · skip 0` | erster Exit 0 im Timer-Pfad |
| **5** | **28.09. 03:45 UTC** | **0** | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` | **zweiter Exit 0**; Skip-Muster weiter durchbrochen |

> Nächster Schnitt bucht **Serienpunkt 6** direkt in diese Tabelle (01.10. 03:45 UTC o. ä.).

### 3.5–3.9 Archiv (Kurz)

| ID | Inhalt |
|---|---|
| 3.5 | Verifikation 26.09. (0.2.9): NewsAgent `eec4c50`, Hub `81502319` |
| 3.6 | B3 23.09.: Host/Bare `3b8ada8`, `d2990d3` Ancestor |
| 3.7 | Remote-Sync ✅ `d96031d5..8edb44f1` @ 15:35 UTC |
| 3.8 | Tip `c77febc8` FF @ 15:44 UTC |
| 3.9 | Tip `3c7ebc1b` FF @ 15:58:52Z (0.3.3) |

### 3.10 Sync-Einspielung 0.3.4 — Audit-Zeile (30.09. 18:18:46Z)

| Schritt | Ergebnis |
|---|---|
| Commit | `b8f66d9d` — `docs(ssot): book SCHWARM_STATUS 0.3.4 — SP5 + PolySentinel lauf-anker 66be8def` |
| Push / Hub FF | `3c7ebc1b`→`b8f66d9d` · Branch `deploy-safe-snapshot` · FF-only @ **`2026-09-30T18:18:46Z`** |
| Hub-Verify | SSOT **0.3.4** · PS `66be8def` · Key-Rotation 🔴 · SP5 |
| Klassifikation | **`b8f66d9d` = Docs-Tip** (SSOT-Commit); **Laufzeit-Anker Hub bleibt `3c7ebc1b`** |
| Hook-Nebenfix | Wave-21-Zähler CLAUDE.md 79→78 + `docs/SWARM_INVENTORY.md` Laufzeit-Sync (Pre-Commit-Gate) — Hinweis auf Doku/Laufzeit-Drift; bei Gelegenheit klären, warum 79 gebucht war |

---

## 4. Baustellen-Tracker (B-Tracks)

**Legende:** ✅ geschlossen · 🟢 i. O. · 🟡 Beobachtung · 🔴 offen/kritisch · ⬛ keine Messung · ⚪ zurückgestellt

| ID | Thema | Status | Anker/Detail |
|---|---|---|---|
| B1 | — | ✅ | `not-found` erledigt |
| B3 | Host-Anker | ✅ | Ist `677c49f` (Wächter-Lauf) |
| **B4** | FalkorDB | ⚪ | newsagent-Scope; Key-Rotationstermin hängt hier (§7) |
| **B6** | venv/Deploy-Gate | 🔴 | `pytest` fehlt; Gate ≠ Startpfad; ABBRUCH Fixture Z.5–6 |
| **B7** | `[OPS]`-Verdrahtung | 🔴 | Exit 2 ohne Journal-`[OPS]`; `RestartPreventExitStatus=2 6` → stiller Ausfall-Risiko |
| Track 12 | `--self-test` + Exit-Inventur | 🔴 | nicht blockierend |
| m2 | EXEC-Repeater | 🟡 | last success 26.09.; beobachten |
| B5 | Exit-3-Kontrakt | ✅ | Kontrakt 0/1/2/3 bestätigt |

---

## 5. Schnittstellen-Verträge (v1.3)

### 5.1–5.2
Unverändert: Schema `1.3`, Pflichtfelder `schema_version` / `agent_id` / `ts_utc` / `msg_type` / `payload`.

### 5.3 NewsAgent/Wächter — Exit 0/1/2/3
- `0` Vollprüfung · `1` WARN · `2` hart/degraded · `3` Skip/WARN (OnFailure ok, kein CRIT)
- Mit 0.3.4+: **zwei** Timer-Pfad-Exit-0 (27.+28.09.) — Erwartungsbild noch nicht umgestellt; Serie weiter.

### 5.4 PolySentinel
- Ziel: Fail-Closed + Preflight. **Ist:** ungated, Gate defekt → bekanntes Risiko bis B6/B7.

### 5.5 `[OPS]`-Format
`[OPS] <severity> <agent_id> <ts_utc> <code> <msg>` · severity INFO|WARN|CRIT

---

## 6. Operational Safety — Wächter

| Komponente | Zustand | Detail |
|---|---|---|
| Timer | 🟢 | enabled+active; Serie Exit 0 an 27.+28.09. |
| 03:45 28.09. | 🟢 Exit 0 | Serienpunkt 5; Offsite 230 Dateien |
| Skip-Muster 24.–26.09. | ✅ durchbrochen (mind. 2× Exit 0) | weiter beobachten |
| **PolySentinel-Gate** | 🔴 defekt | ungated; B6/B7 |
| Exit-Kontrakt | 🟢 0/1/2/3 | Exit außerhalb → CRIT-`[OPS]` + Incident |

---

## 7. Audit-Pfade & Zero-Trust

| Prüfpfad | Stand |
|---|---|
| Hub Laufzeit-Anker | **`3c7ebc1b`** ✅ (Wächter-28.09.-`rev-parse` + 0.3.3-FF) — **maßgeblich für rev-parse-Vergleiche** |
| Hub Docs-Tip | **`b8f66d9d`** ✅ (0.3.4-SSOT-Commit; FF 18:18:46Z) — **nicht** Laufzeit-Anker |
| PolySentinel Commit | **`66be8def`** ✅ Lauf-`rev-parse` 30.09.T18:11:54Z + Fixtures `b97bb551`; `d567966` hist. |
| NewsAgent Commit | **`677c49f`** ✅ Lauf-Messung 28.09. 03:45 UTC |
| Fixtures-Hygiene | ✅ `b97bb551` |
| SSOT-Hygiene | ✅ Docs-Kette bis `b8f66d9d` committed+gepusht+FF |
| Remote-Sync | ✅ Abschluss @ `8edb44f1` (15:35 UTC) |
| Sync 0.3.4 | ✅ **eingespielt** — FF `3c7ebc1b`→`b8f66d9d` @ 18:18:46Z; Hub-Verify SSOT 0.3.4 · PS `66be8def` · Key-Rot 🔴 · SP5 |
| **Zero-Trust SSOT** | ✅ **geschlossen** — Messbeleg + Commit-Anker + Push/Hub-FF; Docs-Tip `b8f66d9d` |
| **Key-Rotation** | 🔴 **offen** — kein Rotations-Ereignis. Befund: `.env` PS mtime `2026-09-25T19:06Z`; newsagent `.env` `2026-09-04`; `docs/SECRETS_BACKUP.md` ohne Rotationsnachweis. Termin an B4 ⚪. **Abschlusskriterium:** Rotation + Beleg (Datum, Scope, Backup-Nachweis) — kein Abschluss ohne Beleg |

---

## 8. Änderungsprotokoll 0.3.4 → 0.3.5

| Thema | 0.3.4 | 0.3.5 |
|---|---|---|
| Charakter | SP5 + PS Lauf-Anker + Audit-Kriterien | Tip-Nachbuchung + Docs≠Laufzeit + Sync-Audit |
| Docs-Tip | (entsteht mit Commit) | **`b8f66d9d`** gebucht |
| Laufzeit-Anker Hub | `3c7ebc1b` | **`3c7ebc1b`** beibehalten (explizit ≠ Docs-Tip) |
| Sync 0.3.4 | erledigbarer Eintrag | ✅ Audit-Zeile FF @ 18:18:46Z |
| Hook-Nebenfix | — | Wave-21 79→78 + Inventory-Laufzeit-Sync vermerkt (Drift-Hinweis) |
| Offene Punkte | inkl. Sync | Sync gestrichen; **sechs** verbleibend, angeführt von Key-Rotation 🔴 |

### 8.1–8.5 Archiv
0.3.3→0.3.4 (SP5/PS) · 0.3.2→0.3.3 (Selbstanker) · 0.3.1→0.3.2 (Remote-Sync) · 0.3.0→0.3.1 (Fixtures/SSOT) · 0.2.9→0.3.0 (erster Timer-Exit-0).

---

## 9. Nächste Schritte (Priorität)

1. **Key-Rotation** 🔴 — Rotation + Beleg (Datum, Scope, Backup-Nachweis); sonst Termin an B4 belassen (nicht als ✅ führen).
2. **B6** venv/Deploy-Gate — `pytest`, Gate≠Startpfad, Fixture Z.5–6.
3. **B7** `[OPS]`-Verdrahtung — Exit 2 muss Journal-`[OPS]` erzeugen; `RestartPreventExitStatus`-Risiko.
4. **Wächter Serienpunkt 6** (nächster 03:45-Timer) — direkt in §3.4 nachbuchen.
5. **m2** EXEC-Repeater — Beobachtung abschließen.
6. **Backlog:** Dashboard-FP · `alpha-pipeline` Scope · Track-12 Exit-Inventur · Option-2 Summary-Datei · Wave-21-Zähler-Drift (warum 79 gebucht?).

**Erledigt (quittiert):** Fixtures · SSOT-Anker · Remote-Sync · Selbstanker · Tip `3c7ebc1b` (Laufzeit) · Wächter SP5 · PolySentinel Lauf-HEAD · Zero-Trust SSOT · Repo-Sync 0.3.4 (`b8f66d9d` Docs-Tip) · Sync-Einspielung FF 18:18:46Z.

~~Sync~~ — gestrichen (offen → erledigt).

---

*SSOT 0.3.5 · Laufzeit-Anker Hub `3c7ebc1b` · Docs-Tip `b8f66d9d` · NewsAgent Lauf `677c49f` · PolySentinel Lauf `66be8def` · Zero-Trust SSOT ✅ · Key-Rotation 🔴 · kein Abschluss ohne Beleg.*
