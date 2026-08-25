# Wave 38 — Live Pre-Registration (Causal Audit & Signal Guard)

**Status:** **bindend** (operative Pre-Reg für Live-Läufe; v1.1 — 2026-08-23, First-Cycle + §7.3 Einschränkungen)  
**Spec:** `docs/WAVE38_DIAGNOSTIC_SPEC.md`  
**Methodik-Referenz (nicht bindend):** `docs/BRIDGE_DIAGNOSTIC_PREREG.md`, `docs/BRIDGE_DIAGNOSTIC_ERGEBNIS.md`  
**Charakter:** Operatives Monitoring — **keine** neue wissenschaftliche Evidenz. Versiegelte Bridge-Serie bleibt read-only.

**Finalisierung 3d-viii:** Diese Pre-Reg ist die methodische Voraussetzung für den ersten `--live`-Lauf (3d-ix). Fixture-Validierung 1→9 ist abgeschlossen (`scripts/test_wave38_diagnostic.py`).

---

## 1. Operative Fragestellung und Verdict-Taxonomie

### 1.1 Was Wave 38 fragt — und was nicht

| | Bridge-Serie (versiegelt) | Wave 38 Live (diese Pre-Reg) |
|--|---------------------------|------------------------------|
| **Frage** | Ist die ETH↔Gnosis-Kopplung auf die fünf `Z_neu`-Kandidaten reduzierbar? | Liefert der Kausalitäts-Auditor ein **verwertbares Live-Signal** für Wave 24 (Trading) und Wave 28 (Defense)? |
| **Charakter** | Wissenschaftliche Falsifikation | Operatives Monitoring / Signalfreigabe |
| **Evidenz** | Erzeugt versiegelte Dossiers (`DIAG_SIGNAL_VALID` / `V3_PERSISTENZ`) | **Erzeugt keine neue wissenschaftliche Evidenz** |
| **Artefakte** | `bridge_*_ergebnis.json` — read-only | Neue Captures unter `{data_root}/{user_id}/wave38/live/` |

Die Bridge-Serie ist mit `DIAG_SIGNAL_VALID` / `V3_PERSISTENZ` wissenschaftlich abgeschlossen und **versiegelt**. Wave 38 **wendet** diese Methodik an; sie **wiederholt** die Studie nicht und **reinterpreted** keine Bridge-JSONs als Live-Verdict.

**Operative Frage (bindend):**  
> Liefern Live-Captures der fünf `Z_neu`-Klassen ein kausal interpretierbares Konditionierer-Signal `S(τ)`, das der Gatekeeper an den Hauptschwarm freigeben darf (`RELEASED`), oder sind sie Filter-Artefakte / No-op-Konditionierer (`BLOCKED`)?

### 1.2 Verdict-Taxonomie

| Verdict | Bedeutung | Gatekeeper |
|---------|-----------|------------|
| `DIAG_SIGNAL_VALID` | Permutation bestanden, Lag-Spearman stabil, keine Grauzone | `RELEASED` |
| `DIAG_FILTER_ARTIFACT` | Permutation fail | `BLOCKED`, `cause=FILTER_ARTIFACT` |
| `DIAG_INCONCLUSIVE` | `unclassified > 0` **oder** Resampling instabil | `BLOCKED`, `cause=INCONCLUSIVE` |

`BLOCKED` erfordert immer `cause` ∈ {`FILTER_ARTIFACT`, `INERT_ENCODING`, `FDR_FAIL`, `INCONCLUSIVE`}.

---

## 2. Kandidaten-Set (Live)

| ID | Klasse | Chains | Capture-Agent |
|----|--------|--------|---------------|
| `chainlink` | Oracle (AnswerUpdated) | ethereum, gnosis | Agent 2 |
| `mev_cluster` | Cross-Chain-EOA-Minute | ethereum, gnosis | Agent 3 |
| `liquidations` | Aave v3 / Spark LiquidationCall | ethereum, gnosis | Agent 4 |
| `intent_relayers` | Across + CoW Trade | ethereum (+ gnosis CoW) | Agent 5 (Familie Intent) |
| `stablecoin_mint_burn` | LitePSM / Classic PSM / CCTP V1+V2 | ethereum | Agent 5 (Familie Stablecoin) |

**Exclusions (hard block, dokumentiert):**

| Bereich | Exclusion |
|---------|-----------|
| Oracle | USDT/USD auf Ethereum; GNO/ETH (beide Chains) |
| MEV | 63 Bridge/Relayer/Protokoll-Adressen (`config/wave38_mev_exclusion_list.json` → Bridge-V3-Liste) |
| Intent | Across nur Ethereum (kein Gnosis-SpokePool) |
| Stablecoin | Gnosis-PSM; Gnosis-CCTP; FiatToken-Pfade außerhalb Resolver |
| Allgemein | LayerZero als Intent-Kandidat (nicht im Set) |

Adressen kommen ausschließlich aus Resolver-Outputs (`bridge_stufe_a_v3_*_resolved.json` als Address-Book-Referenz) bzw. Wave-38-Configs — nicht hardcodiert in Scannern.

---

## 3. Schwellen (bindend — explizit Wave 38)

| Konstante | Wert | Anmerkung |
|-----------|-----:|-----------|
| `EPS_INERT` | 0.001 | Relative LOO-Änderung unterhalb → inert |
| `TAU_CLEANSING` | 0.05 | LOO ≥ Schwelle → cleansing_candidate |
| `RHO_COLLAPSE` | 0.50 | Perm-Kollaps für cleansing_worker |
| `OCC_SAT` | 0.90 | Occupancy-Sättigung → perm nicht testbar |
| `ALPHA_PERM` | 0.05 | Permutations-α |
| `FDR_Q` | 0.05 | Benjamini-Hochberg |
| `P_SIGN_MIN` | 0.95 | **Deskriptiv only** — nicht verdict-tragend (TE ≥ 0) |
| `RHO_SPEARMAN_MIN` | 0.90 | Lag-Profil-Stabilität: min ρ über Folds×Richtungen |
| `K_FOLDS` | 9 | Disjunkte Zeitblöcke |
| `N_UNSTABLE_FOLDS_MAX` | 1 | Max. instabile Folds für `KFOLD_STABLE` |
| `TAU_FN` | 0.10 | Ex-Post FN-model |
| `TAU_FP` | 0.15 | Ex-Post FP-infra |
| `N_PERM_SHIFTS` | 100 | Zirkuläre Shifts je Kandidat |
| `SEED_DEFAULT` | 20260822 | Reproduzierbarkeit Live-Pipeline |

Diese Werte sind **explizit für Wave 38 Live** registriert. Bridge-Pre-Reg-Schwellen sind methodische Referenz, **nicht** operative Bindung. Änderung nach erstem `--live`-Lauf erfordert eine **neue** Pre-Reg-Version (kein stilles Nachjustieren).

---

## 4. Informativitäts-Gate

Neben Coverage gilt für **jede binäre Occupancy-Kodierung** der V3-§8-Protokoll-Satz:

> Ein Gate, das Kandidaten nicht trotz, sondern wegen Sättigung durchwinkt, belohnt die Eigenschaft, die sie als Konditionierer wertlos macht. Neben Abdeckung braucht jede binäre Belegungskodierung ein Gate auf Varianz oder Terzil-Dispersion.

| Kriterium | Schwelle |
|-----------|----------|
| Coverage (Tag) | chainlink ≥ 0.80; intent/stablecoin ≥ 0.60; liquidations ≥ 0.40; mev ≥ 0.70 |
| Events | `N ≥ 100` (Fixture-Softening nur in Unit-Tests, nicht `--live`) |
| Mindest-Terzil-Bins | 2 distinct bins in {0,1,2} |
| `INERT_ENCODING` | Occupancy ≥ `OCC_SAT` **oder** Terzil kollabiert |

`INERT_ENCODING` → Gatekeeper `BLOCKED` mit `cause=INERT_ENCODING` (kein RELEASED trotz Perm-Pass).

---

## 5. Capture-Fenster und Datenquellen

| Parameter | Wert |
|-----------|------|
| Bridge-Fenster (versiegelt) | 2026-05-20T00:00:00Z – 2026-08-17T23:59:59Z — **kein** Live-Rechen-Input |
| Live-Fenster | Rolling **90 Tage UTC**, Minuten-Raster (`t // 60`) |
| Erstes `--live`-Fenster | Bei Start von 3d-ix einfrieren: `[T0−90d, T0]` in UTC; Start/Ende + Seed in GoBD-Report schreiben |
| Verbot | Erstes Live-Fenster **darf nicht** mit dem Bridge-Fenster byte-identisch als alleinige Datenquelle genutzt werden |
| Live-Pfad | `{data_root}/{user_id}/wave38/live/` |
| Referenz-Pfad | Versiegelte Bridge-JSONs im Projektroot — **read-only** (`reference_guard.py`) |

### 5A. Amendment A1 — Resampling: Lag-Spearman (bindend)

#### 5A.1 Begründung

In Bridge Diagnostic war `P_sign ≡ 1,0` strukturell garantiert (TE ≥ 0). Vorzeichen-Invarianz ist **nicht diskriminativ**. Wave 38 ersetzt den verdict-tragenden Resampling-Arm durch **Lag-Spearman** (Rang-Korrelation der Lag-Profil-Form). `P_sign` bleibt deskriptive Telemetrie.

#### 5A.2 Definition

```
ρ_{k,d} = Spearman( CTE_k(τ) , CTE_full(τ) )   über τ ∈ LAGS_MIN
fold_k stable  ⇔  min(ρ_{k,ab}, ρ_{k,ba}) ≥ RHO_SPEARMAN_MIN
n_unstable = #{k : fold_k nicht stable}
resampling_fragment =
    KFOLD_STABLE    falls n_unstable ≤ N_UNSTABLE_FOLDS_MAX
    KFOLD_UNSTABLE  sonst
```

Konstante Reihe → `ρ := 0` (konservativ instabil). Peak-Lag nur deskriptiv.

#### 5A.3 Fold-Geometrie

| Modus | Geometrie |
|-------|-----------|
| Live (90d) | `K_FOLDS=9` × 10 Tage × 1440 min |
| Fixture / verkürzt | `K_FOLDS` gleich große Blöcke über `n_bins` |

---

## 6. Verdict-Mapping (Priorität)

1. `n_unclassified > 0` → `DIAG_INCONCLUSIVE`
2. `perm_fragment == PERM_FAIL` → `DIAG_FILTER_ARTIFACT`
3. `resampling_fragment == KFOLD_UNSTABLE` → `DIAG_INCONCLUSIVE`
4. `perm_fragment == PERM_PASS` ∧ `resampling_fragment == KFOLD_STABLE` → `DIAG_SIGNAL_VALID`
5. sonst → `DIAG_INCONCLUSIVE`

`P_sign` ist **deskriptiv**. `Lag-Spearman` / `resampling_fragment` ist **verdict-tragend** (Amendment A1).

---

## 7. Lauf-Disziplin (inkl. Agent-X-Konventionen)

### 7.1 Methodische Regeln

| Regel | Enforcement |
|-------|-------------|
| Kein `--live` ohne diese Pre-Reg **bindend** | `GatekeeperDispatcherAgent` + `load_wave38_thresholds()` (`LivePreRegNotBoundError`) |
| Keine Schwellenänderung nach erstem Live-Lauf ohne neue Pre-Reg | GoBD JSONL Audit + neue Pre-Reg-Version |
| Bridge-Artefakte read-only | `reference_guard.py` Hash + Write-Block |
| Code-Reuse aus Bridge-Skripten erlaubt | Daten-Reuse auf versiegelte Bridge-JSONs **verboten** |
| Agents 2–5 = SQLite-Konsumenten von Agent 1 | Kein zweiter unabhängiger RPC-Capture-Client |

### 7.2 Vier Agent-X-B2G-Konventionen (bindend)

Analog zu Waves 6 / 15 / 27 / 31 — für Wave 38 Live verpflichtend:

| # | Konvention | Anforderung |
|---|------------|-------------|
| 1 | **Multi-Tenancy** | Alle Live-Artefakte ausschließlich unter `{data_root}/{user_id}/wave38/live/` (Unterordner `oracle/`, `mev/`, `liquidations/`, `intent_stablecoin/`, Reports). Kein Schreiben außerhalb dieses Baums. |
| 2 | **GoBD-WORM** | Jeder `--live`-Lauf erzeugt einen GoBD-konformen Report (Hash-Kette, WORM-Archivierung) unter `wave38/live/reports/`. Agent 9 / Report-Composer archiviert Envelope + Pipeline-Meta. |
| 3 | **Standard-JSON-Envelope** | Externer Ausgang ist `DiagnosticSignalEnvelope`, eingebettet in Agent-X-Standardantwort `{"status","job_id","artifacts","error","logs"}`, damit Wave 24 / 21 / 28 konsumieren können. |
| 4 | **EventBus-Audit-Trail** | Jede Verdict-Entscheidung (`RELEASED`/`BLOCKED` + `cause`) wird über den EventBus publiziert und im JSONL-Audit-Log fortgeschrieben (Pub/Sub-Muster des Gesamtsystems). |

### 7.3 Bekannte operative Einschränkungen (First-Cycle 3d-ix → bindend für Folgeläufe)

Dokumentierte Eingriffe während des ersten `--live`-Laufs — keine stillen Korrekturen; ab v1.1 festgehalten, damit sie nicht erneut ad hoc auftreten:

| # | Einschränkung | Regel |
|---|---------------|-------|
| A | **getLogs Target-Scoping** | Nur adressierte Contracts mit explizitem Topic0 (OmniBridge, aktuelle Chainlink-Aggregator, Liquidation-Pools, Intent/Stablecoin-Resolver). **Verboten:** `eth_getLogs` ohne Topic-Filter (z. B. Uniswap-UR „alle Events“) — unbegrenztes Volumen, Capture-Abbruch. |
| A2 | **getLogs RPC-Fallback** | Ethereum: bei gesetztem `ETHERSCAN_API_KEY` zuerst Etherscan v2 `getLogs` (Bridge-Capture-Reuse); sonst öffentliche Fallback-Liste. OR-Topic0 → Einzel-Topic-Calls. Gnosis: öffentliche RPCs. |
| B | **Address-Book-Frische / Plausibilität** | Bridge-Resolver-JSONs sind Address-Books, keine Live-Preisquellen. `latest_answer_usd` kann veraltet sein. Live: `soft_plausibility=True` (Warnung, kein Hard-Fail); Hard-Fail nur nach frischem On-Chain-`latestRoundData`. |
| C | **First-Cycle Tail** | Lauf `live-first` analysierte Tail **3d** innerhalb des eingefrorenen 90d-Fensters (`capture_tail_days=3`). `KFOLD_UNSTABLE` / ρ_min≈0,02 ist unter dünnen Folds erwartbar. Full-90d (`capture_tail_days=0`) ist keine Pre-Reg-Änderung, sondern dichtere Datengrundlage im **selben** eingefrorenen Fenster. |
| D | **MEV-Subsample** | Full-Block-Receipt-Scan über 90d ist RPC-begrenzt; Live erlaubt Stride + `mev_max_blocks` mit ehrlicher Telemetrie. Dünne MEV-Occupancy → eher inert / Informativitäts-Druck, kein stilles Auffüllen. |

### 7.4 First-Cycle Ergebnis (operativ, 2026-08-22)

| Feld | Wert |
|------|------|
| Job | `live-first` |
| Verdict | `DIAG_INCONCLUSIVE` |
| Gate | `BLOCKED` / `cause=INCONCLUSIVE` |
| Fragmente | `PERM_PASS` ∧ `KFOLD_UNSTABLE` (ρ_min≈0,02 ≪ 0,90) |
| Lesart | Signal real (kein Phantom-Filter), aber Lag-Topologie nicht handelbar |
| Markierung | `OPERATIONAL_SIGNAL_ONLY` — Bridge-Serie unberührt |

---

## 8. Checkliste vor erstem `--live` (3d-ix)

- [x] §1–§7 bindend (operative Frage + Agent-X-Konventionen)
- [x] Amendment A1 (Lag-Spearman) in dieser Pre-Reg
- [x] Agents 1–5 Capture auf Fixture grün
- [x] E2E 1→6 Fixture (Datenfluss, Format, Guard, Determinismus)
- [x] E2E 1→9 Fixture (Lag-Spearman, Verdict, Envelope, Guard)
- [x] Erstes Live-Fenster `[T0−90d, T0]` einfrieren und dokumentieren
- [x] Live-Captures unter `wave38/live/` (Agents 1–5, `--live`; First-Cycle: Tail 3d innerhalb des eingefrorenen Fensters)
- [x] Informativitäts-Gate / Analyse 6→9 auf Live-Bundle
- [x] GoBD-WORM-Report + EventBus-Publikation
- [x] Envelope `RELEASED` oder ehrliches `BLOCKED` mit `cause` — First-Cycle: `BLOCKED` / `INCONCLUSIVE` (`KFOLD_UNSTABLE`, operatives Signal)

**Nach 3d-ix (separat, nicht Teil dieser Pre-Reg):** Aufnahme von Wave 38 in die Wellen-Übersicht / Test-Resultate des Agent-X-Referenzdokuments (`CLAUDE.md`) — analog Wave 27/28 — **nach** Full-90d-Capture im eingefrorenen Fenster (empfohlene Reihenfolge).

---

## 9. Versionsnotiz

| Version | Datum | Inhalt |
|---------|-------|--------|
| 0.1 Stub | 2026-08-22 | Erste bindende Fassung + Amendment A1 |
| 1.0 Final | 2026-08-22 | §1 operative vs. wissenschaftliche Frage; §7 Agent-X-Konventionen; Checklist nach E2E 1→9; Freigabe-Pfad für 3d-ix |
| **1.1** | **2026-08-23** | §7.3 bekannte Einschränkungen (getLogs-Scoping, Address-Book-Frische, Tail/MEV); §7.4 First-Cycle `BLOCKED`/`INCONCLUSIVE`; Full-90d als nächster Capture-Schritt |
