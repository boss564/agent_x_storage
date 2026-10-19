#!/usr/bin/env bash
# Installer fuer das Governance-Gate (B2, Runde 95).
#
# .git/hooks/ ist NICHT versioniert. Auf einem frischen Clone ist der Hook
# sonst tot. Deshalb: duenner Wrapper + getrackter Installer.
#
# Der Wrapper ruft das GETRACKTE scripts/governance_gate.py auf — er
# enthaelt keine Kopie des Koerpers. Sonst gaebe es zwei Wahrheitsquellen
# und die lokale veraltete.
#
# WICHTIG (R95): der Gate-Block steht am ANFANG des Hooks, nicht am Ende.
# Am Ende wartet jeder Commit erst 60s auf den CLAUDE.md-Checker — und ein
# langsamer Hook wird mit --no-verify umgangen. Das Gate ist billig
# (Sekunden, lesend), es gehoert vor die teuren Pruefungen.
#
# CI (.github/workflows/governance.yml) fuehrt dasselbe Gate erneut aus:
# `git commit --no-verify` existiert, der Hook ist lokal umgehbar.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK="$ROOT/.git/hooks/pre-commit"
MARKER="# governance-gate (R95)"
BLOCK='# governance-gate (R95)
# Duenner Wrapper — ruft das getrackte Gate, keine Kopie.
# Steht am Anfang: billig vor teuer, sonst --no-verify.
python3 "$(git rev-parse --show-toplevel)/scripts/governance_gate.py" || exit 1
'

if [ ! -d "$ROOT/.git" ]; then
    echo "kein .git/ — nichts zu installieren"; exit 0
fi

if grep -q "$MARKER" "$HOOK" 2>/dev/null; then
    echo "Governance-Wrapper bereits installiert"; exit 0
fi

mkdir -p "$(dirname "$HOOK")"
TMP="$(mktemp)"
{
    head -1 "$HOOK" 2>/dev/null || echo "#!/bin/bash"
    echo ""
    printf '%s\n\n' "$BLOCK"
    tail -n +2 "$HOOK" 2>/dev/null || true
} > "$TMP"
mv "$TMP" "$HOOK"
chmod +x "$HOOK"

echo "Governance-Wrapper installiert: $HOOK"
echo "Backstop: .github/workflows/governance.yml (nicht lokal umgehbar)"
