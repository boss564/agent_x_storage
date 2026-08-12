#!/usr/bin/env python3
"""Forbidden Word Scanner — detects withdrawn terminology in docs and code.

The list holds terms that were renamed during refactoring. When a term is
removed from code but survives in documentation, this scanner flags it.

Context-aware:
  - Whole-word matching, not substring
  - Python strings and comments stripped before scanning
  - Lines marked with an ALLOW marker are exempt
  - Reports file, line, and the offending word

Usage:
  python3 scripts/forbidden_word_scanner.py              # scan repo
  python3 scripts/forbidden_word_scanner.py CLAUDE.md    # scan one file
Exit code: 1 if violations found, 0 otherwise.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

# ── Forbidden terms (withdrawn/renamed during refactoring) ──────────────────
# Each term: the word to flag, and a hint of its replacement.
FORBIDDEN_TERMS = {
    "sicker": "friction",
    "booty": "collected_fees",
    "sicker_loss": "friction_eur",
    "sicker_rate": "friction_rate",
}

# ── File scope ──────────────────────────────────────────────────────────────

SCAN_EXTENSIONS = {".md", ".py", ".txt", ".yml", ".yaml", ".json", ".sh", ".go", ".sol"}
IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build", "lib"}
ALLOW_MARKERS = (r"^#\s*ALLOW:", r'^"""\s*ALLOW', r"^//\s*ALLOW", r"^<!--\s*ALLOW")


def strip_python_strings_and_comments(line: str) -> str:
    """Remove string literals and comments from a Python line (heuristic)."""
    # Remove single/double-quoted strings
    line = re.sub(r'(["\'])(?:(?=(\\?))\2.)*?\1', "", line)
    # Remove comments
    line = re.sub(r"#.*$", "", line)
    return line


def scan_file(path: Path) -> List[Tuple[int, str, str]]:
    """Scan one file. Returns list of (line_no, original_line, matched_term)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, PermissionError, IsADirectoryError):
        return []

    violations = []
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()

        # Exempt ALLOW-marked lines
        if any(re.search(marker, stripped) for marker in ALLOW_MARKERS):
            continue

        # For Python, strip strings and comments before matching
        candidate = strip_python_strings_and_comments(line) if path.suffix == ".py" else line

        for term, replacement in FORBIDDEN_TERMS.items():
            if re.search(rf"\b{re.escape(term)}\b", candidate, re.IGNORECASE):
                violations.append((lineno, line.strip(), term))
                break  # one report per line

    return violations


def scan_path(root: Path) -> List[Tuple[Path, int, str, str]]:
    """Scan a file or directory recursively. Returns (path, line, content, term)."""
    all_violations = []

    if root.is_file():
        for lineno, content, term in scan_file(root):
            all_violations.append((root, lineno, content, term))
        return all_violations

    for path in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.suffix not in SCAN_EXTENSIONS or not path.is_file():
            continue
        for lineno, content, term in scan_file(path):
            all_violations.append((path, lineno, content, term))

    return all_violations


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    violations = scan_path(root)

    if not violations:
        print("✅ Keine verbotenen Begriffe gefunden.")
        return 0

    print(f"🚨 {len(violations)} verbotene Begriffe gefunden:")
    for path, lineno, content, term in violations:
        replacement = FORBIDDEN_TERMS.get(term, "?")
        print(f"  📁 {path}:{lineno}")
        print(f"     → '{content}'")
        print(f"     └─ '{term}' → '{replacement}'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
