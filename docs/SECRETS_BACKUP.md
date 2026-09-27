# Secrets Backup (Agent X)

Encrypted archive of paths listed in `~/.secrets_manifest`, written to
`secrets-backup/` inside this repo (gitignored). Invoked from
`scripts/backup_agent_x.sh`.

## Create / rotate Keychain passphrase (once)

```bash
# Interactive — passphrase is NOT stored in any script.
security add-generic-password -a "$USER" -s "agent_x_secrets_backup_passphrase" -w
```

**Offline copy required:** the Keychain item dies with the Mac. Keep the same
passphrase in a password manager or on paper offline. Without it, the `.gpg`
archives are worthless after a Mac loss.

## Manifest

```bash
# Only verified-existing paths. No globs.
printf '%s\n' '.farcaster' > ~/.secrets_manifest
chmod 600 ~/.secrets_manifest
```

## Backup

```bash
bash scripts/backup_secrets.sh
# or: make backup  (calls backup_agent_x.sh → backup_secrets.sh)
```

## Restore (probe)

```bash
# Decrypt into a temp dir, then compare to live keys:
TMP=$(mktemp -d)
gpg --batch --pinentry-mode loopback \
  --passphrase "$(security find-generic-password -a "$USER" -s agent_x_secrets_backup_passphrase -w)" \
  -d secrets-backup/secrets-YYYYMMDD-HHMMSS.tar.gz.gpg \
  | tar -xzf - -C "$TMP"
diff -rq ~/.farcaster "$TMP/.farcaster" && echo RESTORE_PROBE_OK
rm -rf "$TMP"
```

Live restore to `$HOME` (destructive if files exist — prefer probe first):

```bash
gpg -d secrets-backup/secrets-….tar.gz.gpg | tar -xzf - -C ~
```

## After key rotation

Re-run `backup_secrets.sh` whenever `~/.farcaster` changes (e.g. after
`app_wallet_rotate.key` is promoted), otherwise the archive is stale exactly
when you need it.
