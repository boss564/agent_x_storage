# Messperiode — Start-Sequenz (Pre-Flight → KeepAlive)

Charter: `diagnostic_only=true`, `live_execution=false`, `order_send=false`.

## Volume- / Launchd-Regel (kritisch)

**Muster Exit 78 / EPERM:** Jeder LaunchAgent, der auf `/Volumes/THX_OS_ULTRA*` schreibt
(Logs, JSONL, SQLite, Offset), scheitert mit `last exit code = 78: EX_CONFIG` bzw.
`Operation not permitted` (sealed / Volume-Policy). Code und Freeze dürfen dort **gelesen**
werden; Runtime-Writes immer unter `~/Library/…`. Gilt für künftige Jobs genauso.

| Artefakt | Pfad |
|---|---|
| Code, Freeze, Policy, venv | `/Volumes/THX_OS_ULTRA/Users/…/agent_x_storage` (read) |
| `news_scores.jsonl` | `~/Library/Application Support/agentx/news_scores.jsonl` |
| `shadow.db` + Tail-Offset | `~/Library/Application Support/agentx/shadow_live/` |
| Logs | `~/Library/Logs/agentx-shadow/` |

**Pfad-Split (Auswertung):** DB und JSONL der Messperiode liegen **nur** unter
`~/Library/Application Support/agentx/` — nicht unter `data/` auf THX (Aug-Altbestand /
EPERM-Falle). `sqlite3 …/shadow_live/shadow/shadow/shadow.db`.

News-Agent und Runner teilen denselben Application-Support-JSONL-Pfad.

## Messperiode 2026-10-04 — Run-Notiz

- Mess-Commit in `config_json`: **`87fba94d`** (`run_id=7`).
- **`run_id` 1–6 ausschließen:** Restart-Spam beim KeepAlive-Warmup (pydantic/WS-Fixes).
  Auswertung, Gates und Tag-7/21 nur ab **`run_id >= 7`**.

## Vorbedingungen

1. Freeze + Policy unter `order_execution_engine/ops/` (committed).
2. Working tree clean; Mess-Commit = `git rev-parse --short HEAD`.
3. `com.agentx.news-agent` letzter Exit **0** (nicht 78).
4. NTP am Host.

## Start + Verifikationspunkte

```bash
REPO="/Volumes/THX_OS_ULTRA/Users/olivermueller/agent_x_storage"
APP="$HOME/Library/Application Support/agentx"
cd "$REPO"
mkdir -p "$APP/shadow_live" ~/Library/Logs/agentx-shadow
# Wrapper muss lokal liegen (Exec von THX → launchd 126)
cp -f scripts/news_agent_launchd.sh "$APP/news_agent_launchd.sh"
chmod +x "$APP/news_agent_launchd.sh"

# 0) News-Agent → Application Support JSONL
cp -f scripts/com.agentx.news-agent.plist ~/Library/LaunchAgents/
launchctl bootout "gui/$(id -u)/com.agentx.news-agent" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.agentx.news-agent.plist
launchctl kickstart -k "gui/$(id -u)/com.agentx.news-agent"
sleep 5
launchctl list | grep news-agent    # … 0 com.agentx.news-agent
stat -f '%Sm %z' "$APP/news_scores.jsonl"

# 1) Pre-Flight
PYTHONPATH=. python3 order_execution_engine/ops/preflight_check.py \
  --expect-commit "$(git rev-parse --short HEAD)" \
  --data-root "$APP/shadow_live" \
  --news-jsonl "$APP/news_scores.jsonl"

# 2) Shadow-Runner KeepAlive (--tail-from-end im plist)
cp -f order_execution_engine/ops/com.agentx.shadow-runner.plist ~/Library/LaunchAgents/
launchctl bootout "gui/$(id -u)/com.agentx.shadow-runner" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.agentx.shadow-runner.plist

# 3) Sofort: Prozess + telemetry_runs + WS = 2 Freeze-IDs
sleep 5
launchctl list | grep shadow-runner
tail -40 ~/Library/Logs/agentx-shadow/shadow-runner.log
python3 - <<PY
import json, sqlite3
from pathlib import Path
db = Path("$APP/shadow_live/shadow/shadow/shadow.db")
conn = sqlite3.connect(db)
rid, commit, cfg = conn.execute(
    "SELECT run_id, git_commit, config_json FROM telemetry_runs ORDER BY run_id DESC LIMIT 1"
).fetchone()
c = json.loads(cfg)
print("run_id", rid, "git_commit", commit)
assert float(c["max_news_age_s"]) == 3900
assert len(c["ws_token_ids"]) == 2
print("ws_token_ids", c["ws_token_ids"])
print("OK")
PY

# 4) Preflight --after-start
PYTHONPATH=. python3 order_execution_engine/ops/preflight_check.py --after-start \
  --expect-commit "$(git rev-parse --short HEAD)" \
  --data-root "$APP/shadow_live" \
  --news-jsonl "$APP/news_scores.jsonl"

# 5) Erster Stunden-Batch (:00): JSONL wächst → Dedup → Dispatches
```

## Tag-1-Gates (nach erstem Batch)

| Gate | Erwartung |
|---|---|
| `no_book` | nahe 0 (2 Freeze-Märkte subscribed); sonst WS |
| `news_too_old` | nicht ~100 % |
| `unresolved_asset:empty_list` | erwartbares Rauschen (leere `target_assets`) |
| `unresolved_asset:mapping_miss` | Stillverlierer — News liefert Asset, Freeze kennt es nicht |
| `STALE_SNAPSHOT` | ≈ 0 |
| `TELEMETRY_RECONCILIATION` | `PROVISIONAL_LEDGER_CONSISTENT` solange der Lauf offen ist (0) — **nicht blockierend**, weil das Schema kein `closed_at` hat und der Fall damit immer gilt; sonst `LEDGER_CONSISTENT`: (0) Verkehr vorhanden ⇒ (1) `telemetry_rows == decision_seq-keyed` (Korollar aus (3)+(3b)), (3) `unattributed == 0` (Erfolg ohne Zeile), (3b) `orphan_rows == 0` (Zeile ohne Erfolg — die Überbehauptung), (4) `dispatched_success == Σ reject_reasons` (sonst RED). `delivered == 0` ist Warnung, kein Blocker. |
| `DELIVERY` (zweites Etikett, eigenes Feld) | `DELIVERING` nur wenn ein Fill im Fenster **und** jünger als `FRESH_FILL_S` (2 Takte) · `DELIVERY_STALLED_SINCE`: `dispatched_success > 0`, aber kein frischer oder kein genehmigter Fill · `NO_TRAFFIC`: keine Erfolge. Spricht über den **Dienst**, nicht über den Ledger — deshalb nicht im Ledger-Etikett. Daneben: `wired` (Import in Produktionscode) und `read_by` (Skript, das die Urteilszeile liest). |
| `fills_total` / `fill_ratio` | `fills` hat **keine Statusspalte** — Vollständigkeit steht nur in `telemetry.status`. `fill_ratio = sum(executed)/sum(requested)` über Fill-Zeilen: die Zahl, die den Dienst beschreibt, nicht `COUNT(*)`. Bei seq 12: fill_ratio 1,0 (5 von 5), Order-Anteil 0,05 (5 von 100). |
| `reason` | Adresse des Urteils (§5.4bk): welcher der sechs RED-Zweige — `(0) underrun`, `(1) schreibseite`, `(2) schluessel`, `(3) unattributed`, `(3b) orphan`, `(4) bilanz`. Erscheint nur bei RED; `verdict: RED` ohne Bedingung wäre ein Zustand, keine Aussage. |
| `blocking` | **Wer** blockt (§5.4br): `ledger` bei RED, `none` bei GRÜN — immer gesetzt. Bei fehlendem Aufrufer `ledger (unenforced)` (§5.4ca): ohne Aufrufer beschreibt der Wert, was blockieren *würde*. Nicht zu verwechseln mit `wired` (Import in Produktionscode) oder `read_by` (Skript, das die Urteilszeile liest). |
| `anchored at` | `blob:<12>` (§5.4cg) — der Typ steht im Feld, nicht im Format. `gate commit:` trägt beide (`commit:blob`). |
| `fills_matched` | Die Zahl, die der JOIN `fills ⋈ telemetry` gesehen hat (§5.4cc). `None` bei fehlender `telemetry`-Tabelle: dann steht `fills_total` allein und ohne Bezug — die Ausgabe vermerkt es. |
| `unattributed` | Dispatches ohne Telemetriezeile, **run-scharf** (§5.4cd): offener Run ordinal in seinem Fenster, frühere Runs im Fenster als `nicht zuordenbar` (≈200–300, nicht 4). `origin` nennt `telemetry_rows` und `unattributed` getrennt — die Differenz ist keine Herkunft (war −266). |
| `reject_context` | 200 Bytes im Ablehnungsmoment (§5.4bt), statt 5,6 Mio Zeilen Snapshot-Tabelle. `branch` ist Pflicht: 1160 `NEUTRAL_SIGNAL` (Schwelle `theta`, Policy), 1174 `NO_SNAPSHOT` (Datenfluß), 1185 `EMPTY_SIDE` / `SIDE_NOT_DELIVERED` (Markt vs. Auslassung, §5.4cb). |
| `theta` | Kalibrierungsparameter, nicht Zustand (§5.4by): `|sentiment| < 0.1` → NEUTRAL → kein Orderpfad. Gewählt, nicht kalibriert — **nicht senken, solange die Delivery-Kette stillsteht** (§5.4bz). |
| `open_for` / `stalled_for` | Zwei Achsen, zwei Dauern (§5.4bl): `open_for` gegen `started_at` (der Lauf), `stalled_for` gegen jetzt (der Dienst). Beide richtig — die Achse steht im Feldnamen, weil ein `alter` ohne Achse in dieser Akte zweimal falsch war. |
| `reject_detail` | `INVALID_PRICE` hat drei Ursachen an drei Code-Stellen (§5.4bm): `NEUTRAL_SIGNAL` (Strategie), `NO_SNAPSHOT` (Zuführung), `EMPTY_SIDE` (Liquidität). Optional; NULL heißt „vor dem Feld geschrieben", nicht „keine Ursache". |
| `fk order_id` | `telemetry_seq` ist in allen 361 Dispatches `NULL`; die Zuordnung läuft über `decision_seq` — eine Reihenfolge-Annahme über zwei Reihenfolgen. `order_id` paart als echter FK, ist aber nur in 8/34 Zeilen gesetzt. **Der Ledger kann grün sein und permutiert.** |
| `telemetry_fill_metrics` | bei Fills |
| Dedup | 0 Doppel-`item_id` |

`TELEMETRY_RECONCILIATION` in `preflight_check.py` (`--min-run-id 7`). Erfolgspfad =
`dispatched_signals` ab `run_id=7.started_at` **ohne** `bridge_discards`-Zeile
(Claim vor Resolve zählt unresolved/no_book nicht als Dispatch-Erfolg).

**Abgleich Doku ↔ Code (§5.4x).** Die Zeile in der Tabelle oben war die Absicht
vom 04.10. und steht seit dem dort; der Code hat sich seither zweimal geändert
(`162a89e7`: `LEDGER_CONSISTENT` statt `GREEN`; `0.0`: `MIN_TELEMETRY_ROWS`
gestrichen, Null-Bedingung). Der Abgleich ist jetzt ein Zeuge:
`test_start_md_gate_line_matches_criterion` liest die Zeile aus dieser Datei und
verlangt, daß Label und Bedingungen mit `_gate_criterion()` übereinstimmen.
Vorher: `0` Abweichungen gemessen, weil nie gemessen wurde.

`CLAIM_DISCARD_ACCOUNTING`: `claims = success + post_claim` und
`discards = post_claim + pre_claim` (gleiche Zeitfenster). Divergenz der
beiden post-Views → RED (Schreiblücke). Run-8: 8 = 1+7, 11 = 7+4 (`empty_list`).

Freeze-Ende 2026-11-01 — Tag-7 Settle-Check. Config nicht anfassen.

## Tag-7-Review (Risiken, nicht ändern während Messung)

Preflight für Run-8-Bilanz explizit: `--min-run-id 8` (Default `7` inkl. 10:00-Alt-`unresolved` vor Run-8-Start).

| Risiko | Stand Run-8 (Stand 2026-10-05) |
|---|---|
| Erfolgspfad-Quote | 1 Dispatch vs. 11 Verwürfe ≈ 8 % — Fill-Pfad bleibt wahrscheinlich unbelegt |
| `STALE`/`no_book` vs. 2-s-Fenster | `telemetry` speichert kein `book_age_ms`; bei STALE nur `latency_ms≈0` → Buch-Alter war bindend, exakter ms-Wert fehlt. `book_age_ms`-Logging erst nach Messperiode |
| Working-Tree-Runner | KeepAlive-Restart lädt aktuellen Tree, nicht gepinnten Commit — während Messung kein Checkout/Code-Edit |
