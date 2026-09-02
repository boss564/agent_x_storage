"""Tests for crontab-derived scheduler interval (G1 / A3)."""
from __future__ import annotations

import os
from unittest import mock

import pytest

from services.news_agent.cron_schedule import (
    interval_minutes_from_cron_line,
    measure_scheduler_interval_minutes,
    news_agent_cron_line,
    parse_interval_minutes_from_cron_fields,
    scheduler_interval_env_mismatch,
)


@pytest.mark.parametrize(
    "minute,hour,expected",
    [
        ("0", "*", 60),
        ("5", "*", 60),
        ("*/5", "*", 5),
        ("*/15", "*", 15),
        ("0", "*/2", 120),
        ("*/5", "1", None),
        ("bad", "*", None),
    ],
)
def test_parse_interval_from_cron_fields(minute, hour, expected):
    assert parse_interval_minutes_from_cron_fields(minute, hour) == expected


def test_interval_from_cron_line_hourly():
    line = '0 * * * * cd "/repo" && python3 scripts/news_agent.py --once  # AGENTX_NEWS_AGENT'
    assert interval_minutes_from_cron_line(line) == 60


def test_interval_from_cron_line_every_5():
    line = '*/5 * * * * cd "/repo" && python3 scripts/news_agent.py --once  # AGENTX_NEWS_AGENT'
    assert interval_minutes_from_cron_line(line) == 5


def test_news_agent_cron_line_picks_marker():
    lines = [
        "# other",
        '*/5 * * * * cd x && true  # AGENTX_NEWS_AGENT',
    ]
    assert news_agent_cron_line(lines) == lines[1]


def test_measure_prefers_crontab_over_env():
    lines = ['*/5 * * * * cd x && true  # AGENTX_NEWS_AGENT']
    with mock.patch(
        "services.news_agent.cron_schedule.crontab_lines", return_value=lines
    ), mock.patch.dict(os.environ, {"NEWS_SCHEDULER_INTERVAL_MINUTES": "60"}, clear=False):
        interval, source = measure_scheduler_interval_minutes()
    assert interval == 5
    assert source == "crontab"


def test_measure_env_fallback_when_no_cron():
    with mock.patch("services.news_agent.cron_schedule.crontab_lines", return_value=[]), mock.patch(
        "services.news_agent.cron_schedule.interval_minutes_from_launchd_plist",
        return_value=None,
    ), mock.patch.dict(os.environ, {"NEWS_SCHEDULER_INTERVAL_MINUTES": "15"}, clear=False):
        interval, source = measure_scheduler_interval_minutes()
    assert interval == 15
    assert source == "env:NEWS_SCHEDULER_INTERVAL_MINUTES"


def test_env_mismatch_when_crontab_differs():
    with mock.patch.dict(os.environ, {"NEWS_SCHEDULER_INTERVAL_MINUTES": "60"}, clear=False):
        msg = scheduler_interval_env_mismatch(5, "crontab")
        assert msg is not None
        assert "60" in msg
        assert "5" in msg


def test_env_mismatch_none_when_aligned():
    with mock.patch.dict(os.environ, {"NEWS_SCHEDULER_INTERVAL_MINUTES": "5"}, clear=False):
        assert scheduler_interval_env_mismatch(5, "crontab") is None


def test_get_scheduler_interval_from_system_alias():
    lines = ['*/5 * * * * cd x && true  # AGENTX_NEWS_AGENT']
    with mock.patch(
        "services.news_agent.cron_schedule.crontab_lines", return_value=lines
    ):
        from services.news_agent.cron_schedule import get_scheduler_interval_from_system

        assert get_scheduler_interval_from_system() == 5


def test_env_mismatch_ignored_for_env_source():
    with mock.patch.dict(os.environ, {"NEWS_SCHEDULER_INTERVAL_MINUTES": "60"}, clear=False):
        assert scheduler_interval_env_mismatch(60, "env:NEWS_SCHEDULER_INTERVAL_MINUTES") is None
