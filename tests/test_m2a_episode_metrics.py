"""Tests for M2a episode-level metrics."""
from scripts.backtest_metrics import assign_funding_episode_ids, metrics_from_episodes


def test_assign_funding_episode_ids_contiguous():
    fr = [0.0, 0.002, 0.002, 0.0, -0.002, -0.002, 0.0]
    ids = assign_funding_episode_ids(fr, 0.001)
    assert list(ids) == [-1, 0, 0, -1, 1, 1, -1]


def test_metrics_from_episodes_one_per_episode():
    trades = [
        {"episode_id": 0, "net_pnl": 0.01, "gross_pnl": 0.012},
        {"episode_id": 1, "net_pnl": -0.005, "gross_pnl": -0.003},
        {"episode_id": 1, "net_pnl": 0.02, "gross_pnl": 0.022},  # ignored (not first)
    ]
    m = metrics_from_episodes(trades)
    assert m["episodes"] == 2
    assert m["trades"] == 3
    assert abs(m["e_pnl_net_episode"] - 0.0025) < 1e-9


def test_metrics_from_episodes_se():
    trades = [{"episode_id": i, "net_pnl": 0.001, "gross_pnl": 0.002} for i in range(5)]
    m = metrics_from_episodes(trades)
    assert m["episodes"] == 5
    assert m["se_pnl_episode"] == 0.0
