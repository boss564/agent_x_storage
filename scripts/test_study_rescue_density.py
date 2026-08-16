"""Tests for the density study script (no real simulations run)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.study_rescue_density import spearman, kruskal_wallis


def test_spearman_perfect_monotone():
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    y = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    rho, p = spearman(x, y)
    assert rho == 1.0
    assert p < 0.001


def test_spearman_negative():
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    y = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    rho, p = spearman(x, y)
    assert rho == -1.0
    assert p > 0.99    # one-sided (rho>0) must be near 1 for rho=-1


def test_spearman_uncorrelated():
    # deterministic pseudo-random sequences
    x = [(i * 7 + 3) % 100 for i in range(20)]
    y = [(i * 13 + 17) % 100 for i in range(20)]
    rho, p = spearman(x, y)
    assert -0.5 < rho < 0.5


def test_kruskal_distinct_groups_significant():
    groups = [[1.0, 2.0, 3.0, 4.0, 5.0],
              [6.0, 7.0, 8.0, 9.0, 10.0],
              [11.0, 12.0, 13.0, 14.0, 15.0]]
    p = kruskal_wallis(groups)
    assert p < 0.01


def test_kruskal_identical_groups_not_significant():
    groups = [[1.0, 2.0, 3.0, 4.0, 5.0]] * 3
    p = kruskal_wallis(groups)
    assert p > 0.05
