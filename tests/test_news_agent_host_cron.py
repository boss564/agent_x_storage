"""Host-cron marker filter — no crontab mutation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.news_agent_host_cron import (
    GAP_MARKER,
    GAP_PHASE_MARKER,
    MARKER,
    PHASE_MARKER,
    PRICE_GAP_MARKER,
    gap_job_line,
    gap_phase_job_line,
    is_gap_line,
    is_gap_phase_line,
    is_managed_line,
    is_phase_line,
    is_price_gap_line,
    job_line,
    keep_other,
    keep_other_gap,
    keep_other_gap_phase,
    keep_other_phase,
    keep_other_price_gap,
    phase_job_line,
    price_gap_job_line,
    render_launchd_plist,
)


def test_marker_owns_only_tagged_lines():
    foreign = "0 * * * * /usr/bin/python3 /opt/other/news_agent.py --sync"
    ours = (
        '0 * * * * cd "/repo" && PYTHONPATH=. python3 -m services.news_agent.runner '
        f"--once >> /repo/logs/audit/news_cron.log 2>&1  {MARKER}"
    )
    legacy = (
        '0 * * * * cd "/repo" && PYTHONPATH=. python3 -m services.news_agent.runner '
        "--once >> /repo/log 2>&1  # agent_x_news_agent_host"
    )
    assert not is_managed_line(foreign)
    assert is_managed_line(ours)
    assert is_managed_line(legacy)
    kept = keep_other([foreign, ours, ours, legacy, foreign])
    assert kept == [foreign]


def test_job_line_uses_canonical_marker():
    from pathlib import Path

    line = job_line(Path("/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage"))
    assert line.endswith(MARKER)
    assert "services.news_agent.runner" in line
    assert is_managed_line(line)
    assert 'PYTHONPATH=. python3 -m' not in line
    assert '.venv/bin/python"' in line or f'"{Path(sys.executable).resolve()}"' in line


def test_launchd_plist_hourly():
    from pathlib import Path

    xml = render_launchd_plist(Path("/repo"))
    assert "com.agentx.news-agent" in xml
    assert "services.news_agent.runner" in xml
    assert "<key>StartCalendarInterval</key>" in xml
    assert "<integer>0</integer>" in xml


def test_gap_marker_is_independent():
    from pathlib import Path

    news = job_line(Path("/repo"))
    gap = gap_job_line(Path("/repo"))
    foreign = "0 0 * * * /usr/bin/python3 /opt/other/gap_detector.py"
    assert GAP_MARKER in gap
    assert gap.endswith(GAP_MARKER)
    assert not is_managed_line(gap)
    assert is_gap_line(gap)
    assert not is_gap_line(news)
    assert keep_other([news, gap, foreign]) == [gap, foreign]
    assert keep_other_gap([news, gap, foreign]) == [news, foreign]


def test_price_gap_marker_hourly_after_news():
    from pathlib import Path

    news = job_line(Path("/repo"))
    entity = gap_job_line(Path("/repo"))
    price = price_gap_job_line(Path("/repo"))
    foreign = "5 * * * * /usr/bin/python3 /opt/other/run_gap_detector.py"
    assert PRICE_GAP_MARKER in price
    assert price.endswith(PRICE_GAP_MARKER)
    assert price.startswith("5 * * * *")
    assert ' cd "' in price
    assert ".venv/bin/python" in price
    assert "Frameworks/Python.framework" not in price
    assert str(Path("/repo/scripts/run_gap_detector.py")) in price or "/scripts/run_gap_detector.py" in price
    assert 'PYTHONPATH=. python3 scripts/run_gap_detector' not in price
    assert "run_gap_detector.py" in price
    assert not is_managed_line(price)
    assert not is_gap_line(price)
    assert is_price_gap_line(price)
    assert not is_price_gap_line(news)
    assert keep_other([news, entity, price, foreign]) == [entity, price, foreign]
    assert keep_other_price_gap([news, entity, price, foreign]) == [news, entity, foreign]


def test_phase_marker_hourly_after_price_gap():
    from pathlib import Path

    news = job_line(Path("/repo"))
    price = price_gap_job_line(Path("/repo"))
    phase = phase_job_line(Path("/repo"))
    foreign = "5 * * * * /usr/bin/python3 /opt/other/news_sentiment_source.py"
    assert PHASE_MARKER in phase
    assert phase.endswith(PHASE_MARKER)
    assert phase.startswith("6 * * * *")
    assert ' cd "' in phase
    assert ".venv/bin/python" in phase
    assert "Frameworks/Python.framework" not in phase
    assert "news_sentiment_source" in phase
    assert "news_sentiment.jsonl" in phase
    assert not is_managed_line(phase)
    assert not is_price_gap_line(phase)
    assert is_phase_line(phase)
    assert not is_phase_line(foreign)
    assert keep_other_phase([news, price, phase, foreign]) == [news, price, foreign]


def test_gap_phase_marker_hourly_after_news_phase():
    from pathlib import Path

    news = job_line(Path("/repo"))
    price = price_gap_job_line(Path("/repo"))
    news_phase = phase_job_line(Path("/repo"))
    gap_phase = gap_phase_job_line(Path("/repo"))
    foreign = "7 * * * * /usr/bin/python3 /opt/other/price_gap_source.py"
    assert GAP_PHASE_MARKER in gap_phase
    assert gap_phase.endswith(GAP_PHASE_MARKER)
    assert gap_phase.startswith("7 * * * *")
    assert PRICE_GAP_MARKER not in GAP_PHASE_MARKER
    assert GAP_PHASE_MARKER not in PRICE_GAP_MARKER
    assert not is_price_gap_line(gap_phase)
    assert not is_phase_line(gap_phase)
    assert is_gap_phase_line(gap_phase)
    assert not is_gap_phase_line(foreign)
    assert not is_gap_phase_line(price)
    assert ' cd "' in gap_phase
    assert ".venv/bin/python" in gap_phase
    assert "Frameworks/Python.framework" not in gap_phase
    assert "price_gap_source" in gap_phase
    assert "price_gap.jsonl" in gap_phase
    assert keep_other_gap_phase([news, price, news_phase, gap_phase, foreign]) == [
        news,
        price,
        news_phase,
        foreign,
    ]


if __name__ == "__main__":
    test_marker_owns_only_tagged_lines()
    test_job_line_uses_canonical_marker()
    test_gap_marker_is_independent()
    test_price_gap_marker_hourly_after_news()
    test_phase_marker_hourly_after_price_gap()
    test_gap_phase_marker_hourly_after_news_phase()
    test_launchd_plist_hourly()
    print("OK: test_news_agent_host_cron 7/7")
