-- ===========================================================================
-- Stand: 2026-10-17 20:30 (Quelle lebt — Zahlen altern zwischen Läufen)
-- DB:    ~/Library/Application Support/agentx/shadow_live/shadow/shadow/shadow.db
-- Akte:  TAG7_ABNAHME.md §5.4bk–bo
-- Vorgänger: 2026-10-17T2020_seq12.sql (unverändert, historischer Stand)
-- ===========================================================================
-- TYP-WARNUNG (§5.4bc). Drei Zeitformate, keins davon sicher:
--   telemetry_runs.started_at / dispatched_signals.dispatched_at /
--   bridge_discards.discarded_at : REAL (unixepoch)
--   fills.filled_at              : TEXT (ISO-8601 "...Z")
--   telemetry                    : keine Zeitspalte
-- Ein WHERE mit String gegen REAL liefert still 0. Gegen REAL: strftime.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- A. Die Adresse des RED (§5.4bk) — welche Bedingung ist rot?
--    Erwartet 20:30: (3) unattributed = 4, nicht der Ledger.
--    Die vier sind Dispatch-Erfolge aus run 8, die nie eine Zeile bekamen.
--    Das ist die Fundstelle: rot ist der Dispatcher-Ledger-Übergang,
--    nicht der Ledger selbst.
-- ---------------------------------------------------------------------------
-- A1  Bilanz, aus der die Bedingungen (1)-(4) direkt lesbar sind
SELECT (SELECT COUNT(*) FROM telemetry WHERE run_id >= 7)              AS telemetry_rows,
       (SELECT COUNT(*) FROM telemetry
         WHERE run_id >= 7 AND decision_seq IS NOT NULL)               AS keyed,
       (SELECT COUNT(*) FROM dispatched_signals d
         WHERE d.dispatched_at >= (SELECT MIN(started_at) FROM telemetry_runs
                                    WHERE run_id >= 7)
           AND NOT EXISTS (SELECT 1 FROM bridge_discards b
                            WHERE b.item_id = d.item_id))              AS dispatch_success;

-- A2  Die vier unattributierten (§5.4bk): 34 - 30 = 4.
--     Alle aus run 8. Sie sind der Grund, warum RED dasteht.
WITH ok AS (
  SELECT item_id, dispatched_at,
         ROW_NUMBER() OVER (ORDER BY dispatched_at, item_id) AS rn
  FROM   dispatched_signals d
  WHERE  d.dispatched_at >= (SELECT MIN(started_at) FROM telemetry_runs
                              WHERE run_id >= 7)
    AND  NOT EXISTS (SELECT 1 FROM bridge_discards b
                      WHERE b.item_id = d.item_id)
)
SELECT 'A2' AS q, rn,
       datetime(dispatched_at, 'unixepoch', 'localtime') AS dispatched_at,
       substr(item_id, 1, 8) AS item
FROM   ok
WHERE  rn > (SELECT COUNT(*) FROM telemetry WHERE run_id >= 7)
ORDER  BY rn;


-- ---------------------------------------------------------------------------
-- B. `order_id`: welche acht? (§5.4bn)
--    Dritte Antwort, die keine Zeitreihe ist: **order_id ist ein
--    Determinant.** Es steht genau dann, wenn eine Order entstand —
--    STALE_SNAPSHOT 7/7 und genehmigt 1/1 ja, INVALID_PRICE 0/26 nein.
--    Kein Schreiber fiel weg, keiner kam: die Spalte ist korrekt gefüllt,
--    sie markiert nur keine Entscheidung, sondern einen Schritt.
-- ---------------------------------------------------------------------------
SELECT reject_reason,
       COUNT(*)        AS n,
       COUNT(order_id) AS with_order_id,
       CASE WHEN COUNT(order_id) = COUNT(*) THEN 'ALLE'
            WHEN COUNT(order_id) = 0 THEN 'KEINE'
            ELSE 'gestreut' END AS verdict
FROM   telemetry
GROUP  BY 1 ORDER BY 2 DESC;

-- B2  Zeitreihen-Hypothese widerlegen: sind die acht am Anfang/Ende?
SELECT MIN(seq) AS first_seq, MAX(seq) AS last_seq,
       MIN(CASE WHEN order_id IS NOT NULL THEN seq END) AS first_with,
       MAX(CASE WHEN order_id IS NOT NULL THEN seq END) AS last_with
FROM   telemetry;

-- B3  Liegt der Fill unter den acht? Wenn ja, ist die korrekte Paarung
--     vorhanden und die Position nur der falsche Weg dorthin.
SELECT f.order_id IS NOT NULL AND t.order_id IS NOT NULL AS paired,
       t.run_id, t.decision_seq, f.executed_size, f.filled_at, t.seq
FROM   fills f
JOIN   telemetry t ON t.order_id = f.order_id;


-- ---------------------------------------------------------------------------
-- C. Zwei Filter, nicht einer (§5.4bo)
--    Mapping: 327 von 361 (9,4 % passieren). Preis: 26 von 34 (3 % total).
--    Der Engpass nach dem Mapping ist INVALID_PRICE, nicht der Name.
-- ---------------------------------------------------------------------------
SELECT 'C1_mapping' AS q,
       COUNT(*)                                   AS dispatched,
       SUM(EXISTS (SELECT 1 FROM bridge_discards b
                    WHERE b.item_id = d.item_id)) AS discarded,
       ROUND(100.0 * SUM(NOT EXISTS (SELECT 1 FROM bridge_discards b
                                      WHERE b.item_id = d.item_id))
             / COUNT(*), 1)                       AS pass_pct
FROM   dispatched_signals d;

SELECT 'C2_price' AS q, reject_reason, COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM telemetry), 1) AS pct
FROM   telemetry
GROUP  BY 2 ORDER BY 3 DESC;

-- C3  Sobald `reject_detail` geschrieben wird, ersetzt das Folgende C2.
--     Heute: die Spalte existiert noch nicht (26 Zeilen sind Bestand vor
--     dem Feld) — nach der nächsten Migration hier einkommentieren, sonst
--     bleibt das eine Behauptung über ein Feld, das niemand sieht.
-- SELECT COALESCE(reject_detail, '<nicht erfasst>') AS detail,
--        COALESCE(reject_reason, '<NULL>')          AS reason,
--        COUNT(*)                                   AS n
-- FROM   telemetry
-- WHERE  reject_reason = 'INVALID_PRICE'
-- GROUP  BY 1, 2 ORDER BY 3 DESC;


-- ---------------------------------------------------------------------------
-- D. `no_book` — der größte Block ohne Untertyp (§5.4ay)
--    Die 1 war nie das Problem. 124 sind es.
--    Herkunft: news_bridge.py:241 `snapshot is None` → kein Buch-Objekt.
--    Kein Untertyp nötig: die Ursache liegt im Buch selbst (fehlt), nicht
--    im Mapping. Und EMPTY_SIDE (Buch da, Seite leer) ist ein anderer Fall,
--    der erst im Engine-Preflight auftritt, nicht im Bridge.
-- ---------------------------------------------------------------------------
SELECT COALESCE(SUBSTR(reason, 1, INSTR(reason || ':', ':') - 1), reason)
              AS base,
       CASE WHEN INSTR(reason, ':') > 0
            THEN SUBSTR(reason, INSTR(reason, ':') + 1)
            ELSE '<ohne Untertyp>' END AS subtype,
       COUNT(*) AS n,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM bridge_discards), 1) AS pct
FROM   bridge_discards
GROUP  BY 1, 2 ORDER BY 3 DESC;


-- ---------------------------------------------------------------------------
-- E. Die zwei Achsen (§5.4bl) — beide richtig, solange die Achse im Namen steht
--    open_for    gegen started_at (der Lauf)
--    stalled_for gegen jetzt      (der Dienst)
-- ---------------------------------------------------------------------------
SELECT 'E_axes' AS q,
       ROUND((julianday('now') - julianday(MIN(started_at), 'unixepoch')) * 24, 1)
                        AS open_for_h,
       ROUND((julianday('now') - julianday(MAX(filled_at))) * 24, 1)
                        AS stalled_for_h
FROM   telemetry_runs, fills;
