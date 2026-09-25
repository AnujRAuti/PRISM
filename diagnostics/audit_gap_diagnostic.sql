-- =====================================================================
-- BE-015 audit ledger gap diagnostic — READ ONLY
-- =====================================================================
-- Establishes the source of the 36 missing sequence numbers across
-- 7 gaps in audit_ledger_events.
--
-- SAFETY: every statement below is a SELECT. There is no DELETE,
-- INSERT, UPDATE, TRUNCATE, ALTER or DROP in this file. It cannot
-- modify ledger state.
--
-- ---------------------------------------------------------------------------
-- GAP DEFINITION (single source of truth, derived from data -- never hardcoded)
-- ---------------------------------------------------------------------------
-- Walking the table in sequence order, a gap exists wherever the current
-- row's sequence is not the previous row's sequence + 1:
--
--     gap_start = prev_seq + 1        (first MISSING sequence)
--     gap_end   = sequence_number - 1 (last  MISSING sequence)
--
-- and therefore:
--
--     predecessor_sequence = gap_start - 1   (last SURVIVING row before)
--     successor_sequence   = gap_end   + 1   (first SURVIVING row after)
--
-- NOTE the distinction that an earlier revision of this file got wrong:
-- the SUCCESSOR is gap_end + 1, which is NOT gap_start. Treating the
-- successor as the gap start shifted every neighbour lookup by one row
-- (inspecting 5351 instead of 5350, and so on). Sections 3, 7, 10 and 11
-- below all derive the boundaries from this definition instead of
-- hardcoding any sequence number, so they cannot drift again.
-- =====================================================================


-- ---------------------------------------------------------------------
-- SECTION 0. Ledger overview / baseline shape
-- ---------------------------------------------------------------------
SELECT
    count(*)                                        AS total_events,
    min(sequence_number)                            AS min_seq,
    max(sequence_number)                            AS max_seq,
    max(sequence_number) - min(sequence_number) + 1  AS expected_span,
    count(*)                                        AS actual_rows,
    (max(sequence_number) - min(sequence_number) + 1)
        - count(*)                                  AS missing_total,
    min(created_at)                                 AS first_event_at,
    max(created_at)                                 AS last_event_at
FROM audit_ledger_events;


-- ---------------------------------------------------------------------
-- SECTION 1. Every sequence gap, derived from the data
-- ---------------------------------------------------------------------
WITH ordered AS (
    SELECT
        sequence_number,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq
    FROM audit_ledger_events
)
SELECT
    prev_seq + 1                    AS gap_start,
    sequence_number - 1             AS gap_end,
    sequence_number - prev_seq - 1   AS missing_count,
    prev_seq                        AS predecessor_sequence,
    sequence_number                 AS successor_sequence
FROM ordered
WHERE prev_seq IS NOT NULL
  AND sequence_number <> prev_seq + 1
ORDER BY gap_start;


-- ---------------------------------------------------------------------
-- SECTION 2. Same gaps, with per-gap width (sanity: 36 missing in total)
-- ---------------------------------------------------------------------
WITH ordered AS (
    SELECT
        sequence_number,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq
    FROM audit_ledger_events
),
gaps AS (
    SELECT
        prev_seq + 1        AS gap_start,
        sequence_number - 1 AS gap_end
    FROM ordered
    WHERE prev_seq IS NOT NULL
      AND sequence_number <> prev_seq + 1
)
SELECT
    count(*)           AS gap_count,
    sum(gap_end - gap_start + 1) AS total_missing,
    min(gap_start)     AS first_gap_start,
    max(gap_end)       AS last_gap_end
FROM gaps;


-- ---------------------------------------------------------------------
-- SECTION 3. Immediate surviving predecessor / successor for each gap
-- ---------------------------------------------------------------------
-- Neighbours are resolved via gap_start - 1 and gap_end + 1, which is the
-- exact inverse of the gap definition. No hardcoded sequence numbers.
WITH ordered AS (
    SELECT
        sequence_number,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq
    FROM audit_ledger_events
),
gaps AS (
    SELECT
        prev_seq + 1        AS gap_start,
        sequence_number - 1 AS gap_end
    FROM ordered
    WHERE prev_seq IS NOT NULL
      AND sequence_number <> prev_seq + 1
)
SELECT
    g.gap_start,
    g.gap_end,
    g.gap_end - g.gap_start + 1 AS missing_count,
    'PREDECESSOR' AS position,
    p.sequence_number,
    p.event_type,
    p.action,
    p.actor_id,
    p.project_id,
    p.resource_type,
    p.resource_id,
    p.created_at
FROM gaps g
LEFT JOIN audit_ledger_events p
       ON p.sequence_number = g.gap_start - 1

UNION ALL

SELECT
    g.gap_start,
    g.gap_end,
    g.gap_end - g.gap_start + 1 AS missing_count,
    'SUCCESSOR' AS position,
    s.sequence_number,
    s.event_type,
    s.action,
    s.actor_id,
    s.project_id,
    s.resource_type,
    s.resource_id,
    s.created_at
FROM gaps g
LEFT JOIN audit_ledger_events s
       ON s.sequence_number = g.gap_end + 1

ORDER BY gap_start, position DESC;


-- ---------------------------------------------------------------------
-- SECTION 4. Do the surviving neighbours match the cleanup predicates?
-- ---------------------------------------------------------------------
-- The two test cleanups delete ledger rows by these shapes:
--
--   test_authorization.py:477
--     WHERE resource_id = <org id>
--
--   test_governance.py:347
--     WHERE resource_id IN (all_ids)
--        OR actor_id    IN (user_ids)
--        OR project_id  IN (project_ids)
--
-- A gap whose predecessor and successor BOTH carry a non-null
-- project_id / actor_id / resource_id is consistent with a bulk
-- delete having removed a contiguous run between them.
WITH ordered AS (
    SELECT
        sequence_number,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq
    FROM audit_ledger_events
),
gaps AS (
    SELECT
        prev_seq + 1        AS gap_start,
        sequence_number - 1 AS gap_end
    FROM ordered
    WHERE prev_seq IS NOT NULL
      AND sequence_number <> prev_seq + 1
)
SELECT
    g.gap_start,
    g.gap_end,
    p.event_type   AS pred_event_type,
    p.actor_id     AS pred_actor,
    p.project_id   AS pred_project,
    p.resource_id  AS pred_resource,
    s.event_type   AS succ_event_type,
    s.actor_id     AS succ_actor,
    s.project_id   AS succ_project,
    s.resource_id  AS succ_resource,
    (p.project_id IS NOT NULL OR p.actor_id IS NOT NULL
     OR s.project_id IS NOT NULL OR s.actor_id IS NOT NULL)
        AS matches_governance_predicate,
    (p.resource_id IS NOT NULL OR s.resource_id IS NOT NULL)
        AS matches_authorization_predicate
FROM gaps g
LEFT JOIN audit_ledger_events p ON p.sequence_number = g.gap_start - 1
LEFT JOIN audit_ledger_events s ON s.sequence_number = g.gap_end + 1
ORDER BY g.gap_start;


-- ---------------------------------------------------------------------
-- SECTION 5. Event-type mix immediately around the gap cluster
-- ---------------------------------------------------------------------
SELECT
    sequence_number,
    event_type,
    action,
    actor_id,
    project_id,
    resource_type,
    resource_id,
    created_at
FROM audit_ledger_events
WHERE sequence_number BETWEEN 5340 AND 5410
   OR sequence_number BETWEEN 5665 AND 5695
ORDER BY sequence_number;


-- ---------------------------------------------------------------------
-- SECTION 6. Volume attribution — how many rows carry the shapes the
--           cleanups target?
-- ---------------------------------------------------------------------
SELECT
    count(*) FILTER (WHERE actor_id   IS NOT NULL) AS with_actor,
    count(*) FILTER (WHERE project_id IS NOT NULL) AS with_project,
    count(*) FILTER (WHERE resource_id IS NOT NULL) AS with_resource,
    count(*) FILTER (WHERE actor_id IS NULL
                       AND project_id IS NULL
                       AND resource_id IS NULL)     AS fully_anonymous,
    count(*)                                          AS total
FROM audit_ledger_events;


-- ---------------------------------------------------------------------
-- SECTION 7. Is the surviving hash chain linked ACROSS each gap?
-- ---------------------------------------------------------------------
-- Compares the ACTUAL predecessor's event_hash (gap_start - 1) with the
-- ACTUAL successor's previous_hash (gap_end + 1).
--
-- EXPECTED UNDER DELETION (hypothesis A): linked = FALSE for every gap.
--   If rows gap_start..gap_end were deleted, the surviving successor
--   carries previous_hash = hash(gap_end) -- pointing at a row that no
--   longer exists -- so it cannot equal the predecessor's event_hash.
--   A FALSE here is therefore CONSISTENT WITH DELETION, not evidence
--   against it. Section 11 is the test that actually discriminates.
WITH ordered AS (
    SELECT
        sequence_number,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq
    FROM audit_ledger_events
),
gaps AS (
    SELECT
        prev_seq + 1        AS gap_start,
        sequence_number - 1 AS gap_end
    FROM ordered
    WHERE prev_seq IS NOT NULL
      AND sequence_number <> prev_seq + 1
)
SELECT
    g.gap_start,
    g.gap_end,
    g.gap_end - g.gap_start + 1 AS missing_count,
    p.sequence_number AS predecessor_sequence,
    s.sequence_number AS successor_sequence,
    p.event_hash      AS predecessor_hash,
    s.previous_hash   AS successor_previous_hash,
    (p.event_hash = s.previous_hash) AS linked,
    CASE
        WHEN p.event_hash = s.previous_hash
            THEN 'unexpected: chain links straight across a hole'
        ELSE 'expected under deletion: successor points at a deleted row'
    END AS interpretation
FROM gaps g
LEFT JOIN audit_ledger_events p ON p.sequence_number = g.gap_start - 1
LEFT JOIN audit_ledger_events s ON s.sequence_number = g.gap_end + 1
ORDER BY g.gap_start;


-- ---------------------------------------------------------------------
-- SECTION 8. Rows the cleanups would STILL be able to delete today
-- ---------------------------------------------------------------------
SELECT
    count(*) FILTER (WHERE resource_id IS NOT NULL) AS resource_scoped,
    count(*) FILTER (WHERE actor_id    IS NOT NULL) AS actor_scoped,
    count(*) FILTER (WHERE project_id  IS NOT NULL) AS project_scoped
FROM audit_ledger_events
WHERE resource_id IS NOT NULL
   OR actor_id    IS NOT NULL
   OR project_id  IS NOT NULL;


-- ---------------------------------------------------------------------
-- SECTION 9. DB RESET FEASIBILITY
-- ---------------------------------------------------------------------

-- 9a. Confirm no sequence / identity object backs sequence_number.
SELECT c.relname AS sequence_name, a.attname AS column_name
FROM pg_class c
JOIN pg_depend d       ON d.objid = c.oid
JOIN pg_attribute a     ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
JOIN pg_class t         ON t.oid = d.refobjid
WHERE c.relkind = 'S'
  AND t.relname = 'audit_ledger_events'
  AND a.attname = 'sequence_number';

-- 9b. Confirm no default/identity preserves numbering across a truncate.
SELECT column_name, column_default, is_identity, identity_generation
FROM information_schema.columns
WHERE table_name = 'audit_ledger_events'
  AND column_name = 'sequence_number';

-- 9c. Confirm audit_ledger_events has no FK dependents either way.
SELECT
    con.conname,
    con.contype,
    src.relname AS referencing_table,
    tgt.relname AS referenced_table
FROM pg_constraint con
JOIN pg_class src ON src.oid = con.conrelid
JOIN pg_class tgt ON tgt.oid = con.confrelid
WHERE (src.relname = 'audit_ledger_events' OR tgt.relname = 'audit_ledger_events')
  AND con.contype = 'f';

-- 9d. Does anything else reference the audit ledger? Empty = it is a leaf.
SELECT src.relname AS referencing_table, con.conname
FROM pg_constraint con
JOIN pg_class src ON src.oid = con.conrelid
WHERE con.contype = 'f'
  AND con.confrelid = 'audit_ledger_events'::regclass;

-- 9e. Genesis anchor state.
SELECT
    min(sequence_number) AS min_seq,
    (SELECT previous_hash FROM audit_ledger_events
      ORDER BY sequence_number ASC LIMIT 1) AS first_row_previous_hash,
    (SELECT count(*) FROM audit_ledger_events
      WHERE sequence_number = 1)             AS genesis_row_present
FROM audit_ledger_events;


-- ---------------------------------------------------------------------
-- SECTION 10. Successor pointer resolution
-- ---------------------------------------------------------------------
-- For each gap, take the ACTUAL successor's previous_hash (gap_end + 1)
-- and search the whole table for an event whose event_hash matches it.
--
-- EXPECTED UNDER DELETION (hypothesis A): NO MATCH -> NULL.
--   The successor points at hash(gap_end), and row gap_end was deleted,
--   so no surviving row can carry that hash.
--
-- A MATCH would be surprising: it would mean the successor points at a
-- row that still exists, implying scrambled rather than severed linkage.
WITH ordered AS (
    SELECT
        sequence_number,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq
    FROM audit_ledger_events
),
gaps AS (
    SELECT
        prev_seq + 1        AS gap_start,
        sequence_number - 1 AS gap_end
    FROM ordered
    WHERE prev_seq IS NOT NULL
      AND sequence_number <> prev_seq + 1
)
SELECT
    g.gap_start,
    g.gap_end,
    s.sequence_number     AS successor_sequence,
    s.previous_hash       AS successor_previous_hash,
    m.sequence_number     AS matching_event_sequence,
    m.event_type          AS matching_event_type,
    m.event_hash          AS matching_event_hash
FROM gaps g
JOIN audit_ledger_events s
  ON s.sequence_number = g.gap_end + 1
LEFT JOIN audit_ledger_events m
  ON m.event_hash = s.previous_hash
ORDER BY g.gap_start;


-- ---------------------------------------------------------------------
-- SECTION 11. Global linkage census — THE decisive A-vs-B discriminator
-- ---------------------------------------------------------------------
-- Walks the table in sequence order and classifies EVERY consecutive
-- surviving pair:
--
--   adjacent pair       : sequence_number = prev_seq + 1
--   adjacent pair linked: previous_hash    = prev_event_hash
--   adjacent pair broken: sequence_number = prev_seq + 1
--                          AND previous_hash != prev_event_hash
--   severed pair        : sequence_number >  prev_seq + 1
--
--   Hypothesis A (rows deleted mid-chain):
--     adjacent_pairs_broken = 0 and severed_pairs = 7.
--     Deletion cannot produce a break between two CONSECUTIVE surviving
--     sequences, so any non-zero broken count falsifies A.
--
--   Hypothesis B (chain constructed incorrectly):
--     adjacent_pairs_broken > 0 -- consecutive sequence numbers whose
--     hashes do not link. That is a real BE-015 production defect.
--
-- previous_hash and event_hash are both selected explicitly into the
-- ordered CTE; the comparison is between the successor's previous_hash
-- and the predecessor's event_hash (lagged as prev_event_hash).
WITH ordered AS (
    SELECT
        sequence_number,
        event_type,
        actor_id,
        project_id,
        resource_id,
        created_at,
        event_hash,
        previous_hash,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq,
        lag(event_hash)       OVER (ORDER BY sequence_number) AS prev_event_hash
    FROM audit_ledger_events
)
SELECT
    count(*) FILTER (
        WHERE prev_seq IS NOT NULL
          AND sequence_number = prev_seq + 1
    ) AS adjacent_pairs,
    count(*) FILTER (
        WHERE prev_seq IS NOT NULL
          AND sequence_number = prev_seq + 1
          AND previous_hash = prev_event_hash
    ) AS adjacent_pairs_linked,
    count(*) FILTER (
        WHERE prev_seq IS NOT NULL
          AND sequence_number = prev_seq + 1
          AND previous_hash IS DISTINCT FROM prev_event_hash
    ) AS adjacent_pairs_broken,
    count(*) FILTER (
        WHERE prev_seq IS NOT NULL
          AND sequence_number > prev_seq + 1
    ) AS severed_pairs,
    -- genesis row: its previous_hash should be the constant genesis anchor
    (SELECT previous_hash FROM audit_ledger_events
      ORDER BY sequence_number ASC LIMIT 1) AS genesis_previous_hash
FROM ordered;


-- 11b. Enumerate ANY adjacent-but-unlinked pair. Under hypothesis A this
--      MUST return zero rows. A non-empty result is a production defect.
--      Capped at 50 to keep the output readable.
WITH ordered AS (
    SELECT
        sequence_number,
        event_type,
        event_hash,
        previous_hash,
        actor_id,
        project_id,
        resource_id,
        created_at,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq,
        lag(event_hash)       OVER (ORDER BY sequence_number) AS prev_event_hash
    FROM audit_ledger_events
)
SELECT
    prev_seq              AS predecessor_sequence,
    sequence_number       AS successor_sequence,
    prev_event_hash       AS predecessor_event_hash,
    previous_hash         AS successor_previous_hash,
    event_type            AS successor_event_type,
    actor_id              AS successor_actor,
    project_id            AS successor_project,
    resource_id           AS successor_resource,
    created_at            AS successor_created_at
FROM ordered
WHERE prev_seq IS NOT NULL
  AND sequence_number = prev_seq + 1
  AND previous_hash IS DISTINCT FROM prev_event_hash
ORDER BY sequence_number
LIMIT 50;


-- 11c. Enumerate the SEVERED pairs, to confirm breaks coincide exactly
--      with the 7 known gaps and nowhere else. Severed pairs SHOULD be
--      broken; that is the expected consequence of deletion.
WITH ordered AS (
    SELECT
        sequence_number,
        event_type,
        actor_id,
        project_id,
        resource_id,
        created_at,
        event_hash,
        previous_hash,
        lag(sequence_number) OVER (ORDER BY sequence_number) AS prev_seq,
        lag(event_hash)       OVER (ORDER BY sequence_number) AS prev_event_hash
    FROM audit_ledger_events
)
SELECT
    prev_seq + 1          AS gap_start,
    sequence_number - 1   AS gap_end,
    sequence_number - prev_seq - 1 AS missing_count,
    prev_seq              AS predecessor_sequence,
    sequence_number       AS successor_sequence,
    event_type            AS successor_event_type,
    actor_id              AS successor_actor,
    project_id            AS successor_project,
    resource_id           AS successor_resource,
    created_at            AS successor_created_at,
    (previous_hash = prev_event_hash) AS linked
FROM ordered
WHERE prev_seq IS NOT NULL
  AND sequence_number > prev_seq + 1
ORDER BY gap_start;
