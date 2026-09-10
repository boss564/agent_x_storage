# Swarm gap analysis

- generated: `2026-08-30T13:57:50Z`
- watchlist: BTC, ETH, SOL, BNB, XRP, AVAX, LINK, SUI, DOGE, PEPE
- rule A: |Δ1h| > 5.0% or |Δ24h| > 8.0% and 0 matching news
- rule B: `$TICKER` cashtags not on the price watchlist
- source: public Binance via ccxt (no API key); news: `data/news_scores.jsonl`
- diagnostic_only · live_execution=false · order_send=false

## Price snapshot

| asset | Δ1h % | Δ24h % | last | error |
|-------|-------|--------|------|-------|
| BTC | 0.1444 | 1.522 | 78898.8 |  |
| ETH | 0.2879 | 1.644 | 2476.57 |  |
| SOL | 1.1969 | 3.329 | 107.38 |  |
| BNB | 0.5155 | 1.645 | 700.0 |  |
| XRP | 0.5204 | 1.724 | 1.41 |  |
| AVAX | 0.4325 | 1.767 | 7.43 |  |
| LINK | 0.8111 | 2.03 | 11.559 |  |
| SUI | 0.1201 | 1.543 | 0.75 |  |
| DOGE | 0.3629 | 0.906 | 0.08574 |  |
| PEPE | 0.5479 | 0.824 | 3.67e-06 |  |

## Rule A — COVERAGE_GAP

Keine Preis-Anomalie ohne News in diesem Lauf.

## Rule B — UNTRACKED_ENTITY

Keine fremden `$TICKER`-Cashtags außerhalb der Watchlist.

## System recommendations

Keine Handlungsempfehlung — Watchlist und News-Abdeckung sind in diesem Fenster konsistent.
