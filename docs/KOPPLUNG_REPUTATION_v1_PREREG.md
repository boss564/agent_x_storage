# Emergenz — Kopplung Reputation/Honor: Pre-Registration

**Arbeitstitel:** `KOPPLUNG_REPUTATION_v1`  
**Status:** **BINDEND → I1_FAILED** — 2026-08-25 · Verdict `SIGNAL_BLIND` · κ-Sweep gesperrt.  
**Vorgänger:** `docs/EMERGENZ_KOPPLUNG_PREREG.md` (geschlossen 2026-08-25, `KOPPLUNG_INVALID`).  
**Datensatz-Regel:** Versiegelter Queue-Sweep wird **nicht** wiederverwendet (kein HARKing).  
**Charakter:** Interventionsstudie — ändert die **Kopplungsgröße**, nicht die Messkette.  
**2.1–2.3 (Trigger / κ(t) / Quorum):** nachgelagert, bis Partnerselektivität einer Größe steht.

---

## Ablauf (verbindlich für diese Studie)

1. DRAFT vervollständigen (fünf Blocker — dieser Stand)  
2. Freigabe → Status `DRAFT → BINDEND` (Vermerk §8)  
3. Adapter implementieren + **nur** I1 ausführen  
4. I1 PASS → κ-Sweep · I1 FAIL → `SIGNAL_BLIND`, Ende  

**Kein Sweep vor Bindung. Kein Sweep vor bestandenem I1.**

---

## 0. Zweck und Abgrenzung

### 0.1 Vorgänger

Queue-Länge als Kopplungsgröße: Arm C mehrheitlich `COUPLED`, Δr(B−C) ≈ 0,001…0,013
statt ≥ 0,10. Diagnose: **partnerblinde Größe**, nicht Über-Synchronisation.

### 0.2 Diese Studie

Trägt **Honor** (swarm-adaptiert über `HonorCalculator`) partnerspezifische Information,
sodass Arm B und Arm C unterscheidbar werden?

### 0.3 Nomenklatur

| Begriff | Bedeutung |
|---------|-----------|
| Arm A / B / C | Studienarme |
| Population | 27 Agenten: 9 Provider, 9 Evaluator, 9 Economic |
| Nicht diese Studie | `BlockchainNodeAgent`, `OracleAgent`, Cluster-Labels Security/Finance/W |

---

## 1. Hypothesen

**H1:** Taktraten-Kopplung an partnerspezifisches Honor erzeugt bei hinreichendem κ
Kohärenz, die unter Partnerpermutation (Arm C) mindestens `Δr ≥ Δr_min` gegenüber B verliert
(und Arm C nach Gate nicht mehrheitlich `COUPLED` bleibt).

**H0:** B und C bleiben ununterscheidbar — Größe ohne Partnerselektivität oder ohne Varianz.

### 1.1 Riskante Vorhersage (nach Bindung eingefroren)

**Arm C bleibt bei allen κ-Stufen `NO_COUPLING` nach Gate §3.1 + Mehrheitsregel §3.3.**

### 1.2 Instrumentations-Voraussetzung I1

I1 prüft Partnerselektivität der Größe **ohne** κ-Kopplung. Scheitert I1 → Verdict
`SIGNAL_BLIND`, **kein** κ-Sweep.

---

## 2. Design

### 2.1 Primäre Kopplungsgröße — Honor (swarm-adaptiert)

**Kanonsiche Größe:** kumuliertes Honor `H_i` je Agent `i` der 27er-Population.

**Rechenkern:** `agents_b2g.valhalla.valhalla.HonorCalculator.calc`  
(`H_event = α·SAT + β·TPS − γ·UNSAT + δ·perfect`, Konstanten unverändert aus Valhalla).

**Nicht zulässig:** globales Mittel, ein gemeinsames Ledger ohne Agent-ID, Nullifier-only
ohne Mapping auf die 27 Agenten-IDs, Queue-Länge, System-TPS.

#### 2.1.1 Event → HonorCalculator-Eingang (fixiert)

Nach jedem Agenten-`tick` / Aktionsabschluss, **rollenweise**:

| Rolle | Ereignis | `z3_sat` | `tps` | `unsat_attempts` |
|-------|----------|:--------:|------:|-----------------:|
| Provider | `report_milestone` | `True` | 1.0 | 0 |
| Provider | `report_inflated` | `False` | 1.0 | 1 |
| Evaluator | Check `holds=True` | `True` | 1.0 | 0 |
| Evaluator | Check `holds=False` | `False` | 1.0 | 1 |
| Economic | Settlement ausgeführt | `True` | 1.0 | 0 |

```
H_i ← H_i + HonorCalculator.calc(...).score
H_i ← max(0, H_i)
```

Start: `H_i(0) = 0` für alle i. Kein Seed-abhängiger Honor-Startwert.

### 2.2 Intervention

```
interval_i = base_i × (1 + κ · s(H_partner_i))
```

- `partner_i` = Sticky-Partner nach Freeze (Arm B) bzw. nach degree-preserving
  Rollensegment-Permutation (Arm C) — gleiche Mechanik wie Vorgänger.
- Abfragezeitpunkt: **unmittelbar vor** `update_sender_interval` im Intervall-Pfad,
  einmal pro globalem Cycle, in dem der Sender aktionsberechtigt geprüft wird.
- Fehlender / undefinierter Partner oder fehlendes `H`: `H_partner := 0` → `s = 0`
  (kein Crash, keine Imputation aus Nachbarn).

### 2.3 `s(H)` — fixiert (Blocker geschlossen)

```
s(H) = min(1.0, H / H_cap)    mit    H_cap = 200.0
```

| Eigenschaft | Festlegung |
|-------------|------------|
| Typ | bounded linear (kein z-score, kein populationsweites σ) |
| Wertebereich | [0, 1] |
| Begründung Cap | ≈ 4 × `HonorCalculator.ALPHA` (50) — wenige SAT-Events füllen die Skala, ohne Globalstatistik |

**Nach Bindung unveränderlich.** Keine Nachjustierung von `H_cap` nach Datenblick.

### 2.4 Struktur (beibehalten)

- Arme A (κ=0) / B / C · Warm-up 32 → Freeze → Messung  
- κ ∈ {0 · 0,2 · 0,4 · 0,6 · 0,8 · 1,2}  
- Population 27 (9/9/9)  
- Messkette `measure.py`, Kuramoto auf `phase`  
- Form-Kriterium analog Vorgänger §3.2 (nur nach I1 PASS + Gate interpretierbar)

### 2.5 Seeds — neu, unabhängig vom Queue-Sweep (Blocker geschlossen)

```
run_seeds = {20260901, 20260902, 20260903, 20260904, 20260905, 20260906}
```

| Regel | Festlegung |
|-------|------------|
| Disjoint | Keine Überlappung mit Queue-Sweep `{20260824…20260829}` |
| Verwendung | `init_timing` · `oscillator_from_gas` (falls) · `permute_sticky_map` (Arm C) · I1 |
| Reproduzierbarkeit | feste Liste, keine Zufallsziehung zur Laufzeit |

### 2.6 Sekundäre Größen

Nur wenn I1 für Honor → `SIGNAL_BLIND`: neue Pre-Reg (Gas-Kontostand / DID-Fehlhistorie).
Kein stiller Fallback innerhalb dieser Studie.

---

## 3. Schwellen

| Konstante | Wert | Status |
|-----------|-----:|--------|
| `N` | 27 | fest |
| `r_random` | 0,1925 | fest (1/√N) |
| `α` | 0,05 | fest |
| `n_surrogates` | 200 | fest |
| `Δr_min` | **0,10** | **bestätigt** — siehe §3.0 |
| `r_floor` | 0,34 | fest (`r_random + 0,15`) |
| `warmup_ticks` | 32 | fest |
| `cycles` (Sweep) | 512 | fest |
| Mehrheit | ≥ 4/6 Seeds | fest |

### 3.0 `Δr_min = 0,10` — Bestätigung (Blocker geschlossen)

**Übernahme aus der Vorgänger-Pre-Reg**, begründet:

1. Dieselbe Nullhypothese der Partnerselektivität (Kriterium 3): B muss C um einen
   vorab festgelegten Effektstärke-Abstand schlagen — nicht nur p < α.
2. Derselbe Zufallsgrundwert `r_random ≈ 0,19`; der Queue-Negativbefund zeigte
   Δr ≈ 0,001…0,013 — die Schwelle 0,10 trennt Signal von Partnerblindheit.
3. Keine Aufweichung nach dem Negativbefund (kein HARKing / keine Schwellen-Senkung).

### 3.1 Gate `COUPLED` (alle vier)

1. `p < α`  
2. `D_dyn > 0`  
3. `r_B − r_C ≥ Δr_min` bei identischem κ  
4. `r_B ≥ r_floor`  

Aggregation: ≥ 4/6 Seeds je κ.

---

## 4. I1 — Instrumentationscheck (Blocker geschlossen)

I1 ist **unabhängig** vom κ-Sweep. κ = 0 während I1 (keine Taktraten-Modulation).
Honor wird fortgeschrieben; es werden nur Beobachtungsserien ausgewertet.

### 4.1 I1-Laufparameter

| Parameter | Wert |
|-----------|-----:|
| `warmup_ticks` | 32 |
| `cycles` (Messfenster) | 64 |
| `kappa` | 0 |
| `run_seed` | `20260901` (erster Seed der neuen Liste) |
| Arme | Freeze wie Sweep; Auswertung B-Map vs. C-Permutation derselben Freeze-Map |

Prozedur:

1. Warm-up 32 → Freeze Sticky-Map `M`.  
2. Parallel (oder sequentiell deterministisch): Pfad B mit `M`, Pfad C mit
   `permute_sticky_map(M, seed=20260901)`.  
3. Messfenster 64 Ticks: für jeden Sender mit Partner in der Map  
   `x^B_i(t) = s(H_{partner^B_i}(t))`, `x^C_i(t) = s(H_{partner^C_i}(t))`.

### 4.2 Binäre Kriterien — I1 PASS nur wenn **alle** gelten

| ID | Kriterium | Schwelle |
|----|-----------|----------|
| **I1-V** | Varianz am Ende des Messfensters: Stichproben-σ von `{H_i}` über alle 27 Agenten | `σ(H) ≥ 10.0` |
| **I1-S** | Partnerselektivität: Mittel über Sender von `MAE_t(x^B_i, x^C_i)` | `≥ 0.05` |
| **I1-U** | Update-Frequenz: Anteil Agenten mit mindestens einer Honor-Änderung im Messfenster | `≥ 0.40` |
| **I1-G** | Nicht-Globalität: Median über i von `|corr_t(H_i(t), H̄(t))|` | `≤ 0.90` |

`H̄(t) = mean_j H_j(t)`. Bei undefiniertem corr (konstante Reihe): zählt als Fail für I1-G
bei diesem Agenten; Median über die übrigen — wenn < 14 Agenten corr-fähig → I1-G Fail.

| Outcome | Folge |
|---------|--------|
| Alle vier PASS | I1 bestanden → κ-Sweep freigegeben |
| Mindestens eines FAIL | Verdict `SIGNAL_BLIND` · Studie endet · keine Schwellen-Nachjustierung |

---

## 5. Verdict-Mapping

| Verdict | Bedingung (Priorität top-down) |
|---------|--------------------------------|
| `SIGNAL_BLIND` | I1 scheitert |
| `KOPPLUNG_INVALID` | Arm C bei irgendeinem κ `COUPLED` (Mehrheit) → §1.1 widerlegt |
| `HOMOGENIZED` | analog Vorgänger |
| `COUPLED_EMERGENT` | Gate + Form |
| `COUPLED_FORCED` | Gate ohne Form |
| `NO_COUPLING` | kein κ erfüllt Gate |

---

## 6. HARKing- und Nachjustierungs-Sperren

- Queue-Sweep: nur Negativbefund, keine Neuauswertung für H1.  
- Keine Anpassung von `s(H)`, I1-Schwellen, Seeds, `Δr_min` nach Datenblick.  
- Form-Hypothesen Trigger/κ(t)/Quorum: eigene Pre-Regs nach erfolgreicher Partnerselektivität.  
- Statuswechsel nur mit explizitem Freigabe-Vermerk §8.

---

## 7. Adapter-Spezifikation (Definition — noch keine Implementierung)

**Modulziel:** `agents_b2g/emergence/adapter_agentx.py` + `honor_signal.py`, ohne Änderung an `measure.py`.

| Frage | Festlegung |
|-------|------------|
| Welche Größe? | `H_i` kumuliertes Honor je Agent-ID |
| Woher? | Event-Mapping §2.1.1 → `HonorCalculator.calc` → Summe |
| Wann aktualisiert? | Sofort nach dem auslösenden Akt (Provider-Report / Evaluator-Check / Settlement), vor Snapshot des Ticks |
| Abfrage für Kopplung? | `H[partner_id]` vor `update_sender_interval` |
| Arm A | κ=0; Honor darf fortgeschrieben werden (für State-Export), greift nicht in Intervalle ein |
| Arm B | Partner aus eingefrorener Sticky-Map |
| Arm C | Partner aus permutierter Map; **dieselbe** `H`-Tabelle (Permutation ändert nur den Index, nicht die Honor-Werte) |
| Normalisierung | ausschließlich `s(H)` aus §2.3 |
| Fehlwerte | fehlender Partner / fehlendes H → 0 |
| State-Export | `honor` und `s_honor` in `numeric_state` (Messbarkeit / Audit) |

**Explizit nicht in diesem Adapter:** Implementierung von 2.1–2.3-Form-Varianten.

---

## 8. Freigabe-Vermerk

```text
Status: DRAFT → BINDEND
Datum: 2026-08-25
Studie: KOPPLUNG_REPUTATION_v1
Blocker geschlossen:
- Honor-Adapter: Event → HonorCalculator je Rolle;
  Abfrage vor update_sender_interval; fehlend → 0 (§2.1, §7)
- s(H): min(1, H/200) (§2.3)
- I1: V ≥ 10 · S ≥ 0.05 · U ≥ 0.40 · G ≤ 0.90 ·
  alle Pflicht · κ = 0 (§4)
- Seeds: 20260901 … 20260906 (§2.5)
- Δr_min = 0.10 bestätigt (§3.0)
Nächster Schritt:
- Adapter + I1
- kein Sweep
```

Bedingung: Sweep erst nach bestandenem I1-Instrumentationscheck (§4).

---

## 9. Bindungs-Checkliste

| Punkt | Stand im DRAFT |
|-------|----------------|
| Honor-Adapter spezifiziert | ✅ §2.1 + §7 (Implementierung erst nach Bindung) |
| `s(H)` fixiert | ✅ §2.3 |
| I1-Schwellen | ✅ §4.2 |
| Neue Seeds | ✅ §2.5 |
| `Δr_min = 0,10` bestätigt | ✅ §3.0 |
| Explizite Bindungs-Freigabe | ✅ §8 · 2026-08-25 |

**I1_FAILED.** Verdict `SIGNAL_BLIND` (§10–§11). κ-Sweep gesperrt. Keine Nachjustierung.

---

## 10. I1-Ergebnis (2026-08-25)

| Feld | Wert |
|------|------|
| Lauf | warmup=32 · cycles=64 · κ=0 · seed=20260901 |
| Verdict | **`SIGNAL_BLIND`** |
| I1-V | PASS (σ ≈ 257 ≥ 10) |
| I1-S | FAIL (MAE = 0 < 0.05) — `s(H)` gesättigt bei 1 |
| I1-U | PASS (1.0 ≥ 0.40) |
| I1-G | FAIL (median |ρ| ≈ 0.99 > 0.90) |
| κ-Sweep | **nicht freigegeben** |

Artefakte: `agents_b2g/emergence/reputation_i1/`. Keine Schwellen-Nachjustierung.

---

## 11. Abschluss I1 (Negativbefund, final)

```text
Status: BINDEND → I1_FAILED
Verdict: SIGNAL_BLIND
Folge: κ-Sweep gesperrt
Artefakte: agents_b2g/emergence/reputation_i1/
Keine Nachjustierung.
```

**Interpretation (append-only):** Honor in der gebundenen Operationalisierung ist
nicht partnerselektiv — (1) `s(H)`-Sättigung bei `H_cap=200`, (2) fast globale
Honor-Synchronität (`|ρ|≈0.99`). Entscheidend: `MAE=0` unter Partnerpermutation.

Keine Änderung von `H_cap`, `s(H)` oder I1-Schwellen. Keine Umdeutung in ein
späteres Ergebnis. Fortsetzung nur als **neuer DRAFT** (andere Größe oder andere
Honor-Operationalisierung), nicht als Reparatur dieser Pre-Reg.
