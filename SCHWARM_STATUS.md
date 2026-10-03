# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> Zentrales Ledger für das Agent-X-Ökosystem. Alle Statusangaben hier sind verbindlich.
> Änderungen nur nach verifizierter Messung + Git-Anker.
> **Pflege-Regel:** Kein Audit-Pfad-Abschluss ohne Messbeleg. Key-Rotation schließt nur mit Rotation + Beleg (Datum, Scope, Backup-Nachweis).

---

## 0. Dokument-Metadaten

| Feld | Wert |
|---|---|
| SSOT-Version | **0.3.8** |
| Messstand (Host) | **03.10.2026** Wächter SP8–SP10 (Journal-Paste) · PolySentinel `66be8def` · Docs-Tip-Vorgänger **`2a19a1d8`** · Inventar `83dcbedc` |
| Buchungsdatum | **03.10.2026** |
| Nächster geplanter Check | Wächter-Timer → **04.10.2026, 03:45 UTC** (Serienpunkt 11 → Schnitt 0.3.9; erwartet: erste `hub_rev=`-Zeile) |
| Betriebsstatus | Betrieb läuft. **Serie = 10** reguläre Timer-Punkte Exit **0** (SP1–3 Exit 3; SP4–SP10 Exit 0). Kein CRIT; keine `[OPS]` in SP5–SP10. **Laufzeit-Anker Hub `3c7ebc1b`** (formal) · abgeleiteter Lauf-Stand SP10 **`2a19a1d8` 🟡**. Zero-Trust SSOT ✅. Key-Rotation 🔴. Gate 🔴 (B6/B7). Journal-Lücke Hub-`rev-parse` 🔵. |

---

## 1. Schwarm-Architektur (Zielbild v1.3)

```
┌─────────────────────────────────────────────┐
│  AGENT X  — Steuerungs-/Daten-Hub           │
│  Hetzner-Deploy · v1.3 Schema · Compose-DB  │
│  (FalkorDB ≠ Hub → newsagent / B4 ⚪)       │
│  SSOT 0.3.8                                 │
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
| **Daten-Weg (Wächter-Paste)** | **Option 2 = Standard:** Host schreibt Summary nach Repo/`logs/` (oder Offsite-Sync); abgeschottete Wakes lesen Datei, erfinden nichts. |
| **Docs-Tip ≠ Laufzeit-Anker** | SSOT-Commits = **Docs-Tip**; **Laufzeit-Anker Hub** = zuletzt *gemessener* Deploy-/Wächter-`rev-parse`. Rekonstruktion (FF-Zeit) ≠ Messung → Anker-Nachzug nur mit Journal-`hub_rev=` oder manuellem Paste. |
| **Diff-Lärm-Regel** | „hash:FEHLT" / Hook-Diff = **Rauschen**. Maßgeblich: Summary `[OK] Hook-Drift: RC=0, kein Drift`. |
| **Offsite-Trend-Toleranz** | Erwartung ≈ **+4 Dateien/Lauf**. Abweichung **> ±4** vom Trend = Befund. Mittel über Intervalle beobachten. |
| **§-Mapping Repo ↔ Redaktion** | Repo-Unterabschnitte vs. Redaktion 1–8 — inhaltlich deckungsgleich; Nummern allein kein Drift. |

---

## 2. Modul-Status

| Modul | Commit-Anker | Status | Bemerkung |
|---|---|---|---|
| **Agent X (Hub)** | **`3c7ebc1b`** (Laufzeit, formal) | 🟢 aktiv | Formaler Anker unverändert. **Abgeleiteter Lauf-Stand SP10: `2a19a1d8` 🟡** (FF @ 02.10. 04:01:46Z lag vor SP10; SP8/SP9 noch auf `ebf94d4d`). Nachzug formell nach `hub_rev=`-Messung. |
| **PolySentinel** | `66be8def` | 🔴 **läuft ungated — Gate defekt** | unverändert |
| **NewsAgent / Wächter** | **`677c49f`** (Referenz) | 🟢 aktiv | Referenz 28.09. Host-Tip-Kontext **`3c15251`** (03.10.) — kein Anker-Update (§1.1 analog) |

### 2.1 Anker-Kette NewsAgent
- Referenz: **`677c49f`** (Lauf 28.09.).
- Kontext: `d4e6455` (30.09.) → `46d7d5f` (02.10.) → **`3c15251`** (03.10.) — nur Kontext.

### 2.2 Anker-Kette Hub + Selbstanker-Regel
- **Laufzeit (formal):** … → **`3c7ebc1b`**.
- **Abgeleitet 🟡:** SP8/SP9 Checkout `ebf94d4d` · SP10 Checkout **`2a19a1d8`** (Rekonstruktion über FF-Zeit, nicht Journal-Zeile).
- **Docs-/Ledger-Kette:** … → `ebf94d4d` (0.3.6) → **`2a19a1d8` (0.3.7 / Docs-Tip)** → *(dieser Commit = Tip bis 0.3.9)*.
- **Hygiene:** Inventar-Sync **`83dcbedc`** (vor 0.3.7-Ledger).
- **Selbstanker:** 0.3.8 bucht Docs-Tip `2a19a1d8`; eigener Commit = Tip bis 0.3.9 / SP11.

---

## 3. Verifikationsprotokolle

### 3.1–3.3 Archiv-Kern
SP5 (28.09.): Exit 0, Offsite 230, Hub-Laufzeit-Anker `3c7ebc1b`, NA `677c49f`. Diff-Lärm-Regel §1.1. PolySentinel `66be8def` ungated.

### 3.4 Wächter-Serie 03:45-Timer — **Serienpunkt 10**

| # | Wann | Exit | Offsite | Bewertung |
|---|---|---|---|---|
| 1–3 | 24.–26.09. | 3 | — | WARN/Skip |
| — | 26.09. manuell | 0 | — | manueller Pfad |
| 4 | 27.09. | 0 | — | erster Timer-Exit-0 |
| 5 | 28.09. | 0 | **230** | SP5 |
| 6 | 29.09. | 0 | **234** | +4 |
| 7 | 30.09. | 0 | **238** | +4 |
| 8 | 01.10. 03:45:00 | **0** | **242** | +4; Beleg 84300 s; Hub-Checkout abgeleitet `ebf94d4d` |
| 9 | 02.10. 03:45:03 | **0** | **245** | **+3**; Beleg 84301 s; Checkout `ebf94d4d` (FF erst 04:01:46Z) |
| **10** | **03.10. 03:45:01** | **0** | **250** | **+5**; Beleg 84297 s; Checkout abgeleitet **`2a19a1d8` 🟡**; `ExecMainStatus=0` |

> Alle SP5–SP10: `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` · Hook Summary `[OK] RC=0, kein Drift` · kein CRIT · keine `[OPS]`.
> Nächster Schnitt: **SP11** am **04.10.2026, 03:45 UTC** → **0.3.9** (erste erwartete `hub_rev=`-Zeile).

**Offsite-Trend:** 230→234→238→242→245→250. Δ: +4/+4/+4/**+3**/+**5**. Abweichungen −1/+1 vom +4-Soll **innerhalb ±4-Toleranz — kein Befund**. Mittel über 5 Intervalle (SP5→SP10) = **+4,0/Lauf**. Beleg-Alter stabil ~84 300 s.

**Timer:** LAST `2026-10-03 03:45:01 UTC` · NEXT `2026-10-04 03:45:00 UTC`.

### 3.11–3.13 Archiv
3.11 Tip `8b98ec85` · 3.12 SP6/SP7 · 3.13 SP8/SP9 + Tip `ebf94d4d` (0.3.7).

### 3.14 Tip-Nachbuchung `2a19a1d8` + Inventar `83dcbedc` (0.3.7-Sync)

| Schritt | Ergebnis |
|---|---|
| Inventar | `83dcbedc` — `chore(inventory): sync SWARM_INVENTORY Laufzeit-Block` |
| Commit | `2a19a1d8` — `docs(ssot): book SCHWARM_STATUS 0.3.7 — SP8/SP9 + docs-tip ebf94d4d` |
| Push / Hub FF | `ebf94d4d`→`2a19a1d8` · FF-only @ **`2026-10-02T04:01:46Z`** (inkl. Code bis `7e306cb1`) |
| Vollhash | `2a19a1d8d71ce5ab70ed939b5593cbc6b18403a6` |
| Klassifikation | **Docs-Tip**; Laufzeit-Anker formal **`3c7ebc1b`** |

### 3.15 SP8–SP10-Paste + §1.1-Entscheidung (03.10.)

| Feld | Wert |
|---|---|
| SP8–SP10 | Exit 0 · Offsite 242/245/250 · Serie **10** |
| Hub `rev-parse` im Journal | **fehlt** — Unit loggt nur NewsAgent-Repo + Offsite + Hook |
| Abgeleitet 🟡 | SP8/9 = `ebf94d4d` · SP10 = `2a19a1d8` |
| Entscheidung | Formaler Anker bleibt **`3c7ebc1b`**; `2a19a1d8` = abgeleiteter Lauf-Stand 🟡. Nachzug erst nach gemessener `hub_rev=`-Zeile (oder manuellem Paste). |
| NewsAgent Kontext | `3c15251` · Referenz `677c49f` |

---

## 4. Baustellen-Tracker (B-Tracks)

**Legende:** ✅ geschlossen · 🟢 i. O. · 🟡 Beobachtung · 🔴 offen/kritisch · ⬛ keine Messung · ⚪ zurückgestellt · 🔵 Fix-Auftrag

| ID | Thema | Status | Anker/Detail |
|---|---|---|---|
| B1 | — | ✅ | `not-found` erledigt |
| B3 | Host-Anker | ✅ | Referenz `677c49f` |
| **B4** | FalkorDB | ⚪ | Key-Rotationstermin |
| **B6** | venv/Deploy-Gate | 🔴 | `pytest` / Gate≠Startpfad |
| **B7** | `[OPS]`-Verdrahtung | 🔴 | Exit 2 ohne Journal-`[OPS]` |
| **B8** | Hub-`rev-parse` im Wächter-Journal | 🔵 | Fix: `hub_rev=$(git -C /root/agent_x_storage rev-parse --short=8 HEAD)` neben Repo-Zeile in `waechter_lauf.sh` — nicht ExecStartPost |
| Track 12 | `--self-test` | 🔴 | nicht blockierend |
| m2 | EXEC-Repeater | 🟡 | beobachten |
| B5 | Exit-3-Kontrakt | ✅ | 0/1/2/3 |

---

## 5. Schnittstellen-Verträge (v1.3)

### 5.1–5.2
Unverändert: Schema `1.3`.

### 5.3 NewsAgent/Wächter — Exit 0/1/2/3
- Mit 0.3.8: **sieben** Timer-Pfad-Exit-0 in Folge (SP4–SP10). Erwartungsbild noch nicht umgestellt.
- Oneshot „Deactivated successfully" = normal bei Exit 0.

### 5.4 PolySentinel
- Ist: ungated, Gate defekt → B6/B7.

### 5.5 `[OPS]`-Format
Unverändert.

### 5.6 Wächter-Journal — Hub-Zeile (Soll, B8 🔵)
```
hub_rev=<short8>
```
Pfad: `/root/agent_x_storage`. Position: Script-Hauptlauf neben `Repo :`. Optional später: `hub_anchor_ok=yes/no`.

---

## 6. Operational Safety — Wächter

| Komponente | Zustand | Detail |
|---|---|---|
| Timer | 🟢 | LAST 03.10. 03:45:01 · NEXT 04.10. 03:45 (SP11) |
| SP5–SP10 | 🟢 Exit 0 | Serie 10; Offsite Mittel +4,0/Lauf |
| **PolySentinel-Gate** | 🔴 defekt | B6/B7 |
| Exit-Kontrakt | 🟢 | 0/1/2/3 |
| Diff-Lärm | 🟢 Regel | Summary maßgeblich |
| Hub-`rev-parse` Log | 🔵 fehlt | B8 Fix-Auftrag |

---

## 7. Audit-Pfade & Zero-Trust

| Prüfpfad | Stand |
|---|---|
| Hub Laufzeit-Anker (formal) | **`3c7ebc1b`** ✅ |
| Hub abgeleiteter Lauf-Stand | **`2a19a1d8` 🟡** (SP10; Rekonstruktion ≠ Messung) |
| Hub Docs-Tip | **`2a19a1d8`** ✅ (0.3.7; FF 04:01:46Z) — dieser Commit = nächster Docs-Tip |
| Inventar-Hygiene | **`83dcbedc`** ✅ |
| PolySentinel | **`66be8def`** ✅ |
| NewsAgent Referenz | **`677c49f`** ✅ · Kontext `3c15251` |
| **Zero-Trust SSOT** | ✅ |
| **Key-Rotation** | 🔴 **offen** |
| Journal Hub-`rev-parse` | 🔵 Lücke — B8 |

---

## 8. Änderungsprotokoll 0.3.7 → 0.3.8

| Thema | 0.3.7 | 0.3.8 |
|---|---|---|
| Charakter | SP8/SP9 + Origin-Tip | **SP8–SP10 final** + Tip `2a19a1d8` + Anker-🟡 + B8 |
| Docs-Tip | `ebf94d4d` | **`2a19a1d8`** (+ Inventar `83dcbedc`) |
| Laufzeit-Anker | `3c7ebc1b` | formal **`3c7ebc1b`** · abgeleitet SP10 **`2a19a1d8` 🟡** |
| Serie | SP9 | **SP10** (10 Punkte) |
| Offsite | …→245 | →**250**; ±4-Toleranz, Mittel +4,0 |
| Hub-FF §9 | ausstehend | ✅ `ebf94d4d`→`2a19a1d8` @ 04:01:46Z |
| Journal-Lücke | — | B8 🔵 Fix-Auftrag `hub_rev=` |
| Nächster Schnitt | SP10 | **SP11 → 0.3.9** (04.10.) |

### 8.1–8.7 Archiv
0.3.6→0.3.7 (SP8/9) · 0.3.5→0.3.6 (SP6/7) · … · 0.2.9→0.3.0.

---

## 9. Nächste Schritte (Priorität)

1. **Key-Rotation** 🔴 — Beleg oder Termin B4.
2. **B8** 🔵 — `hub_rev=` in `waechter_lauf.sh` verdrahten (Weg 2); ab SP11 Anker-Nachzug `3c7ebc1b`→`2a19a1d8` formell möglich.
3. **B6** / **B7** — Gate + `[OPS]`.
4. **SP11** (04.10. 03:45 UTC) → Schnitt **0.3.9**.
5. **m2** / Backlog (Dashboard-FP, Option-2 Summary, Offsite-Trend).

**Erledigt (quittiert):** SP5–SP10 · Docs-Tips bis `2a19a1d8` · Inventar `83dcbedc` · Hub-FF 0.3.7 · Zero-Trust · Diff-Lärm-Regel · Offsite-Toleranz-Bewertung SP9/SP10 · 0.3.7-Lücke nachträglich geschlossen.

---

*SSOT 0.3.8 · Laufzeit-Anker formal `3c7ebc1b` · abgeleitet SP10 `2a19a1d8` 🟡 · Docs-Tip-Vorgänger `2a19a1d8` · NA Referenz `677c49f` · PS `66be8def` · Serie SP10 · Key-Rotation 🔴 · B8 🔵 · kein Abschluss ohne Beleg.*
