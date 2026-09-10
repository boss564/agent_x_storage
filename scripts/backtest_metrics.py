"""Trade-level Sharpe and related backtest statistics.

Per-trade returns are decimal fractions (0.0019 = 19 bps).

Wrong pattern (do not use):
  mean/std * sqrt(365 * 24 * 4)  # bar-count annualization on sparse trades

Correct:
  sharpe_per_trade = mean / std
  sharpe_annualized = sharpe_per_trade * sqrt(trades_per_year)
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def years_from_timestamps(series: pd.Series) -> float:
    """Calendar years spanned by timestamp series (minimum 1 day)."""
    t0 = pd.Timestamp(series.iloc[0])
    t1 = pd.Timestamp(series.iloc[-1])
    days = max((t1 - t0).total_seconds() / 86400.0, 1.0)
    return days / 365.25


def trade_sharpe_stats(
    net_returns: np.ndarray | list[float],
    *,
    years: float | None = None,
) -> dict[str, float]:
    """
    Compute Sharpe from per-trade decimal returns.

    Returns sharpe_per_trade (mean/std) and optional sharpe_annualized
    using sqrt(trades_per_year), not bar frequency.
    """
    net = np.asarray(net_returns, dtype=float)
    n = len(net)
    if n == 0:
        return {
            "sharpe_per_trade": 0.0,
            "sharpe_annualized": 0.0,
            "mean": 0.0,
            "std": 0.0,
            "n_trades": 0.0,
        }
    mu = float(np.mean(net))
    std = float(np.std(net, ddof=1)) if n > 1 else 0.0
    sharpe_pt = mu / std if std > 0 else 0.0
    sharpe_ann = sharpe_pt
    if years is not None and years > 0:
        trades_per_year = n / years
        sharpe_ann = sharpe_pt * float(np.sqrt(trades_per_year))
    return {
        "sharpe_per_trade": sharpe_pt,
        "sharpe_annualized": sharpe_ann,
        "mean": mu,
        "std": std,
        "n_trades": float(n),
    }


def metrics_from_trades(
    trades: list[dict[str, Any]],
    *,
    years: float | None = None,
) -> dict[str, float]:
    """Aggregate trade list into PnL metrics including corrected Sharpe."""
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "e_pnl_gross": 0.0,
            "e_pnl_net": 0.0,
            "sharpe_per_trade": 0.0,
            "sharpe_annualized": 0.0,
            "profit_factor": 0.0,
        }

    net_pnls = np.array([t["net_pnl"] for t in trades])
    wins = net_pnls[net_pnls > 0]
    losses = net_pnls[net_pnls < 0]
    gross_wins = float(np.sum(wins)) if len(wins) else 0.0
    gross_losses = float(np.abs(np.sum(losses))) if len(losses) else 0.0
    sharpe = trade_sharpe_stats(net_pnls, years=years)

    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "e_pnl_gross": float(np.mean([t["gross_pnl"] for t in trades])),
        "e_pnl_net": sharpe["mean"],
        "sharpe_per_trade": sharpe["sharpe_per_trade"],
        "sharpe_annualized": sharpe["sharpe_annualized"],
        "profit_factor": (gross_wins / gross_losses) if gross_losses > 0 else 999.0,
    }


def assign_funding_episode_ids(
    funding_rates: np.ndarray | pd.Series,
    threshold: float,
) -> np.ndarray:
    """
    Label contiguous runs with |fr| >= threshold (one squeeze episode per id).

    Bars below threshold get episode_id = -1.
    """
    fr = np.asarray(funding_rates, dtype=float)
    ids = np.full(len(fr), -1, dtype=int)
    ep = 0
    in_ep = False
    for i, val in enumerate(fr):
        if np.isnan(val) or abs(val) < threshold:
            if in_ep:
                ep += 1
                in_ep = False
            continue
        if not in_ep:
            in_ep = True
        ids[i] = ep
    return ids


def metrics_from_episodes(
    trades: list[dict[str, Any]],
    *,
    years: float | None = None,
) -> dict[str, float]:
    """
    Primary M2a inference: one net return per episode (first trade in episode).

    SE clustered at episode level: std(episode_means) / sqrt(n_episodes).
    """
    if not trades:
        return {
            "episodes": 0,
            "trades": 0,
            "win_rate_episode": 0.0,
            "e_pnl_net_episode": 0.0,
            "se_pnl_episode": 0.0,
            "sharpe_episode": 0.0,
            "sharpe_episode_annualized": 0.0,
            "profit_factor_episode": 0.0,
        }

    tdf = pd.DataFrame(trades)
    if "episode_id" not in tdf.columns:
        raise ValueError("trades require episode_id for episode metrics")

    ep_df = tdf.groupby("episode_id", as_index=False).first()
    ep_net = ep_df["net_pnl"].to_numpy(dtype=float)
    ep_gross = ep_df["gross_pnl"].to_numpy(dtype=float)
    n_ep = len(ep_net)
    wins = ep_net[ep_net > 0]
    losses = ep_net[ep_net < 0]
    gross_wins = float(np.sum(wins)) if len(wins) else 0.0
    gross_losses = float(np.abs(np.sum(losses))) if len(losses) else 0.0
    sharpe = trade_sharpe_stats(ep_net, years=years)
    se = float(np.std(ep_net, ddof=1) / np.sqrt(n_ep)) if n_ep > 1 else 0.0

    return {
        "episodes": n_ep,
        "trades": len(trades),
        "win_rate_episode": float(np.mean(ep_net > 0)),
        "e_pnl_net_episode": sharpe["mean"],
        "e_pnl_gross_episode": float(np.mean(ep_gross)),
        "se_pnl_episode": se,
        "sharpe_episode": sharpe["sharpe_per_trade"],
        "sharpe_episode_annualized": sharpe["sharpe_annualized"],
        "profit_factor_episode": (gross_wins / gross_losses) if gross_losses > 0 else 999.0,
    }
