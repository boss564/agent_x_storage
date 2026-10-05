# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> Zentrales Ledger für das Agent-X-Ökosystem. Alle Statusangaben hier sind verbindlich.
> Änderungen nur nach verifizierter Messung + Git-Anker.
> **Pflege-Regel:** Kein Audit-Pfad-Abschluss ohne Messbeleg. Key-Rotation schließt nur mit Rotation + Beleg (Datum, Scope, Backup-Nachweis).

---

## 0. Dokument-Metadaten

| Feld | Wert |
|---|---|
| SSOT-Version | **0.3.10** |
| Messstand (Host) | **05.10.2026** Wächter SP12 (Journal-Paste) · `hub_rev=d2839763` · Offsite **232** (B-OFF-1 🟠) |
| Buchungsdatum | **05.10.2026** |
| Nächster geplanter Check | Wächter-Timer → **06.10.2026, 03:45 UTC** (Serienpunkt 13 → Schnitt 0.3.11; B-OFF-1 Review) |
| Betriebsstatus | Betrieb läuft. **Serienpunkt 12** · **Exit-0-Serie 9** (SP4–SP12). B8 ✅. Laufzeit-Anker Hub **`d2839763`** (gemessen SP12). B-OFF-1 🟠 Offsite 232. Key-Rotation 🔴. Gate 🔴 (B6/B7). Sync 0.3.9 ✅ · 0.3.10 ⏳. |
| Sync-Status | **0.3.9 ✅** — Hub-FF belegt durch SP12 `hub_rev=d2839763`. **0.3.10 ⏳** wartet auf Push/Hub-FF (Docs-Tip > `d2839763`), Beleg via SP13 `hub_rev=` |

---

## 1. Schwarm-Architektur (Zielbild v1.3)

```
┌─────────────────────────────────────────────┐
│  AGENT X  — Steuerungs-/Daten-Hub           │
│  Hetzner-Deploy · v1.3 Schema · Compose-DB  │
│  (FalkorDB ≠ Hub → newsagent / B4 ⚪)       │
│  SSOT 0.3.10                                │
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
| **Fixtures repo-getrackt** | Anker **`b97bb551`** ✅ |
| **Daten-Weg (Wächter-Paste)** | **Option 2 = Standard.** |
| **Gemessener Checkout = Anker** | Mit live `hub_rev=`-Logging: **Journal-`hub_rev` am Lauf = Laufzeit-Anker Hub**, unabhängig vom Commit-Typ. Docs/Runtime-Trennung war Messlücke, kein Prinzip. Nachzug ohne Zwischenstopp auf überholten Ständen. |
| **Diff-Lärm-Regel** | Hook-Diff / „hash:FEHLT" = Rauschen; Summary maßgeblich. |
| **Offsite-Trend-Toleranz** | ≈ +4/Lauf; Abweichung **> ±4** = Befund (B-OFF-*). |
| **Zählweise (ab 0.3.10)** | **Serienpunkt (SPn)** = laufende Nummer des Wächter-Laufs seit SP1. **Exit-0-Serie** = Anzahl aufeinanderfolgender Exit-0-Läufe (seit SP4). Bis 0.3.9 vermischt („Serie = 11“ meinte SP11, nicht 11 Exit-0). |
| **Exit-0-Serie vs. Offsite-Befund** | Serie zählt `ExecMainStatus=0` + Hook/Zähler sauber + keine `[OPS]`. Offsite-Einbruch = Vollständigkeits-Befund, **kein** automatischer Serienbruch. |

---

## 2. Modul-Status

| Modul | Commit-Anker | Status | Bemerkung |
|---|---|---|---|
| **Agent X (Hub)** | **`d2839763`** (Laufzeit) | 🟢 aktiv | **Anker-Nachzug SP12:** `16e48880` → `d2839763` per Journal-`hub_rev=`. Hist.: `16e48880`, `3c7ebc1b`, `2a19a1d8` 📁. |
| **PolySentinel** | `66be8def` | 🔴 ungated — Gate defekt | unverändert |
| **NewsAgent / Wächter** | **`677c49f`** (Referenz) | 🟢 aktiv | Kontext **`8afde1f`** (05.10.; vorher `2a18b92`) — kein Anker-Update |

### 2.1 Anker-Kette NewsAgent
- Referenz: **`677c49f`**. Kontext → … → `3250be4` (B8-Fix) → `2a18b92` (04.10.) → `0a88df0` → **`8afde1f`** (05.10., Backup-Defaults pipefail-fest).

### 2.2 Anker-Kette Hub
- **Laufzeit (aktuell):** **`d2839763`** — gemessen SP12 `hub_rev=d2839763` · Vollhash `d2839763429179e7da6628bfe6ee6495f2cd8d3a`.
- **Historisch 📁:** `16e48880` (Laufzeit SP11) · `3c7ebc1b` (formal bis SP11) · `2a19a1d8` (abgeleitet/Smoke, überholt als Zwischenschritt).
- **Docs-Kette:** … → `2a19a1d8` (0.3.7) → `16e48880` (0.3.8) → **`d2839763` (0.3.9 Docs-Tip / Laufzeit-Anker SP12)** → *(dieser Commit = Tip 0.3.10)*.
- **Hub-FF 0.3.9:** `16e48880` → `d2839763` — zwischen SP11 und SP12; Beleg = SP12-Journal `hub_rev=d2839763` (Origin = lokal = `d2839763`, geprüft 05.10. 04:16 UTC).
- **Hub-FF 0.3.8 (nachgetragen):** `2a19a1d8` → `16e48880` @ **`2026-10-03T08:01:33Z`** · Vollhash `16e48880e771b2570c853fb5cebab57fd2c0ec39`.
- Origin nach 0.3.8: Tip-Kontext bis `9556b1d7` u. a. — **Hub-Checkout bei SP11 bewusst `16e48880`** (kein FF vor Messung).

---

## 3. Verifikationsprotokolle

### 3.4 Wächter-Serie — **Serienpunkt 12**

| # | Wann | Exit | Offsite | Bewertung |
|---|---|---|---|---|
| 5 | 28.09. | 0 | **230** | SP5 |
| 6 | 29.09. | 0 | **234** | +4 |
| 7 | 30.09. | 0 | **238** | +4 |
| 8 | 01.10. | 0 | **242** | +4 |
| 9 | 02.10. | 0 | **245** | +3 |
| 10 | 03.10. | 0 | **250** | +5 |
| 11 | 04.10. 03:45:04 UTC | 0 | **230** | `hub_rev=16e48880` ✅ · B-OFF-1 🟠 (−20 vs SP10) · Beleg 84303 s |
| **12** | **05.10. 03:45:01 UTC** | **0** | **232** | **`hub_rev=d2839763`** ✅ · +2 vs SP11 · B-OFF-1 🟠 bleibt · Beleg 84297 s · Hook OK · keine `[OPS]` |

> SP1–3 Exit 3; SP4–SP12 Exit 0 → **Serienpunkt 12 · Exit-0-Serie 9** (Zählweise §1.1).  
> Nächster Schnitt: **SP13** am **06.10.2026, 03:45 UTC** → **0.3.11** (B-OFF-1 Review; Eskalation 🔴 bei Offsite < 230).

**Timer:** LAST `2026-10-05 03:45:01 UTC` · NEXT `2026-10-06 03:45:00 UTC`.

### 3.14–3.15 Archiv
Tip `2a19a1d8` + Inventar · SP8–SP10 + §1.1-Entscheidung (0.3.8).

### 3.16 SP11 + B8-Schließung + Anker-Nachzug (Paste 04.10.)

| Feld | Wert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, Result=success) |
| Zähler | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` |
| Hook | `[OK] RC=0, kein Drift` |
| **`hub_rev=`** | **`16e48880`** — erste Journal-Zeile; Soll exakt |
| Offsite | **230** Dateien · Beleg 84303 s → **B-OFF-1 🟠** |
| B8 | ✅ geschlossen (Beleg = SP11-Journal, nicht Smoke) |
| Anker | `3c7ebc1b` → **`16e48880`** (direkt) |
| NA Kontext | `2a18b92` |

### 3.17 B-OFF-1 — Offsite-Einbruch SP11

| | |
|---|---|
| Ist / Soll | 230 / Band 250–258 (−20 vs. SP10=250) |
| Beleg-Alter | 84303 s — **kein Taktproblem** |
| Hinweis | 230 = SP5-Stand → eher Quellbestand/Sync-Scope als Zufall |
| Serie | **kein Bruch** — Exit-0-Kriterium erfüllt; Befund separat |
| Follow-up | Ursachenklärung P1; Review SP12; bei weiterem Rückgang → 🔴 |
| **Review SP12** | Ist **232** (+2 vs SP11) · Beleg 84297 s (stabil zu 84303 s → kein Taktproblem). Kein Rückgang < 230 → **kein 🔴**. Nicht ≥ 238 und nicht zurück im Band 250–258 → **🟠 bleibt**. Trend +2 liegt in Toleranz (±4 um +4) → kein neuer Befund; Niveau-Lücke (−18 zum Bandboden) unverändert offen. |

### 3.18 SP12 + Hub-FF-Beleg 0.3.9 + Anker-Nachzug (Paste 05.10.)

| Feld | Wert |
|---|---|
| Exit | **0** (`ExecMainStatus=0`, Result=success) |
| Zähler | `geprüft 2 · befund 0 · blind 0 · alarm 0 · skip 0` |
| Hook | `[OK] RC=0, kein Drift` · keine `[OPS]` |
| **`hub_rev=`** | **`d2839763`** = Docs-Tip 0.3.9 = origin → Hub-FF belegt |
| Offsite | **232** Dateien · Beleg 84297 s → B-OFF-1 🟠 bleibt |
| Anker | `16e48880` → **`d2839763`** |
| NA Kontext | `8afde1f` |
| Timer | LAST 05.10. 03:45:01 · NEXT 06.10. 03:45:00 UTC |

---

## 4. Baustellen-Tracker (B-Tracks)

| ID | Thema | Status | Anker/Detail |
|---|---|---|---|
| B1 / B3 / B5 | — | ✅ | |
| **B4** | FalkorDB | ⚪ | Key-Rotationstermin |
| **B6** | venv/Deploy-Gate | 🔴 | |
| **B7** | `[OPS]`-Verdrahtung | 🔴 | |
| **B8** | Hub-`rev-parse` Journal | ✅ | SP11 `hub_rev=16e48880`; Fix `3250be4` / `waechter_lauf.sh` |
| **B-OFF-1** | Offsite-Einbruch | 🟠 | SP11: 230 · SP12: 232 (Band 250–258); Ursache offen; Review SP13 |
| Track 12 / m2 | — | 🔴/🟡 | |

---

## 5. Schnittstellen-Verträge (v1.3)

### 5.3 Exit 0/1/2/3
- SP4–SP12: **neun** Timer-Exit-0 in Folge (Exit-0-Serie 9). Serie läuft trotz B-OFF-1.

### 5.6 Wächter-Journal — Hub-Zeile
```
hub_rev=<short8>
```
**Ist:** live seit NA `3250be4`; Messungen SP11 (`16e48880`) ✅ · SP12 (`d2839763`) ✅.

---

## 6. Operational Safety — Wächter

| Komponente | Zustand | Detail |
|---|---|---|
| Timer | 🟢 | NEXT 06.10. 03:45 (SP13) |
| SP4–SP12 | 🟢 Exit 0 | Serienpunkt **12** · Exit-0-Serie **9** |
| B8 `hub_rev=` | ✅ | gemessen |
| **B-OFF-1** | 🟠 | Offsite 232 |
| PolySentinel-Gate | 🔴 | B6/B7 |

---

## 7. Audit-Pfade & Zero-Trust

| Prüfpfad | Stand |
|---|---|
| Hub Laufzeit-Anker | **`d2839763`** ✅ (SP12 `hub_rev=`) |
| Hub Docs-Tip (0.3.8) | **`16e48880`** · FF @ 08:01:33Z nachgetragen |
| Sync 0.3.9 | ✅ Hub-FF `d2839763` (SP12) |
| Sync 0.3.10 | ⏳ Docs-Tip nach diesem Commit |
| NewsAgent Referenz | **`677c49f`** · Kontext `8afde1f` |
| PolySentinel | **`66be8def`** |
| B8 / Journal-Lücke | ✅ geschlossen |
| **Zero-Trust SSOT** | ✅ |
| **Key-Rotation** | 🔴 offen |
| **B-OFF-1** | 🟠 offen |

---

## 8. Änderungsprotokoll 0.3.9 → 0.3.10

| Thema | 0.3.9 | 0.3.10 |
|---|---|---|
| Charakter | SP11 + B8 ✅ + Anker-Nachzug + B-OFF-1 | **SP12** + Hub-FF-Beleg 0.3.9 + Anker-Nachzug + B-OFF-1-Review |
| Laufzeit-Anker | `16e48880` | **`d2839763`** (gemessen SP12) |
| Sync | 0.3.9 ⏳ | 0.3.9 ✅ · 0.3.10 ⏳ |
| Zählung | „Serie = 11“ (mehrdeutig) | **Serienpunkt 12 · Exit-0-Serie 9** (§1.1 Zählweise) |
| Offsite | 230 (SP11) | **232** — B-OFF-1 🟠 bleibt |
| NA Kontext | `2a18b92` | **`8afde1f`** |
| Nächster Schnitt | SP12 → 0.3.10 | **SP13 → 0.3.11** |

---

## 9. Nächste Schritte (Priorität)

1. **B-OFF-1** 🟠 — Offsite 232: Quellbestand/Sync-Scope klären (Niveau seit SP11 ≈ SP5-Stand); Review SP13; Eskalation 🔴 bei < 230.
2. **Key-Rotation** 🔴 — B4.
3. **B6 / B7** — Gate + `[OPS]`.
4. **SP13** (06.10. 03:45 UTC) → **0.3.11**.
5. **Sync 0.3.10** — Push + Hub-FF; Beleg via SP13 `hub_rev=`.

**Erledigt:** Sync 0.3.9 ✅ (SP12) · Anker-Nachzug `d2839763` · Zählweise vereinheitlicht · B8 ✅ · Anker-Nachzug `16e48880` · Journal-Lücke · SP11 Exit-0-Serie · Hub-FF-Beleg 0.3.8 nachgetragen · Frischstart-Staging verworfen.

---

*SSOT 0.3.10 · Laufzeit-Anker Hub `d2839763` · Serienpunkt 12 · Exit-0-Serie 9 · B8 ✅ · B-OFF-1 🟠 · Key-Rotation 🔴 · Sync 0.3.10 ⏳ · kein Abschluss ohne Beleg.*
