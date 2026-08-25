# Bridge Filter-Diagnose — Leserhinweise vor Ergebnis-Lektüre

**Status:** Interpretativ — **ändert die bindende Pre-Reg nicht**  
**Pre-Reg:** `docs/BRIDGE_DIAGNOSTIC_PREREG.md` (bindend, 2026-08-22)  
**Zweck:** Reichweite, Schwellen-Herkunft und bekannte Inconclusive-Pfade dokumentieren,
bevor der konfirmatorische Lauf gelesen wird.

---

## 1. Verdict-tragende Permutation zielt nicht auf die Kopplung

**Frage der Studie (§0, §1):** Ist `V3_PERSISTENZ` ein Filter-Artefakt?

**Was Phase 1 verdict-tragend testet (Pre-Reg §2.3):** Zirkulärer Shift der
**fünf Kandidaten-Ströme** (`Z_neu`). `bridge_eth` und `bridge_gnosis` werden
permutiert, aber **explizit deskriptiv, nicht verdict-tragend**.

**Konsequenz:**

| Verdict | Was es tatsächlich bedeutet | Was es nicht bedeutet |
|---|---|---|
| `DIAG_SIGNAL_VALID` (Phase 1) | Konditionierer-Logik verhält sich auf permutierten Null-Daten neutral | ETH↔Gnosis-Kopplung ist kausal/real bewiesen |
| `DIAG_FILTER_ARTIFACT` | Filter reagiert auf Struktur, die nach Permutation nicht da sein sollte | — |

Ein Signal, das aus **Minuten-Raster**, **Occupancy-Autokorrelation** oder
**Binarisierung** des Treatment-Paars selbst entstünde, bliebe unter jedem Shift
der Kandidaten **unberührt** — weil `bridge_eth` und `bridge_gnosis` im
Verdict-Pfad fix bleiben.

**Der Test, der das aufdecken würde:** zirkulärer Shift von `bridge_eth` gegen
`bridge_gnosis` (unter dem ein reines Raster-Artefakt zusammenbrechen müsste).
Dieser Test **läuft deskriptiv mit** (Pre-Reg §2.3), geht aber **nicht** ins
Verdict ein.

**Leser-Disziplin:** Das Ergebnis der deskriptiven Bridge-Permutation mindestens
so aufmerksam lesen wie das bindende Verdict. `DIAG_SIGNAL_VALID` = „Konditionierer
neutral", nicht „Signal echt".

---

## 2. Schwellen aus Add-one-Größen, angewandt auf LOO

**Bindende Schwelle:** `τ_cleansing = 0,05` (5 % relative LOO-Änderung, Pre-Reg §3.1).

**Bekannte V3-Referenzwerte** sind aber **Add-one** gegen `Z_alt` allein
(V3-Dossier §5.4, versiegelt):

| Kandidat | Relative CTE-Änderung (Add-one vs. Baseline) |
|---|---:|
| Chainlink | +23,7 % |
| MEV-Cluster | +31,8 % |
| Liquidationen | +7,2 % |

**LOO** entfernt einen Kandidaten aus der **Vollunion** `Z_alt ∪ alle Z_neu`.
Bei Redundanz zwischen Konditionierern fällt die LOO-Differenz systematisch
**kleiner** aus als die Add-one-Differenz — teils erheblich.

**Grauzone-Risiko:**

```
ε_inert = 0,001  <  rel_loo  <  τ_cleansing = 0,05
```

Liegt ein Kandidat in diesem Band **und** ist perm-neutral, klassifiziert §3.1
ihn weder als `inert`, `neutral` noch `cleansing_worker` → **`unclassified`**
→ **`DIAG_INCONCLUSIVE`** (Pre-Reg §6.2, Priorität 1).

**Wahrscheinlichster Inconclusive-Pfad:** **Liquidationen** (+7,2 % Add-one)
haben den kürzesten Weg unter die 5-%-Marke in LOO. Die Schwelle stammt
konzeptionell aus einer anderen Rechenart — das ist vor dem Lauf bekannt,
nicht post-hoc.

**Was das für die Lesart bedeutet:** `DIAG_INCONCLUSIVE` wäre hier **kein**
methodischer Kollaps, sondern ein **Schwellen-Mismatch** zwischen V3-Deskriptiva
und LOO-Metrik. Die bindende Pre-Reg bleibt; die Interpretation muss den Pfad
kennen.

---

## 3. Asymmetrie der Sättigungs-Ausnahmeregel

Pre-Reg §3.2 definiert zwei unterschiedliche Regeln:

**`perm_neutral_i` (Filter neutral):**

```
p_perm_i > α_perm
  ODER
(occ_rate_i ≥ OCC_SAT  UND  rel_loo_i < ε_inert)
```

**`PERM_FAIL` (Verdict-Fail):**

```
∃ i : occ_rate_i < OCC_SAT  UND  p_perm_i ≤ α_perm
```

**Asymmetrie:** Für **Freistellung vom Fail** genügt hohe Occupancy allein
nicht — Fail erfordert `occ_rate < OCC_SAT`. Aber ein gesättigter Kandidat
(`occ ≥ 0,90`) mit **großem** LOO-Effekt (`rel_loo ≥ τ_cleansing`):

- scheitert **nicht** an `PERM_FAIL` (weil `occ ≥ OCC_SAT`)
- erfüllt **nicht** `perm_neutral` (dort ist `rel_loo < ε_inert` gefordert)
- landet in **`unclassified`** → **`DIAG_INCONCLUSIVE`**

Vermutlich beabsichtigt (Sättigung ≠ Perm-Neutralität), aber die Konsequenz
ist vor Ergebnis-Lektüre zu kennen: **`unclassified` ist kein Randfall**.

---

## 4. Registrierte Vorhersage §1.2 — was wirklich falsifizierbar ist

| Vorhersage-Teil | Falsifizierbar? | Begründung |
|---|---|---|
| Intent-Relayers + Stablecoin → `inert` | **Nein** (tautologisch) | 62/62 byte-identisch im versiegelten V3-Ergebnis; §3.1 Byte-Identitäts-Klausel |
| Chainlink, Liquidationen, MEV → nicht `inert` | **Ja** | LOO + Perm auf wirksamen Konditionierern |
| `PERM_PASS` | **Ja** | Gesättigte PASS-Regel schützt No-ops; Fail nur bei `occ < 0,90` |
| Gesamt `DIAG_SIGNAL_VALID` | **Ja** (eingeschränkt) | Siehe §1 — Reichweite auf Konditionierer, nicht Kopplung |

Die Studie verliert durch die tautologische Hälfte der Vorhersage **keinen**
Informationsgehalt — sie **verschiebt** ihn auf die drei wirksamen Kandidaten,
die deskriptive Bridge-Permutation und den Inconclusive-Pfad aus §2.

---

## 6. K-Fold-Stabilität über Vorzeichen ist strukturell leer

Pre-Reg §3.3 misst Fold-Stabilität über **Vorzeichen-Invarianz**:

```
P_sign_k,d = (1/31) × |{τ : sign(CTE_k,d(τ)) = sign(CTE_full,d(τ))}|
Fold instabil:  P_sign_k,d < 0,95
```

**Strukturelles Problem:** CTE wird als frequenzbasierte KL-Divergenz geschätzt
(`transfer_entropy_binary`) und ist **nicht-negativ**. Im versiegelten V3-Ergebnis
(434 CTE-Werte über Baseline + Primär + Sensitivität):

```
n = 434     min ≈ 5,05×10⁻⁴     max ≈ 2,73×10⁻³
negativ: 0     exakt null: 0
```

Damit ist `sign(CTE) = +1` **überall**. Folge:

- `P_sign = 1,0` in jedem Fold und jeder Richtung
- **Kein Fold kann instabil werden** → `KFOLD_STABLE` ist **garantiert**
- Die Lokalisierungs-Maschinerie (`MARKET_EVENT`, `RPC_DATA_LOSS`,
  `UNEXPLAINED_LOCAL`) hängt an einer Bedingung, die **nie eintritt**

**Was stattdessen bereits existiert (deskriptiv, V3):** Fold-Kollaps-Spalte
(`n_folds_mit_kollaps`: 3/9, 2/9, 1/9 je Kandidat) — eine echte fold-weise
Statistik. Für eine streng positive Größe wäre ein sinnvolleres Stabilitätsmaß
die **Form des Lag-Profils** (Spearman `CTE_k(τ)` vs. `CTE_full(τ)`) oder
**Peak-Lag-Erhalt** (τ=6 ab, τ=15/16 ba) — nicht das Vorzeichen.

**Konsequenz für die Lesart:** Der K-Fold-Arm von Phase 1 trägt **nichts** zum
Verdict bei. Er läuft bindend mit, ändert aber die Disjunktion in §6.1 nicht.

---

## 7. Zweiter Pfad zu `DIAG_FILTER_ARTIFACT` ist logisch leer

Pre-Reg §6.1:

```
DIAG_FILTER_ARTIFACT  ⟺  PERM_FAIL
                        ODER  ∃ cleansing_worker mit perm_collapse_i ≤ ρ_collapse
```

Pre-Reg §3.1 definiert **`cleansing_worker`** als:

```
rel_loo_i ≥ τ_cleansing   UND   perm_collapse_i > ρ_collapse
```

Ein `cleansing_worker` mit `perm_collapse_i ≤ ρ_collapse` **widerspricht**
seiner eigenen Definition — die Menge ist **leer**. Der zweite Disjunkt in
§6.1 ist damit **logisch tot**.

**Konsequenz:** In Phase 1 reduziert sich die Entscheidung auf:

```
DIAG_IN_SILICO_PASS   ⟺  PERM_PASS
DIAG_FILTER_ARTIFACT  ⟺  PERM_FAIL
PERM_FAIL             ⟺  ∃ i : occ_rate_i < 0,90  UND  p_perm_i ≤ 0,05
```

---

## 8. Effektive Diagnose — ein Test, drei Arme

**Zusammenfassung der strukturellen Reduktion (§1, §6, §7):**

| Arm (Pre-Reg) | Trägt verdict-tragend? | Grund |
|---|---|---|
| Permutation (Kandidaten) | **Ja** | Einziger nicht-trivialer Pfad zu PASS/FAIL |
| K-Fold (P_sign) | **Nein** | CTE immer ≥ 0 → P_sign ≡ 1,0 |
| Ablation-Rollen → FILTER_ARTIFACT | **Nein** | Zweiter Disjunkt leer (§7) |
| Bridge-Permutation | **Nein** | Deskriptiv (§1) |

**Permutations-Arme mit Fail-Potenzial** (`occ_rate < OCC_SAT = 0,90`):

| Kandidat | Occupancy (Integrity Gate) | Kann `PERM_FAIL` auslösen? |
|---|---:|---|
| Chainlink | 7,4 % | Ja |
| Liquidationen | 0,58 % | Ja — plausibler Kandidat für gesättigten No-op bei niedriger Occupancy |
| MEV-Cluster | 57,3 % | Ja |
| Intent-Relayers | 98,8 % | Nein (Sättigungs-Freistellung) |
| Stablecoin Mint/Burn | 95,5 % | Nein |

Die Studie ist **nicht wertlos:** `PERM_FAIL` ist erreichbar; ein No-op bei
Liquidationen trotz `occ < 0,90` wäre genau die Art Fund, die diese Diagnose
rechtfertigt. Aber die **Reichweite** ist enger als der Agenten-Name nahelegt.

**Protokoll-Satz beim Verdict-Lesen:**

> **`DIAG_SIGNAL_VALID` bedeutet hier nicht „drei unabhängige Prüfungen
> bestanden", sondern „ein Permutationstest über drei Kandidaten bestanden;
> zwei weitere Arme waren strukturell nicht in der Lage zu widersprechen,
> und der K-Fold-Arm trug nichts."**

Dazu §1: selbst bei `PERM_PASS` ist das **Kopplungs-Signal** nicht validiert —
nur die **Konditionierer-Logik** auf den permutierten Kandidaten-Strömen.

**Für künftige Pre-Regs (nicht diese):** K-Fold auf Spearman/Peak-Lag;
Verdict-tragende Bridge-Permutation; LOO-Schwellen kalibriert auf LOO-Null,
nicht Add-one-Deskriptiva.

---

## 9. Protokollsatz V3 §8

Der wörtliche Satz zur Coverage/Informativitäts-Falle steht bindend in
Pre-Reg §3.2. Er gehört dort, wo er beim nächsten Gate-Design gelesen wird —
unabhängig vom Ergebnis dieser Diagnose.

---

## Referenzen

| Dokument | Rolle |
|---|---|
| `docs/BRIDGE_DIAGNOSTIC_PREREG.md` | Bindende Schwellen und Verdicts |
| `docs/BRIDGE_DIAGNOSTIC_SPEC.md` | 9-Agenten-Implementierung |
| `docs/BRIDGE_STUFE_A_V3_ERGEBNIS.md` | V3 Add-one-Deskriptiva, No-op-Diagnose |
| `bridge_stufe_a_v3_ergebnis.json` | Byte-Identität Intent/Stablecoin; CTE min/max (§6) |
| `bridge_stufe_a_v3_integrity_gate.json` | Occupancy-Raten (§8) |
