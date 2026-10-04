# SCHWARM_STATUS.md — Single Source of Truth (SSOT)

> Zentrales Ledger für das Agent-X-Ökosystem. Alle Statusangaben hier sind verbindlich.
> Änderungen nur nach verifizierter Messung + Git-Anker.
> **Pflege-Regel:** Kein Audit-Pfad-Abschluss ohne Messbeleg. Key-Rotation schließt nur mit Rotation + Beleg (Datum, Scope, Backup-Nachweis).

---

## 0. Dokument-Metadaten

| Feld | Wert |
|---|---|
| SSOT-Version | **0.3.9** |
| Messstand (Host) | **04.10.2026** Wächter SP11 (Journal-Paste) · `hub_rev=16e48880` · Offsite **230** (B-OFF-1 🟠) |
| Buchungsdatum | **04.10.2026** |
| Nächster geplanter Check | Wächter-Timer → **05.10.2026, 03:45 UTC** (Serienpunkt 12 → Schnitt 0.3.10; B-OFF-1 Review) |
| Betriebsstatus | Betrieb läuft. **Serie = 11** Exit-0 (SP4–SP11). B8 ✅. Laufzeit-Anker Hub **`16e48880`** (gemessen SP11). B-OFF-1 🟠 Offsite 230. Key-Rotation 🔴. Gate 🔴 (B6/B7). Sync ⏳. |
| Sync-Status | ⏳ **wartet** auf Commit/Push/Hub-FF (Docs-Tip > `16e48880`) → danach 0.3.9-sync |

---

## 1. Schwarm-Architektur (Zielbild v1.3)

```
┌─────────────────────────────────────────────┐
│  AGENT X  — Steuerungs-/Daten-Hub           │
│  Hetzner-Deploy · v1.3 Schema · Compose-DB  │
│  (FalkorDB ≠ Hub → newsagent / B4 ⚪)       │
│  SSOT 0.3.9                                 │
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
| **Exit-0-Serie vs. Offsite-Befund** | Serie zählt `ExecMainStatus=0` + Hook/Zähler sauber + keine `[OPS]`. Offsite-Einbruch = Vollständigkeits-Befund, **kein** automatischer Serienbruch. |

---

## 2. Modul-Status

| Modul | Commit-Anker | Status | Bemerkung |
|---|---|---|---|
| **Agent X (Hub)** | **`16e48880`** (Laufzeit) | 🟢 aktiv | **Anker-Nachzug SP11:** `3c7ebc1b` → `16e48880` per Journal-`hub_rev=`. Hist.: `3c7ebc1b`, `2a19a1d8` 📁. |
| **PolySentinel** | `66be8def` | 🔴 ungated — Gate defekt | unverändert |
| **NewsAgent / Wächter** | **`677c49f`** (Referenz) | 🟢 aktiv | Kontext **`2a18b92`** (04.10.; vorher `3c15251`/`3250be4`) — kein Anker-Update |

### 2.1 Anker-Kette NewsAgent
- Referenz: **`677c49f`**. Kontext → … → `3250be4` (B8-Fix) → **`2a18b92`** (04.10.).

### 2.2 Anker-Kette Hub
- **Laufzeit (aktuell):** **`16e48880`** — gemessen SP11 `hub_rev=16e48880`.
- **Historisch 📁:** `3c7ebc1b` (formal bis SP11) · `2a19a1d8` (abgeleitet/Smoke, überholt als Zwischenschritt).
- **Docs-Kette:** … → `2a19a1d8` (0.3.7) → **`16e48880` (0.3.8 Docs-Tip / Laufzeit-Anker SP11)** → *(dieser Commit = Tip bis 0.3.10)*.
- **Hub-FF 0.3.8 (nachgetragen):** `2a19a1d8` → `16e48880` @ **`2026-10-03T08:01:33Z`** · Vollhash `16e48880e771b2570c853fb5cebab57fd2c0ec39`.
- Origin nach 0.3.8: Tip-Kontext bis `9556b1d7` u. a. — **Hub-Checkout bei SP11 bewusst `16e48880`** (kein FF vor Messung).

---

## 3. Verifikationsprotokolle

### 3.4 Wächter-Serie — **Serienpunkt 11**

| # | Wann | Exit | Offsite | Bewertung |
|---|---|---|---|---|
| 5 | 28.09. | 0 | **230** | SP5 |
| 6 | 29.09. | 0 | **234** | +4 |
| 7 | 30.09. | 0 | **238** | +4 |
| 8 | 01.10. | 0 | **242** | +4 |
| 9 | 02.10. | 0 | **245** | +3 |
| 10 | 03.10. | 0 | **250** | +5 |
| **11** | **04.10. 03:45:04 UTC** | **0** | **230** | **`hub_rev=16e48880`** ✅ · Offsite **B-OFF-1 🟠** (−20 vs SP10) · Beleg 84303 s · Hook OK · keine `[OPS]` |

> SP1–3 Exit 3; SP4–SP11 Exit 0 → **Serie 11**.  
> Nächster Schnitt: **SP12** am **05.10.2026, 03:45 UTC** → **0.3.10** (B-OFF-1 Review; Eskalation 🔴 bei erneutem Rückgang).

**Timer:** LAST `2026-10-04 03:45:03 UTC` · NEXT `2026-10-05 03:45:00 UTC`.

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

---

## 4. Baustellen-Tracker (B-Tracks)

| ID | Thema | Status | Anker/Detail |
|---|---|---|---|
| B1 / B3 / B5 | — | ✅ | |
| **B4** | FalkorDB | ⚪ | Key-Rotationstermin |
| **B6** | venv/Deploy-Gate | 🔴 | |
| **B7** | `[OPS]`-Verdrahtung | 🔴 | |
| **B8** | Hub-`rev-parse` Journal | ✅ | SP11 `hub_rev=16e48880`; Fix `3250be4` / `waechter_lauf.sh` |
| **B-OFF-1** | Offsite-Einbruch | 🟠 | SP11: 230 statt 250–258; Review SP12 |
| Track 12 / m2 | — | 🔴/🟡 | |

---

## 5. Schnittstellen-Verträge (v1.3)

### 5.3 Exit 0/1/2/3
- SP4–SP11: **acht** Timer-Exit-0 in Folge. Serie läuft trotz B-OFF-1.

### 5.6 Wächter-Journal — Hub-Zeile
```
hub_rev=<short8>
```
**Ist:** live seit NA `3250be4`; erste Messung SP11 ✅.

---

## 6. Operational Safety — Wächter

| Komponente | Zustand | Detail |
|---|---|---|
| Timer | 🟢 | NEXT 05.10. 03:45 (SP12) |
| SP4–SP11 | 🟢 Exit 0 | Serie **11** |
| B8 `hub_rev=` | ✅ | gemessen |
| **B-OFF-1** | 🟠 | Offsite 230 |
| PolySentinel-Gate | 🔴 | B6/B7 |

---

## 7. Audit-Pfade & Zero-Trust

| Prüfpfad | Stand |
|---|---|
| Hub Laufzeit-Anker | **`16e48880`** ✅ (SP11 `hub_rev=`) |
| Hub Docs-Tip (0.3.8) | **`16e48880`** · FF @ 08:01:33Z nachgetragen |
| Sync 0.3.9 | ⏳ Docs-Tip nach diesem Commit |
| NewsAgent Referenz | **`677c49f`** · Kontext `2a18b92` |
| PolySentinel | **`66be8def`** |
| B8 / Journal-Lücke | ✅ geschlossen |
| **Zero-Trust SSOT** | ✅ |
| **Key-Rotation** | 🔴 offen |
| **B-OFF-1** | 🟠 offen |

---

## 8. Änderungsprotokoll 0.3.8 → 0.3.9

| Thema | 0.3.8 | 0.3.9 |
|---|---|---|
| Charakter | SP8–SP10 + B8-Soll | **SP11** + B8 ✅ + Anker-Nachzug + B-OFF-1 |
| Laufzeit-Anker | formal `3c7ebc1b` | **`16e48880`** (gemessen) |
| B8 | 🔵 / Fix live | ✅ SP11-Journal |
| Serie | 10 | **11** |
| Offsite | 250 (SP10) | **230** B-OFF-1 🟠 |
| §1.1 | Docs≠Runtime (Messlücke) | **gemessener Checkout = Anker** |
| Nächster Schnitt | SP11 | **SP12 → 0.3.10** |

---

## 9. Nächste Schritte (Priorität)

1. **B-OFF-1** 🟠 — Offsite 230: Quellbestand/Sync-Scope klären; Review SP12; Eskalation 🔴 bei erneutem Rückgang.
2. **Key-Rotation** 🔴 — B4.
3. **B6 / B7** — Gate + `[OPS]`.
4. **SP12** (05.10. 03:45 UTC) → **0.3.10**.
5. **Sync 0.3.9** — nach Hub-FF Docs-Tip buchen.

**Erledigt:** B8 ✅ · Anker-Nachzug `16e48880` · Journal-Lücke · SP11 Exit-0-Serie · Hub-FF-Beleg 0.3.8 nachgetragen · Frischstart-Staging verworfen.

---

*SSOT 0.3.9 · Laufzeit-Anker Hub `16e48880` · Serie SP11 · B8 ✅ · B-OFF-1 🟠 · Key-Rotation 🔴 · Sync ⏳ · kein Abschluss ohne Beleg.*
