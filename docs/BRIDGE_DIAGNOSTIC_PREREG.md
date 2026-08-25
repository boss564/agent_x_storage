# Bridge Filter-Diagnose — Pre-Registration (Wave 38)

**Status:** **bindend** (gesetzt am 2026-08-22)  
**Spec:** `docs/BRIDGE_DIAGNOSTIC_SPEC.md`  
**Ziel:** Prüfen, ob `V3_PERSISTENZ` ein **echtes Signal** oder ein **Filter-Artefakt** ist  
**Bindender Vorlauf:** `docs/BRIDGE_STUFE_A_V3_ERGEBNIS.md` (`V3_PERSISTENZ`, versiegelt)  
**Charakter:** Konfirmatorische Diagnose-Studie. Kein HARKing. Kein Datenblick vor Bindung.

Die Stufen A, A v2 und A v3 bleiben unverändert und versiegelt. Diese Pre-Reg
referenziert V3-Artefakte **read-only** (Integrity Gate, Ergebnis-JSON). Sie
führt **neue** Analysen (Ablation, Permutation, K-Fold) ein — getrennt von der
V3-Add-one-Konditionierung.

---

## 0. Vorbedingungen und Scope

1. **Startvoraussetzung:** `bridge_stufe_a_v3_integrity_gate.json` mit `status=PASS`
   und `bridge_stufe_a_v3_ergebnis.json` mit `verdict=V3_PERSISTENZ`.
2. **Zeitfenster:** identisch zu Stufe A/v3 — 2026-05-20 00:00:00 UTC bis
   2026-08-17 23:59:59 UTC (129 600 Minuten-Raster).
3. **Zweck:** Trennung Modell-Fehler (Phase 1 In-Silico) vs. Infrastruktur-Fehler
   (Phase 2 Ex-Post).
4. **Keine Schwellen-Anpassung nach erstem Diagnose-Lauf.** Keine Kandidaten-Erweiterung
   in dieser Pre-Reg.

### 0.1 Lauf-Disziplin (HARKing-Schutz)

| Erlaubt vor Bindung | Verboten vor Bindung |
|---|---|
| Code-Skeleton, Typen, JSON-Schemas | Jeder Lauf, der ΔCTE, Permutations-p oder Verdict produziert |
| Loader-Unit-Tests **ohne** V3-Occupancy (leerer Input, Typfehler) | Ablation-Smoke gegen V3-Daten |
| Review der **versiegelten** V3-Dossiers/Gates | Ergebnis-Werte in Schwellen-Formulierung einfließen lassen |

**Technischer Smoke (vor Bindung):** nur Tests, die **keine** CTE-, Permutations-
oder Verdict-Ausgabe erzeugen. Konfirmatorischer Lauf erst **nach** Status
**bindend** dieser Pre-Reg.

---

## 1. Hypothesen

### 1.1 Primär (Phase 1 — In-Silico)

**H1-diag (Signal gültig):** Die unter `V3_PERSISTENZ` dokumentierte Kopplung
übersteht Permutations-Null und K-Fold-Stabilität. Kein Kandidat zeigt
Phantom-Bereinigung (Filter reagiert auf permutierte Null-Struktur).

**H0-diag (Filter-Artefakt):** Mindestens ein Test der Phase 1 schlägt fehl
(`PERM_FAIL`, oder Klassifikation widerspricht Permutations-Neutralität) →
Persistenz ist (teilweise) Folge der Filter-Logik, nicht eines robusten Signals.

### 1.2 Registrierte quantitative Vorhersage (theoretisch abgeleitet)

**Quelle der Ableitung:** V3-Dossier §5.3 (gesättigte Occupancy, No-op-
Konditionierer) und Integrity-Gate-Occupancy-Raten — **ohne** Diagnose-Ablations-Lauf.

| Vorhersage | Operationalisierung (§3) |
|---|---|
| Intent-Relayers und Stablecoin Mint/Burn werden **`inert`** klassifiziert | Occupancy ≥ 0,90 (Integrity Gate) + LOO \|ΔCTE\| < ε_inert |
| Chainlink, Liquidationen, MEV werden **nicht** `inert` | LOO \|ΔCTE\| ≥ ε_inert oder Permutation nicht neutral |
| Gesamt-Verdict Phase 1 | `DIAG_IN_SILICO_PASS` (kein `PERM_FAIL`) |
| Gesamt-Verdict konfirmatorisch | **`DIAG_SIGNAL_VALID`** (§6) |

Diese Vorhersage ist **falsifizierbar**. Bestätigung oder Widerlegung erfolgt
ausschließlich im konfirmatorischen Lauf nach Bindung.

### 1.3 Sekundär (Phase 2 — Ex-Post, optional)

**H1-expost:** Bei vorhandenem Decision-Log überwiegen TP+TN gegenüber
Modell-Fehlern (FN-model); Infrastruktur-Fehler (FP-infra) sind quantifizierbar
und vom Modell trennbar.

**H0-expost:** FN-model oder FP-infra dominieren → Schwellen- oder Bot-Anpassung
indiziert (Verdict §6).

Phase 2 darf mit `--skip-ex-post` übersprungen werden; dann endet die Studie
mit Phase-1-Verdict + `DIAG_SIGNAL_VALID` / `DIAG_FILTER_ARTIFACT` ohne
Ex-Post-Komponente (§6.4).

---

## 2. Blocking-Entscheidungen

### 2.1 Ablation vs. V3-Konditionierung (verbindlich getrennt)

| Pfad | Formel | Rolle in dieser Studie |
|---|---|---|
| **Ablation (primär)** | Leave-one-out aus `Z_alt ∪ {Z_neu_ter_i : i=1..5}` | **Primäre Evidenz** für `inert` / `cleansing_worker` / `neutral` |
| **V3-Add-one (sekundär)** | `CTE(X→Y \| Z_alt ∪ Z_neu_ter_i)` je Kandidat | **Nur deskriptiv**, read-only aus `bridge_stufe_a_v3_ergebnis.json` |

Die LOO-Differenzen entscheiden die Kandidaten-Rollen. V3-Ergebnisse werden
parallel berichtet, überschreiben aber **nicht** die Ablation-Klassifikation.

### 2.2 Referenz-Modell (Ablation-Basis)

**Vollunion:** `drivers_full = Z_alt_ter + [Z_neu_ter_1, …, Z_neu_ter_5]`

- `Z_alt`: Gas, BTC, CEX — Tertile wie V3 (`encode_drivers_tertiles`)
- `Z_neu_ter_i`: Tertile der binären Occupancy je Kandidat (`encode_z_neu_tertile`)
- CTE-Schätzer: `transfer_entropy_binary` (identisch V3 §4.3)
- Surrogate: 1000, plus-one-p, Seed §7

**Referenz-Summen-CTE** (pro Richtung `d ∈ {ab, ba}`):

```
S_ref_d = Σ_{τ=0}^{30} CTE_d(τ | drivers_full)
```

**Leave-one-out** (Kandidat `i` entfernt):

```
S_loo_d,i = Σ_{τ=0}^{30} CTE_d(τ | drivers_full \ {Z_neu_ter_i})
Δ_loo_d,i = S_ref_d − S_loo_d,i
rel_loo_i = max_d ( |Δ_loo_d,i| / max(|S_ref_d|, 1×10⁻¹²) )
```

### 2.3 Permutations-Design

- **Methode:** Zirkulärer Minuten-Shift der **Timestamp-Indizes** je Datenstrom
  (marginal Occupancy invariant, zeitliche Struktur zerstört)
- **Shift-Set:** `{s_k : s_k = k × ⌊N/100⌋ Minuten}`, `k = 1..100` (100 Shifts)
- **Targets:** je `Z_neu`-Kandidat einzeln; zusätzlich Sensitivität `bridge_eth`,
  `bridge_gnosis` (deskriptiv, nicht verdict-tragend)
- **Metrik pro Target:** `S_perm_d` = Summen-CTE wie §2.2 nach Shift + Rekodierung
  Occupancy/Tertile

### 2.4 K-Fold-Geometrie

Identisch V3: `K = 9`, `FOLD_DAYS = 10`, `fold_minute_ranges()` aus
`bridge_stufe_a_v3_config.py`.

---

## 3. Kategoriale Schwellen (bindende Zahlen)

### 3.1 Ablation-Rollen

| Konstante | Wert | Bedeutung |
|---|---:|---|
| `ε_inert` | **0,001** | 0,1 % relative LOO-Änderung |
| `τ_cleansing` | **0,05** | 5 % relative LOO-Änderung (Mindest-Schwelle „nicht inert") |
| `ρ_collapse` | **0,50** | Permutation bricht LOO-Effekt um >50 % |
| `OCC_SAT` | **0,90** | Sättigungs-Schwelle (Integrity Gate) |

**Klassifikation** (Kandidat `i`, nach LOO + Permutation):

| Rolle | Bedingung (alle müssen gelten, sofern nicht „oder") |
|---|---|
| **`inert`** | `rel_loo_i < ε_inert` **UND** `perm_neutral_i = true` |
| **`cleansing_worker`** | `rel_loo_i ≥ τ_cleansing` **UND** `perm_collapse_i > ρ_collapse` |
| **`neutral`** | `rel_loo_i ≥ τ_cleansing` **UND** `perm_collapse_i ≤ ρ_collapse` |
| **`unclassified`** | sonst (wird als `DIAG_INCONCLUSIVE`-Trigger gewertet, wenn >0) |

Hilfsgrößen:

```
perm_collapse_i = 1 − ( rel_loo_i_after_perm / max(rel_loo_i, 1×10⁻¹²) )
perm_neutral_i  = true  wenn  p_perm_i > 0,05  ODER  (occ_rate_i ≥ OCC_SAT  UND  rel_loo_i < ε_inert)
```

`p_perm_i`: Anteil der 100 Shifts mit `|S_perm − S_ref| / max(|S_ref|, 1×10⁻¹²) ≥ ε_inert`
(zweiseitig). Plus-one-Korrektur nicht erforderlich (empirische Null).

**Byte-Identität:** Zusätzlich `inert`, wenn alle 62 Lag-CTE-Werte (je Richtung)
nach LOO identisch zur Vollunion-Referenz (`|Δ| < 1×10⁻¹⁵`).

### 3.2 Permutations-Null (Filter-Neutralität)

| Konstante | Wert |
|---|---:|
| `α_perm` | **0,05** |
| `ε_inert` | **0,001** (wie §3.1) |

**`perm_neutral_i`** (Filter neutral für Target `i`):

- `p_perm_i > α_perm`, **oder**
- `occ_rate_i ≥ OCC_SAT` **und** `rel_loo_i < ε_inert` (gesättigter No-op — **kein Fail**)

**`PERM_PASS`:** `perm_neutral_i` für **alle** fünf Kandidaten.

**`PERM_FAIL`:** ∃ Kandidat `i` mit `occ_rate_i < OCC_SAT` **und** `p_perm_i ≤ α_perm`.

**Protokoll-Satz (Pflicht, aus V3-Dossier §8):**

> *Ein Gate, das Kandidaten nicht trotz, sondern wegen Sättigung durchwinkt
> (`coverage_ratio = 1.0` als Gütesiegel), belohnt genau die Eigenschaft, die
> sie als binäre Konditionierer wertlos macht — Bestehen und Unbrauchbarkeit
> korrelieren. Neben Abdeckung braucht jede binäre Belegungskodierung ein Gate
> auf Varianz oder Terzil-Dispersion.*

Gesättigte Kandidaten mit Δ=0 unter Permutation sind **explizit PASS**, nicht Fail.

### 3.3 K-Fold — Vorzeichen-Invarianz

| Konstante | Wert |
|---|---:|
| `P_sign_min` | **0,95** |
| `N_break_folds_max` | **1** | max. zulässige instabile Folds für `KFOLD_STABLE` |
| `EVENT_DENSITY_RATIO` | **2,0** | Markt-Event-Lokalisierung |
| `RPC_GAP_RATE` | **0,10** | RPC-Datenverlust-Schwelle pro Fold |

Pro Fold `k`, Richtung `d`:

```
P_sign_k,d = (1/31) × |{τ : sign(CTE_k,d(τ)) = sign(CTE_full,d(τ))}|
```

**Fold instabil:** `P_sign_k,ab < P_sign_min` **oder** `P_sign_k,ba < P_sign_min`

**`KFOLD_STABLE`:** ≤ `N_break_folds_max` (=1) instabile Folds.

**`KFOLD_LOCALIZED_BREAK`:** ≥ 2 instabile Folds.

**Lokalisierungs-Attribution** (nur bei instabilem Fold):

| Label | Bedingung |
|---|---|
| `MARKET_EVENT` | Event-Count eines Kandidaten im Fold > `EVENT_DENSITY_RATIO` × Median-Fold-Count |
| `RPC_DATA_LOSS` | `rpc_gap_rate_k > RPC_GAP_RATE` (Ex-Post-RPC-Audit, falls verfügbar; sonst `UNKNOWN`) |
| `UNEXPLAINED_LOCAL` | instabil, weder MARKET_EVENT noch RPC_DATA_LOSS |

---

## 4. Informativitäts-Gate (vor erstem Diagnose-CTE-Blick)

Zusätzlich zum V3-Coverage-Gate (read-only). Wird **vor** Ablation/Permutation
berechnet und in `bridge_diagnostic_informativity_gate.json` geschrieben.

| Prüfung | Schwelle | Fail-Wirkung |
|---|---|---|
| Terzil-Dispersion | `n_distinct_tertile_bins ≥ 2` | `INERT_ENCODING` (weiter testbar, Perm-Regel §3.2) |
| Occupancy-Sättigung | `occ_rate ≥ OCC_SAT` (=0,90) | `INERT_ENCODING` — kein Blocker |
| Event-Count-Varianz | `std(events_per_minute) > 0` | deskriptiv; Intensitäts-Kodierung **nicht** in v1 |

**Blocker (`DIAG_UNTESTABLE`):** Integrity Gate FAIL **oder** V3-Verdict ≠
`V3_PERSISTENZ` **oder** fehlende Capture-Datei.

Kein Kandidat wird wegen `INERT_ENCODING` aus der Ablation entfernt — die
Klassifikation erfolgt über §3.1.

---

## 5. Phase 2 — Ex-Post (optional)

### 5.1 Attributions-Matrix

| Agent-X | On-Chain | Zelle |
|---|---|---|
| RELEASED | Erfolg (Profit) | **TP** |
| RELEASED | Revert / Gas-Fail | **FP-infra** |
| BLOCKED | Gewinn entgangen | **FN-model** |
| BLOCKED | Revert vermieden | **TN** |

### 5.2 Ex-Post-Schwellen

| Konstante | Wert |
|---|---:|
| `τ_fn` | **0,10** | FN-model-Rate >10 % → überkonservativ |
| `τ_fp` | **0,15** | FP-infra-Rate >15 % → infra-dominiert |
| `τ_rpc_gap` | **0,20** | >20 % unmatched → `DIAG_INCONCLUSIVE` |

**Schwellen-Nachjustierung (Agent 8):** nur aus **FN-model**-Zellen indiziert.
FP-infra → Ausführungs-Bot, **nicht** CTE-Filter.

---

## 6. Verdict-Mapping (bindend)

### 6.1 Phase-1-Fragmente

| Fragment | Bedingung |
|---|---|
| `DIAG_IN_SILICO_PASS` | `PERM_PASS` **und** (`KFOLD_STABLE` **oder** `KFOLD_LOCALIZED_BREAK` nur mit `MARKET_EVENT`-Attribution) |
| `DIAG_FILTER_ARTIFACT` | `PERM_FAIL` **oder** ∃ `cleansing_worker` mit `perm_collapse_i ≤ ρ_collapse` nach Permutation (Phantom-Bereinigung) |

### 6.2 Finales Verdict

| Verdict | Bedingungen (Priorität top-down) |
|---|---|
| **`DIAG_INCONCLUSIVE`** | Integrity/Informativity-Blocker; **oder** `unclassified` > 0; **oder** Ex-Post required but `rpc_gap > τ_rpc_gap`; **oder** widersprüchliche Fragmente |
| **`DIAG_FILTER_ARTIFACT`** | `DIAG_FILTER_ARTIFACT` Fragment (§6.1) |
| **`DIAG_OVERCONSERVATIVE`** | Phase 1 = `DIAG_IN_SILICO_PASS` **und** Ex-Post **und** `FN_model_rate > τ_fn` |
| **`DIAG_INFRA_DOMINATED`** | Phase 1 = `DIAG_IN_SILICO_PASS` **und** Ex-Post **und** `FP_infra_rate > τ_fp` **und** `FP_infra_rate > FN_model_rate` |
| **`DIAG_SIGNAL_VALID`** | Phase 1 = `DIAG_IN_SILICO_PASS` **und** (Ex-Post skipped **oder** (`FN_model_rate ≤ τ_fn` **und** `FP_infra_rate ≤ τ_fp`)) |

**Priorität:** Erste zutreffende Zeile von oben nach unten gewinnt.

### 6.3 Mapping registrierte Vorhersage → Verdict

| Vorhersage §1.2 | Verdict bei Bestätigung |
|---|---|
| ≥2 `inert`, ≥1 nicht-inert, `PERM_PASS` | `DIAG_SIGNAL_VALID` (wenn K-Fold stabil) |
| `PERM_FAIL` | `DIAG_FILTER_ARTIFACT` (Vorhersage widerlegt) |
| ≥3 `cleansing_worker` | `DIAG_SIGNAL_VALID` möglich, aber Collider-Verdacht im Report |
| Intent/Stablecoin **nicht** `inert` | Vorhersage widerlegt; Verdict kann trotzdem `DIAG_SIGNAL_VALID` sein |

### 6.4 Ex-Post-Skip

Mit `--skip-ex-post`: finales Verdict = Phase-1-Mapping ohne Zeilen
OVERCONSERVATIVE/INFRA (nur `DIAG_SIGNAL_VALID`, `DIAG_FILTER_ARTIFACT`,
`DIAG_INCONCLUSIVE`).

---

## 7. Determinismus

| Parameter | Wert |
|---|---|
| `BRIDGE_DIAGNOSTIC_SEED` | **20260822** |
| `N_SURROGATES` | **1000** (identisch V3) |
| `N_PERM_SHIFTS` | **100** |
| `FDR_Q` | **0,05** (nur falls BH über Permutations-Familie; Primär: fixed-α §3.2) |

Seed-Verwendung:

- Surrogate-CTE: `SEED`
- Permutations-Shifts Kandidat `i`: `SEED + 1000 × (i + 1)`
- K-Fold-Reihenfolge: `SEED + 9000`

Gleiche Inputs + gleicher Seed → byte-identische Outputs.

---

## 8. Berichtspflichten (Artefakte)

Vor Verdict-Bekanntgabe:

1. `bridge_diagnostic_informativity_gate.json`
2. `bridge_diagnostic_ablation.json`
3. `bridge_diagnostic_permutation.json`
4. `bridge_diagnostic_kfold.json`
5. `bridge_diagnostic_ergebnis.json` (aggregiert)
6. `diagnostic_report.pdf` + WORM-Trail (Agent 9)

V3-Add-one-Deskriptiva: eingebettet als `v3_reference` (read-only), nicht neu berechnet.

---

## 9. Was diese Pre-Reg explizit nicht tut

- Keine Änderung von V3-Verdict, Schwellen oder FDR-Familie
- Keine Intensitäts-Kodierung (Events/Minute-Terzile) — **neue Pre-Reg** nötig
- Keine Kandidaten-Erweiterung über die fünf V3-Klassen hinaus
- Keine Ex-post-Schwellen-Anpassung nach Datenblick
- Kein konfirmatorischer Lauf vor Status **bindend**

---

## 10. Bindungs-Checkliste

- [x] Kategoriale Schwellen als Zahlen (§3)
- [x] Ablation LOO vs. V3-Add-one getrennt (§2.1)
- [x] Permutations-Regel für gesättigte Kandidaten (§3.2)
- [x] K-Fold-Schwellen und Lokalisierung (§3.3)
- [x] Verdict-Mapping bindend (§6)
- [x] Informativitäts-Gate + V3-§8-Protokoll-Satz (§4)
- [x] Registrierte Vorhersage vor Datenblick (§1.2)
- [x] Lauf-Disziplin (§0.1)
- [x] Konfirmatorischer Pipeline-Lauf (2026-08-22, `DIAG_SIGNAL_VALID`)

---

## 11. Referenzen

| Dokument | Rolle |
|---|---|
| `docs/BRIDGE_STUFE_A_V3_PREREG.md` | V3-Methodik (versiegelt) |
| `docs/BRIDGE_STUFE_A_V3_ERGEBNIS.md` | V3-Ergebnis + No-op-Diagnose |
| `docs/BRIDGE_DIAGNOSTIC_SPEC.md` | Implementierungs-Spec (9 Agenten) |
| `docs/BRIDGE_DIAGNOSTIC_LESERHINWEISE.md` | Reichweite, Schwellen-Herkunft (interpretativ, nicht bindend) |
| `docs/BRIDGE_DIAGNOSTIC_ERGEBNIS.md` | Ergebnis-Dossier (versiegelt) |
| `bridge_stufe_a_v3_integrity_gate.json` | Occupancy-Raten, Alignment |
| `bridge_stufe_a_v3_ergebnis.json` | V3-Deskriptiva (read-only) |
