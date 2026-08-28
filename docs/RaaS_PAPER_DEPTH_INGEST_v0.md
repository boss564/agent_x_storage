# RaaS Paper Depth Ingest & Shadow-Fills (Paket 2 + 2.1) v0

**Scope:** `DEFENSIVE_CAUSAL_GROUNDING` · `live_execution=false` · **no order send**

B + C as layers: **B** collects read-only depth; **C** attaches book snapshots to `SIM_FILL`.

## Phase B — Passive depth ingest

| Item | Value |
|------|-------|
| Endpoint | `GET /api/v3/depth?symbol=…&limit=10` (public, no trade key) |
| Guard | `assert_no_order_urls` — order paths forbidden |
| WORM | `logs/worm/depth_snapshots.jsonl` (`action=DEPTH_SNAPSHOT`) |
| Config | `config/paper_trading_config.json` → `depth_ingest` |
| Cron | `scripts/raas_depth_ingest.sh` · systemd `raas-depth-ingest.timer` (60 s) |

```bash
make raas-depth-ingest          # append snapshots for ETHUSDC + BTCUSDC
make raas-depth-ingest-dry      # fetch only, no WORM write
```

## Phase C — Shadow-fills with book snapshot

On each `SIM_FILL`, when `shadow_fill.attach_orderbook=true`:

| WORM field | Content |
|------------|---------|
| `orderbook_snapshot` | `{bids, asks}` top-N levels at fill time |
| `depth_source` | `binance_rest_depth` \| `shadow_synthetic` \| `depth_worm` |
| `snapshot_ts` | ISO time of depth row used (Paket 2.1) |
| `snapshot_age_s` | fill `ts` − `snapshot_ts` in seconds (Paket 2.1) |
| `depth_snapshot_hash` | WORM hash when book from ingest log |
| `mark_price` / `qty` | Fixed tuple for replay A/B |

Smoke dry-run uses `shadow_synthetic` with `snapshot_age_s=0`. Production:

- `make_live_depth_fetcher()` — fetch at fill (age ≈ API latency)
- `make_worm_depth_fetcher(path)` — latest ingest row (age up to `interval_s`)

Sizing remains **fixed EUR notional** (`shadow_fill.notional_eur`, default 100 €) — no equity feedback.

### Snapshot age bias (Paket 2.1)

`depth_ingest.interval_s=60` → fills can use books up to ~60 s old. In flash-crash conditions
**stale depth is systematically deeper than at fill time** → replay **understates** slippage
(directional bias). `snapshot_age_s` on every `SIM_FILL` makes freshness reconstructable later.

## Phase 3 — Replay

`replay.py` uses `orderbook_snapshot` when present; schema `raas_paper_slippage_replay_v1`.

| Metric / report | Meaning |
|-----------------|---------|
| `slippage_cost_delta_eur` | Σ (dynamic − fixed) per fill |
| `fee_delta_eur` | Σ fee delta per fill |
| `snapshot_age_strata` | Buckets `< 5 s` · `5–30 s` · `> 30 s` · `unknown` with per-stratum slipΔ |

Interpret strata before citing aggregate slipΔ — crash fills in `> 30 s` need explicit caveat.

## Empirical collection (Sammellauf)

Long-running loop: live ticks + `make_live_depth_fetcher()` at each fill (no order send).

```bash
make raas-paper-collect              # default 24h, depth-mode live
make raas-paper-collect-smoke        # 2 ticks, network smoke
```

Manifest: `logs/worm/paper_collect_manifest.jsonl` · PID: `logs/paper_collect.pid` ·
per-symbol WORM copies under `logs/worm/paper_runs/<run_id>-<symbol>/`.

On REST failure, optional `synthetic_fallback` (`depth_source` on SIM_FILL) — collect continues;
replay reports `fills_synthetic_fallback` separately from `fills_binance_rest_depth`.

### Shadow pairs (BTC / ETH / SOL)

`config/paper_trading_config.json` → `pairs[]`: per-symbol `notional_eur` (fixed, no equity
feedback) and `volatility_profile` (`low` / `medium` / `high`). `depth_ingest` and collect
derive symbols from `pairs` when present. Replay reports `by_symbol` with profile labels —
analyze pairs separately before citing aggregates.

### Manifest hashes (`config_hash` vs `pair_manifest_hash`)

| Hash | Scope | Use |
|------|-------|-----|
| `config_manifest_hash` | Entire `paper_trading_config.json` | Run freeze, 30-day eval amendment |
| `pair_manifest_hash` | Per symbol: fees, slippage, `notional_eur`, `attach_orderbook` | Fill-comparable across runs |

`volatility_profile` and other pairs are **excluded** from `pair_manifest_hash` — adding SOL does
not invalidate BTC/ETH replay buckets. `SIM_FILL` rows carry `pair_manifest_hash`; replay
`by_symbol.manifests[]` refuses silent cross-hash aggregation (`manifest_split` + warnings).

Full-file `config_hash` still differs between the 2-pair and 3-pair collect runs — cite it per
run window, but merge BTC fills across those runs only when `pair_manifest_hash` matches.

## Not in scope

- Phase A historical backfill
- Live order send (Map violation)
- Equity-derived sizing

## Adoption

Depth + shadow parameters are in `config/paper_trading_config.json` → `config_manifest_hash()`.
Change requires amendment note before gated 30-day eval.

Parent: `docs/PAPER_TRADING_SETUP_v0.md` · slippage: `docs/RaaS_PAPER_FEES_SLIPPAGE_v0.md`
