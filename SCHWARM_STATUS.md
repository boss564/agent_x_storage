# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> Zentrales Ledger für das Agent-X-Ökosystem. Alle Statusangaben hier sind verbindlich.
> Änderungen nur nach verifizierter Messung + Git-Anker.
> **Pflege-Regel:** Kein Audit-Pfad-Abschluss ohne Messbeleg. Key-Rotation schließt nur mit Rotation + Beleg (Datum, Scope, Backup-Nachweis).

---

## 0. Dokument-Metadaten

| Feld | Wert |
|---|---|
| SSOT-Version | **0.3.4** |
| Messstand (Host) | **28.09.2026** Wächter 03:45 UTC (Paste) · PolySentinel Lauf-`rev-parse` **30.09.2026T18:11:54Z** · Remote-Sync-Abschluss 27.09. 15:35 UTC @ `8edb44f1` |
| Buchungsdatum | **30.09.2026** |
| Nächster geplanter Check | Wächter-Timer → **01.10.2026, 03:45 UTC** (Serienpunkt 6) |
| Betriebsstatus | Betrieb läuft. **Serienpunkt 5:** zweiter Exit-0 im Timer-Pfad (27.+28.09.). Hub Tip `3c7ebc1b`. PolySentinel Live-HEAD `66be8def` (Lauf-verifiziert). Zero-Trust SSOT ✅. Key-Rotation 🔴 offen. Gate 🔴 (B6/B7). |

---

## 1. Schwarm-Architektur (Zielbild v1.3)

```
┌─────────────────────────────────────────────┐
│  AGENT X  — Steuerungs-/Daten-Hub           │
│  Hetzner-Deploy · v1.3 Schema · Compose-DB  │
│  (FalkorDB ≠ Hub → newsagent / B4 ⚪)       │
│  SSOT 0.3.4                                 │
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

---

## 2. Modul-Status

| Modul | Commit-Anker | Status | Bemerkung |
|---|---|---|---|
| **Agent X (Hub)** | `3c7ebc1b` | 🟢 aktiv | Tip gemessen 27.09. **15:58:52Z** (0.3.3-Commit FF). Remote-Sync-Abschluss @ `8edb44f1` (15:35 UTC). Wächter-28.09.-`rev-parse` = `3c7ebc1b` |
| **PolySentinel** | `66be8def` | 🔴 **läuft ungated — Gate defekt** | **Lauf-`rev-parse` 30.09.T18:11:54Z** @ `/opt/polysentinel`; Service active seit 26.09. 15:39:27Z PID 384439; Fixtures `b97bb551`. `d567966` = Vorgänger (`merge-base --is-ancestor` YES) — archiviert, kein Ist-HEAD |
| **NewsAgent / Wächter** | `677c49f` | 🟢 aktiv | **Lauf-Messung 28.09. 03:45 UTC** @ `/root/apps/newsagent` (nicht späterer Tip) |

### 2.1 Anker-Kette NewsAgent
- Kette: `d2990d3` → `3b8ada8` → `eec4c50` → **`677c49f` (Ist / Wächter-Lauf 28.09.)**.
- Regel: Ledger-Anker = gemessener Ist-HEAD am Lauf; spätere Tips ohne Paste nicht nachziehen.

### 2.2 Anker-Kette Hub + Selbstanker-Regel
- Kette: `5a5985c5` → `81502319` → `d96031d5` → `8edb44f1` (Remote-Sync-Abschluss) → `c77febc8` → **`3c7ebc1b` (Tip / 0.3.3-Commit, FF 15:58:52Z; Wächter-28.09.-`rev-parse`)**.
- Ledger-Datei-Anker: `32771676` → `8edb44f1` → `c77febc8` → `3c7ebc1b`.
- **Selbstanker-Regel:** Commit-Anker der *aktuellen* Version entsteht erst mit ihrem Commit → Nachbuchung im Folge-Schnitt als „Tip gemeldet", keine Ledger-Lücke. (0.3.4 bucht `3c7ebc1b`; eigener Commit = Tip bis 0.3.5.)

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
| Hub `rev-parse` | `3c7ebc1b` (`3c7ebc1b6493657c228745e883fda5c0da964e2c`) |
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

### 3.5–3.8 Archiv (Kurz)

| ID | Inhalt |
|---|---|
| 3.5 | Verifikation 26.09. (0.2.9): NewsAgent `eec4c50`, Hub `81502319` |
| 3.6 | B3 23.09.: Host/Bare `3b8ada8`, `d2990d3` Ancestor |
| 3.7 | Remote-Sync ✅ `d96031d5..8edb44f1` @ 15:35 UTC |
| 3.8 | Tip `c77febc8` FF @ 15:44 UTC |

### 3.9 Tip-Nachbuchung `3c7ebc1b` (27.09. 15:58:52Z)

| Schritt | Ergebnis |
|---|---|
| Commit | `3c7ebc1b` — `docs(ssot): book SCHWARM_STATUS 0.3.3 — tip c77febc8 + self-anchor rule` |
| Push / Hub FF | `c77febc8..3c7ebc1b` · FF-only @ `2026-09-27T15:58:52Z` |
| Verify | 21 Treffer `0.3.3`/`c77febc8` auf Hub |

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
- Mit 0.3.4: **zwei** Timer-Pfad-Exit-0 (27.+28.09.) — Erwartungsbild noch nicht umgestellt; Serie weiter.

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
| Hub Commit | Tip **`3c7ebc1b`** ✅ (FF 15:58:52Z + Wächter-28.09.-`rev-parse`); Abschluss Remote-Sync @ `8edb44f1` |
| PolySentinel Commit | **`66be8def`** ✅ Lauf-`rev-parse` 30.09.T18:11:54Z + Fixtures `b97bb551`; `d567966` hist. |
| NewsAgent Commit | **`677c49f`** ✅ Lauf-Messung 28.09. 03:45 UTC |
| Fixtures-Hygiene | ✅ `b97bb551` |
| SSOT-Hygiene | ✅ Kette bis `3c7ebc1b` committed+gepusht |
| Remote-Sync | ✅ Abschluss @ `8edb44f1` (15:35 UTC) |
| **Zero-Trust SSOT** | ✅ **geschlossen** — Messbeleg + Commit-Anker + Push/Hub-FF (seit 0.3.2/0.3.3); Tip-Kette bis `3c7ebc1b` |
| **Key-Rotation** | 🔴 **offen** — kein Rotations-Ereignis. Befund: `.env` PS mtime `2026-09-25T19:06Z`; newsagent `.env` `2026-09-04`; `docs/SECRETS_BACKUP.md` nur „After key rotation". Termin an B4 ⚪. **Abschlusskriterium:** Rotation + Beleg (Datum, Scope, Backup-Nachweis) — kein Abschluss ohne Beleg |
| **Repo-Sync 0.3.4** | ✅ **erledigt** mit diesem Commit (ersetzt 0.3.3) |

---

## 8. Änderungsprotokoll 0.3.3 → 0.3.4

| Thema | 0.3.3 | 0.3.4 |
|---|---|---|
| Charakter | Tip/Selbstanker | Wächter Serienpunkt 5 + PolySentinel Lauf-Anker + Audit-Klarstellung |
| Hub-Tip | `c77febc8` gemeldet | **`3c7ebc1b`** gebucht |
| Wächter | wartet 28.09. | Exit **0**, Serienpunkt **5** |
| PolySentinel | Fixtures-only | + Lauf-`rev-parse` 30.09.; `d567966` explizit Vorgänger |
| Zero-Trust SSOT | ✅ | ✅ bestätigt |
| Key-Rotation | Termin an B4 | 🔴 offen + Abschlusskriterium festgeschrieben |
| Daten-Weg | — | Option 2 = Standard (§1.1) |

### 8.1–8.4 Archiv
0.3.2→0.3.3 (Selbstanker) · 0.3.1→0.3.2 (Remote-Sync) · 0.3.0→0.3.1 (Fixtures/SSOT) · 0.2.9→0.3.0 (erster Timer-Exit-0).

---

## 9. Nächste Schritte (Priorität)

1. **Wächter Serienpunkt 6** (nächster 03:45-Timer) — direkt in §3.4 nachbuchen.
2. **PolySentinel-Gate** (Fail-Closed) — B6 venv + B7 `[OPS]` — einziger 🔴-Satelliten-Pfad.
3. **Key-Rotation** — Beleg liefern oder Termin an B4 belassen (nicht als ✅ führen).
4. **m2** Beobachtung abschließen.
5. **Backlog:** Dashboard-FP, `alpha-pipeline` Scope, Track-12 Exit-Inventur, Option-2 Summary-Datei implementieren.

**Erledigt (quittiert):** Fixtures · SSOT-Anker · Remote-Sync · Selbstanker · Tip `3c7ebc1b` · Wächter SP5 · PolySentinel Lauf-HEAD · Zero-Trust SSOT · Repo-Sync 0.3.4.

---

*SSOT 0.3.4 · Hub `3c7ebc1b` · NewsAgent Lauf `677c49f` · PolySentinel Lauf `66be8def` · Zero-Trust SSOT ✅ · Key-Rotation 🔴 · kein Abschluss ohne Beleg.*
