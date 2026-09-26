# Remote-Telemetrie — Hetzner (Pull-Modell)

> **Abgrenzung:** Diese Datei = Betrieb, Architektur, Deploy-Runbook.
> Arbeitsregeln für den Coding-Agenten (Schema-Fallen, Verbote) →
> `dashboard/CLAUDE_TELEMETRY.md`. Keine doppelte Wahrheitsquelle.

Erweitert das X-STORAGE Control Center um einen zweiten Host. Der Host liefert
seine eigene `status.json`; geholt wird sie vom Mac.

## Architektur

```
Hetzner                                          Mac
┌────────────────────────────┐                   ┌──────────────────────────────┐
│ agent-x-telemetry.service  │                   │ com.agentx.telemetry-bridge  │
│  telemetry_bridge.py       │                   │  → public/status.json        │
│  alle 5s                   │                   │                              │
│         ↓                  │   ssh cat         │ com.agentx.telemetry-pull    │
│ /var/lib/agent-x-telemetry │◄─────── 15s ──────│  → public/status-hetzner.json│
│  status.json               │                   │  + stale-Erkennung           │
└────────────────────────────┘                   └──────────────────────────────┘
```

**Warum Pull und nicht Push:** Der Host bleibt dumm — kein Zielhost, keine
Credentials Richtung Mac, kein offener Port. Fällt er aus, meldet der
Pull-Agent `REMOTE_STALE` statt einfach nichts zu liefern.

**Warum keine SSH-Einzelabfragen (`git rev-parse` pro Repo):** Ein Vertrag,
ein Code-Pfad. Die Bridge läuft auf beiden Hosts identisch, nur die Registry
unterscheidet sich. Ein zweiter Abfragemechanismus würde auseinanderdriften.

## Deploy

```bash
# Bridge + Registry + Env auf den Host, Dienst neu starten
make telemetry-deploy-hetzner
```

Das macht:
1. `install -d /opt/agent-x /etc/agent-x /var/lib/agent-x-telemetry`
2. `scp` der Bridge nach `/opt/agent-x/telemetry_bridge.py`
3. `scp` der Registry nach `/etc/agent-x/telemetry-registry.json`
4. `scp` der Env nach `/etc/agent-x/telemetry-bridge.env`
5. `systemctl restart agent-x-telemetry.service`

## Betrieb

```bash
make telemetry-pull          # einmalig holen
make telemetry-pull-status   # Transport-Zustand + Alerts anzeigen
make telemetry-pull-watch    # Vordergrund, 15s-Takt
make telemetry-test          # 43 Tests (Bridge + Pull-Agent)
```

Auf dem Host:

```bash
systemctl status agent-x-telemetry.service
journalctl -u agent-x-telemetry -f
```

## Dateien

| Datei | Ort | Zweck |
|-------|-----|-------|
| `telemetry_bridge.py` | `dashboard/` → `/opt/agent-x/` | Sammelt Status, schreibt JSON |
| `pull_agent.py` | `dashboard/` | Holt Remote-JSON, stempelt Transport |
| `telemetry-registry.hetzner.json` | `deploy/hetzner/` → `/etc/agent-x/` | Repos + Prozesse des Hosts |
| `telemetry-bridge.env.example` | `deploy/hetzner/` | Vorlage ohne Secrets; live: `/etc/agent-x/telemetry-bridge.env` (bewusst untracked, host-spezifische Pfade) |
| `agent-x-telemetry.service` | `deploy/systemd/` → `/etc/systemd/system/` | Dauerbetrieb + Restart |

**Env-Datei:** `telemetry-bridge.env` enthält host-spezifische Pfade (`/opt/…`,
`/root/…`, `/var/lib/…`) und wird **nicht** committed. Deploy kopiert die
`.example`-Vorlage; Anpassungen leben nur auf dem Host unter
`/etc/agent-x/telemetry-bridge.env`. Keine Secrets in der Vorlage.

## Stolpersteine (gemessen 2026-09-21)

Diese fünf Punkte haben beim ersten Deploy Zeit gekostet. Sie stehen hier,
damit der nächste Deploy sie überspringt.

### 1. `${VAR}` wird in `ExecStart` NICHT expandiert

```ini
# FALSCH — uebergibt das wortwoertliche "${AGENTX_TELEMETRY_INTERVAL}"
ExecStart=/usr/bin/python3 ... --interval ${AGENTX_TELEMETRY_INTERVAL}

# RICHTIG
ExecStart=/bin/sh -c 'exec /usr/bin/python3 ... --interval "${VAR:-5}"'
```

systemd ersetzt Variablen in `ExecStart=` nicht. Das Ergebnis wäre
`argparse: invalid float value` — und bei `Restart=always` eine stille
Neustartschleife.

### 2. Der Host-Checkout hat kein `dashboard/`

`/root/agent_x_storage` ist ein älterer Stand (10.09.). Die Bridge wird
deshalb nach `/opt/agent-x/` deployt, nicht in den Repo-Baum. Ein Pfad
`@AGENT_X_ROOT@/dashboard/telemetry_bridge.py` existiert dort nicht.

### 3. `dubious ownership` bei rsync-Repos

Repos vom Mac tragen eine fremde UID (`UNKNOWN:staff`). Git verweigert dann
mit `detected dubious ownership` — die Bridge meldet `error` für ein gesundes
Repo.

`git config --global --add safe.directory` löst das **nicht zuverlässig**:
Unter systemd zeigt `HOME` woanders hin, und `ProtectHome` kann `~/.gitconfig`
ausblenden.

**Lösung in der Bridge:** `_run_git()` übergibt `-c safe.directory=<repo>` bei
jedem Aufruf. Die Bridge trägt ihre Voraussetzung selbst, statt an einer
Host-Konfiguration zu hängen.

### 4. Bare-Repos brauchen `kind: bare`

`/root/newsagent-bare.git` hat keinen Arbeitsbaum. Die naive Prüfung
`(path/".git").exists()` ist dort `False` → `no_git`. `git status` bricht mit
`this operation must be run in a work tree` ab → `error`.

Beides wäre ein **falscher Fehlerzustand** für ein gesundes Repo. Die Bridge
erkennt Bare-Repos an `HEAD` + `objects/` + `refs/` und fragt nur
`git --git-dir=...` ab. `dirty=None` (nicht `False`) — ein Bare hat keinen
Arbeitsbaum und damit keinen Dirty-Zustand.

### 5. Unit-Namen stehen nicht in der Kommandozeile

`pgrep -f newsagent-poll.service` findet nichts, obwohl der Dienst läuft.
Timer- und oneshot-Dienste haben zwischen zwei Läufen ohnehin keinen Prozess.

**Lösung:** Die Registry kann `unit: <name>` setzen. Findet `pgrep` nichts,
fragt die Bridge `systemctl is-active` und mappt: `active` → `running`,
`failed` → `failed` (critical Alert), `inactive` → `not_running`.

**Falle:** `is-active` liefert `failed` mit **RC 3** — der Zustand steht auf
stdout, nicht im Exit-Code. Wer `rc != 0` als Fehler wertet, verliert den Befund.

## Registry-Format

`AGENTX_TELEMETRY_REGISTRY` zeigt auf eine JSON:

```json
{
  "repos": [
    {"name": "hub", "path": "/root/agent_x_storage", "role": "hub"},
    {"name": "bare", "path": "/root/newsagent-bare.git",
     "role": "git-remote", "kind": "bare"}
  ],
  "processes": [
    {"name": "poll", "pattern": "newsagent-poll",
     "unit": "newsagent-poll.service", "required": true}
  ]
}
```

| Feld | Werte | Bedeutung |
|------|-------|-----------|
| `kind` | `worktree` (Default), `bare`, `package` | Bare = ohne Arbeitsbaum |
| `unit` | systemd-Unit-Name | Fallback, wenn `pgrep` nichts findet |
| `required` | `true` (Default), `false` | `true` → `critical` Alert bei Ausfall |

Fehlt die Datei oder ist sie kaputt, greift die eingebaute Default-Registry
(Mac-Sicht). Eine **leere** Liste ist kein Wunsch, sondern ein stiller Ausfall
— auch dann greift der Default.

## Live-Befunde (21.09.2026)

| Eintrag | Zustand | Interpretation |
|---------|---------|----------------|
| `hetzner-agent_x_storage` | `ok` / DIRTY, 6 uncommitted | Älterer Host-Stand |
| `hetzner-newsagent` | `ok` / WARN, 6 untracked | Untracked Dateien, kein Verlustrisiko |
| `hetzner-newsagent-bare` | `ok` / BARE, `c2ff340` | Gesund |
| `newsagent-poll.service` | `running` (systemd) | Läuft |
| `m2-live-monitor.service` | `failed` (systemd) | **Befund: dokumentiert, aber tot** |
| `newsagent-backup.service` | `failed` (systemd) | **Befund: dokumentiert, aber tot** |

Die zwei `failed`-Units sind kein Schönheitsfehler, sondern der Zweck des
Systems: Sie stehen wochenlang sichtbar, bis jemand entscheidet — Dienst
reparieren oder Erwartung streichen.

## Sicherheit

- **Keine Secrets in der Remote-`status.json`.** Der Log-Tail liest
  ausschließlich die konfigurierte Datei (`AGENTX_TELEMETRY_LOG`), es gibt
  kein Verzeichnis-Scanning. Geprüft: `news_cron.log` enthält keine
  Key-/Token-/Password-Muster (0 Treffer).
- **Nie auf `settings.env` / `.env` zeigen.** Die `status.json` wandert über
  SSH und erscheint im Browser-Kontext.
- **Kein offener Port.** Der Transport ist `ssh cat` in Pull-Richtung; der
  `--serve`-Endpunkt bleibt auf dem Host aus.
- **Service-Hardening:** `NoNewPrivileges`, `PrivateTmp`,
  `ProtectSystem=strict`, `ProtectHome=read-only`, `ReadWritePaths` nur auf
  `/var/lib/agent-x-telemetry`.
