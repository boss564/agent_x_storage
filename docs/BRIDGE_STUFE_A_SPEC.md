# Stufe A — Bridge-Kreuz-Anregung: Implementierungs-Spezifikation

**Status:** Spec fixiert nach Parameter-Bestätigung (2026-08-17)
**Pre-Reg:** `docs/BRIDGE_STUFE_A_PREREG.md`
**Lock-in-Code:** `scripts/bridge_stufe_a_config.py`, `scripts/bridge_stufe_a_stats.py`,
`scripts/bridge_stufe_a_capture.py`, `scripts/bridge_stufe_a_drivers.py`,
`scripts/bridge_stufe_a_pipeline.py`
**Tests:** `scripts/test_bridge_stufe_a.py`

Keine Analyse starten, bevor Capture-Manifest die eingefrorenen Adressen,
das Fenster und die topic0-Hashes byte-gleich zur Config schreibt.

---

## 0. Bestätigungen (eingeflossen)

| # | Entscheidung | Spec-Konsequenz |
|---|---|---|
| 1 | Kontroll-Chain = Arbitrum One | RPC + Universal-Router-Liste chainId 42161 |
| 2 | OmniBridge = Mediator, nicht AMB/xDAI | nur die zwei Mediator-Adressen + zwei topic0 |
| 3 | Keine Value-Schwelle | Logs/txs ungefiltert nach `value` |
| 4 | 90 Tage kalendarisch | `WINDOW_START_UTC` / `WINDOW_END_UTC` in der Config |
| 5 | Lag 0–30 min, 1 min | `LAGS_MIN = range(0, 31)` → 31 × … = 248 Tests |

---

## 1. Artefakte (geplant)

| Schritt | Skript | Output (gitignored) |
|---|---|---|
| 1 Event-Capture | `scripts/bridge_stufe_a_capture.py` | `bridge_eth.jsonl`, `bridge_gnosis.jsonl`, `uniswap_eth.jsonl`, `uniswap_arb.jsonl` + `.manifest.json` |
| 2 Treiber-Capture | `scripts/bridge_stufe_a_drivers.py` | `drivers_90d.jsonl` + `.manifest.json` |
| 3 Auswertung | `scripts/bridge_stufe_a_pipeline.py` | `bridge_stufe_a_ergebnis.json` |
| 4 Dossier | manuell gegen Pre-Reg | `docs/BRIDGE_STUFE_A_ERGEBNIS.md` |

Capture: OmniBridge via `eth_getLogs` (eingefrorene topic0). Uniswap-Kontrolle via
Etherscan `txlist` (`tx.to`), Fallback `eth_getLogs` aller Logs der eingefrorenen
Universal-Router-Adressen (ein Event je `txHash`). **Kein** Uniswap-V2-`Swap`-Topic
auf dem Router — der Universal Router emittiert das Event nicht.

`--chain ethereum` allein ist mehrdeutig (Treatment vs. Kontrolle) und wird
abgelehnt; `--stream treat_eth|ctrl_eth` oder `--source omnibridge|uniswap`.

Smoke (`--smoke`, letzte 200 Blöcke) ist **nicht** konfirmatorisch. Die Pipeline
verweigert Smoke-Manifeste ohne `--allow-smoke`.

---

## 2. Event-Capture

### 2.1 Treatment (OmniBridge-Logs)

`eth_getLogs` je Mediator, `topics = [[TOPIC_INITIATED, TOPIC_BRIDGED]]`,
`fromBlock`/`toBlock` aus dem UTC-Fenster (über `eth_getBlockByNumber` /
Binärsuche auf Timestamp).

Chunk-Größe: 2_000 Blöcke (ETH) / 5_000 Blöcke (Gnosis). Bei RPC-Fehler
`−32005` / range too large: halbieren, nicht überspringen.

Pro Log speichern: `chain`, `address`, `txHash`, `logIndex`, `blockNumber`,
`blockTime`, `topic0`, `token`, `counterparty` (sender oder recipient aus
indexed topics).

Punktprozess = sortierte Liste `blockTime` (Unix-Sekunden, float ok).

### 2.2 Kontrolle (Uniswap `tx.to`)

Öffentliche RPCs liefern selten volle `tx.to`-Historie ohne Indexer.
Zulässige Quellen, in dieser Reihenfolge, im Manifest vermerkt:

1. Archive-RPC + Block-Iteration ist **nicht** Pflicht (90 Tage ETH ≈ 650k
   Blöcke — unzumutbar).
2. **Etherscan / Arbiscan `txlist` intern** auf die eingefrorenen Router
   (API-Key aus Env, nicht committen).
3. Fallback: `eth_getLogs` auf Universal-Router `Swap`-Events, falls die
   Scanner-API ausfällt — nur mit denselben Router-Adressen. Das ist kein
   Adresswechsel, nur ein Transportwechsel; im Manifest `capture_method`
   festhalten.

Wenn Capture unvollständig (Lücken > 1 % der Minuten mit Scanner-Fehler):
`INCONCLUSIVE`, keine Lückenfüllung mit Zufall.

### 2.3 Manifest-Pflichtfelder

```text
window_start, window_end, addresses, topic0, n_events per stream,
rpc_urls (redacted), capture_method, utc_captured_at, git_commit
```

Adressen im Manifest müssen `scripts/bridge_stufe_a_config.py` entsprechen
(`assert_frozen_addresses`).

---

## 3. Treiber-Capture

1-Minuten-Index über das ganze Fenster (90 × 24 × 60 = 129_600 Minuten).

- **Gas:** `eth_feeHistory` in Chunks, Median `baseFeePerGas` je Minute.
- **BTC:** CoinGecko `market_chart` oder Binance-Klines 1m `BTCUSDT`.
- **CEX:** CoinGecko `/exchanges/{id}/volume_chart` reicht oft nicht für
  1-min. Frozen Fallback: Summe der 1m-Quote-Volumina
  `BTCUSDT + ETHUSDT` auf Binance, Coinbase, Kraken, OKX, Bybit
  (Top-5-Spot nach CoinGecko-Trust zum Capture-Zeitpunkt **nicht** neu
  wählen — die fünf Namen sind hier fixiert).

Lücken ≤ 5 min: linear. Lücken > 5 min: NaN. Coverage-Quote ins Manifest.

---

## 4. Hawkes γ(τ) — Histogram-Kern

Kein volles MLE eines exponentiellen Hawkes für die 248 Tests (das wäre
ein α, nicht 31 Lags). Konfirmatorisch ist der **nicht-parametrische
Anregungskern**:

Für Quell-Events `{s_i}` und Ziel-Events `{t_j}`:

```text
γ̂(τ) = (1 / (N_src · Δτ)) · #{ Paare (i,j) : τ ≤ t_j − s_i < τ + Δτ }
        − λ̂_tgt
```

mit `Δτ = 60 s`, `λ̂_tgt = N_tgt / T`, `T` = Fensterlänge in Sekunden,
`τ = 0, 60, …, 1800` s.

Rand: Paare nur zählen, wenn `s_i + τ + Δτ` noch im Fenster liegt
(vollständige Bins; kein Wrap).

Jitter-Null: jedes `s_i` → `s_i + U(−300, +300)` s, Rejection bis
`WINDOW_START ≤ s' ≤ WINDOW_END`. Ziel unverändert. 1000× `γ̂_null(τ)`,
p plus-one.

---

## 5. CTE

1. Beide Punktprozesse → binäre Minuten-Serien `X_t`, `Y_t` ∈ {0,1}.
2. Treiber `G_t`, `B_t`, `C_t` auf dieselben Minuten; z-score innerhalb
   des Fensters; dann je Treiber **Tertile** {0,1,2} (gleiche Bin-Kanten
   für Observation und alle Surrogate — Kanten nur aus der Observation
   berechnen und einfrieren).
3. Schätzer: diskrete Transferentropie, Embedding k=1, l=1:

```text
TE_{X→Y}(τ) = H(Y_t | Y_{t−1}, G_t, B_t, C_t)
            − H(Y_t | Y_{t−1}, X_{t−τ}, G_t, B_t, C_t)
```

τ in Minuten, 0…30. Minuten mit NaN-Treiber droppen (paarweise).

Plugin-Entropie auf der empirischen Verteilung (kein kNN/Kraskov — zu
viele Freiheitsgrade für Pre-Reg). Add-ε = 0 für leere Zellen
(Maximum-Likelihood-Plugin).

Shuffle-Null: Permutation von `X` (die ganze Serie), `Y` und Treiber fest.

UTE: dieselbe Formel ohne `G,B,C`.

---

## 6. BH-FDR

`scripts/bridge_stufe_a_stats.benjamini_hochberg(p_values, q=0.05)`

Reihenfolge: alle 248 p-Werte in einem Vektor, eine BH-Prozedur
(nicht 4× separat — das wäre eine andere Korrektur).

---

## 7. Auswertungs-Pipeline

```text
events.json + drivers.json
    → vier Punktprozesse + drei Treiber
    → N-Check (≥100) und Coverage-Check (≥80 %)
    → 2×31 Hawkes γ + 1000 Jitter
    → 2×31 CTE + 1000 Shuffle  (×2 Paare)
    → 248 p-Werte → BH
    → Verdict-Funktion (Pre-Reg §6) — reine Funktion, getestet
    → JSON + Dossier-Rohdaten
```

Seed für Surrogate: `BRIDGE_STUFE_A_SEED = 20260817`. Ein RNG,
sequentiell Hawkes-dann-CTE, dokumentierte Ziehung (reproduzierbar).

---

## 8. Tests (jetzt vs. später)

**Jetzt (`scripts/test_bridge_stufe_a.py`):**

- Config: 248 = 2×31×2×2, Fenster 90 Tage, Adressen-Checksummen
- topic0 = keccak der eingefrorenen Signaturen
- Jitter erhält N und bleibt im Fenster
- Histogram-Kern: synthetische Delta-Anregung bei bekanntem Lag wird
  dort maximal
- BH: klassisches Beispiel (unabhängig, q=0.05)
- Verdict-Funktion: die fünf Labels an Mini-Matrizen

**Später (mit Capture, nicht in diesem Schritt):**

- Manifest-Adressen == Config
- Eval weigert sich bei Fenster-Mismatch
- Kein Live-RPC im CI

---

## 9. Out of scope

- Stufe B / Ausfallfenster
- IAAFT, Kuramoto, Blockzeiten als Punktprozess
- xDAI-Native-Bridge, AMB-only
- Arbitrum-Inbox als Kontrolle
- Nachjustage von q, Lag-Raster, N_min nach Zahlenblick
