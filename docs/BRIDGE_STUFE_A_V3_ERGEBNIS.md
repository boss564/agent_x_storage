# Bridge Stufe A v3 — Kandidaten-Konditionierung: Ergebnis-Dossier

**Status:** Abgeschlossen — `confirmatory_verdict` **`V3_PERSISTENZ`** (definitiv)
**Auswertung:** 2026-08-22 UTC (`bridge_stufe_a_v3_ergebnis.json`)
**Fenster:** 2026-05-20 00:00:00 UTC – 2026-08-17 23:59:59 UTC (unverändert)
**Pre-Registration:** `docs/BRIDGE_STUFE_A_V3_PREREG.md` (bindend, 2026-08-19)
**Lock-in:** `scripts/bridge_stufe_a_v3_config.py`, `scripts/bridge_stufe_a_v3_load.py`,
`scripts/bridge_stufe_a_v3_integrity_gate.py`, `scripts/bridge_stufe_a_v3_pipeline.py`
**Charakter:** Folgestudie. Stufe A und A v2 bleiben versiegelt. Keine Umdeutung der
Vorgänger-Verdicts. Studie endet bindend — keine Kandidatenerweiterung in dieser Pre-Reg.

Dieses Dossier berichtet die registrierte Last. Qualitative Beobachtungen stehen
getrennt und ändern das Label nicht.

---

## 1. Verdict und Einordnung

**`V3_PERSISTENZ`** — unter der präregistrierten Kollaps-Definition löst kein
Kandidat die Kopplung auf (0/62 BH-Rejects je Kandidat). Die Kopplung bleibt nach
Konditionierung einzeln (309/310) und gemeinsam (60/62) signifikant.

Das ist kein Fehlschlag, sondern das explizit vorab definierte Persistenz-Outcome
(Pre-Reg §1.4): Wenn `Z_neu` die Kopplung nicht auflöst, endet die Studie hier.
Kein HARKing, keine nachträgliche Erweiterung des Kandidatensets.

**Kernaussage in einem Satz:** Die ETH↔Gnosis-Informationskopplung ist real und
robust. Unter den **präregistrierten Kollaps-Regeln** löst kein Kandidat die Kopplung
auf (`V3_PERSISTENZ`). **Effektiv getestet** wurden drei Kandidaten mit ausreichender
Occupancy-Varianz (Chainlink, Liquidationen, MEV); zwei weitere (Intent-Relayers,
Stablecoin Mint/Burn) wirkten als Konditionierer **nicht** — gesättigte Binär-Occupancy
(§5.3).

---

## 2. Hypothese und Regel

**H1-v3:** Mindestens ein Kandidat aus `Z_neu` verursacht **Kollaps** — nach
Konditionierung auf `Z_alt ∪ Z_kandidat_i` bleibt kein FDR-signifikanter
Treatment-CTE-Lag in **beiden** Richtungen (`ab` und `ba`).

**H0-v3:** Die Kopplung **persistiert** — auch nach Konditionierung bleibt mindestens
ein Treatment-Lag in der globalen 310er-FDR-Familie signifikant.

| Parameter | Festlegung |
|---|---|
| Primärpfad | `CTE(X→Y \| Z_alt ∪ Z_kandidat_i)`, `i = 1..5` |
| Sensitivität | `CTE(X→Y \| Z_alt ∪ Z_kandidat_1..5)` (separat berichtet) |
| Tests | **310** = 5 Kandidaten × 2 Richtungen × 31 Lags |
| FDR | eine Benjamini-Hochberg-Prozedur, **q = 0.05**, über alle 310 Tests |
| CTE-Null | Shuffle der Quell-Belegung, Ziel und Treiber fest, 1000 Surrogate |
| p | plus-one: `(1 + #{surr ≥ obs}) / 1001` |
| Seed | `BRIDGE_STUFE_A_V3_SEED = 20260819` |
| Kollaps | **ab UND ba:** kein BH-Reject unter den 62 Tests des Kandidaten |
| ΔCTE | deskriptiv (`CTE_vorher − CTE_nachher`), nicht Teil der Kollaps-Entscheidung |
| Tie-Break | ΔCTE → Fold-Robustheit (K=9) → frühester Peak-Lag (nur bei Mehrfach-Kollaps) |

**Baseline (Replikation):** `CTE(X→Y \| Z_alt)` — 62 Tests, separate BH nur zur
Verifikation, dass vor Konditionierung auf `Z_neu` ein behandelbares Signal existiert.

---

## 3. Vorlauf-Gates

### 3.1 Coverage-Gate (vor erstem CTE-Blick)

`scripts/bridge_stufe_a_v3_coverage_gate.py` → `bridge_stufe_a_v3_coverage_gate.json`

| Kandidat | N (Events) | Occupancy | Coverage | Status |
|---|---:|---:|---:|---|
| Chainlink | 12 199 | 7,4 % | 90/90 (1,0) | TESTBAR |
| Intent-Relayers | 746 034 | **98,8 %** | 90/90 (1,0) | TESTBAR |
| Liquidationen | 2 865 | 0,6 % | 76/90 (0,844) | TESTBAR |
| Stablecoin Mint/Burn | 530 194 | **95,5 %** | 90/90 (1,0) | TESTBAR |
| MEV-Cluster | 74 237 occ. min | 57,3 % | 90/90 (1,0) | TESTBAR |

**5/5 testbar**, `untestable_candidates = 0`. FDR-Matrix vollständig: **310 Tests**.

**Integritäts-Hinweis (2026-08-23):** `bridge_stufe_a_v3_coverage_gate.json` am
2026-08-23 12:06 UTC aus dem abgeschlossenen MEV-Capture neu erzeugt — nicht die
Datei zum Auswertungszeitpunkt 2026-08-22. Werte identisch zum Stand der Tabelle
oben. Fixiert in `bridge_manifest.json`; Prüfung:
`python3 scripts/check_bridge_seal.py`.

Gesamt-Eventvolumen über alle Kandidaten-Captures: **≈1,37 Mio.** Zeilen
(inkl. Mehrfach-Events pro Minute; Occupancy-Join per OR). Davon entfallen
**≈1,28 Mio.** (746k + 530k) auf die beiden gesättigten Kandidaten (§5.3);
das **effektiv konditionierende** Volumen liegt bei **≈89k** Events
(Chainlink 12,1k + Liquidationen 2,9k + MEV 74,2k).

**Methodische Lücke (post-hoc, nicht im Gate):** Das Coverage-Gate prüft
Tages-Abdeckung und N≥100, nicht **Informativität** der Konditioniererreihe.
Kandidaten mit Occupancy ≈1 sind definitionsgemäß als binäre Konditionierer
unbrauchbar — ein künftiges Gate auf Varianz/Terzil-Dispersion wäre neben
Coverage nötig (vgl. §5.3).

### 3.2 Pre-CTE Integrity Gate

`scripts/bridge_stufe_a_v3_integrity_gate.py` → `bridge_stufe_a_v3_integrity_gate.json`

**Status: PASS** (2026-08-22 UTC)

- 129 600 Minuten-Raster (90 × 1 440), alle Serien aligned
- Treatment: ETH 6 197 Events / 4,4 % Occupancy; Gnosis 6 258 / 4,4 %
- `Z_alt` Joint-AND-Coverage: **99,8 %** (≥ 80 %-Schwelle)
- Chainlink-Join: OR über Feeds, **USDT/USD Ethereum ausgeschlossen** (Feed-strikt, Pre-Reg §3.0.1)
- MEV: sparse Occupancy-Serie (74 237 unique Minuten, 0 Dup)

---

## 4. Ergebnis — konfirmatorisch

Quelle: `bridge_stufe_a_v3_ergebnis.json` (Seed 20260819, 1000 Surrogate)

| Ebene | BH-signifikant | Interpretation |
|---|---:|---|
| Baseline (`Z_alt` only) | **62 / 62** | Treatment-CTE repliziert (Stufe A: 62/62) |
| Primär (310 Tests, je Kandidat einzeln) | **309 / 310** | Kein Kollaps — Kopplung bleibt fast vollständig |
| Sensitivität (alle `Z_neu` gemeinsam) | **60 / 62** | **Persistency = True** — stärkster Persistenz-Befund |

**Verdict:** `V3_PERSISTENZ` (0 Kollaps-Kandidaten, Sensitivität weiterhin signifikant)

---

## 5. Kollaps-Tabelle (Primärpfad)

Kollaps erfordert **0 / 62** BH-Rejects pro Kandidat (global über 310 korrigiert).

| Kandidat | Sig. Tests | ΔCTE (mittel) | CTE vs. Baseline | Folds Kollaps | Konditionierung |
|---|---:|---:|---:|---:|---|
| Chainlink | 62/62 | −0,00022 | **+24 %** (0/62 identisch) | 3/9 | **wirksam** |
| Intent-Relayers | 62/62 | ≈0 | **0 %** (**62/62 identisch**) | 2/9 | **inert** |
| Liquidationen | 62/62 | −0,00007 | **+7 %** (0/62 identisch) | 2/9 | **wirksam** |
| Stablecoin Mint/Burn | 62/62 | ≈0 | **0 %** (**62/62 identisch**) | 2/9 | **inert** |
| **MEV-Cluster** | **61/62** | −0,00032 | **+31 %** (0/62 identisch) | **1/9** | **wirksam** |

ΔCTE = `CTE_baseline − CTE_konditioniert` (deskriptiv; negatives Vorzeichen bei
positiver relativer Änderung). Relative Änderung = Mittel über alle 62 Lags
gegenüber Baseline (`Z_alt` only).

### 5.3 Gesättigte Occupancy — zwei Kandidaten ohne wirksame Konditionierung

Post-hoc-Vergleich der konditionierten CTE-Schätzer gegen die Baseline zeigt:

| Kandidat | Occupancy | Tertile-Bins (nach `encode_z_neu_tertile`) | CTE-Identität |
|---|---:|---|---|
| Intent-Relayers | 98,8 % | **nur Bin 0** (129 600/129 600) | **62/62 byte-identisch** |
| Stablecoin Mint/Burn | 95,5 % | **nur Bin 0** (129 600/129 600) | **62/62 byte-identisch** |
| Chainlink | 7,4 % | Bins {0, 2} | 0/62 identisch |
| MEV-Cluster | 57,3 % | variabel | 0/62 identisch |
| Liquidationen | 0,6 % | variabel | 0/62 identisch |

**Mechanismus:** Pre-Reg §4.3 verlangt binäre Occupancy (OR-Join) und Tertile für
`Z_neu`. Bei Occupancy ≈96–99 % ist die binäre Reihe praktisch konstant (=1).
Tertile-Kodierung kollabiert auf einen einzigen Bin → die Variable tritt in
`transfer_entropy_binary` nicht informativ auf → Konditionierung ist ein **No-op**.
Die Pipeline reproduziert exakt die Baseline (62/62 identische CTE-Werte).

**Konsequenz für die Interpretation:** Für Intent-Relayers und Stablecoin Mint/Burn
liefert diese Studie **keinen Negativ-Befund** im Sinne von „getestet und
 verworfen", sondern **keinen Test** — die Kandidaten konnten unter der gewählten
Diskretisierung die Kollaps-Hypothese nicht einmal prinzipiell adressieren.
Das Label `V3_PERSISTENZ` bleibt korrekt (kein Kollaps bei 0/62 BH-Rejects), aber
die Evidenzlast für „diese fünf sind es nicht" trägt nur die **drei wirksamen**
Kandidaten.

**Abhilfe (nicht in dieser Pre-Reg):** Gesättigte Binärreihen bräuchten einen
**abgestuften** Konditionierer — Ereigniszahl pro Minute, Intensität oder Terzile
auf der Zählvariable statt auf dem Sättigungs-Indikator. Bei 746k Events auf
129 600 Minuten schwankt die *Anzahl* pro Minute erheblich, auch wenn der
Binär-Indikator fast überall 1 ist.

### 5.4 CTE-Anstieg nach wirksamer Konditionierung (Nebenbefund)

Bei allen **drei wirksamen** Kandidaten **steigt** der CTE-Schätzer gegenüber
der Baseline — entgegen der intuitiven Erwartung, dass ein gemeinsamer Treiber
die Assoziation *dämpft*:

| Kandidat | Relative CTE-Änderung (Mittel, 62 Lags) |
|---|---:|
| Chainlink | +24 % |
| Liquidationen | +7 % |
| MEV-Cluster | +31 % |
| Sensitivität (alle Z_neu) | **+94 % (ab), +67 % (ba)** Summen-CTE |

Das Verhalten ist konsistent mit **Collider-/Suppressor-Effekten** oder
unvollständiger Konditionierung — es ändert **`V3_PERSISTENZ` nicht** (Kollaps
verlangt Signifikanzverlust, nicht Richtung der CTE-Änderung), gehört aber in
die Einordnung, weil ein echter gemeinsamer Treiber typischerweise CTE senkt.

---

### 5.5 Einziger nicht-signifikanter Primär-Test (MEV)

| Kandidat | Richtung | τ (min) | CTÊ | p | BH-Reject |
|---|---|---:|---:|---:|:---:|
| mev_cluster | ab | 20 | 0,000709 | 0,069 | nein |

Ein einzelner Lag in einer Richtung (1/62 ≈ 1,6 %) erfüllt die bidirektionale
Kollaps-Regel nicht. Die niedrigste Fold-Robustheit (1/9) zeigt, dass dieser
partielle Effekt **nicht stabil** ist — **Korrelation ≠ Kollaps** (vgl. §6).

### 5.6 Sensitivität — nicht-signifikante Lags (alle Z_neu)

| Richtung | τ (min) | p | BH-Reject |
|---|---:|---:|:---:|
| ab | 17 | 0,072 | nein |
| ab | 20 | 0,178 | nein |

Selbst bei gleichzeitiger Konditionierung auf **alle fünf** Kandidaten bleiben
**60 von 62** Treatment-Lags FDR-signifikant — der stärkste Persistenz-Befund.
Zwei der fünf Konditionierer sind dabei inert (§5.3); die Sensitivität misst
primär die **drei wirksamen** plus zwei No-ops.

---

## 6. Interpretation (präreg-bindend)

**Verdict unverändert:** `V3_PERSISTENZ` ist unter den eigenen Regeln korrekt —
Kollaps verlangt 0/62 BH-Rejects, das trat bei keinem Kandidaten ein.

### 6.1 Was die Studie belegt (drei wirksame Kandidaten)

1. **Die Kopplung ist real und robust.** Baseline repliziert Stufe A (62/62).
   Nach **wirksamer** Konditionierung auf Chainlink, Liquidationen oder MEV bleibt
   die Kopplung signifikant (61–62/62 je Kandidat; 309/310 global).

2. **Diese drei Kandidaten-Klassen erklären die Kopplung nicht** (Kollaps-Definition).
   Orakel-Updates, seltene Liquidationen und Cross-Chain-MEV-Searcher-Aktivität
   wurden getestet und verworfen — die Kopplung übersteht die Konditionierung.

3. **MEV (61/62):** stärkster partielle Effekt, aber kein Kollaps (τ=20 ab,
   p=0,069; 1/9 Folds). Korrelation ≠ Kollaps.

4. **Sensitivität (60/62):** auch unter gemeinsamer Konditionierung bleibt das
   Signal nahezu vollständig — robustes Persistenz-Signal für die **wirksamen**
   Konditionierer.

5. **CTE-Anstieg** nach wirksamer Konditionierung (+7 % bis +31 %; Sensitivität
   bis +94 % ab) — unerwartet für einen gemeinsamen Treiber; Collider/Suppressor-
   Verdacht (§5.4). Ändert das Verdict nicht.

### 6.2 Was die Studie nicht belegt (zwei inerte Kandidaten)

6. **Intent-Relayers und Stablecoin Mint/Burn wurden nicht effektiv getestet.**
   Occupancy 98,8 % bzw. 95,5 % → Tertile kollabiert → 62/62 byte-identische CTE
   zur Baseline (§5.3). Die Formulierung „diese fünf sind es nicht" gilt für
   **drei** Klassen definitiv; für **zwei** lautet die korrekte Lesart: **nicht
   testbar unter der gewählten Diskretisierung** — nicht „verworfen".

7. **Evidenzgewicht:** ≈1,28 Mio. der ≈1,37 Mio. Events stammen von den inerten
   Kandidaten; effektives Konditionierungsvolumen ≈89k Events.

### 6.3 Gesamt und Serie

8. **`V3_PERSISTENZ` = „diese fünf sind es nicht"** nur eingeschränkt lesbar:
   präziser: **„Kein Kollaps; drei Kandidaten wirksam getestet und verworfen;
   zwei nicht informativ kodiert."** Das ist ein definitives Negativ-Ergebnis
   innerhalb des präregistrierten Rahmens, kein inconclusive-Befund.

9. **OmniBridge-Finalitäts-Hypothese** (Stufe A: τ_ab≈6, τ_ba≈15/16) bleibt
   **konsistent, aber nicht kausal bewiesen.** Stufe B blockiert. Neue Pre-Reg
   für weitere Kandidaten oder abgestufte Konditionierer (Intensität statt
   Sättigungs-Binär) wäre nötig.

---

## 7. Verbindung zur Studien-Serie (A → A v2 → A v3)

| Studie | Verdict | Kernaussage |
|---|---|---|
| **Stufe A** | `UNSPEZIFISCH` | Treatment zeigt bidirektionale Kopplung (62/62 CTE-Hits nach `Z_alt`); Kontrolle ebenfalls mit Restsignal (3/62 CTE) |
| **Stufe A v2** | `V2_UNSPEZIFISCH` | Matched-N (21 Draws): Kontroll-Restsignal ist kein reiner Power-Artefakt (15/21 Draws unspezifisch); saubere Negativkontrolle scheitert |
| **Stufe A v3** | **`V3_PERSISTENZ`** | Kein Kollaps; **3/5 Kandidaten wirksam getestet** (Chainlink, Liquidationen, MEV) und verworfen; 2/5 inert (Intent, Stablecoin) |

**Gesamt-Interpretation:** Die ETH↔Gnosis-Kopplung ist ein **reales, robustes
Phänomen**. **Chainlink, Liquidationen und Cross-Chain-MEV** erklären sie unter
der präregistrierten Konditionierung **nicht**. **Intent-Relayers und Stablecoin
Mint/Burn** sind unter Binär-Occupancy + Tertile **nicht informativ getestet**
worden (§5.3). Die brückenvermittelte Hypothese (OmniBridge, Finalitäts-Lags)
bleibt konsistent, aber **nicht kausal verifiziert**.

Die Serie schließt methodisch ab: A etabliert das Signal, v2 testet Spezifität gegen
Matched-N-Kontrolle, v3 testet mechanistische Erklärungen — alle drei bleiben
versiegelt; v3 liefert das bindende Persistenz-Urteil.

---

## 8. Implikationen

- **Wissenschaftlich:** Residuale Cross-Chain-Kopplung jenseits von Gas/BTC/CEX und
  **drei wirksam getesteten** `Z_neu`-Klassen — offenes Erklärungsproblem.
- **Methodisch:** Coverage-Gate ohne Informativitäts-Gate → gesättigte Occupancy
  erzeugt No-op-Konditionierer (§5.3). **Protokoll-Satz für künftige Pre-Regs:**
  *Ein Gate, das Kandidaten nicht trotz, sondern wegen Sättigung durchwinkt
  (`coverage_ratio = 1.0` als Gütesiegel), belohnt genau die Eigenschaft, die
  sie als binäre Konditionierer wertlos macht — Bestehen und Unbrauchbarkeit
  korrelieren. Neben Abdeckung braucht jede binäre Belegungskodierung ein Gate
  auf Varianz oder Terzil-Dispersion.*
- **OmniBridge:** Plausibelste narrative Erklärung, ohne Stufe B nicht kausal.
- **Operativ:** Studie versiegelt; Erweiterung = neue Pre-Reg (Intensitäts-Kodierung).
- **MEV:** Partieller Lag-Verlust (61/62) ohne Kollaps; hohe Occupancy ≠ Treiber.

---

## 9. Was unverändert bleibt

- Stufe A: Verdict **`UNSPEZIFISCH`**, Dossier `docs/BRIDGE_STUFE_A_ERGEBNIS.md`
- Stufe A v2: Verdict **`V2_UNSPEZIFISCH`**, Dossier `docs/BRIDGE_STUFE_A_V2_ERGEBNIS.md`
- Keine rückwirkende Anpassung von Schwellen, FDR-Familie oder Fenster
- Keine Umdeutung der Lag-Peaks (τ=6 ab, τ=15/16 ba) zu kausaler Bestätigung

---

## 10. Reproduzierbarkeit

```bash
# Coverage (vor CTE)
python3 scripts/bridge_stufe_a_v3_coverage_gate.py

# Pre-CTE Integrity Gate
python3 scripts/bridge_stufe_a_v3_integrity_gate.py

# Konfirmatorische CTE (310 Tests)
python3 scripts/bridge_stufe_a_v3_pipeline.py \
  --integrity-gate bridge_stufe_a_v3_integrity_gate.json \
  --bridge-eth bridge_eth.jsonl \
  --bridge-gnosis bridge_gnosis.jsonl \
  --drivers drivers_90d.jsonl \
  --output bridge_stufe_a_v3_ergebnis.json
```

| Artefakt | Rolle |
|---|---|
| `bridge_stufe_a_v3_coverage_gate.json` | Coverage vor CTE-Blick |
| `bridge_stufe_a_v3_integrity_gate.json` | Alignment / Join / Z_alt-Gate |
| `bridge_stufe_a_v3_ergebnis.json` | Konfirmatorisches Ergebnis (310 + Baseline + Sensitivität) |
| `bridge_stufe_a_v3_{candidate}.jsonl` | Roh-Captures je Kandidat |
| `docs/BRIDGE_STUFE_A_V3_PREREG.md` | Bindende Regeln |
| `bridge_manifest.json` | SHA-256 der 4 JSONL-Captures + 8 Gate/Ergebnis-JSONs |
| `scripts/check_bridge_seal.py` | Verify (Exit 1 bei Abweichung) |

**Determinismus:** Seed `20260819`, gleiche Inputs → reproduzierbare Outputs
(Pre-Reg §2.5). Laufzeit Primärpfad: ~3 h (1000 Surrogate × 129 600 Bins × 310 Tests).

**Siegel:** Gate- und Ergebnis-JSONs unter Git; JSONL-Captures nur per Manifest.
`coverage_gate.json` wurde nach Erstversiegelung neu erzeugt (§3.1) — Ausloeser
fuer `bridge_manifest.json` + `check_bridge_seal.py`.

---

## 11. Abschluss

**Bridge Stufe A v3** ist abgeschlossen mit **`V3_PERSISTENZ`**. Die Studien-Serie
A → A v2 → A v3 ist konfirmatorisch geschlossen und versiegelt. Das Dossier
trennt explizit **Verdict** (präreg-korrekt) von **Evidenztragfähigkeit**
(3/5 Kandidaten wirksam getestet). Weitere Kandidaten oder abgestufte
Konditionierer erfordern eine neue Pre-Registration.
