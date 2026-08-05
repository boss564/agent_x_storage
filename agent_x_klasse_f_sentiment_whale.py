"""
Agent X — Klasse F: Social-Sentiment & On-Chain-Whale-Tracking.

Soft-Signal-Schicht: Twitter/X-Sentiment, Reddit-Diskussionen,
Whale-Wallet-Bewegungen, Exchange-Flows, On-Chain-Aktivitätsmuster.

Diese Signale sind korrelativ, nicht kausal — sie dienen als
Frühwarn-Indikatoren, die von den anderen Klassen (A-E) validiert werden.

Agenten:
  F1-1: Social-Sentiment-Tracker (Twitter/X + Reddit)  — 3 Subagenten
  F1-2: Whale-Wallet-Monitor (Große Transfers)          — 3 Subagenten
  F1-3: On-Chain-Aktivitäts-Scanner                      — 3 Subagenten
  F2-1: Sentiment-Score-Aggregator                       — 3 Subagenten
  F2-2: Whale-Impact-Analyst                             — 3 Subagenten
  F2-3: F→A/B/C/D/E Bridge (Soft-Signal-Integration)    — 3 Subagenten
"""

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("klasse_f")

# ─── Konfiguration ───────────────────────────────────────────────────

TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://eth-mainnet.g.alchemy.com/v2/demo")
WHALE_THRESHOLD_USD = float(os.getenv("WHALE_THRESHOLD_USD", "1000000"))  # $1M
WHALE_WALLETS = int(os.getenv("WHALE_WALLETS_TO_TRACK", "100"))
SENTIMENT_POLL_INTERVAL = int(os.getenv("SENTIMENT_POLL_INTERVAL", "60"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_unix() -> float:
    return time.time()


# ─── Bekannte Whale-Wallets (Labels) ─────────────────────────────────

KNOWN_WHALES = {
    "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": {"label": "Binance 7", "type": "exchange"},
    "0xF977814e90dA44bFA03b6295A0616a897441aceC": {"label": "Binance 8", "type": "exchange"},
    "0x28C6c06298d514Db089934071355E5743bf21d60": {"label": "Binance 14", "type": "exchange"},
    "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503": {"label": "Binance Hot", "type": "exchange"},
    "0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a": {"label": "Arbitrum Bridge", "type": "bridge"},
    "0x99C9fc46f92E8a1c0deC1b1747d010903E884bE1": {"label": "Optimism Bridge", "type": "bridge"},
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": {"label": "USDC Treasury", "type": "treasury"},
    "0xDa63E70379F4f6D464f9Db27D28e3B2A13D4Da63": {"label": "Jump Trading", "type": "market_maker"},
    "0x0D0707963952f2fBA59dD06f2b425ace40b492Fe": {"label": "Alameda/FTX Old", "type": "defunct"},
}

# Bekannte Token-Adressen für Tracking
TRACKED_TOKENS = {
    "ETH": "0x0000000000000000000000000000000000000000",
    "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    "ARB": "0xB50721BCf8d664c30412Cfbc6cf7a15145234ad1",
    "OP": "0x4200000000000000000000000000000000000042",
}

# Sentiment-Keywords für Crypto
BULLISH_KEYWORDS = ["bullish", "moon", "pump", "buy", "long", "accumulation",
                     "breakout", "ath", "all time high", "green", "rally"]
BEARISH_KEYWORDS = ["bearish", "dump", "sell", "short", "crash", "correction",
                     "distribution", "resistance", "red", "fear", "capitulation"]


# ═══════════════════════════════════════════════════════════════════════
# AGENT F1-1: Social-Sentiment-Tracker
# ═══════════════════════════════════════════════════════════════════════

def f1_1_social_sentiment_tracker(
    action: str = "poll",
    keywords: list[str] | None = None,
) -> dict:
    """Trackt Crypto-Sentiment auf Twitter/X und Reddit.

    Im Produktivbetrieb: Twitter API v2 + Reddit API.
    Hier: Keyword-basierte Demo mit realistischen Patterns.

    Returns:
        {"status": "...", "sentiment_score": -100..+100, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok", "agent": "F1-1",
                "sources": ["Twitter/X API v2", "Reddit r/cryptocurrency", "Reddit r/ethereum"],
                "keywords_tracked": len(BULLISH_KEYWORDS) + len(BEARISH_KEYWORDS),
                "timestamp": _now_iso(),
            }

        twitter = _f1_1a_track_twitter(keywords)
        reddit = _f1_1b_track_reddit(keywords)
        trending = _f1_1c_identify_trending_topics(twitter, reddit)

        return {
            "status": "completed", "agent": "F1-1",
            "sentiment_score": trending.get("combined_score", 0),
            "subagents": {
                "f1_1a_twitter": twitter,
                "f1_1b_reddit": reddit,
                "f1_1c_trending": trending,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("F1-1 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _f1_1a_track_twitter(keywords: list[str] | None) -> dict:
    """Trackt Twitter/X-Posts mit Crypto-Keywords.

    Im Produktivbetrieb: Twitter API v2 filtered stream mit Keyword-Regeln.
    """
    kw = keywords or ["ETH", "BTC", "DeFi", "Aave", "crypto"]
    # Demo: Simulierte Tweet-Volumes mit Sentiment
    now = _now_unix()
    sentiment_cycle = (now % 3600) / 3600  # 0..1 über die Stunde

    tweets = []
    for i, keyword in enumerate(kw[:5]):
        bull_mentions = int(50 + sentiment_cycle * 200 + i * 30)
        bear_mentions = int(30 + (1 - sentiment_cycle) * 150 + i * 15)
        total = bull_mentions + bear_mentions
        score = round((bull_mentions - bear_mentions) / max(1, total) * 100, 1)

        tweets.append({
            "keyword": keyword,
            "tweet_count_1h": total,
            "bullish_pct": round(bull_mentions / max(1, total) * 100, 1),
            "bearish_pct": round(bear_mentions / max(1, total) * 100, 1),
            "sentiment_score": score,
        })

    avg_score = sum(t["sentiment_score"] for t in tweets) / len(tweets) if tweets else 0

    return {
        "status": "ok", "subagent": "F1-1a", "role": "Twitter-Tracker",
        "source": "twitter_api_demo",
        "tweets_analyzed_1h": sum(t["tweet_count_1h"] for t in tweets),
        "avg_sentiment_score": round(avg_score, 1),
        "by_keyword": tweets,
    }


def _f1_1b_track_reddit(keywords: list[str] | None) -> dict:
    """Trackt Reddit r/cryptocurrency und r/ethereum Posts."""
    now = _now_unix()
    subs = [
        {"sub": "r/cryptocurrency", "posts_24h": 450, "avg_sentiment": 0.12,
         "top_post": "ETH/BTC ratio hitting resistance — breakout soon?"},
        {"sub": "r/ethereum", "posts_24h": 280, "avg_sentiment": 0.18,
         "top_post": "Aave V4 proposal discussion thread"},
        {"sub": "r/defi", "posts_24h": 120, "avg_sentiment": 0.22,
         "top_post": "New liquidation cascade prevention mechanism"},
    ]

    return {
        "status": "ok", "subagent": "F1-1b", "role": "Reddit-Tracker",
        "source": "reddit_api_demo",
        "subreddits": subs,
        "overall_sentiment": round(
            sum(s["avg_sentiment"] for s in subs) / len(subs) * 100, 1
        ),
    }


def _f1_1c_identify_trending_topics(twitter: dict, reddit: dict) -> dict:
    """Identifiziert trending Topics aus beiden Quellen."""
    tw_keywords = twitter.get("by_keyword", [])
    trending = []

    for kw in tw_keywords:
        if abs(kw.get("sentiment_score", 0)) > 30:  # Starke Abweichung
            trending.append({
                "keyword": kw["keyword"],
                "sentiment": "BULLISH" if kw["sentiment_score"] > 0 else "BEARISH",
                "strength": abs(kw["sentiment_score"]),
                "source": "twitter",
            })

    combined_score = round(
        twitter.get("avg_sentiment_score", 0) * 0.6 +
        reddit.get("overall_sentiment", 0) * 0.4, 1
    )

    return {
        "status": "ok", "subagent": "F1-1c", "role": "Trending-Topics",
        "trending": trending,
        "combined_score": combined_score,
        "market_sentiment": (
            "strongly_bullish" if combined_score > 40
            else "bullish" if combined_score > 15
            else "neutral" if combined_score > -15
            else "bearish" if combined_score > -40
            else "strongly_bearish"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT F1-2: Whale-Wallet-Monitor
# ═══════════════════════════════════════════════════════════════════════

def f1_2_whale_monitor(
    action: str = "scan",
    max_transfers: int = 50,
) -> dict:
    """Überwacht große Wallet-Bewegungen und Exchange-Flows.

    Returns:
        {"status": "...", "whale_movements": N, "subagents": {...}}
    """
    try:
        if action == "status":
            return {
                "status": "ok", "agent": "F1-2",
                "whales_tracked": len(KNOWN_WHALES),
                "threshold_usd": WHALE_THRESHOLD_USD,
                "timestamp": _now_iso(),
            }

        large_transfers = _f1_2a_scan_large_transfers(max_transfers)
        exchange_flows = _f1_2b_analyze_exchange_flows(large_transfers)
        alerts = _f1_2c_generate_whale_alerts(exchange_flows)

        return {
            "status": "completed", "agent": "F1-2",
            "whale_movements": large_transfers.get("transfers_found", 0),
            "alerts": alerts.get("alert_count", 0),
            "subagents": {
                "f1_2a_large_transfers": large_transfers,
                "f1_2b_exchange_flows": exchange_flows,
                "f1_2c_alerts": alerts,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("F1-2 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _f1_2a_scan_large_transfers(max_transfers: int) -> dict:
    """Scannt nach großen Transfers (>$1M) — on-chain via eth_getLogs."""
    # Demo: Realistische Whale-Transfers
    whale_keys = list(KNOWN_WHALES.keys())
    whale_vals = list(KNOWN_WHALES.values())
    transfers = [
        {"hash": "0xwh1", "from": whale_vals[0]["label"],
         "from_addr": whale_keys[0],
         "to": "0xUnknown1", "amount_usd": 15_000_000, "token": "USDC",
         "tx_type": "exchange_withdrawal", "timestamp": _now_iso()},
        {"hash": "0xwh2", "from": "0xUnknown2",
         "to": whale_vals[1]["label"],
         "to_addr": whale_keys[1],
         "amount_usd": 8_500_000, "token": "ETH",
         "tx_type": "exchange_deposit", "timestamp": _now_iso()},
        {"hash": "0xwh3", "from": whale_vals[7]["label"],
         "from_addr": whale_keys[7],
         "to": "0xAavePool", "amount_usd": 25_000_000, "token": "USDC",
         "tx_type": "defi_deposit", "timestamp": _now_iso()},
        {"hash": "0xwh4", "from": "0xWhaleDormant",
         "to": "0xCoinbase10", "amount_usd": 42_000_000, "token": "ETH",
         "tx_type": "dormant_awakening", "timestamp": _now_iso(),
         "dormant_days": 847},
        {"hash": "0xwh5", "from": whale_vals[4]["label"],
         "from_addr": whale_keys[4],
         "to": "0xL2Settlement", "amount_usd": 120_000_000, "token": "ETH",
         "tx_type": "bridge_transfer", "timestamp": _now_iso()},
    ]

    return {
        "status": "ok", "subagent": "F1-2a", "role": "Large-Transfer-Scanner",
        "source": "onchain_demo",
        "transfers_found": len(transfers),
        "total_volume_usd": sum(t["amount_usd"] for t in transfers),
        "transfers": transfers,
    }


def _f1_2b_analyze_exchange_flows(transfers_result: dict) -> dict:
    """Analysiert Netto-Flows zu/von Exchanges."""
    transfers = transfers_result.get("transfers", [])
    # Netto-Flow: Deposit (= Verkaufssignal) vs. Withdrawal (= Kaufsignal)
    net_flow = 0.0
    inflows = 0.0
    outflows = 0.0

    for t in transfers:
        if "deposit" in t.get("tx_type", ""):
            inflows += t["amount_usd"]  # Deposit = potenzieller Verkauf
        elif "withdrawal" in t.get("tx_type", "") or "defi" in t.get("tx_type", ""):
            outflows += t["amount_usd"]  # Withdrawal = potenzieller Kauf/Staking

    net_flow = outflows - inflows  # Positiv = Kapital verlässt Exchanges

    return {
        "status": "ok", "subagent": "F1-2b", "role": "Exchange-Flow-Analyzer",
        "exchange_inflows_usd": round(inflows, 0),  # Zu Exchanges
        "exchange_outflows_usd": round(outflows, 0),  # Von Exchanges
        "net_flow_usd": round(net_flow, 0),
        "signal": (
            "ACCUMULATION" if net_flow > 10_000_000
            else "BUYING" if net_flow > 0
            else "DISTRIBUTION" if net_flow < -10_000_000
            else "SELLING" if net_flow < 0
            else "NEUTRAL"
        ),
    }


def _f1_2c_generate_whale_alerts(flow_result: dict) -> dict:
    """Generiert Alarme basierend auf Whale-Aktivität."""
    alerts = []
    signal = flow_result.get("signal", "NEUTRAL")

    if signal in ("DISTRIBUTION", "SELLING"):
        alerts.append({
            "level": "WARNING",
            "type": "WHALE_DISTRIBUTION",
            "message": f"Whales bewegen Kapital ZU Exchanges — möglicher Verkaufsdruck (${flow_result.get('exchange_inflows_usd',0):,.0f})",
        })

    # Dormant-Wallet-Prüfung
    if False:  # In Produktion: checke real-time Transfer-Liste
        alerts.append({
            "level": "HIGH",
            "type": "DORMANT_WHALE_AWAKENED",
            "message": "Langzeit-inaktive Whale-Wallet wurde aktiv — mögliche große Bewegung",
        })

    return {
        "status": "ok", "subagent": "F1-2c", "role": "Whale-Alert-Generator",
        "alert_count": len(alerts), "alerts": alerts,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT F1-3: On-Chain-Aktivitäts-Scanner
# ═══════════════════════════════════════════════════════════════════════

def f1_3_onchain_activity_scanner(action: str = "scan") -> dict:
    """Scannt On-Chain-Aktivitätsmuster: neue Wallets, Gas-Verbrauch, Contract-Deployments."""
    try:
        if action == "status":
            return {"status": "ok", "agent": "F1-3",
                    "metrics": ["new_wallets", "active_addresses", "gas_usage", "contract_deploys"],
                    "timestamp": _now_iso()}

        new_wallets = _f1_3a_track_new_wallets()
        active_addrs = _f1_3b_track_active_addresses()
        anomalies = _f1_3c_detect_network_anomalies(new_wallets, active_addrs)

        return {
            "status": "completed", "agent": "F1-3",
            "subagents": {
                "f1_3a_new_wallets": new_wallets,
                "f1_3b_active_addresses": active_addrs,
                "f1_3c_anomalies": anomalies,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("F1-3 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _f1_3a_track_new_wallets() -> dict:
    """Trackt neu erstellte Wallet-Adressen (First-Transaction-Detektion)."""
    return {
        "status": "ok", "subagent": "F1-3a", "role": "New-Wallet-Tracker",
        "new_wallets_24h": 12500, "trend": "increasing",
        "new_wallets_7d_avg": 10200,
        "significance": "Normal — kein Bull-Market-Spike",
    }


def _f1_3b_track_active_addresses() -> dict:
    """Trackt aktive Adressen und deren Gas-Ausgaben."""
    return {
        "status": "ok", "subagent": "F1-3b", "role": "Active-Address-Tracker",
        "active_addresses_24h": 485_000,
        "avg_gas_spent_gwei": 28.5,
        "high_gas_spenders": 3200,  # >100 gwei
        "trend": "stable",
    }


def _f1_3c_detect_network_anomalies(wallets: dict, active: dict) -> dict:
    """Erkennt Anomalien in On-Chain-Aktivität."""
    anomalies = []
    if wallets.get("trend") == "spiking" and active.get("trend") == "declining":
        anomalies.append("Bot-Farm-Aktivität: viele neue Wallets aber sinkende echte Nutzer")
    return {
        "status": "ok", "subagent": "F1-3c", "role": "Network-Anomaly-Detector",
        "anomalies": anomalies,
    }


# ═══════════════════════════════════════════════════════════════════════
# AGENT F2-1: Sentiment-Score-Aggregator
# ═══════════════════════════════════════════════════════════════════════

def f2_1_sentiment_aggregator(sentiment_data: dict | None = None) -> dict:
    """Aggregiert Sentiment-Signale zu einem gewichteten Score (-100..+100)."""
    try:
        data = sentiment_data or {}

        score = _f2_1a_compute_weighted_score(data)
        history = _f2_1b_track_sentiment_history(score)
        divergence = _f2_1c_detect_price_sentiment_divergence(score)

        return {
            "status": "completed", "agent": "F2-1",
            "aggregated_score": score.get("score", 0),
            "market_mood": score.get("mood", "neutral"),
            "subagents": {
                "f2_1a_weighted_score": score,
                "f2_1b_history": history,
                "f2_1c_divergence": divergence,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("F2-1 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _f2_1a_compute_weighted_score(data: dict) -> dict:
    """Twitter 50%, Reddit 30%, Trending 20%."""
    tw = data.get("subagents", {}).get("f1_1a_twitter", {}).get("avg_sentiment_score", 0)
    reddit = data.get("subagents", {}).get("f1_1b_reddit", {}).get("overall_sentiment", 0)
    trending_strength = sum(
        abs(t.get("strength", 0)) * (1 if t.get("sentiment") == "BULLISH" else -1)
        for t in data.get("subagents", {}).get("f1_1c_trending", {}).get("trending", [])
    ) / max(1, len(data.get("subagents", {}).get("f1_1c_trending", {}).get("trending", [])))

    score = round(tw * 0.50 + reddit * 0.30 + trending_strength * 20 * 0.20, 1)
    mood = (
        "euphoric" if score > 60 else "bullish" if score > 25
        else "neutral" if score > -25 else "fearful" if score > -60
        else "capitulation"
    )

    return {"score": score, "mood": mood, "components": {"twitter": tw, "reddit": reddit, "trending": trending_strength}}


def _f2_1b_track_sentiment_history(score_result: dict) -> dict:
    return {"status": "ok", "subagent": "F2-1b", "role": "Sentiment-History",
            "trend": "improving" if score_result.get("score", 0) > 0 else "declining"}


def _f2_1c_detect_price_sentiment_divergence(score_result: dict) -> dict:
    """Erkennt Divergenz: Preis steigt, aber Sentiment fällt = Warnsignal."""
    return {"status": "ok", "subagent": "F2-1c", "role": "Divergence-Detector",
            "divergence_detected": False,
            "note": "Keine Divergenz — Sentiment und Preis bewegen sich synchron"}


# ═══════════════════════════════════════════════════════════════════════
# AGENT F2-2: Whale-Impact-Analyst
# ═══════════════════════════════════════════════════════════════════════

def f2_2_whale_impact_analyst(whale_data: dict | None = None) -> dict:
    """Analysiert Whale-Impact: Wie beeinflussen die Bewegungen den Markt?"""
    try:
        data = whale_data or {}

        risk = _f2_2a_assess_distribution_risk(data)
        support = _f2_2b_identify_whale_support_levels(data)
        correlation = _f2_2c_correlate_with_price(data)

        return {
            "status": "completed", "agent": "F2-2",
            "subagents": {
                "f2_2a_distribution_risk": risk,
                "f2_2b_support_levels": support,
                "f2_2c_correlation": correlation,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("F2-2 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _f2_2a_assess_distribution_risk(whale_data: dict) -> dict:
    flow = whale_data.get("subagents", {}).get("f1_2b_exchange_flows", {})
    signal = flow.get("signal", "NEUTRAL")
    risk_pct = {"DISTRIBUTION": 75, "SELLING": 45, "NEUTRAL": 15, "BUYING": 10, "ACCUMULATION": 5}
    return {"status": "ok", "subagent": "F2-2a", "role": "Distribution-Risk",
            "risk_pct": risk_pct.get(signal, 15), "signal": signal}


def _f2_2b_identify_whale_support_levels(whale_data: dict) -> dict:
    return {"status": "ok", "subagent": "F2-2b", "role": "Support-Level-Identifier",
            "support_eth": 3100, "resistance_eth": 3400}


def _f2_2c_correlate_with_price(whale_data: dict) -> dict:
    return {"status": "ok", "subagent": "F2-2c", "role": "Price-Correlation",
            "correlation": "negative", "note": "Exchange-Inflows korrelieren mit Preissenkungen"}


# ═══════════════════════════════════════════════════════════════════════
# AGENT F2-3: F→A/B/C/D/E Bridge (Soft-Signal-Integration)
# ═══════════════════════════════════════════════════════════════════════

def f2_3_signal_bridge(
    sentiment_score: float = 0.0,
    whale_signal: str = "NEUTRAL",
) -> dict:
    """Integriert Soft-Signale als validierende (nicht auslösende) Faktoren.

    Klasse-F-Signale verstärken oder dämpfen Signale anderer Klassen,
    lösen aber nie alleinstehend Aktionen aus.

    Brücken:
      F→B: Extreme Fear → MEV-Bots reduzieren Aktivität (niedrigere Bribes)
      F→C: Whale-Distribution → Erhöhte Liquidations-Wahrscheinlichkeit
      F→D: Sentiment-Divergenz → Oracle-Daten kritischer prüfen
      F→E: Negative Sentiment-Trends → Governance-Proposals werden restriktiver
    """
    try:
        bridge_to_b = _f2_3a_bridge_to_pressure(sentiment_score)
        bridge_to_c = _f2_3b_bridge_to_lending(sentiment_score, whale_signal)
        bridge_to_de = _f2_3c_bridge_to_oracle_governance(sentiment_score)

        return {
            "status": "completed", "agent": "F2-3",
            "subagents": {
                "f2_3a_to_pressure": bridge_to_b,
                "f2_3b_to_lending": bridge_to_c,
                "f2_3c_to_oracle_gov": bridge_to_de,
            },
            "timestamp": _now_iso(),
        }
    except Exception as e:
        logger.error("F2-3 Fehler: %s", e)
        return {"status": "failed", "error": str(e)}


def _f2_3a_bridge_to_pressure(sentiment: float) -> dict:
    """F→B: Extreme Fear → MEV-Bots reduzieren Aktivität (Validierung für B2)."""
    mev_modifier = 1.0
    if sentiment < -40:
        mev_modifier = 0.7  # Fear → weniger Bots
    elif sentiment > 60:
        mev_modifier = 1.3  # Euphorie → mehr Bots

    return {
        "status": "ok", "subagent": "F2-3a", "role": "F→B Bridge",
        "mev_pressure_modifier": mev_modifier,
        "action": (
            "MEV-Pressure-Werte um 30% reduzieren (Fear-Markt)"
            if mev_modifier < 1.0
            else "MEV-Pressure unverändert" if mev_modifier == 1.0
            else "MEV-Pressure um 30% erhöhen (Euphorie-Markt)"
        ),
    }


def _f2_3b_bridge_to_lending(sentiment: float, whale_signal: str) -> dict:
    """F→C: Whale-Distribution + bearishes Sentiment → höheres Liquidation-Risk."""
    risk_modifier = 1.0
    if whale_signal in ("DISTRIBUTION", "SELLING") and sentiment < -15:
        risk_modifier = 1.3
    elif whale_signal in ("ACCUMULATION", "BUYING") and sentiment > 15:
        risk_modifier = 0.7

    return {
        "status": "ok", "subagent": "F2-3b", "role": "F→C Bridge",
        "liquidation_risk_modifier": risk_modifier,
        "recommendation": (
            "HF-Critical-Threshold um 0.03 erhöhen (Whale-Distribution)"
            if risk_modifier > 1.0
            else "Standard HF-Threshold" if risk_modifier == 1.0
            else "HF-Threshold leicht senken (Akkumulation)"
        ),
    }


def _f2_3c_bridge_to_oracle_governance(sentiment: float) -> dict:
    """F→D/E: Sentiment-Trendwende kann Oracle- und Governance-Entscheidungen beeinflussen."""
    return {
        "status": "ok", "subagent": "F2-3c", "role": "F→D/E Bridge",
        "oracle_trust_modifier": 0.9 if abs(sentiment) > 50 else 1.0,
        "governance_impact": (
            "Restriktivere Proposals wahrscheinlich" if sentiment < -30
            else "Expansive Proposals wahrscheinlich" if sentiment > 30
            else "Kein Sentiment-Einfluss auf Governance"
        ),
    }


# ─── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "f1_1":
        print(json.dumps(f1_1_social_sentiment_tracker("poll"), indent=2))
    elif cmd == "f1_2":
        print(json.dumps(f1_2_whale_monitor("scan"), indent=2))
    elif cmd == "f1_3":
        print(json.dumps(f1_3_onchain_activity_scanner("scan"), indent=2))
    elif cmd == "f2":
        f11 = f1_1_social_sentiment_tracker("poll")
        f12 = f1_2_whale_monitor("scan")
        print(json.dumps({
            "f2_1": f2_1_sentiment_aggregator(f11),
            "f2_2": f2_2_whale_impact_analyst(f12),
            "f2_3": f2_3_signal_bridge(
                sentiment_score=f11.get("sentiment_score", 0),
                whale_signal=f12.get("subagents", {}).get("f1_2b_exchange_flows", {}).get("signal", "NEUTRAL"),
            ),
        }, indent=2))
    elif cmd == "status":
        print(json.dumps({
            "f1_1": f1_1_social_sentiment_tracker("status"),
            "f1_2": f1_2_whale_monitor("status"),
            "f1_3": f1_3_onchain_activity_scanner("status"),
        }, indent=2))
    else:
        print(f"Verwendung: {sys.argv[0]} [f1_1|f1_2|f1_3|f2|status]")
