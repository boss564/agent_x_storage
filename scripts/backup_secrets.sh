#!/usr/bin/env bash
# backup_secrets.sh — encrypted backup of paths listed in ~/.secrets_manifest
#
# Passphrase: macOS Keychain service "agent_x_secrets_backup_passphrase"
#   (never in this script; store a second copy offline — Keychain dies with the Mac)
# Manifest:   $HOME/.secrets_manifest — one relative path per line, no globs
# Output:     <repo>/secrets-backup/secrets-YYYYMMDD-HHMMSS.tar.gz.gpg
#
# Missing manifest entry → WARN + exit 1 (no silent skip).
set -euo pipefail

REPO="${REPO:-/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage}"
MANIFEST="${SECRETS_MANIFEST:-${HOME}/.secrets_manifest}"
OUT_DIR="${SECRETS_BACKUP_DIR:-${REPO}/secrets-backup}"
KEYCHAIN_SERVICE="${SECRETS_KEYCHAIN_SERVICE:-agent_x_secrets_backup_passphrase}"
GPG="${GPG:-$(command -v gpg)}"

die() { echo "ERROR: $*" >&2; exit 1; }
warn() { echo "WARN: $*" >&2; }

[ -n "${GPG}" ] && [ -x "${GPG}" ] || die "gpg not found (brew install gnupg)"
[ -f "${MANIFEST}" ] || die "manifest missing: ${MANIFEST}"

PASS="$(security find-generic-password -a "${USER}" -s "${KEYCHAIN_SERVICE}" -w 2>/dev/null)" \
  || die "Keychain item missing: service=${KEYCHAIN_SERVICE} account=${USER}
  Create once: security add-generic-password -a \"\$USER\" -s \"${KEYCHAIN_SERVICE}\" -w"

paths=()
missing=0
while IFS= read -r line || [ -n "${line}" ]; do
  # trim CR; skip blanks and comments
  line="${line%$'\r'}"
  case "${line}" in
    ''|\#*) continue ;;
  esac
  case "${line}" in
    *[\*\?\[]*)
      die "Glob not allowed in manifest (use explicit paths): ${line}"
      ;;
  esac
  # refuse absolute / traversal — paths are relative to $HOME
  case "${line}" in
    /*|*/../*|../*|*/..)
      die "Path must be relative to \$HOME, no traversal: ${line}"
      ;;
  esac
  target="${HOME}/${line}"
  if [ ! -e "${target}" ]; then
    warn "Manifest entry missing: ${target}"
    missing=1
    continue
  fi
  paths+=("${line}")
done < "${MANIFEST}"

if [ "${missing}" -ne 0 ]; then
  die "One or more manifest entries missing — refusing silent skip."
fi
if [ "${#paths[@]}" -eq 0 ]; then
  die "No paths to back up (empty manifest after filtering)."
fi

mkdir -p "${OUT_DIR}"
chmod 700 "${OUT_DIR}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${OUT_DIR}/secrets-${STAMP}.tar.gz.gpg"

# Encrypt: passphrase on fd 3 so stdin stays free for tar→gpg stream
# shellcheck disable=SC2094
tar -C "${HOME}" -czf - "${paths[@]}" \
  | "${GPG}" --batch --yes --pinentry-mode loopback \
      --passphrase-fd 3 --symmetric --cipher-algo AES256 \
      -o "${OUT}" 3<<< "${PASS}"

chmod 600 "${OUT}"
unset PASS
echo "secrets backup: ${OUT}"
