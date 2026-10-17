-- ===========================================================================
-- Stand: 2026-10-17 20:20 (Quelle lebt: 360 -> 361 um 20:00:08)
-- DB:    ~/Library/Application Support/agentx/shadow_live/shadow/shadow/shadow.db
-- Akte:  TAG7_ABNAHME.md §5.4ay, §5.4bb–bi
-- ===========================================================================
-- TYP-WARNUNG (§5.4bc). Drei Zeitformate in einer DB, keins davon sicher:
--   telemetry_runs.started_at      REAL   (unixepoch)
--   dispatched_signals.dispatched_at REAL (unixepoch)
--   bridge_discards.discarded_at   REAL   (unixepoch)
--   fills.filled_at                TEXT   (ISO-8601 "...Z")
--   telemetry                      —      (keine Zeitspalte)
-- Ein WHERE mit String gegen eine REAL-Spalte liefert still 0. In dieser
-- Akte hat das mindestens einmal eine falsche Antwort erzeugt
-- (`WHERE dispatched_at > '2026-10-17 18:00:09'` -> 0 Treffer).
-- Regel: gegen REAL immer strftime('%s',?).  Gegen TEXT immer ISO-String.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- A. Der Positivfall (§5.4bb) — die einzige Stunde in 13 Tagen, in der die
--    Kette vollständig durchlief: 34 -> 1 -> 1.
--    Antwort: approved, INVALID_PRICE bei 11 und 13, requested_size NULL dort
--    (Ablehnung vor Ordererzeugung). Kein anderes Asset — ein anderer Preis.
--
--    ACHTUNG: requested_size steht sowohl in telemetry (Order) als auch in
--    fills (Fill). Sie sind NICHT gleich: 100 vs. 5. Das ist kein Datenfehler,
--    sondern zwei verschiedene Fragen (§5.4bc).
-- ---------------------------------------------------------------------------
SELECT 'A1_decision'                AS q,
       decision_seq, approved, reject_reason, status,
       requested_size               AS order_size, order_id
FROM   telemetry
WHERE  run_id = 8 AND decision_seq BETWEEN 10 AND 14
ORDER  BY decision_seq;

SELECT 'A2_fill'                    AS q,
       order_id, fill_idx, side, execution_price,
       executed_size, requested_size AS fill_size, filled_at,
       CAST(executed_size AS REAL) / NULLIF(CAST(requested_size AS REAL), 0)
                                    AS fill_ratio
FROM   fills;


-- ---------------------------------------------------------------------------
-- B. Approval-Taxonomie (§5.4bg) — drei Zustände, zwei Spalten, null offene.
--    Erwartet: rejected=33 (26 INVALID_PRICE + 7 STALE_SNAPSHOT), approved=1,
--              not_evaluated=0.
--
--    `not_evaluated` ist heute nicht belegbar. Wäre es das, stünde hier eine
--    Zahl > 0 — dann wäre die Stelle taub. Sie ist es nicht: models.py
--    ExecutionReport._consistency verlangt reject_reason != NONE bei
--    approved=0. Ein Wert != 0 hier wäre ein Bug im Validator, nicht im Schema.
-- ---------------------------------------------------------------------------
SELECT CASE WHEN approved = 1 THEN 'approved'
            WHEN reject_reason IS NOT NULL THEN 'rejected'
            ELSE 'not_evaluated' END        AS status,
       COUNT(*)                             AS n
FROM   telemetry
GROUP  BY 1 ORDER BY 2 DESC;

-- Aufschlüsselung nach Grund × ob eine Order entstand (§5.4bg):
--   requested_size IS NULL  ->  Ablehnung VOR der Ordererzeugung
SELECT reject_reason,
       requested_size IS NULL AS before_order,
       COUNT(*)               AS n
FROM   telemetry
GROUP  BY 1, 2 ORDER BY 3 DESC;


-- ---------------------------------------------------------------------------
-- C. Kardinalität ist nicht Identität (§5.4bh) — der FK, den es gibt.
--    telemetry_seq ist in ALLEN Dispatches NULL. Die Zuordnung läuft über
--    decision_seq, eine Reihenfolge-Annahme über zwei Reihenfolgen.
--    order_id existiert und paart — aber nur 8 von 34.
-- ---------------------------------------------------------------------------
SELECT 'C1_seq_null'                AS q,
       COUNT(*)                      AS dispatches,
       COUNT(telemetry_seq)          AS with_seq
FROM   dispatched_signals;

SELECT 'C2_order_id'                AS q,
       (SELECT COUNT(*) FROM telemetry)              AS telemetry_rows,
       (SELECT COUNT(order_id) FROM telemetry)       AS with_order_id;

SELECT 'C3_paired'                  AS q,
       COUNT(*) AS fills_paired
FROM   fills f
JOIN   telemetry t ON t.order_id = f.order_id;

-- C4 — der Beweis, daß die Positionsannahme falsch ist, wo sie zählt:
--      Fill(decision_seq=12) um 06.10. 18:00:06
--      12. nicht-discardeter Dispatch um 06.10. 20:00:06  (+2h)
WITH ok AS (
  SELECT ROW_NUMBER() OVER (ORDER BY dispatched_at, item_id) AS rn,
         item_id, dispatched_at
  FROM   dispatched_signals d
  WHERE  NOT EXISTS (SELECT 1 FROM bridge_discards b
                     WHERE b.item_id = d.item_id)
)
SELECT 'C4_position' AS q, rn,
       datetime(dispatched_at, 'unixepoch', 'localtime') AS dispatched_at
FROM   ok WHERE rn BETWEEN 11 AND 13
ORDER  BY rn;


-- ---------------------------------------------------------------------------
-- D. Der vierte Grund ohne Namen (§5.4ay) — 1 unresolved_asset ohne Untertyp.
--    Erwartet: empty_list 66, mapping_miss 201, <ohne> 1 = 268.
--    Der vierte ist der Warmup-Dispatch 08:00:08, außerhalb jedes Fensters,
--    bewußt unklassifiziert.
-- ---------------------------------------------------------------------------
SELECT COALESCE(SUBSTR(reason, 1, INSTR(reason || ':', ':') - 1), reason)
              AS base,
       CASE WHEN INSTR(reason, ':') > 0
            THEN SUBSTR(reason, INSTR(reason, ':') + 1)
            ELSE '<ohne Untertyp>' END AS subtype,
       COUNT(*) AS n
FROM   bridge_discards
GROUP  BY 1, 2 ORDER BY 3 DESC;

-- D2 — die Discard-Menge, die nie einen Dispatch bekam (§5.4ae).
SELECT 'D2_orphan_discards' AS q, COUNT(*) AS n
FROM   bridge_discards b
WHERE  NOT EXISTS (SELECT 1 FROM dispatched_signals d
                   WHERE d.item_id = b.item_id);


-- ---------------------------------------------------------------------------
-- E. Delivery-Etikett (§5.4bd/be) — drei Angaben, die zusammengehören:
--    letzter Fill, sein Alter in Tagen, und ob er im Fenster liegt.
--    Ein Fill 2,4 Tage NACH Fensterbeginn ist "im Fenster", aber nicht frisch.
-- ---------------------------------------------------------------------------
SELECT 'E_delivery' AS q,
       MIN(started_at) AS window_start,
       (SELECT MAX(filled_at) FROM fills) AS last_fill,
       ROUND((julianday('now') - julianday(
              (SELECT MAX(filled_at) FROM fills))) , 2) AS fill_age_days
FROM   telemetry_runs;
