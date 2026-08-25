# Kanten-Ledger — Architektur-DRAFT

**Arbeitstitel:** `KANTEN_LEDGER_v1`  
**Status:** **ABGESCHLOSSEN** — 2026-08-25 · `ARCH_BINDEND` → Abnahme · Label **`LEDGER_SCREEN_PASS`**  
**Charakter:** **Architekturänderung** mit Screening-Abnahme (S-S / S-G) — **keine** Interventionsstudie  
**Artefakte:** `agents_b2g/emergence/kanten_ledger_v1/`  

### Bindungs-Vermerk

```text
Status: DRAFT → ARCH_BINDEND → ABGESCHLOSSEN
Dokument: docs/KANTEN_LEDGER_v1_DRAFT.md
Datum: 2026-08-25
Outcome: LEDGER_SCREEN_PASS
Kandidaten (≥2/3): interaction_count, avg_latency
Near-Miss (≥2/3): (keine)
Implementierung: agents_b2g/emergence/kanten_ledger.py + kanten_ledger_capture.py
Runner: scripts/run_kanten_ledger_v1_screen.py
Trennregel: bindend — kein κ-Sweep auf diesem Datensatz
```

### S_neu-Mapping (eingefroren bei ARCH_BINDEND)

Nach Decay auf Kante `(i,j)` bei Interaktion:

| Idx | Name | S_neu |
|----:|------|-------|
| 0 | `interaction_count` | `+= 1` |
| 1 | `bilateral_balance` | `+= signed_net` aus Payload (`net_amount`, sonst 0); Sender→Empfänger positiv |
| 2 | `trust_score` | Beta-Update: Erfolg `α+=1`, Fail `β+=1`; Export `α/(α+β)` |
| 3 | `avg_latency` | EWMA `λ=0.3` der Tick-Latenz (hier: 1.0 pro zugestellter Msg) |
| 4 | `edge_risk` | Fail: `min(1, risk+0.1)`; Erfolg: `max(0, risk−0.05)` |

---

## 0. Kontext und Motivation

### 0.1 Versiegelte Vorgänger (HARKing-Sperre)

| Artefakt | Status | Aussage |
|----------|--------|---------|
| Queue-Kopplung | `KOPPLUNG_INVALID` | partnerblinde Größe |
| `KOPPLUNG_REPUTATION_v1` | `I1_FAILED` | Sättigung / Sync |
| `state_screen/` | `NONE_CLOSE` | 18 Knoten-Dims, cycles=64 |
| `PARTNERSELECT_SCREEN_v1` | `NONE_CLOSE` | 18 Knoten-Dims, cycles=512, 3 Seeds; Near-Miss nur MAE-Band, `|ρ|≈0.999` |
| `KOPPLUNG_EIJ_v1` | I1_PASS · Sweep `KOPPLUNG_INVALID` | Kante parametrisch selektiv; Intervention erfüllt §1.1 nicht |

**Kernbefund der Serie:** Im knotenbasierten Trace dominieren Gleichanteile
(`|ρ|≈0.999`). Partnerselektivität ertrinkt. **Kopplung muss gebaut werden,
nicht eingestellt.**

### 0.2 Warum nicht noch eine Mess-Frage

Ein weiterer reiner Mess-DRAFT ohne Architekturänderung wiederholt dieselbe
Aussage. Dieser DRAFT spezifiziert eine **neue Komponente**: ein Beziehungsgedächtnis
`E[i][j]`, das nur bei Interaktion `(i,j)` geschrieben wird — und prüft es mit
**demselben** Screening (S-S / S-G) als Abnahme.

### 0.3 Abgrenzung zu `KOPPLUNG_EIJ_v1` / `edge_signal.py`

| | `E_ij` (versiegelt) | `KANTEN_LEDGER_v1` (dieser DRAFT) |
|--|---------------------|-----------------------------------|
| Charakter | Parametrische Kopplungsgröße aus Trust/Freshness/Risk | Bewusst gebautes Beziehungsgedächtnis |
| Zweck damals | κ-Intervention / Sweep §1.1 | Persistenter Ledger + Screening-Abnahme |
| Update | Thompson/Decay in Kopplungs-Pipeline | Ausschließlich bei Interaktion `(i,j)` |
| Abnahme | I1-Edge + κ-Sweep | **Nur** S-S / S-G (wie `PARTNERSELECT_SCREEN_v1`) |
| Retest | **verboten** (HARKing) | Neuer Code, neue Seeds, neue Artefakte |

`E_ij` `I1_PASS` bleibt gültig und gesperrt. Dieses Ledger ist **kein** Retest jener
Studie, sondern die nächste prüfbare Stufe: eine Größe, deren Wert davon abhängt,
**welcher** Partner beteiligt war — nicht nur, dass einer beteiligt war.

---

## 1. Architektur-Spezifikation

### 1.1 Tensor

```text
E[i][j] ∈ ℝ^k    für alle Agentenpaare (i, j) mit i ≠ j
```

| Feld | Festlegung (einfrieren bei `ARCH_BINDEND`) |
|------|-----------------------------------------------|
| Population | **27** Agenten (9 Provider / 9 Evaluator / 9 Economic) — konsistent mit der Serie |
| Topologie | **gerichtet**, keine Selbstkanten (`i ≠ j`) |
| Kapazität | bis zu `27×26` gerichtete Paare; lazy: Kante existiert erst nach erster Interaktion |
| Kanal | Vektorlänge **k = 5** (siehe §4); Reihenfolge der Komponenten fix |

> Hinweis: „9×9“ wäre eine Rollen-Teilmatrix. Dieser DRAFT spezifiziert den
> **vollen** 27er-Schwarm; rollenweise Teilbücher sind Implementierungsdetail,
> solange `(i,j)`-Updates nur bei echter Interaktion zwischen genau diesen IDs
> erfolgen.

### 1.2 Update-Regel (bindend)

1. `E[i][j]` wird **ausschließlich** aktualisiert, wenn eine Nachricht / ein Check /
   ein Settlement zwischen Sender `i` und Empfänger `j` stattfindet.
2. Broadcasts, die faktisch an **viele** Empfänger gehen, erzeugen **pro zugestelltem
   Empfänger** ein Paar-Update `(i, j_r)` — nicht ein globales Update.
3. `E[i][j]` ist unabhängig von `E[i][k]` für `k ≠ j` (kein Softmax über Partner,
   kein globales Mittel in die Kante schreiben).
4. Lesen für Screening: skalarer oder komponentenweiser Export je Sticky-Kante
   `(sender → partner)` analog I1-S (Wert am Partner `M(i)` vs. `π(M(i))`).

### 1.3 Decay (im DRAFT fixiert)

Zwischen Updates auf derselben Kante:

```text
E[i][j](t) = E[i][j](t−1) · exp(−γ · Δt) + S_neu(i, j, t)
```

| Symbol | Wert bei `ARCH_BINDEND` | Bedeutung |
|--------|-------------------------|-----------|
| `γ` | `0.05` / Tick | wie Architektur-Referenz / früheres Edge-Decay |
| `Δt` | Ticks seit `last_tick` der Kante | |
| `S_neu` | komponentenweise, §4 | nur bei Interaktion `(i,j)` |

Kein Decay auf unberührten Kanten vor Erst-Update (Kante existiert noch nicht).

### 1.4 Kein Global-State

Verboten in diesem Ledger:

- Schreiben von Schwarm-Mitteln, globalem Honor, Queue-Länge in `E[i][j]`
- Ein gemeinsames Ledger ohne Paar-Index
- Update bei Tick ohne Interaktion `(i,j)`

---

## 2. Abnahme-Kriterien (Screening, nicht Sweep)

Identisch zu `PARTNERSELECT_SCREEN_v1` / I1-S und I1-G:

| ID | Kriterium | Schwelle |
|----|-----------|----------|
| **S-S** | MAE unter Partnerpermutation (Min-Max-skaliertes Panel bzw. Kanten-MAE analog I1E-S) | `≥ 0.05` |
| **S-G** | Median `|corr_t(x_i(t), x̄(t))|` bzw. Kanten-Nicht-Globalität analog I1E-G | `≤ 0.90` |

**Bestehensregel (Abnahme bestanden):**

- Mindestens **eine** Ledger-Komponente (oder vereinbarter Skalar aus dem Vektor)
  erfüllt **beide** Kriterien in **≥ 2 von 3** Seeds.
- Near-Miss (`MAE ∈ [0.03, 0.05)` oder `|ρ| ∈ (0.90, 0.95]`) zählt **nicht**.
- κ = 0; keine Arme; kein κ-Sweep in dieser Phase.
- **`n_corr < 14` ⇒ S_G nicht prüfbar** („kein Test“, nicht Fail/Ausschluss).
- **MAE-Skala:** absolute Schwelle 0.05 ist nicht skaleninvariant; Folgestudien
  sollen MAE relativ zur Streuung / Min-Max normieren (siehe Abschlussdokument).

**Abnahme gescheitert:**

- Kein Kandidat unter Mehrheit → Label `LEDGER_SCREEN_FAIL`.
- Dann ist C die logische Folgerung: auch ein gebautes Ledger wird vom
  Gleichanteil / Router dominiert — Ursache eher Routing als Speicherform.
  Neuer DRAFT nur mit Router-Änderung, nicht Schwellen-Senkung.

### 2.1 Laufparameter Abnahme (einfrieren bei `ARCH_BINDEND`)

| Parameter | Wert |
|-----------|------|
| Seeds | `{20261201, 20261202, 20261203}` (neu; keine Überschneidung mit Screen/E_ij) |
| warmup | 32 |
| cycles | 512 |
| κ | 0 |
| Mehrheit | ≥2/3 Seeds |
| Artefakte | `agents_b2g/emergence/kanten_ledger_v1/` |

---

## 3. Implementierungs-Anforderungen (nach `ARCH_BINDEND`)

1. Modul `agents_b2g/emergence/kanten_ledger.py` (oder gleichwertig): `LedgerBook`
   mit `update(i, j, event)`, Decay, Export.
2. Hook in den Nachrichtenpfad des Capture-Adapters / `demo_producer_cluster`-äquivalent:
   jedes zugestellte `(sender, receiver)`-Ereignis → Ledger-Update.
3. Export der k Komponenten (und optional eines Skalars) so, dass
   `state_space_screen` / Kanten-MAE sie screenen kann — **ohne** die versiegelten
   `edge_signal.py`-Semantiken von `KOPPLUNG_EIJ_v1` zu überschreiben.
4. Runner: `scripts/run_kanten_ledger_v1_screen.py` (Abnahme only).
5. Keine Änderung an versiegelten Artefakt-Verzeichnissen.

Referenz (inspirierend, nicht bindend): `crew/did_registry.py` zählt bisher
`failed_attempts` je DID — Erweiterungslogik **je Paar** statt je Agent.

---

## 4. Kanten-Zustände (k = 5, Reihenfolge fix)

| Index | Name | `S_neu`-Skizze (bei Interaktion i→j) |
|------:|------|-------------------------------------|
| 0 | `interaction_count` | `+= 1` (vor Decay-Additiv: Inkrement nach Decay-Schritt) |
| 1 | `bilateral_balance` | signierter Nettobeitrag der Transaktion (i schuldet j / j schuldet i), Decimal-sicher |
| 2 | `trust_score` | Anteil erfolgreicher Checks auf dieser Kante (laufendes Mittel oder Beta-Mean) |
| 3 | `avg_latency` | EWMA der Tick-Latenz der Interaktion |
| 4 | `edge_risk` | Risiko-/Fehlschlag-Signal dieser Kante ∈ [0,1] |

Genaues `S_neu`-Mapping wird bei `ARCH_BINDEND` in einer kurzen Implementierungsnotiz
festgezogen (eine Seite), ohne die Namen/Reihenfolge zu ändern.

**Primäre Abnahme-Größe (default):** Komponente `trust_score` (Index 2), zusätzlich
Screening aller fünf Komponenten (Reporting); Bestehen = ≥1 Komponente S-S∧S-G
in ≥2/3 Seeds.

---

## 5. Trennregel (bindend)

1. Besteht die Abnahme mit `SOME_CANDIDATES` / Ledger-Pass: **kein** κ-Sweep und
   keine Interventions-Hypothese auf **demselben** Datensatz.
2. Folgetest (Kopplung / §1.1) = **neue** Pre-Reg + **neue** Seeds + neue Läufe.
3. Scheitert die Abnahme: **keine** Schwellen-Nachjustierung; optional neuer DRAFT
   zu Router/Fan-out (C-Pfad).
4. Versiegelte Serien bleiben gesperrt (`partnerselect_screen_v1/`, `eij_*`, …).

---

## 6. Ausgänge dieser Phase

| Label | Bedeutung | Nächster Schritt |
|-------|-----------|------------------|
| `LEDGER_SCREEN_PASS` | ≥1 Komponente S-S∧S-G in ≥2/3 Seeds | Neue Pre-Reg für Intervention möglich (Trennregel) |
| `LEDGER_SCREEN_CLOSE` | nur Near-Miss, kein Pass | Kein Sweep; Transformations-/Skalierungs-DRAFT oder Router-DRAFT |
| `LEDGER_SCREEN_FAIL` | kein Pass, kein Near-Miss nach DRAFT-Bändern | C: Ledger allein reicht nicht → Router/Fan-out adressieren |

---

## 7. Freigabe

| Stufe | Bedeutung |
|-------|-----------|
| **DRAFT** (dieser Stand) | Spezifikation formuliert; **kein** Code-Lauf |
| **`ARCH_BINDEND`** | γ, k, Seeds, Komponenten-Mapping eingefroren; Implementierung + Abnahme freigegeben |
| Abgeschlossen | Label gesetzt; Artefakte unter `kanten_ledger_v1/` |

**Nächster Schritt:** Explizite Freigabe `DRAFT → ARCH_BINDEND` (oder Änderungswunsch).
Kein Ledger-Code und kein Screening-Lauf vor diesem Vermerk.

---

## 8. Checkliste DRAFT

| Anforderung | Status |
|-------------|--------|
| Tensor / Update / Decay spezifiziert | ✅ §1 |
| Abnahme = S-S / S-G, Near-Miss zählt nicht | ✅ §2 |
| Abgrenzung zu `E_ij` klar | ✅ §0.3 |
| k=5 Komponenten gelistet | ✅ §4 |
| Trennregel | ✅ §5 |
| Ausgänge inkl. Fail→C | ✅ §6 |
| HARKing-Sperre Alt-Artefakte | ✅ §0.1 |
