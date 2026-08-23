# Bridge Filter-Diagnose (Wave 38) — Ergebnis-Dossier

**Status:** Abgeschlossen — `final_verdict = DIAG_SIGNAL_VALID` (definitiv)
**Auswertung:** 2026-08-22 UTC · Seed `20260822`
**Pre-Registration:** `docs/BRIDGE_DIAGNOSTIC_PREREG.md` (bindend, 2026-08-22)
**Leserhinweise:** `docs/BRIDGE_DIAGNOSTIC_LESERHINWEISE.md` (interpretativ, nicht bindend)
**Vorlauf:** `docs/BRIDGE_STUFE_A_V3_ERGEBNIS.md` (`V3_PERSISTENZ`, versiegelt, read-only)
**Charakter:** Konfirmatorische Diagnose. Stufen A, A v2, A v3 bleiben unverändert.

---

## 1. Verdict

**`DIAG_SIGNAL_VALID`** — `PERM_PASS`, `KFOLD_STABLE`, `n_unclassified = 0`,
`perm_fail_candidates = []`.

### 1.1 Reichweiten-Vorbehalt (gehört neben das Verdict, nicht in eine Fußnote)

Das Verdict ruht auf **einem** diskriminierenden Kriterium, nicht auf drei:

| Arm | Beitrag zum Verdict |
|-----|---------------------|
| Permutation | **trägt** — einziger Arm, der `DIAG_FILTER_ARTIFACT` auslösen kann |
| K-Fold (§3.3) | **trägt nicht** — `P_sign` nicht-diskriminativ (§5) |
| §6.1, zweiter Disjunkt | **trägt nicht** — logisch leere Menge (§5.2) |

`DIAG_SIGNAL_VALID` bedeutet daher: *ein Permutationstest über drei testbare
Arme wurde bestanden* — nicht *drei unabhängige Prüfungen bestanden*.

Es bedeutet ausdrücklich **nicht**, dass die ETH↔Gnosis-Kopplung kausal bewiesen
ist. Die Bridge-Permutation (`bridge_eth` gegen `bridge_gnosis`) war
präregistriert als deskriptiv und **nicht verdict-tragend**. Die Frage, ob die
Kopplung selbst ein Artefakt des Schätzers, des Minuten-Rasters oder der
Occupancy-Autokorrelation ist, wird von dieser Studie nicht beantwortet.

---

## 2. Registrierte Vorhersage — auf zwei Ebenen bestätigt

Die Vorhersage aus Pre-Reg §1.2 wurde vor dem Datenblick aus V3 §5.3 abgeleitet.

| Vorhersage | Ergebnis |
|------------|----------|
| Intent-Relayers + Stablecoin Mint/Burn → `inert` | **bestätigt**, auf zwei unabhängigen Ebenen |
| Chainlink, Liquidationen, MEV → nicht `inert` | **bestätigt** (alle `cleansing_worker`) |
| Phase 1 → `DIAG_IN_SILICO_PASS` | **bestätigt** |
| Gesamt → `DIAG_SIGNAL_VALID` | **bestätigt** |

Zwei Ebenen für die beiden inerten Kandidaten:

1. **Encoding-Gate** (vor jedem CTE-Blick): `INERT_ENCODING`, Terzil kollabiert
   auf einen Bin bei Occupancy 98,8 % bzw. 95,5 %.
2. **LOO** (nach dem Lauf): `rel_loo_max = 0,0000`, `byte_identical_to_ref = true`.

Eine Vorhersage, die auf zwei methodisch getrennten Ebenen eintrifft, ist eine
starke Validierung — allerdings mit einer Einschränkung, die genannt gehört:
Für die beiden gesättigten Kandidaten war sie **nicht riskant**. Dass eine
praktisch konstante Reihe sich als No-op verhält, folgt aus ihrer Kodierung.
Riskant war die Vorhersage für die drei informativen Arme und für `PERM_PASS`.

---

## 3. Ablation (Leave-one-out) — primäre Evidenz

Referenz: `drivers_full = Z_alt_ter + [Z_neu_ter_1..5]`
`S_ref = { ab: 0,047058 · ba: 0,063024 }`

| Kandidat | `rel_loo_max` | `S_loo` ab | `S_loo` ba | byte-identisch | Rolle |
|----------|--------------:|-----------:|-----------:|:--------------:|-------|
| chainlink | 0,2417 | 0,035686 | 0,051061 | nein | `cleansing_worker` |
| mev_cluster | 0,2852 | 0,033635 | 0,047414 | nein | `cleansing_worker` |
| liquidations | 0,0578 | 0,044338 | 0,059771 | nein | `cleansing_worker` |
| intent_relayers | 0,0000 | 0,047058 | 0,063024 | **ja** | `inert` |
| stablecoin_mint_burn | 0,0000 | 0,047058 | 0,063024 | **ja** | `inert` |

`n_unclassified = 0` — kein Kandidat fiel in die Grauzone zwischen
`ε_inert` (0,001) und `τ_cleansing` (0,05).

### 3.1 Dokumentierter Beinahe-Ausfall

Die Leserhinweise hatten den Transfer der Schwelle `τ_cleansing = 0,05` von
Add-one- auf LOO-Größen als Risiko markiert: LOO-Differenzen fallen bei
Redundanz zwischen Konditionierern systematisch kleiner aus, und Liquidationen
war mit +7,2 % Add-one der Kandidat mit dem kürzesten Weg unter die Marke.

**Beobachtet: `rel_loo = 0,0578`** — 0,78 Prozentpunkte über der Schwelle.
Wäre der Wert darunter gelegen, hätte `unclassified > 0` das Verdict nach §6.2
auf `DIAG_INCONCLUSIVE` gezogen. Die Interpretierbarkeit dieser Studie hing an
weniger als einem Prozentpunkt. Das ist kein Mangel des Laufs, aber ein Argument,
Schwellen künftig aus der Rechenart abzuleiten, in der sie angewandt werden.

---

## 4. Permutation — der verdict-tragende Arm

100 zirkuläre Minuten-Shifts je Target, `α_perm = 0,05`, `ε_inert = 0,001`.

| Kandidat | Occupancy | testbar | `p_perm` | `perm_collapse` | neutral |
|----------|----------:|:-------:|---------:|----------------:|:-------:|
| chainlink | 0,0741 | ja | 0,98 | 0,9224 | ja |
| liquidations | 0,0058 | ja | 0,99 | 0,5759 | ja |
| mev_cluster | 0,5728 | ja | 0,99 | 0,9184 | ja |
| intent_relayers | 0,9877 | nein | 0,00 | 0,0000 | ja (Sättigung) |
| stablecoin_mint_burn | 0,9553 | nein | 0,00 | 0,0000 | ja (Sättigung) |

`perm_fail_candidates = []` → **`PERM_PASS`**.

Die drei testbaren Arme reagieren in 98–99 von 100 Shifts auf die Zerstörung der
Zeitstruktur. Ihr LOO-Effekt bricht dabei um 57,6–92,2 % ein. Die von ihnen
getragene Bereinigung hängt also an der **zeitlichen Struktur**, nicht an der
Randverteilung — das ist die Definition von *kein Phantom-Filter*.

Die beiden gesättigten Kandidaten sind nach §3.2 explizit `PASS`, nicht `FAIL`
(`perm_testable = false`). Ihr `p_perm = 0,00` ist kein Befund, sondern die
arithmetische Folge einer konstanten Reihe.

**Liquidationen** ist der aufschlussreichste Arm: mit 0,58 % die mit Abstand
niedrigste Occupancy, dennoch `p_perm = 0,99` und ein LOO-Effekt über der
Schwelle. Ein sehr dünner, aber informativer Konditionierer — das Gegenstück zu
den beiden gesättigten, die dicht und uninformativ sind. Occupancy und
Informationsgehalt sind nachweislich unabhängige Eigenschaften.

---

## 5. K-Fold — deskriptiv, nicht-diskriminativ

`K = 9`, `FOLD_DAYS = 10`. Ergebnis: `n_unstable_folds = 0`, `KFOLD_STABLE`.

**Dieser Arm konnte nicht fehlschlagen.** Über alle 9 Folds und beide Richtungen
existiert genau ein Wertepaar: `(P_sign_ab, P_sign_ba) = (1,0 · 1,0)`.

Ursache: `P_sign` vergleicht das **Vorzeichen** von `CTE_k(τ)` mit
`CTE_full(τ)`. Transferentropie ist eine KL-Divergenz und damit nicht-negativ.
Nachgezählt über alle 434 CTE-Werte des versiegelten V3-Ergebnisses:

```
n = 434   min = 5,051e-04   max = 2,734e-03   negativ: 0   exakt null: 0
```

`sign(CTE)` ist konstant `+1`, `P_sign` folglich immer `1,0`. Die daran
hängende Lokalisierungs-Attribution (`MARKET_EVENT`, `RPC_DATA_LOSS`,
`UNEXPLAINED_LOCAL`) wurde nie erreicht. `bridge_diagnostic_kfold.json` führt
den Vermerk *„Descriptive only — P_sign non-discriminative"* selbst mit.

### 5.1 Empfehlung für eine Folge-Pre-Reg

Für eine streng positive Größe ist Vorzeichen-Invarianz kein Stabilitätsmaß.
Brauchbar wären die **Form des Lag-Profils** — Spearman von `CTE_k(τ)` gegen
`CTE_full(τ)` — oder der **Erhalt des Peak-Lags**, was direkt an die
Asymmetrie `τ_ab ≈ 6` / `τ_ba ≈ 15,16` aus Stufe A anschließt. Die fold-weise
Kollaps-Statistik aus V3 (3/9, 2/9, 1/9) zeigt, dass die Maschinerie dafür
vorhanden ist.

### 5.2 Leerer Disjunkt in §6.1

`DIAG_FILTER_ARTIFACT` war definiert als `PERM_FAIL` **oder**
*„∃ `cleansing_worker` mit `perm_collapse ≤ ρ_collapse`"*. §3.1 definiert
`cleansing_worker` jedoch über `perm_collapse > ρ_collapse`. Die zweite
Bedingung beschreibt eine leere Menge; `DIAG_FILTER_ARTIFACT` reduziert sich
auf `PERM_FAIL`. Ohne Wirkung auf dieses Ergebnis (`PERM_PASS`), aber für die
nächste Fassung zu bereinigen.

---

## 6. Der zentrale Befund: Kandidaten tragen, statt zu erklären

### 6.1 Was beide Analysen übereinstimmend zeigen

| Analyse | Operation | Wirkung auf CTE |
|---------|-----------|-----------------|
| V3 Add-one | Kandidat zu `Z_alt` **hinzufügen** | CTE **steigt** (+7 % … +32 %) |
| Diagnostic LOO | Kandidat aus Vollunion **entfernen** | CTE **sinkt** (−5,8 % … −28,5 %) |

Diese beiden Aussagen sind **nicht** entgegengesetzt — sie sind dieselbe
Aussage, zweimal gemessen: Die Anwesenheit eines Kandidaten in der
Konditionierungsmenge **erhöht** den geschätzten Informationsfluss.

Bemerkenswert ist die Übereinstimmung der Beträge: Chainlink +23,7 % / −24,2 %,
MEV +31,8 % / −28,5 %, Liquidationen +7,2 % / −5,8 %. Zwei methodisch getrennte
Wege — Add-one gegen `Z_alt`, LOO aus der Fünferunion — liefern nahezu
spiegelbildliche Beträge. Das spricht für einen weitgehend additiven Beitrag
mit geringer Redundanz zwischen den Kandidaten.

### 6.2 Was das ausschließt

Ein **Erklärer** der Kopplung müsste sich umgekehrt verhalten: Hinzufügen würde
den Informationsfluss absorbieren und die CTE senken; Entfernen würde ihn
zurückgeben und sie erhöhen. Genau dieses Muster tritt bei keinem der fünf
Kandidaten auf — weder einzeln (V3) noch aus der Vollunion heraus (Diagnostic).

Das Verhalten ist konsistent mit **Collider- oder Redundanz-Struktur**: Die
Kandidaten sind mit der Kopplung verschränkt, ohne ihre Ursache zu sein. Sie
sind Teil des Informationsgeflechts, das die Kopplung trägt — nicht ihr Ursprung.

### 6.3 Grenze dieser Aussage

Sie gilt für die **drei wirksam getesteten** Kandidaten. Für Intent-Relayers und
Stablecoin Mint/Burn liefert auch dieser Lauf keinen Befund, sondern die
Bestätigung, dass sie unter binärer Occupancy + Terzil nicht testbar sind
(V3 §5.3, hier §2 und §3).

---

## 7. Verbindung zur Serie

| Studie | Verdict | Kernaussage |
|--------|---------|-------------|
| Stufe A | `UNSPEZIFISCH` | Kopplung im Treatment (62/62); Kontrolle nicht sauber |
| Stufe A v2 | `V2_UNSPEZIFISCH` | Kontroll-Restsignal ist kein Power-Artefakt (15/21 Draws) |
| Stufe A v3 | `V3_PERSISTENZ` | Kein Kollaps; 3/5 wirksam getestet und verworfen, 2/5 inert |
| **Diagnose** | **`DIAG_SIGNAL_VALID`** | Kandidaten sind keine Phantom-Filter — und keine Erklärer |

Die Serie konvergiert: Die ETH↔Gnosis-Kopplung ist real, robust und nicht auf
die fünf getesteten Kandidatenklassen reduzierbar — weder individuell noch
kollektiv. Die OmniBridge-Finalitätshypothese (`τ_ab ≈ 6`, `τ_ba ≈ 15/16`)
bleibt mit den deskriptiven Peak-Lags vereinbar, ist aber nicht kausal bewiesen.

---

## 8. Was etabliert ist — und was nicht

**Etabliert**

- Die drei informativen Kandidaten sind keine Phantom-Filter: ihr
  Bereinigungseffekt bricht unter Zerstörung der Zeitstruktur um 57–92 % ein.
- Keiner der fünf Kandidaten erklärt die Kopplung; drei tragen messbar zu ihr bei.
- Die präregistrierte Vorhersage traf auf Encoding- und LOO-Ebene ein.
- Occupancy und Informationsgehalt sind unabhängig (Liquidationen 0,58 % / `p_perm` 0,99
  gegen Intent-Relayers 98,8 % / No-op).

**Nicht etabliert**

- Kausalität der ETH↔Gnosis-Kopplung. Die Bridge-Permutation war deskriptiv.
- Ausschluss eines Schätzer- oder Rasterartefakts als Ursache der Kopplung.
- Aussagen über Intent-Relayers und Stablecoin Mint/Burn (unverändert nicht testbar).
- Stabilität über Zeitabschnitte — der K-Fold-Arm hat dazu nichts beigetragen (§5).

---

## 9. Artefakte und Reproduzierbarkeit

```bash
python3 scripts/bridge_diagnostic_pipeline.py --skip-ex-post
```

| Artefakt | Rolle |
|----------|-------|
| `bridge_diagnostic_informativity_gate.json` | Terzil-Dispersion, Occupancy, `INERT_ENCODING` |
| `bridge_diagnostic_ablation.json` | LOO je Kandidat, Rollen-Klassifikation |
| `bridge_diagnostic_permutation.json` | 100 Shifts je Target, `PERM_PASS` |
| `bridge_diagnostic_kfold.json` | 9 Folds, deskriptiv (§5) |
| `bridge_diagnostic_ergebnis.json` | Aggregat, `final_verdict` |
| `bridge_stufe_a_v3_ergebnis.json` | V3-Deskriptiva, read-only eingebettet |
| `bridge_stufe_a_v3_coverage_gate.json` | V3-Vorlauf (Upstream; siehe Hinweis unten) |
| `bridge_manifest.json` | SHA-256 aller 12 Siegel-Artefakte (4 JSONL + 8 JSON) |
| `scripts/check_bridge_seal.py` | Verify (Exit 1 bei Abweichung) |

**Integritäts-Hinweis (2026-08-23):** `coverage_gate.json` nach Erstversiegelung
neu erzeugt (V3 §3.1). Alle Gate-/Ergebnis-JSONs und JSONL-Captures sind in
`bridge_manifest.json` fixiert; der 08-22-Stand der Coverage-Datei selbst ist
ohne Git-Historie nicht rekonstruierbar.

Seed `20260822` · 1000 Surrogate · 100 Permutations-Shifts ·
Phase 2 (Ex-Post) übersprungen (`--skip-ex-post`) → Verdict nach §6.4.
Gleiche Inputs und gleicher Seed ergeben byte-identische Outputs.

---

## 10. Abschluss

Die Bridge-Diagnose ist abgeschlossen und versiegelt. Sie bestätigt die
V3-Persistenz über einen zweiten methodischen Zugang und schließt Phantom-Bereinigung für
die drei testbaren Kandidaten aus. Ihre Reichweite ist durch einen einzigen
diskriminierenden Arm begrenzt (§1.1); zwei weitere Arme waren strukturell
nicht in der Lage zu widersprechen. Eine Folge-Studie mit abgestufter
Konditionierung (Ereignisse/Minute statt Sättigungs-Indikator), einem
verdict-tragenden Bridge-Permutationstest und einem Stabilitätsmaß auf dem
Lag-Profil erfordert eine neue Pre-Registration.
