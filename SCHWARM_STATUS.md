# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> Zentrales Ledger für das Agent-X-Ökosystem. Alle Statusangaben hier sind verbindlich.
> Änderungen nur nach verifizierter Messung + Git-Anker.
> **Pflege-Regel:** Kein Audit-Pfad-Abschluss ohne Messbeleg. Key-Rotation schließt nur mit Rotation + Beleg (Datum, Scope, Backup-Nachweis).

---

## 0. Dokument-Metadaten

| Feld | Wert |
|---|---|
| SSOT-Version | **0.3.7** |
| Messstand (Host) | **02.10.2026** Wächter SP8+SP9 (Journal-Paste) · PolySentinel Lauf `66be8def` · Docs-Tip-Vorgänger **`ebf94d4d`** · Origin-Tip-Kontext `7e306cb1` |
| Buchungsdatum | **02.10.2026** |
| Nächster geplanter Check | Wächter-Timer → **03.10.2026, 03:45 UTC** (Serienpunkt 10 → Schnitt 0.3.8) |
| Betriebsstatus | Betrieb läuft. **Serie = 9 Punkte**, Timer-Pfad Exit **0** ab SP4 (27.09.–02.10., 6×); kein CRIT; keine `[OPS]` in SP5–SP9. **Laufzeit-Anker Hub `3c7ebc1b`** · Docs-Tip-Vorgänger `ebf94d4d` · Origin-Tip `7e306cb1` (Kontext; Hub-Checkout noch `ebf94d4d`). PolySentinel `66be8def`. Zero-Trust SSOT ✅. Key-Rotation 🔴. Gate 🔴 (B6/B7). |

---

## 1. Schwarm-Architektur (Zielbild v1.3)

```
┌─────────────────────────────────────────────┐
│  AGENT X  — Steuerungs-/Daten-Hub           │
│  Hetzner-Deploy · v1.3 Schema · Compose-DB  │
│  (FalkorDB ≠ Hub → newsagent / B4 ⚪)       │
│  SSOT 0.3.7                                 │
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
| **Diff-Lärm-Regel** | „hash:FEHLT" / Hook-Diff-Block = **Rauschen**. Ledger-maßgeblich ist die **Summary-Zeile** (`[OK] Hook-Drift: RC=0, kein Drift`). Diff allein ≠ Befund. |
| **§-Mapping Repo ↔ Redaktion** | Repo nutzt Unterabschnitte (§1.1, §3.10, §9 …); Redaktions-Kopie Abschnitte 1–8. Inhaltlich deckungsgleich — Sektionsnummern allein kein Drift. |

---

## 2. Modul-Status

| Modul | Commit-Anker | Status | Bemerkung |
|---|---|---|---|
| **Agent X (Hub)** | **`3c7ebc1b`** (Laufzeit) | 🟢 aktiv | **Laufzeit-Anker** unverändert (Wächter-28.09.-`rev-parse`). Docs-Tip-Vorgänger `ebf94d4d` (0.3.6). Hub-Checkout 02.10. = `ebf94d4d`; Origin-Tip `7e306cb1` — Kontext, kein Anker-Update. |
| **PolySentinel** | `66be8def` | 🔴 **läuft ungated — Gate defekt** | Lauf-`rev-parse` 30.09.T18:11:54Z; Fixtures `b97bb551`; `d567966` Vorgänger archiviert |
| **NewsAgent / Wächter** | **`677c49f`** (Referenz) | 🟢 aktiv | **Referenz-Anker** = Lauf-Messung 28.09. Host-Tip-Kontext `46d7d5f` (02.10.; Vorgänger `d4e6455`) **ohne** Anker-Update |

### 2.1 Anker-Kette NewsAgent
- Kette: `d2990d3` → `3b8ada8` → `eec4c50` → **`677c49f` (Referenz / Wächter-Lauf 28.09.)**.
- Kontext 30.09.: Host-Tip `d4e6455`; Kontext 02.10.: Host-Tip **`46d7d5f`** — beide nur Kontext, kein Nachziehen ohne Lauf-`rev-parse`-Paste.
- Regel: Ledger-Anker = gemessener Ist-HEAD am Lauf; spätere Tips ohne Paste nicht nachziehen.

### 2.2 Anker-Kette Hub + Selbstanker-Regel
- **Laufzeit-Kette:** `5a5985c5` → `81502319` → `d96031d5` → `8edb44f1` → `c77febc8` → **`3c7ebc1b` (Laufzeit-Anker)**.
- **Docs-/Ledger-Kette:** `32771676` → `8edb44f1` → `c77febc8` → `3c7ebc1b` → `b8f66d9d` → `8b98ec85` (0.3.5) → **`ebf94d4d` (Docs-Tip / 0.3.6)** → *(dieser Commit = Tip bis 0.3.8)*.
- **Code-Commits nach 0.3.6 (Origin-Tip-Kontext, kein Anker):** `35f5ec4d` (fix bridge REPO_NESTED) → `45a5b74f` (gitignore krypto_steuer_analytix) → **`7e306cb1`** (feat see PeakEvent Befunde 3+4). Stand 02.10.: auf Origin, **nicht** auf Hub-Deploy-Tree (Checkout `ebf94d4d`).
- **Selbstanker-Regel:** Commit-Anker der *aktuellen* Version entsteht erst mit ihrem Commit → Nachbuchung im Folge-Schnitt. (0.3.7 bucht Docs-Tip `ebf94d4d`; eigener Commit = Tip bis 0.3.8 / SP10.)
- **Unterscheidung:** Docs-Tip für Sync/SSOT-Hygiene; Laufzeit-Anker für Deploy- und Wächter-`rev-parse`-Vergleiche.

---

## 3. Verifikationsprotokolle

### 3.1 Wächter-Lauf 28.09. 03:45 UTC — Exit 0 (Serienpunkt 5)

| Feld | Messwert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, `Result=success`) |
| Zähler | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` |
| Timer (damals) | LAST `2026-09-28 03:45:02 UTC` · NEXT `2026-09-29 03:45:00 UTC` |
| Hook-Drift | `[OK] Hook-Drift: RC=0, kein Drift` (Summary; Diff-Lärm → Regel §1.1) |
| Offsite | **hash-bestätigt** — **230** Dateien |
| Hub `rev-parse` | `3c7ebc1b` — **Laufzeit-Anker** |
| NewsAgent `rev-parse` | `677c49f` — **Referenz-Anker** |
| `[OPS]` | keine |

### 3.2 Diff-Lärm-Regel (Observability)

- Diff-Block kann „DRIFT ERKANNT" / „hash:FEHLT" zeigen → **Rauschen**.
- **Ledger-maßgeblich:** Summary-Zeile `[OK] Hook-Drift: RC=0, kein Drift`.
- Folgeaktion (Hygiene/Dashboard-FP) bleibt Backlog — kein Befund aus Diff allein.

### 3.3 PolySentinel — unverändert

| Feld | Messwert |
|---|---|
| HEAD | **`66be8def`** (Fixtures + Lauf 30.09.) |
| Fixtures-Anker | **`b97bb551`** ✅ |
| Befund | **läuft ungated — Gate defekt** |

### 3.4 Wächter-Serie 03:45-Timer — **Serienpunkt 9**

| # | Wann | Exit | Zähler | Bewertung |
|---|---|---|---|---|
| 1 | 24.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` | WARN, OnFailure ok |
| 2 | 25.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` | WARN, OnFailure ok |
| 3 | 26.09. 03:45 UTC | 3 | `geprüft 1 · skip 1` | WARN, OnFailure ok |
| — | 26.09. 11:11 UTC (manuell) | 0 | `geprüft 2 · skip 0` | Vollprüfung, manueller Pfad |
| 4 | 27.09. 03:45 UTC | 0 | `geprüft 2 · … · skip 0` | erster Exit 0 im Timer-Pfad |
| 5 | 28.09. 03:45 UTC | 0 | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` | zweiter Exit 0; Offsite **230** |
| 6 | 29.09. 03:45:00 UTC | 0 | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` | Journal-Paste; Offsite **234**; „Deactivated successfully" = normale Oneshot-Signatur; kein CRIT; keine `[OPS]` |
| 7 | 30.09. 03:45:02 UTC | 0 | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` | `ExecMainStatus=0`, Result=success; Offsite **238**; Hook Summary OK; kein CRIT; keine `[OPS]` |
| **8** | **01.10. 03:45:00 UTC** | **0** | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` | „Deactivated successfully"; Offsite **242** hash-bestätigt; `[OK] RC=0, kein Drift`; kein CRIT; keine `[OPS]` |
| **9** | **02.10. 03:45:03 UTC** | **0** | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` | `ExecMainStatus=0`, Result=success; Offsite **245** hash-bestätigt; `[OK] RC=0, kein Drift`; kein CRIT; keine `[OPS]` |

> Nächster Schnitt: **Serienpunkt 10** am **03.10.2026, 03:45 UTC** → eigener Schnitt **0.3.8**.
> Hinweis: SP8 wurde nicht zeitnah gebucht (Lücke 01.10.) → in 0.3.7 mit SP9 zusammengefasst; Messwerte aus Journal-Paste 02.10.

**Offsite-Trend (Beobachtung, kein Befund):** 230 → 234 → 238 → 242 → 245 (SP5→SP9; +4/+4/+4/**+3**). Erste Abweichung vom +4-Muster bei SP9 — weiter beobachten.

**Timer (gemessen 02.10.):** LAST `2026-10-02 03:45:03 UTC` · NEXT `2026-10-03 03:45:00 UTC`.

### 3.5–3.10 Archiv (Kurz)

| ID | Inhalt |
|---|---|
| 3.5–3.9 | wie 0.3.5 (Verifikation / B3 / Remote-Sync / Tips `c77febc8` / `3c7ebc1b`) |
| 3.10 | Sync 0.3.4: FF `3c7ebc1b`→`b8f66d9d` @ 18:18:46Z |

### 3.11 Tip-Nachbuchung `8b98ec85` (0.3.5) — Audit geschlossen

| Schritt | Ergebnis |
|---|---|
| Commit | `8b98ec85` — `docs(ssot): book SCHWARM_STATUS 0.3.5 — docs-tip b8f66d9d ≠ laufzeit-anker 3c7ebc1b` |
| Push / Hub FF | `b8f66d9d`→`8b98ec85` · FF-only @ **`2026-09-30T18:27:47Z`** |
| Vollhash | `8b98ec85c3c1c4216bd08b53940a79fe1820db82` |
| FF-Kette Docs | `3c7ebc1b` → `b8f66d9d` → **`8b98ec85`** |
| Klassifikation | **Docs-Tip**; Laufzeit-Anker Hub bleibt **`3c7ebc1b`** |

### 3.12 SP6/SP7-Nachbuchung (Paste 30.09. ~18:33Z)

| SP | Exit | Offsite | Hook Summary | Anmerkung |
|---|---|---|---|---|
| 6 | 0 | 234 | RC=0, kein Drift | Oneshot „Deactivated successfully" = normal |
| 7 | 0 | 238 | RC=0, kein Drift | `ExecMainStatus=0` |
| Kontext | — | — | — | Host-Tips Hub `8b98ec85`, NewsAgent `d4e6455` — **kein** Anker-Update |

### 3.13 SP8/SP9 + Tip-Nachbuchung `ebf94d4d` (Paste 02.10.)

| Feld | Wert |
|---|---|
| SP8 | 01.10. 03:45:00 UTC · Exit 0 · Offsite 242 · `[OK] RC=0, kein Drift` |
| SP9 | 02.10. 03:45:03 UTC · Exit 0 (`ExecMainStatus=0`) · Offsite 245 · `[OK] RC=0, kein Drift` |
| Docs-Tip gebucht | **`ebf94d4d`** — `docs(ssot): book SCHWARM_STATUS 0.3.6 — SP6/SP7 + Diff-Lärm-Regel` |
| Hub `rev-parse` (02.10., Checkout) | `ebf94d4d` — Docs-Tip, **kein** Laufzeit-Anker-Update |
| Origin-Tip | `7e306cb1` (`35f5ec4d` → `45a5b74f` → `7e306cb1`) — Kontext; Hub-FF ausstehend |
| NewsAgent `rev-parse` (02.10.) | `46d7d5f` — Kontext; Referenz bleibt `677c49f` |

---

## 4. Baustellen-Tracker (B-Tracks)

**Legende:** ✅ geschlossen · 🟢 i. O. · 🟡 Beobachtung · 🔴 offen/kritisch · ⬛ keine Messung · ⚪ zurückgestellt

| ID | Thema | Status | Anker/Detail |
|---|---|---|---|
| B1 | — | ✅ | `not-found` erledigt |
| B3 | Host-Anker | ✅ | Referenz `677c49f` (Wächter-Lauf 28.09.) |
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
- Mit 0.3.7: **sechs** aufeinanderfolgende Timer-Pfad-Exit-0 (SP4–SP9, 27.09.–02.10.) — Erwartungsbild noch nicht umgestellt; Serie weiter.
- Oneshot-Ende: „Deactivated successfully" = normale Signatur bei Exit 0 (kein Ausfall).

### 5.4 PolySentinel
- Ziel: Fail-Closed + Preflight. **Ist:** ungated, Gate defekt → bekanntes Risiko bis B6/B7.

### 5.5 `[OPS]`-Format
`[OPS] <severity> <agent_id> <ts_utc> <code> <msg>` · severity INFO|WARN|CRIT

---

## 6. Operational Safety — Wächter

| Komponente | Zustand | Detail |
|---|---|---|
| Timer | 🟢 | enabled+active; NEXT 03.10. 03:45 UTC (SP10) |
| SP5–SP9 | 🟢 Exit 0 | kein CRIT; keine `[OPS]`; Offsite 230→234→238→242→245 |
| Skip-Muster 24.–26.09. | ✅ durchbrochen | 6× Exit 0 im Timer-Pfad |
| **PolySentinel-Gate** | 🔴 defekt | ungated; B6/B7 |
| Exit-Kontrakt | 🟢 0/1/2/3 | Exit außerhalb → CRIT-`[OPS]` + Incident |
| Diff-Lärm | 🟢 Regel | Summary maßgeblich (§1.1) |

---

## 7. Audit-Pfade & Zero-Trust

| Prüfpfad | Stand |
|---|---|
| Hub Laufzeit-Anker | **`3c7ebc1b`** ✅ — maßgeblich für rev-parse-Vergleiche |
| Hub Docs-Tip | **`ebf94d4d`** ✅ (0.3.6; Hub-Checkout 02.10.) — **nicht** Laufzeit-Anker; dieser Commit = nächster Docs-Tip |
| Origin-Tip | `7e306cb1` — Kontext; Hub-FF ausstehend |
| PolySentinel Commit | **`66be8def`** ✅ |
| NewsAgent Referenz | **`677c49f`** ✅; Host-Tip `46d7d5f` nur Kontext |
| Fixtures-Hygiene | ✅ `b97bb551` |
| SSOT-Hygiene | ✅ Docs-Kette bis `ebf94d4d` |
| Remote-Sync / Sync 0.3.4 | ✅ |
| **Zero-Trust SSOT** | ✅ **geschlossen** |
| **Key-Rotation** | 🔴 **offen** — Abschlusskriterium: Rotation + Beleg (Datum, Scope, Backup-Nachweis) |

---

## 8. Änderungsprotokoll 0.3.6 → 0.3.7

| Thema | 0.3.6 | 0.3.7 |
|---|---|---|
| Charakter | SP6/SP7 + Diff-Lärm-Regel | **SP8/SP9** + Tip-Nachbuchung + Origin-Tip-Kontext |
| Docs-Tip gebucht | `8b98ec85` | **`ebf94d4d`** |
| Laufzeit-Anker Hub | `3c7ebc1b` | **`3c7ebc1b`** unverändert |
| Origin-Tip | — | `7e306cb1` (Kontext; Hub-FF ausstehend) |
| NewsAgent Host-Tip | `d4e6455` | `46d7d5f` (Kontext) |
| Wächter-Serie | SP7 | **SP9** (9 Punkte; SP4–SP9 Exit 0) |
| Offsite | 230→234→238 | →242→245 (+4/+3) |
| Nächster Schnitt | SP8 → 0.3.7 | **SP10 → 0.3.8** (03.10. 03:45 UTC) |

### 8.0 Änderungsprotokoll 0.3.5 → 0.3.6

| Thema | 0.3.5 | 0.3.6 |
|---|---|---|
| Charakter | Tip-Nachbuchung Docs≠Laufzeit | **SP6/SP7** + Diff-Lärm-Regel + Offsite-Trend |
| Docs-Tip gebucht | `b8f66d9d` | **`8b98ec85`** (Audit §3.11 geschlossen) |
| Laufzeit-Anker Hub | `3c7ebc1b` | **`3c7ebc1b`** unverändert |
| Wächter-Serie | SP5 | **SP7** (7 Punkte; SP4–SP7 Exit 0) |
| Diff-Lärm | Fußnote | **Ledger-Regel** §1.1 |
| Offsite | 230 (SP5) | Trend 230→234→238 (Beobachtung) |
| Nächster Schnitt | SP6 ausstehend (Paste-Lücke) | **SP8 → 0.3.7** (01.10. 03:45 UTC) |

### 8.1–8.6 Archiv
0.3.4→0.3.5 (Docs≠Laufzeit) · 0.3.3→0.3.4 (SP5/PS) · 0.3.2→0.3.3 (Selbstanker) · 0.3.1→0.3.2 (Remote-Sync) · 0.3.0→0.3.1 (Fixtures/SSOT) · 0.2.9→0.3.0 (erster Timer-Exit-0).

---

## 9. Nächste Schritte (Priorität)

1. **Key-Rotation** 🔴 — Rotation + Beleg; sonst Termin an B4 belassen.
2. **B6** venv/Deploy-Gate.
3. **B7** `[OPS]`-Verdrahtung.
4. **Wächter Serienpunkt 10** (03.10. 03:45 UTC) — eigener Schnitt **0.3.8**. Hub-FF `ebf94d4d`→`7e306cb1` + Checkout nachziehen.
5. **m2** EXEC-Repeater — Beobachtung abschließen.
6. **Backlog:** Dashboard-FP · `alpha-pipeline` · Track-12 · Option-2 Summary-Datei · Wave-21-Zähler-Drift · Offsite-Trend (+3 bei SP9) weiter beobachten.

**Erledigt (quittiert):** Fixtures · SSOT-Anker · Remote-Sync · Selbstanker · Laufzeit-Tip `3c7ebc1b` · Docs-Tips `b8f66d9d`/`8b98ec85` · Wächter SP5–SP9 · Docs-Tip `ebf94d4d` · PolySentinel Lauf-HEAD · Zero-Trust SSOT · Diff-Lärm-Regel · Sync-Einspielungen.

---

*SSOT 0.3.7 · Laufzeit-Anker Hub `3c7ebc1b` · Docs-Tip-Vorgänger `ebf94d4d` · Origin-Tip `7e306cb1` · NewsAgent Referenz `677c49f` · PolySentinel `66be8def` · Serie SP9 · Zero-Trust SSOT ✅ · Key-Rotation 🔴 · kein Abschluss ohne Beleg.*
