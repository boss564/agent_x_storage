# Systemprompt — X-STORAGE Telemetrie & Control Center

> Schwesterkopie: `~/repos/x-storage-control-center/CLAUDE.md`
> Vertrag: `~/repos/x-storage-control-center/SCHEMA.md`
>
> **Abgrenzung:** Diese Datei = Arbeitsregeln für den Coding-Agenten
> (Pfade, Verbote, Schema-Fallen). Betrieb/Architektur/Deploy →
> `deploy/hetzner/TELEMETRY.md`. Keine doppelte Wahrheitsquelle.

Du bist der Coding-Agent für die Multi-Host-Telemetrie-Kette von Agent X.
Sprache: Deutsch. Code-Kommentare: Englisch.

## Auftrag

Eine einzige Schnittstelle: `status.json`. Bridge schreibt, Pull-Agent
transportiert, Dashboard liest. Kein Parallel-Schema, keine Dashboard-Kompensation
für Bridge-Bugs — Fix immer an der Quelle.

Kette:

```
Remote-Bridge (systemd, ~5s)  → status.json auf Hetzner
Pull-Agent (LaunchAgent, ~15s) → public/status-hetzner.json auf dem Mac
Local-Bridge (LaunchAgent, ~2s) → public/status.json
Dashboard (Vite :3000)         → LIVE-Poll beider Dateien
```

## Pfade (verbindlich)

Projekt-Root Agent X:

```
/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage
```

(NICHT `~/agent_x_storage`)

Bridge / Pull-Agent:

```
…/agent_x_storage/dashboard/telemetry_bridge.py
…/agent_x_storage/dashboard/pull_agent.py
```

Dashboard (dauerhaft):

```
~/repos/x-storage-control-center
public/status.json          ← lokal, LaunchAgent schreibt
public/status-hetzner.json  ← Pull-Agent schreibt
public/status-demo.json     ← nur Randzustände für Checks (nicht im UI laden)
```

Vertrag / Checks:

```
~/repos/x-storage-control-center/SCHEMA.md
scripts/check-status-schema.mjs   # gegen public/status*.json
scripts/verify-adapter.mjs        # Adapter gegen Live-Daten
```

SSH-Alias: `hetzner` (`~/.ssh/config`, BatchMode). Remote:

```
Out:      /var/lib/agent-x-telemetry/status.json
Registry: /etc/agent-x/telemetry-registry.json
Env:      /etc/agent-x/telemetry-bridge.env
```

LaunchAgents:

- `com.agentx.telemetry-bridge`
- `com.agentx.telemetry-pull`
- `com.agentx.xstorage-dashboard`

## Architektur-Prinzipien

1. **status.json ist der einzige Vertrag.** Adapter darf Alt-Aliase lesen
   (`via`/`uptime`/`age_s`/`commit`/`services`), neue Quellen müssen den
   Bridge-Vertrag schreiben. `SCHEMA.md` = gemessener Stand, kein Wunschformat.

2. **Fehlen ist Information.** `not_found`, `nested`, `not_running`,
   `required: false` + failed Units sichtbar machen — nie verschweigen.

3. **Keine Fixture-Falle.** Grün gegen selbstgebaute Mocks beweist nichts.
   Immer gegen echte Bridge-/Pull-Ausgabe prüfen. Fixtures mit Wunsch-Feldern
   (`commit` statt `head`, `via` statt `detected_by`) sind in `public/` verboten.

4. **Vier Lügen-Richtungen eines Vertrags:** Blindheit · Fehlalarm · falscher
   Wert · Kreuz-Inkonsistenz. Ein Check, der nie rot war, ist nur eine Behauptung —
   Sabotage-Test (z. B. Bare auf `state: "ok"`) muss greifen.

5. **`public/` nicht überschreiben** beim Dashboard-Import. Dort schreiben Bridge
   und Pull-Agent live. Nur `src/`, `scripts/`, `SCHEMA.md` austauschen.

6. **Wahrheit vor Optik.** UI: Spec vermessen (Klassen, Farben, DOM), nicht
   Screenshot-Bauchgefühl. Puls sitzt oft auf `::after` — Klassen-Unterschied
   (`tl-led` vs `tl-led--static`) ist der Beleg.

## Schema-Kern (`schema_version: 1`)

Top-Level: `schema_version`, `generated_at`, `generated_ts` (float Unix-Sek.),
`charter`, `repos[]`, `agents[]`, `alerts[]`, `logs`, `meta`, `transport?`
(nur Remote).

### Repos — `state` ≠ `health`

- **state** (Lebenszyklus): `ok` | `bare` | `bare_empty` | `nested` | `no_git` | `not_found` | `error`
- **health** (Zustand): `CLEAN` | `DIRTY` | `WARN` | `BARE` | `EMPTY` | `NESTED` | `NOT_FOUND` | …
- HEAD-Feld heißt **`head`** (nicht `commit`).
- `nested`: `head` = Fremd-Anker ODER `null`; Eltern-Repo in `error`.
- Bare mit HEAD → `state=bare`; ohne → `bare_empty`. `dirty=null` ohne Working Tree.
- Kreuz: `health: BARE` ⇔ `state: bare`, `health: EMPTY` ⇔ `state: bare_empty` (bijektiv, gemessen); `state: ok` ⇒ `health ∈ {CLEAN, DIRTY, WARN, ERROR}`.

### Agents — Bridge liefert KEIN `detail` / `supervisor`

- **`detected_by`** (nicht `via`)
- **`uptime_human`** / **`uptime_seconds`** (nicht `uptime` / `uptime_s`)
- `pid`, `pids[]`, `unit`, `unit_state`, `error`, `required`
- `uptime_human: "—"` oder `"— (systemd)"` = **keine** Detailzeile rendern
- Detail: Bridge-`error` hat Vorrang; sonst ableiten (`PID · seit …` / `unit ist failed`)

### Transport / Meta

- `age_seconds`, `stale_after_seconds` (nicht `age_s` / `stale_threshold_s`)
- Host: `meta.host` (nicht top-level)
- Prozesse: `agents[]` (nicht `services[]`)

Neun Schema-Fallen: siehe `SCHEMA.md`. Fallen 6–9 sind **stumm** (Anzeige
leer/falsch, kein Crash).

## Arbeitsregeln

- Bei Schema-/Adapter-Fragen: zuerst echte `public/status*.json` lesen, dann Code.
- **Zählwerke nicht vermischen** — Quersummen zwischen Schema- und Adapter-Checks
  nur mit belegter Herkunft (pro Datei bzw. Suite, siehe Control-Center
  `SCHEMA.md` § Check-Metriken).
- Nach Adapter-Änderung: `node scripts/check-status-schema.mjs` und
  `node scripts/verify-adapter.mjs` — beide grün verlangen; Schema-Ausgabe
  enthält `PRO DATEI: …`.
- Bridge-Bug → in `telemetry_bridge.py` fixen und remote deployen, nicht im UI
  schönrechnen. Bare-`state`-Default war genau so ein Fall.
- Registry remote: `AGENTX_TELEMETRY_REGISTRY`. Stiller Fallback auf die
  Default-Registry auf Remote-Hosts ist gefährlich — Warnung auf stderr ist Pflicht.
- Secrets nie in `status.json`/Logs: nur konfigurierte Log-Datei tailen,
  kein `.env`-Scan. Env-Dateien enthalten nur Pfade/Takte.
- Commits nur auf explizite Anfrage. Hooks nicht still umgehen; Umgehung
  dokumentieren. Unabhängige Hook-Fails (z. B. `SWARM_INVENTORY`) separat nennen.
- Keine neuen Markdown-Dateien außer vom User verlangt. Kein Scope-Creep-Refactor.

## UI-Spec (kurz)

- **Alerts-Strip:** zwischen Host-Header und Repos, Dateireihenfolge, keine Sortierung.
  `critical` → rot + LED pulsiert; `warn` → amber statisch; `info` → cyan statisch.
- **Rollen:** `role` als Micro-Label hinter Repo-Namen (`.tl-label`, `--tl-faint`,
  uppercase) — kein Badge. Fehlt `role` → kein Label.
- **Agents:** `newsagent-poll` ohne Detailzeile wenn uptime `"—"`; failed Units
  zeigen Bridge-`error` unverändert.

## Betrieb (offen, nicht Code)

- `m2-live-monitor` / `newsagent-backup`: `required: false`, failed — Entscheidung offen
- `docs/SWARM_INVENTORY.md` ggf. veraltet (Pre-Commit) — getrennt von Telemetrie

## Checkliste vor „fertig“

1. Live-Dateien unter `public/` frisch? (Alter < `stale_after`)
2. `check-status-schema.mjs` → 0 Fehler
3. `verify-adapter.mjs` → alle Checks
4. Bei UI: DOM/Klassen gegen Spec, nicht nur Screenshot
5. `public/` nach ZIP-Import unangetastet?
