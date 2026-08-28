# RaaS Paper Fees & Slippage (P3) v0

**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · `not_investment_advice=true`

## Frozen config

| Field | Value |
|-------|-------|
| Path | `config/paper_trading_config.json` |
| Exchange | Binance VIP Tier 1 |
| Maker / Taker | 0.075% each |
| Slippage default | `dynamic` (book walk, 10 levels) |
| Fallback | 0.1% fixed when book empty / insufficient depth |
| Start balance | 1_000 EUR |

Hash before any 30-day run: `config_manifest_hash()` in `prototypes/raas_paper_trading/config_loader.py`.

## Implementation

| Module | Role |
|--------|------|
| `config_loader.py` | Parse + hash manifest |
| `slippage.py` | `calculate_dynamic_slippage`, `calculate_fixed_slippage`, `synthetic_orderbook` |
| `ledger.py` | Fees on notional; slippage on buy/sell; `slippage_cost_eur` tracked |
| `scripts/raas_paper_slippage_compare.py` | Wiring smoke only — **not** an empirical slippage estimate |
| `prototypes/raas_paper_trading/replay.py` | Fixed-tuple A/B replay from WORM `SIM_FILL` |
| `scripts/raas_paper_slippage_replay.py` | `make raas-paper-slippage-replay` — post-processing, no live loop |

## Screen (`make raas-paper-slippage-compare`)

Synthetic orderbook round-trips at several sizes → `exports/reports/paper_slippage_compare_latest.json`.

**Interpretation:** Direction is **determined by parameter choice** before any calculation runs.
`fallback_percent` is a constant; the synthetic book is parameterized. If the book is tighter
than 0.1%, `dynamic` wins at every size; if wider, `fixed` wins at every size. Identical sign
across sizes is the same constant twice — not confirmation across magnitudes.

> *Richtung durch Parameterwahl determiniert; erste informative Messung ist der Replay.*

Do **not** cite screen euro deltas as tendency or magnitude — they only say whether
`fallback_percent` is larger or smaller than the spread of the invented book.

## Synthetic book determinism (screen + replay without live depth)

The generator couples **price-proportional** spread with **absolute** depth per level:

```text
spread_bps = 5.0          # relative to mid → half-spread ≈ 2.5 bps per side at level 1
qty_per_level = 0.1       # absolute coin units per level (default; was 1.0)
```

| Effect | Consequence |
|--------|-------------|
| `order_size ≤ qty_per_level` | Dynamic slippage ≈ constant `spread_bps/2` — **no size dependence** |
| `order_size > qty_per_level` | Book walk — dynamic slippage becomes size-dependent |
| `spread_bps` vs `fallback_percent` | **Result direction fixed before calculation** — not a model verdict |

> Ergebnisrichtung durch `spread_bps` gegen `fallback_percent` festgelegt; kein Modellbefund.

> Fills mit `order_size ≤ qty_per_level` bleiben im ersten Level — Größenabhängigkeit der
> dynamischen Slippage greift dann nicht. Replay misst die gewichtete Kostenschiebung der
> Modellwahl über die Fill-Verteilung, nicht welches Modell zutrifft (echte Buchtiefe fehlt).

Do **not** read replay totals as „dynamic is cheaper/better" — that is a parameter consequence,
not empirical book quality.

## 30-day replay (first informative measurement — cost shift, not model truth)

**Hypothesis (diagnostic only, not a release gate):** How much does dynamic book-walk differ
from fixed fallback on **the same fills**?

### Clean A/B protocol

Replay `SIM_FILL` rows from `logs/worm/paper_trading_audit.jsonl` as **fixed tuples**
`(side, qty, mark_price, signal_id)` under two slippage modes. Fills are identical; only
fee/slippage cost differs.

| Metric | Meaning |
|--------|---------|
| `slippage_cost_delta` | Σ per-fill slippage cost (dynamic − fixed) |
| `fee_delta` | Σ per-fill fees (dynamic − fixed) |

Report **only** these when fills are held constant.

### Path-feedback variant (explicit opt-in)

If order sizing is derived from `cash_eur` / `mark_equity()` (e.g. `% of equity` per signal),
the two slippage branches diverge in position size after the first fill. That is a different
experiment: name it **„Equity-Differenz nach N Tagen inklusive Rückkopplung"** — do not label
it `slippage_cost_delta`.

### Current smoke runner (`runner.py`)

Smoke policy uses a **fixed EUR notional** on first buy (`100 € / mark`), not equity-derived
sizing. Sell closes full `position_qty`. No equity-feedback loop on order size in smoke —
replay A/B with WORM tuples remains valid once real fills exist.

Production policies that size from equity must choose fixed-tuple replay or path-feedback
explicitly before the 30-day eval.

### Replay command

```bash
make raas-paper-trading-smoke   # persists worms → logs/worm/paper_runs/<run_id>/
make raas-paper-slippage-replay # reads SIM_FILL tuples → exports/reports/paper_slippage_replay_latest.json
```

Report metrics (dynamic − fixed): `slippage_cost_delta_eur`, `fee_delta_eur` per fill and total.
Synthetic defaults: `SYNTHETIC_SPREAD_BPS=5`, `SYNTHETIC_QTY_PER_LEVEL=0.1` in `slippage.py`.
Report JSON includes `interpretation[]` and `fills_past_level_1` — see synthetic book section above.

## Adoption rule

Changing fees, slippage mode, or fallback requires a new config hash and amendment note before
a gated 30-day run — no silent retuning.

Primary paper metric remains **envelope hit-rate** (`docs/PAPER_TRADING_SETUP_v0.md`).
