"""Self-test for the forbidden word scanner.

Verifies the scanner catches:
  - terms separated by underscores (total_booty, sicker_loss_eur)
  - terms inside string literals (dict keys)
  - terms in comments
  - terms in markdown

and correctly skips ALLOW-marked lines and clean files.

This is the guard that turns red if the scanner itself regresses —
a watcher that checks itself.
"""

import sys
from pathlib import Path

# Repo root is 3 levels up from this file (tests/test_forbidden_words/test_scanner.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from forbidden_word_scanner import load_config, scan_path  # noqa: E402

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_scanner_finds_underscore_and_string_violations():
    cfg = load_config(REPO_ROOT)
    violations = scan_path(FIXTURE_DIR, cfg)

    # Expected: a.py (comment), b.py (underscore), d.md (markdown), f.py (dict key)
    # Skipped: c.py (ALLOW), e.py (clean)
    found_files = {v[0].name for v in violations}
    assert found_files == {"a.py", "b.py", "d.md", "f.py"}, \
        f"Wrong files flagged: {found_files}"

    # Check specific matches
    found = {(v[0].name, v[3]) for v in violations}
    # b.py → booty (underscore-boundary), f.py → sicker (in string)
    assert ("b.py", "booty") in found, "total_booty not caught"
    assert ("f.py", "sicker") in found, "sicker_loss_pct in dict key not caught"
    assert ("a.py", "sicker") in found, "sicker in comment not caught"


def test_scanner_skips_allow_and_clean():
    cfg = load_config(REPO_ROOT)
    violations = scan_path(FIXTURE_DIR, cfg)
    found_files = {v[0].name for v in violations}
    assert "c.py" not in found_files, "ALLOW-marked line should be skipped"
    assert "e.py" not in found_files, "clean file should not be flagged"


def test_scanner_real_repo_is_clean():
    cfg = load_config(REPO_ROOT)
    # Scan the actual agents_b2g and CLAUDE.md, not the fixtures
    violations = scan_path(REPO_ROOT / "CLAUDE.md", cfg)
    violations += scan_path(REPO_ROOT / "agents_b2g", cfg)
    assert not violations, \
        f"Real repo has forbidden terms: {[(v[0].name, v[3]) for v in violations]}"


if __name__ == "__main__":
    # Standalone runner (no pytest needed)
    cfg = load_config(REPO_ROOT)
    violations = scan_path(FIXTURE_DIR, cfg)
    found_files = {v[0].name for v in violations}
    print(f"Fixture violations: {len(violations)} in {sorted(found_files)}")
    assert found_files == {"a.py", "b.py", "d.md", "f.py"}, f"Got {found_files}"
    assert "c.py" not in found_files, "ALLOW line flagged"
    assert "e.py" not in found_files, "clean file flagged"
    print("✅ Scanner self-test passed")
