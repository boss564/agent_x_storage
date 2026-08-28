# RaaS Paper Depth Ingest & Shadow-Fills (Paket 2) v0

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
| `depth_source` | `binance_rest_depth` \| `shadow_synthetic` |
| `mark_price` / `qty` | Fixed tuple for replay A/B |

Smoke dry-run uses `shadow_synthetic` (offline). Production paper loop should set
`depth_fetcher=fetch_binance_depth` and `depth_source=binance_rest_depth`.

Sizing remains **fixed EUR notional** (`shadow_fill.notional_eur`, default 100 €) — no equity feedback.

## Phase 3 — Replay

`replay.py` uses `orderbook_snapshot` on each fill when present; falls back to synthetic book otherwise.

Report fields: `fills_with_orderbook_snapshot`, `fills_binance_rest_depth`, `fills_past_level_1`.

## Planned (Paket 2.1 — before production stress replay)

`depth_ingest.interval_s=60` means a fill may use a book up to ~60 s old. In flash-crash
conditions stale depth is systematically **deeper than at fill time** → replay **understates**
slippage (directional bias, not noise).

| Field | Purpose |
|-------|---------|
| `snapshot_ts` | ISO time of depth row used |
| `snapshot_age_s` | fill `ts` − snapshot `ts` |
| Report strata | `< 5 s` · `5–30 s` · `> 30 s` per fill |

Without `snapshot_age_s`, freshness at fill time cannot be reconstructed later.

## Not in scope (Paket 2)

- Phase A historical backfill
- Live order send (Map violation)
- Equity-derived sizing

## Adoption

Depth + shadow parameters are in `config/paper_trading_config.json` → `config_manifest_hash()`.
Change requires amendment note before gated 30-day eval.

Parent: `docs/PAPER_TRADING_SETUP_v0.md` · slippage replay: `docs/RaaS_PAPER_FEES_SLIPPAGE_v0.md`
