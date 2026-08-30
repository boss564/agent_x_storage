# News-Feed Structural Liveness — Pre-Reg

**Status:** VALIDIERT (2026-08-30) — Strang geschlossen  
**Erstellt:** 2026-08-30  
**Strang:** Einzelstrang, eine gemessene Parse-Lücke. Kein Subsystem.  
**Parent:** [`NEWS_AGENT.md`](NEWS_AGENT.md) · `agents_b2g/news/feed_health.py` · `agents_b2g/news/scraper.py`  
**Liveness-Inventar:** [`AUDIT_WRITER_LIVENESS.md`](AUDIT_WRITER_LIVENESS.md) (Instanz 3)  
**Außerhalb:** `prototypes/raas_paper_trading/*` (Paper-Exit, Feed-Gap, WORM) bleibt unberührt.  
**Closing:** Commit `bbb18dd5` · Gate §5 S1–S7 (13/13) · Freeze §6 Live `run_marker` 2026-08-30T17:42:15Z — CoinDesk/Cointelegraph/BinanceCMS `structure_ok=true` + `ok` · H1/H2 live-Randfälle nicht beobachtet (Smoke S1/S2 tragen die Logik)

---

## 0. Abgrenzung — was dies NICHT ist

Die bestehenden Invarianten greifen bereits und werden **nicht** neu gebaut:

| # | Invariante | Ort |
|---|------------|-----|
| 1 | Transport-Health (`ok`/`quiet`/`degraded`/`dead`) | `fetch_feed_report` → `feed_health` |
| 2 | Status-Aggregation (`FEED_SILENT` / `DEGRADED` / `WRITER_STALE`) | `services/news_agent/runner.py` |
| 3 | Dedup (`item_id = MD5(source\|link)`, URL zusätzlich im Processor) | `scraper.item_id` · `processor` |
| 4 | Run-Marker-Liveness + 72h Quiet→Stale | `liveness.py` (`QUIET_STALE_AFTER_S` frozen) |
| 5 | Charter (`diagnostic_only`, `live_execution=false`, `order_send=false`) | Processor / JSONL |
| 6 | Isolation (Host-Cron, kein Cluster-Patch) | `NEWS_AGENT.md` |

Diese Pre-Reg schließt **eine** gemessene Lücke in der Zuordnung `entries=0 → quiet` und sonst nichts.

---

## 1. Die gemessene Lücke

```text
status=200 ∧ bozo=0 ∧ entries=0  ⇒  health=quiet   (immer)
```

`bozo` ist nur `ET.ParseError`. `parse_rss_xml` wirft bei wohlgeformtem Nicht-Feed **nicht**. Nach erfolgreichem `ET.fromstring` fehlt jede Strukturprüfung. Damit gilt:

```text
„legitim leerer Feed“  ≡  „wohlgeformter Müll / XHTML-Hülle / <error/>“
```

beides `entries=0`, beides `quiet`. „Dead sieht aus wie quiet“ — ohne `feedparser.bozo`, über fehlende Strukturprüfung.

**Warum 72h-Quiet-Stale das nicht vollständig fängt**

1. **Intermittierend:** Wechselt die Quelle zwischen ruhigem Feed und Nicht-Feed, reißt die Quiet-Streak → 72h werden nie erreicht.
2. **Verzögerung:** Selbst im besten Fall bis zu 72h, bis `streaks.*.stale` greift.
3. **Daten-Pollution:** Der `run_marker` kann „wirklich ruhig“ nicht von „liefert Müll“ unterscheiden — die Beobachtung ist verfälscht, bevor ein Alert greift.

**Nicht die Lücke:** „0 neue Items nach Dedup“. `entries` zählt geparste Items dieses Fetches. Ein voller Feed mit nur schon gesehenen Artikeln bleibt `ok` (`entries>0`).

---

## 2. Claim (falsifizierbar)

| ID | Claim |
|----|--------|
| **H1** | Eine 200-Response, deren geparstes XML keine für `parse_rss_xml` erkennbare Feed-Struktur trägt, wird **nicht** als `quiet` klassifiziert. |
| **H2** | Eine 200-Response mit gültiger Feed-Struktur und 0 extrahierbaren Items bleibt `quiet` (kein False-Positive). |

---

## 3. Die eine neue Invariante: `structure_ok`

```text
structure_ok ∈ {true, false}
```

**True** genau dann, wenn nach erfolgreichem `ET.fromstring` ein Container vorliegt, den `parse_rss_xml` tatsächlich abfragt:

- RSS 2.0: `rss` / `channel` (Pfad `./channel/item`), oder
- Atom: `feed` (Pfad `entry` / `{Atom}entry`)

**False** sonst (inkl. wohlgeformtes Nicht-Feed). Bei `ET.ParseError` wird `structure_ok` nicht gesetzt bzw. ist gegenstandslos — `bozo=1` bleibt führend → `dead` wie heute.

Wird Teil von `feed_report`.

**Rückwärtskompatibilität:** Fehlt das Feld, gilt `structure_ok = true` (kein Verhaltenswandel für Aufrufer, die es nicht setzen). Nur der RSS-Fetch-Pfad setzt es explizit.

**Binär**, kein Schwellenwert → nichts zu tunen, kein HARKing-Hebel.

### Klassifikator (eine Stelle vor dem Quiet-Check)

Reihenfolge unverändert außer dem eingeschobenen Struktur-Zweig:

```text
1. status ∉ {None, 200}  ∨  (bozo ∧ entries==0)  →  dead
2. bozo ∧ entries>0                              →  degraded
3. ¬structure_ok                                 →  degraded     ← NEU (H1)
4. entries==0                                    →  quiet        (H2)
5. else                                          →  ok
```

### Entscheidung: `degraded` vs `dead` bei `¬structure_ok`

**Festgelegt (dieser Entwurf): `degraded`.**

| | Begründung |
|---|------------|
| `dead` | bleibt Transport-/Parse-Versagen (HTTP, Timeout, `ET.ParseError`) |
| `degraded` | erreichbar (200), XML parsebar, aber kein Feed — „reachable but not delivering“ |

`DEGRADED` im Runner bleibt sichtbar; wird nicht als `FEED_SILENT` (tot + 0 Items) fehlinterpretiert. Quiet-Streak wird bei `degraded` unterbrochen (wie bei `ok`/`dead`) — korrekt, weil es kein „ruhiger Feed“ war.

---

## 4. Klassifikation vorher / nachher

| Response | vorher | nachher |
|----------|--------|---------|
| HTTP / Timeout / OS-Fehler | dead | dead |
| `ET.ParseError` (Müll / Truncate) | dead | dead |
| 200 + RSS/Atom-Struktur, 0 Items | quiet | quiet (H2) |
| 200 + wohlgeformtes XML, kein Feed-Schema | **quiet** | **degraded** (H1) |
| 200 + Feed-Struktur, N Items | ok | ok |
| 200 + bozo, N Items > 0 | degraded | degraded |

---

## 5. Smoke (Fault-Injection)

| ID | Eingabe | Erwartet |
|----|---------|----------|
| **S1** | `<rss><channel></channel></rss>`, 200 | `structure_ok=true`, `quiet` (H2) |
| **S2** | `<error><message>Not found</message></error>`, 200 | `structure_ok=false`, `degraded` (H1) |
| **S3** | truncated / malformed → `ET.ParseError` | `bozo=1`, `dead` |
| **S4** | HTTP 404 / 500 / Timeout | `dead` |
| **S5** | gültiger Feed, N Items | `structure_ok=true`, `ok` |
| **S6** | Atom `<feed>…<entry>…` | `structure_ok=true`, `ok` |
| **S7** | Regression: alle Zeilen §4 außer der H1-Zielzeile unverändert | PASS |

**Gate:** S1–S7 grün. Kein Smoke außerhalb dieser Tabelle.

---

## 6. Anti-HARKing / Freeze

1. Die Definition von `structure_ok` (welche Container als Feed gelten) wird **vor dem ersten Live-Lauf** eingefroren.
2. Sie spiegelt **ausschließlich**, was `parse_rss_xml` extrahiert (`channel`/`item` bzw. `feed`/`entry`). Kein RDF/RSS-1.0-Sonderfall in diesem Strang — der Extraktor kennt ihn nicht; ihn als `structure_ok=true` zu markieren ohne Items zu liefern wäre ein False-Positive auf H2 bzw. stilles Quiet.
3. Kein nachträgliches Anpassen der Struktur-Erkennung, um eine bestimmte Quelle „ruhig“ oder „degraded“ aussehen zu lassen.

---

## 7. Außerhalb / Follow-ups (bewusst getrennt)

| Thema | Status |
|-------|--------|
| RSS-Shell, Items ohne title/link → `entries=0` trotz Struktur | optional Observability `items_dropped`; **keine** Umklassifikation hier |
| Alerting auf `degraded` vs. Quiet-Streak | eigener Strang; hier nur korrektes Signal im `run_marker` |
| RDF / RSS 1.0 Extraktion | eigener Strang, falls je benötigt |
| Cluster-Patch | nein — Host-Cron-Isolation bleibt |

---

## 8. Charter

`diagnostic_only` · `live_execution=false` · `order_send=false`. Kein Order-Pfad; der Processor wirft weiterhin bei `order_send=true`.

---

## 9. Implementierungs-Scope (nach FREIGABE)

| Datei | Änderung |
|-------|----------|
| `agents_b2g/news/scraper.py` | nach `ET.fromstring`: `structure_ok` setzen; an `feed_report` durchreichen |
| `agents_b2g/news/feed_health.py` | `classify_transport_health(..., structure_ok=True)` — Zweig §3 |
| `tests/test_news_agent.py` | S1–S7 |
| Docs | dieser Pre-Reg → FREIGABE; Kurzverweis in `NEWS_AGENT.md` / `AUDIT_WRITER_LIVENESS.md` |

Keine Änderung an Dedup, Run-Marker-Schema (außer dem neuen Report-Feld), Processor, Host-Cron-Isolation, Paper-Pfad.

---

## 10. Review-Checkliste vor FREIGABE

- [x] H1/H2 und §4-Tabelle akzeptiert
- [x] `degraded` (nicht `dead`) für `¬structure_ok` akzeptiert
- [x] Freeze: Container-Liste = Extraktor-Pfade, kein RDF in diesem Strang
- [x] S1–S7 als einziges Smoke-Gate akzeptiert
- [x] Kein Code vor Status FREIGABE (FREIGABE erteilt; Code danach)
- [x] Freeze gegen echte Feeds bestätigt (Live-Lauf 2026-08-30) → Status VALIDIERT
