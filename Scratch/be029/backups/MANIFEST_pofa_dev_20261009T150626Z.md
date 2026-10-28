# BE-029 G3 preflight — `pofa_dev` backup manifest

Generated 2026-10-09 (local) / 2026-10-09T15:06:26Z (dump start, UTC).
Purpose: prove that live `pofa_dev` can be recovered to its current state
before BE-029 runs. **No migration, cleanup, commit or push was performed.**

## Backup artifact

| Field | Value |
| --- | --- |
| Host path | `D:\CODING\Scratch\be029\backups\pofa_dev_20261009T150626Z_pre-be029.dump` |
| Size | 1,728,985 bytes |
| SHA-256 | `bf7ff0d667542f64ac297597680b661b833ed9c429a94e7e2c5821274c7542ce` |
| SHA-256 computed twice | inside the container (immediately after dump) and on the host (after `docker cp`) — identical, so the copy is intact |
| Format | PostgreSQL custom (`-Fc`), compression 6, `--no-sync`, dump version 1.14-0 |
| Tool / server | `pg_dump` 15.13 (Debian) against server 15.13 — exact major/minor match |
| Source | `pofa_dev` (verified by `current_database()`), revision `n4o5p6q7r022` |
| `pg_dump` exit status | `0` (`backups/dump_step1_20261009T150626Z.log`) |
| `pg_restore -l` exit status | `0`; 484 TOC entries, `Format: CUSTOM`, `Dumped from database version: 15.13` (`backups/restore_list_*.txt`) |
| Credentials | no artifact contains a connection string, password or token (`grep -rlE "postgres:postgres\|password"` over `backups/`, `restore_verify.json`, `p0_bkpverify_restored.json` → clean) |

Container-side copy `/tmp/pofa_dev_20261009T150626Z_pre-be029.dump` still exists in `pofa_db`.

## Recoverability proof — restored into a new scratch database

Target `pofa_be029_bkpverify` (confirmed absent before `CREATE DATABASE`; no existing
database was overwritten). `pg_restore -U postgres --no-owner --no-privileges --role=postgres
-d pofa_be029_bkpverify` → **exit 0, zero warning output**, 4.24 s wall clock
(`backups/restore_run.log`, empty).

### Source vs restored (`restore_verify.py` → `restore_verify.json`)

| Check | `pofa_dev` | `pofa_be029_bkpverify` |
| --- | --- | --- |
| Alembic revision | `n4o5p6q7r022` | `n4o5p6q7r022` ✔ |
| tables / indexes / constraints / views / extensions / functions / triggers | 69 / 246 / 271 / 2 / 3 / 890 / 0 | identical ✔ |
| `users` | 1,094 | 1,094 ✔ |
| `projects` | 584 | 584 ✔ |
| `evidence` | 324 | 324 ✔ |
| `audit_ledger_events` | 6,017 | 6,017 ✔ |
| residue triples (`testuser`/`test@example.com`/`testproj`/`foo.jpg`) | 40 / 40 / 40 | 40 / 40 / 40 ✔ |
| duplicate username groups | 1 (`testuser` × 40) | 1 ✔ (present, as expected pre-BE-029) |
| duplicate email groups | 1 (`test@example.com` × 40) | 1 ✔ (present) |
| NULL `external_subject` | 1,009 / 1,094 | 1,009 / 1,094 ✔ |
| `ix_users_username`, `ix_users_email` | both plain `CREATE INDEX` (non-unique) | identical ✔ |
| `uq_user_identity_subject` | `UNIQUE (identity_provider, external_subject)` | identical ✔ |
| `identity_retirement_archive` | absent | absent ✔ |
| FKs into the residue set | `projects.owner_id` 40, `evidence.project_id` 40 | identical ✔ |

**Content, not just counts:** every one of the 69 tables was fingerprinted with
`md5(string_agg(row::text, E'\n' ORDER BY row::text))`, which is independent of physical row
order. **0 row-count mismatches and 0 content mismatches across all 69 tables**, so the
restored database holds exactly the source's values, including all 6,017 ledger events.

### Predicate-text difference, resolved not waved through

`pg_dump` re-creates CHECK constraints and partial-index predicates through
`ALTER TABLE … ADD CONSTRAINT` / `CREATE INDEX`, and PostgreSQL stores that form with the
`::text` coercion applied per array element rather than around the array. 64 CHECK
constraints and 2 partial unique indexes therefore deparse differently after restore while
having identical names.

`check_equiv.py` evaluated **both** text forms side by side over every value each column
actually stores, plus a value outside the allowed set and `NULL`:
`objects compared: 66`, `VERDICT: ALL PREDICATE DIFFERENCES ARE DEPARSE-ONLY
(SEMANTICALLY EQUAL)`. The BE-029-relevant one is `users.ck_user_status` (`ACTIVE`,
`SUSPENDED`, `DISABLED`) — equivalent.

### Audit chain

Read-only `verify_chain()` on both:

| | rows | span | valid | failures |
| --- | --- | --- | --- | --- |
| `pofa_dev` | 6,017 | 1..6,053 | False | 7 sequence gaps (before 5350, 5380, 5385, 5392, 5397, 5677, 5682) |
| `pofa_be029_bkpverify` | 6,017 | 1..6,053 | False | the same 7 gaps, at the same sequence numbers |

Identical — the restore reproduces the pre-existing damage exactly, which is what a backup
must do. The gaps are BE-028-recorded and out of scope.

## `pofa_dev` was not modified

`pg_stat_activity` showed **0 backends** on `pofa_dev` before the dump (no API or worker
running). The P0 measurement taken before the dump and the one taken after the whole
backup/restore/verify procedure are byte-equal (`p0_pofa_dev_predump.json` vs
`p0_pofa_dev_postbackup.json`: `identical: True`). No `alembic upgrade`, no cleanup SQL, no
write statement was run against `pofa_dev` or `pofa_test` in this task; every probe used
`set_session(readonly=True, autocommit=True)`.

## Limitations

1. **`archive_mode = off`** (`wal_level = replica`, `pg_stat_archiver.archived_count = 0`).
   WAL archiving is not configured, so true point-in-time recovery to an arbitrary instant
   is not available. This dump is a single transactionally-consistent snapshot as of
   **2026-10-09T15:06:26Z**; any write after that instant is not covered. Recovery restores
   the database to the dump moment, not to a chosen timestamp.
2. `pg_dump` is per-database and excludes globals. Checked and immaterial here: the only
   login role is `postgres` (superuser) and there are no user tablespaces, so a restore as
   `postgres` recreates the whole database faithfully. If a role or ACL is ever added, the
   dump will not capture it (`--no-privileges/--no-owner` were passed on restore).
3. Verification compared the restored copy to the live source *after* the dump. Because
   `pofa_dev` is provably quiescent and its P0 facts are unchanged, that is equivalent to
   comparing against a second read of the snapshot; it is not a replay of the dump's own
   transaction ID.
4. The scratch restore database `pofa_be029_bkpverify` and the container-side copy are kept
   until the verification results above are accepted; deleting them is not authorised here.
5. This task did **not** run either BE-029 revision against the restored database, per the
   instruction. The migrations were rehearsed against a separate `pofa_dev` clone
   (`pofa_be029_rehearsal`) in the earlier step 5–9 work.

## Restore command (for the record)

```
docker exec pofa_db psql -U postgres -c 'CREATE DATABASE <new-db-name>'
docker exec pofa_db sh -c 'pg_restore -U postgres --no-owner --no-privileges \
  --role=postgres -d <new-db-name> /tmp/pofa_dev_20261009T150626Z_pre-be029.dump'
```

Verified working, exit 0, in 4.24 s.
