#!/usr/bin/env bash
# Aktiviert die versionierte Wand (R106, Buchung 5).
#
# Befund aus R105: die Hook-DATEI lag im Baum (githooks/pre-commit),
# aber der Schalter (core.hooksPath) lag in .git/config — unversioniert.
# Ein frischer Clone hatte die Datei und keine Wand.
#
# Dieses Skript IST die Aktivierung und liegt im Baum. make init ruft es.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
git config core.hooksPath githooks
test -x githooks/pre-commit || { echo "pre-commit nicht ausfuehrbar"; exit 1; }
akt="$(git config --get core.hooksPath || true)"
[ "$akt" = "githooks" ] || { echo "Aktivierung fehlgeschlagen: '$akt'"; exit 1; }
echo "Wand aktiv: core.hooksPath=githooks (Datei: githooks/pre-commit)"
