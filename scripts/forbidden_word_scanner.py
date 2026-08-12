#!/usr/bin/env python3
"""Forbidden Word Scanner — detects withdrawn terminology in docs and code.

Reads config/forbidden_words.yaml (falls PyYAML installiert, sonst interne
Defaults). Context-aware: whole-word matching, Python strings/comments
stripped, ALLOW-marker lines exempt, file whitelist supported.

Usage:
  python3 scripts/forbidden_word_scanner.py              # scan repo
  python3 scripts/forbidden_word_scanner.py CLAUDE.md    # scan one file
Exit code: 1 if violations found, 0 otherwise.
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# ── Fallback-Defaults (genutzt, wenn PyYAML fehlt oder keine Config) ────────

DEFAULT_TERMS: Dict[str, str] = {
    "sicker": "friction",
    "booty": "collected_fees",
    "sicker_loss": "friction_eur",
    "sicker_rate": "friction_rate",
}

DEFAULT_EXTENSIONS = {".md", ".txt", ".py", ".yml", ".yaml", ".json", ".sh", ".go", ".sol"}
DEFAULT_IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "dist", "build", "lib"}
DEFAULT_MARKERS = (r"^#\s*ALLOW:", r'^"""\s*ALLOW', r"^//\s*ALLOW", r"^<!--\s*ALLOW")


def load_config(root: Path, config_path: Path | None = None) -> Dict:
    """Load config (default config/forbidden_words.yaml), falling back to defaults.

    An explicit config_path may be passed (e.g. the self-test's minimal config).
    """
    config_path = config_path or (root / "config" / "forbidden_words.yaml")
    terms = dict(DEFAULT_TERMS)
    extensions = set(DEFAULT_EXTENSIONS)
    ignore_dirs = set(DEFAULT_IGNORE_DIRS)
    markers = DEFAULT_MARKERS
    whitelist = set()

    if config_path.exists():
        try:
            import yaml
        except ImportError:
            yaml = None
        if yaml is not None:
            try:
                cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                if cfg.get("forbidden_terms"):
                    terms = dict(cfg["forbidden_terms"])
                if cfg.get("scan_extensions"):
                    extensions = set(cfg["scan_extensions"])
                if cfg.get("ignore_dirs"):
                    ignore_dirs = set(cfg["ignore_dirs"])
                if cfg.get("allowed_markers"):
                    markers = tuple(cfg["allowed_markers"])
                if cfg.get("whitelist_files"):
                    whitelist = set(cfg["whitelist_files"])
            except Exception:
                pass  # YAML parse error → keep defaults

    return {
        "terms": terms,
        "extensions": extensions,
        "ignore_dirs": ignore_dirs,
        "markers": markers,
        "whitelist": whitelist,
    }


def scan_file(path: Path, cfg: Dict) -> List[Tuple[int, str, str]]:
    """Scan one file. Returns list of (line_no, original_line, matched_term).

    Scans the FULL line (comments and string literals included) — those are
    exactly where terminology drift survives. Only ALLOW-marker lines are exempt.
    Word boundaries treat underscore as a separator: (?!...)[A-Za-z0-9] lookarounds.
    """
    if path.name in cfg["whitelist"]:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, PermissionError, IsADirectoryError):
        return []

    violations = []
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if any(re.search(marker, stripped) for marker in cfg["markers"]):
            continue
        # Skip very long lines (e.g. base64 blobs) to avoid false positives
        if len(stripped) > 10000:
            continue
        for term in cfg["terms"]:
            # Lookarounds treat underscore as a boundary: total_booty and
            # sicker_loss_eur are caught, but "sauber" is not.
            if re.search(
                rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])",
                line, re.IGNORECASE,
            ):
                violations.append((lineno, line.strip(), term))
                break
    return violations


def scan_path(root: Path, cfg: Dict) -> List[Tuple[Path, int, str, str]]:
    all_violations = []
    if root.is_file():
        for lineno, content, term in scan_file(root, cfg):
            all_violations.append((root, lineno, content, term))
        return all_violations
    for path in root.rglob("*"):
        if any(part in cfg["ignore_dirs"] for part in path.parts):
            continue
        if path.suffix not in cfg["extensions"] or not path.is_file():
            continue
        for lineno, content, term in scan_file(path, cfg):
            all_violations.append((path, lineno, content, term))
    return all_violations


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    cfg = load_config(root)
    violations = scan_path(root, cfg)

    if not violations:
        print("✅ Keine verbotenen Begriffe gefunden.")
        return 0

    print(f"🚨 {len(violations)} verbotene Begriffe gefunden:")
    for path, lineno, content, term in violations:
        replacement = cfg["terms"].get(term, "?")
        rel = path.relative_to(root) if root.is_dir() else path.name
        print(f"  📁 {rel}:{lineno}")
        print(f"     → '{content}'")
        print(f"     └─ '{term}' → '{replacement}'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
