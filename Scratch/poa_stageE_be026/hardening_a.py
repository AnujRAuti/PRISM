"""BE-026 Stage E hardening probe, part A.

Covers the §23 shapes that need no dependency outage: duplicate
synchronization, concurrent synchronization, timeout/retry, conflicting client
payload, revoked assignment, expired assignment, activity/context closure.

Run against two live uvicorn processes (BASE, BASE2) with AUTH_MODE=enforcing
and real MinIO, so every burst here is genuine cross-process contention.
"""

import json
import sys
import time

from fixtures import (build_world, close, get_capture, list_ops,
                      open_session_http, patch_assignment, resolve, work)
from h import (BASE, BASE2, LABEL, assignment_row, audit_count, audit_events,
               burst, chain, check, clone_as_pending, create_assignment, delete_operation,
               iso, jpeg, new_activity, new_claim, note, op_row, payload_of, q1,
               restore_identity, scalar, section, summary, sync, teardown, track_evidence,
               tracked, try_delete, wait_ready)

#: One byte-exact payload and one fixed metadata set, so an identity that must
#: replay identically really does.
PAYLOAD = jpeg(size=24, color=(9, 99, 199))
METADATA = {
    "captured_at": "2026-09-01T10:00:00+00:00",
    "queued_at": "2026-09-01T10:05:00+00:00",
    "uploaded_at": "2026-09-01T10:06:00+00:00",
    "latitude": "51.500767",
    "longitude": "-0.124636",
    "capture_accuracy_m": "4.50",
    "altitude_m": "12.00",
    "location_source": "DEVICE_GPS",
    "client_device_id": "pad-A",
    "client_capture_id": "cap-A",
}

#: op_row() column positions (see h.op_row).
C_ID, C_STATUS, C_SYNC_COUNT, C_EVIDENCE, C_HASH, C_SHA = 0, 1, 2, 3, 4, 5
C_PROJECT, C_CLAIM, C_SESSION, C_ASSIGNMENT = 6, 7, 8, 9
C_CONFLICT, C_RESOLUTION, C_LAT, C_LNG = 10, 11, 12, 13
C_FLAGS, C_FILE_SIZE = 17, 18

#: assignment_row() column positions (see h.assignment_row).
A_STATUS, A_CLAIM, A_ACTIVITY, A_PROJECT, A_USER = 0, 3, 4, 5, 6
A_VALID_FROM, A_EXPIRES, A_CLOSED_REASON = 7, 8, 9


def detail_of(response):
    """Decided outcomes carry the FieldSyncResponse body; refusals carry {detail}."""
    if not response.content:
        return {}
    try:
        body = response.json()
    except ValueError:
        return {"raw": response.text[:200]}
    if isinstance(body, dict) and isinstance(body.get("detail"), dict):
        return body["detail"]
    return body if isinstance(body, dict) else {"raw": str(body)[:200]}


def s(value):
    return str(value) if value is not None else None


def op_id_for(client_op, user):
    row = op_row(client_op=client_op, user=user)
    return s(row[C_ID]) if row else None


def n_ops(client_op, user):
    return scalar("select count(*) from field_capture_operations"
                  " where client_operation_id = :c and user_id = :u", c=client_op, u=user)


def n_ops_total():
    return scalar("select count(*) from field_capture_operations")


def evidence_total():
    return scalar("select count(*) from evidence")


def adopt_clone(src_op_id, rewind):
    """Leftover-reservation state for `src_op_id`'s identity; returns the clone id."""
    clone_id, _ = clone_as_pending(src_op_id, status="PENDING", rewind_seconds=rewind)
    return clone_id


def feed_assignment_ids(actor):
    response = work(actor)
    if not response.ok:
        return None
    return [s(item["assignment_id"]) for item in response.json().get("items", [])]


# ---------------------------------------------------------------------------
# S1 duplicate synchronization
# ---------------------------------------------------------------------------

def s1_duplicate(w):
    section("S1 duplicate synchronization (sequential exact retries)")
    officer, sid = w["officer"], w["session"]
    op = f"se-{LABEL}-s1"
    ev0 = evidence_total()
    dup0 = audit_count("FIELD_SYNC_DUPLICATE")

    r1 = sync(officer, op, session_id=sid, data=PAYLOAD, **METADATA)
    check("S1.1.first-sync-201-accepted",
          r1.status_code == 201 and r1.json().get("sync_status") == "accepted",
          f"{r1.status_code} {r1.text[:250]}")
    body1 = r1.json() if r1.ok else {}
    evidence_id = track_evidence(body1.get("evidence_id"))
    oid = op_id_for(op, officer)
    row = op_row(op_id=oid) if oid else None
    check("S1.2.one-operation-row", oid is not None and n_ops(op, officer) == 1, str(oid))
    check("S1.3.status-accepted-sync-count-1",
          row is not None and row[C_STATUS] == "ACCEPTED" and int(row[C_SYNC_COUNT]) == 1,
          str(row)[:220])
    check("S1.4.payload-digest-and-size-recorded",
          row is not None and row[C_SHA] and int(row[C_FILE_SIZE]) == len(PAYLOAD),
          str(row)[:220])
    check("S1.5.response-echoes-identity",
          s(body1.get("operation_id")) == oid and body1.get("client_operation_id") == op
          and body1.get("sync_count") == 1 and s(body1.get("evidence_id")) == evidence_id,
          json.dumps(body1)[:300])

    codes, counts, statuses = [], [], []
    for _ in range(3):
        r = sync(officer, op, session_id=sid, data=PAYLOAD, **METADATA)
        codes.append(r.status_code)
        body = detail_of(r)
        statuses.append(body.get("sync_status"))
        counts.append(body.get("sync_count"))
    check("S1.6.retries-report-already-synchronized",
          set(statuses) == {"already_synchronized"}, str(statuses))
    check("S1.7.retries-are-200", codes == [200, 200, 200], str(codes))
    check("S1.8.sync-count-advances-2-3-4", counts == [2, 3, 4], str(counts))
    check("S1.9.still-one-operation-row", n_ops(op, officer) == 1, str(n_ops(op, officer)))
    check("S1.10.no-duplicate-evidence", evidence_total() == ev0 + 1,
          f"expected={ev0 + 1} actual={evidence_total()}")
    check("S1.11.accepted-and-associated-audited-once",
          audit_count("FIELD_SYNC_ACCEPTED", oid) == 1
          and audit_count("FIELD_EVIDENCE_ASSOCIATED", evidence_id) == 1,
          f"accepted={audit_count('FIELD_SYNC_ACCEPTED', oid)}"
          f" associated={audit_count('FIELD_EVIDENCE_ASSOCIATED', evidence_id)}")
    dups = audit_events("FIELD_SYNC_DUPLICATE", oid)
    check("S1.12.three-duplicate-events", len(dups) == 3, str(len(dups)))
    counts_seen = [payload_of(d[0]).get("sync_count") for d in dups]
    check("S1.13.duplicate-events-carry-progressing-counts", counts_seen == [2, 3, 4],
          str(counts_seen))
    check("S1.14.duplicate-events-point-at-the-same-evidence",
          all(payload_of(d[0]).get("status") == "ACCEPTED"
              and payload_of(d[0]).get("evidence_id") == evidence_id for d in dups),
          str([payload_of(d[0]) for d in dups][:1])[:250])
    check("S1.15.duplicate-count-is-not-a-conflict", audit_count("FIELD_SYNC_CONFLICT", oid) == 0,
          str(audit_count("FIELD_SYNC_CONFLICT", oid)))
    check("S1.16.session-sync-marker-moved",
          q1("select last_sync_at from field_sessions where id=:i", i=sid)[0] is not None,
          "session.last_sync_at never moved")
    check("S1.17.no-ordinary-duplicate-became-a-conflict-row",
          scalar("select count(*) from field_capture_operations where client_operation_id=:c"
                 " and user_id=:u and status='CONFLICT'", c=op, u=officer) == 0,
          "duplicate retries must not create CONFLICT rows")
    check("S1.18.stored-row-identity-untouched-by-replays",
          op_row(op_id=oid)[C_HASH] == row[C_HASH]
          and s(op_row(op_id=oid)[C_EVIDENCE]) == evidence_id,
          "a replay must never re-decide the identity")
    return oid, op


# ---------------------------------------------------------------------------
# S2 concurrent synchronization
# ---------------------------------------------------------------------------

def s2_concurrent(w):
    section("S2 concurrent synchronization (two server processes, one identity)")
    officer, sid = w["officer"], w["session"]

    # (a) eight simultaneous FIRST submissions of one identity
    op_a = f"se-{LABEL}-s2a"
    ev0, accepted0 = evidence_total(), audit_count("FIELD_SYNC_ACCEPTED")
    responses = burst(8, lambda i, base: sync(officer, op_a, session_id=sid,
                                             data=PAYLOAD, base=base, **METADATA))
    codes = sorted(r.status_code for r in responses)
    statuses = sorted({detail_of(r).get("sync_status") for r in responses
                       if r.status_code < 500})
    note(f"S2a codes={codes} statuses={statuses}")
    check("S2a1.no-500-and-no-transport-loss", 500 not in codes and -1 not in codes, str(codes))
    check("S2a2.vocabulary-limited-to-201-200-503", set(codes) <= {201, 200, 503}, str(codes))
    check("S2a3.exactly-one-201", codes.count(201) == 1, str(codes))
    check("S2a4.exactly-one-operation-row", n_ops(op_a, officer) == 1, str(n_ops(op_a, officer)))
    check("S2a5.exactly-one-evidence-row", evidence_total() == ev0 + 1,
          f"before={ev0} after={evidence_total()}")
    check("S2a6.exactly-one-accepted-event", audit_count("FIELD_SYNC_ACCEPTED") - accepted0 == 1,
          str(audit_count("FIELD_SYNC_ACCEPTED") - accepted0))
    oid_a = op_id_for(op_a, officer)
    row = op_row(op_id=oid_a)
    track_evidence(row[C_EVIDENCE])
    check("S2a7.final-state-accepted", row is not None and row[C_STATUS] == "ACCEPTED",
          str(row)[:200])
    check("S2a8.exactly-one-row-carries-the-evidence-link",
          scalar("select count(*) from field_capture_operations where client_operation_id=:c"
                 " and evidence_id is not null", c=op_a) == 1,
          "two rows would mean the identity is not unique")
    check("S2a9.every-served-answer-names-the-same-evidence",
          all(s(detail_of(r).get("evidence_id")) in (None, s(row[C_EVIDENCE]))
              for r in responses if r.status_code in (200, 201)),
          str([detail_of(r).get("evidence_id") for r in responses
               if r.status_code < 500])[:250])

    # (b) eight simultaneous EXACT retries of the accepted identity
    before = int(op_row(op_id=oid_a)[C_SYNC_COUNT])
    dup0 = audit_count("FIELD_SYNC_DUPLICATE")
    ev1 = evidence_total()
    responses_b = burst(8, lambda i, base: sync(officer, op_a, session_id=sid,
                                               data=PAYLOAD, base=base, **METADATA))
    codes_b = sorted(r.status_code for r in responses_b)
    ok_retries = codes_b.count(200)
    final = int(op_row(op_id=oid_a)[C_SYNC_COUNT])
    note(f"S2b codes={codes_b} sync_count {before} -> {final}, duplicates={ok_retries}")
    check("S2b1.retries-served-without-500", set(codes_b) <= {200, 503}, str(codes_b))
    check("S2b2.no-new-evidence-under-contention", evidence_total() == ev1,
          f"expected={ev1} actual={evidence_total()}")
    check("S2b3.still-one-operation-row", n_ops(op_a, officer) == 1, str(n_ops(op_a, officer)))
    check("S2b4.one-duplicate-event-per-duplicate",
          audit_count("FIELD_SYNC_DUPLICATE") - dup0 == ok_retries,
          f"events={audit_count('FIELD_SYNC_DUPLICATE') - dup0} duplicates={ok_retries}")
    check("S2b5.sync-count-accounts-for-every-duplicate", final == before + ok_retries,
          f"sync_count={final} before={before} duplicates={ok_retries}")
    counts_in_events = [payload_of(d[0]).get("sync_count")
                        for d in audit_events("FIELD_SYNC_DUPLICATE", oid_a)]
    check("S2b6.duplicate-counters-distinct-and-increasing",
          counts_in_events == sorted(counts_in_events)
          and len(set(counts_in_events)) == len(counts_in_events),
          str(counts_in_events))
    check("S2b7.every-duplicate-was-audited-with-its-own-count",
          max(counts_in_events) == final, f"events={counts_in_events} row={final}")

    # (c) two simultaneous adopters of a leftover reservation (crash recovery)
    op_c = f"se-{LABEL}-s2c"
    r = sync(officer, op_c, session_id=sid, data=PAYLOAD, **METADATA)
    check("S2c1.identity-established-for-adoption", r.status_code == 201,
          f"{r.status_code} {r.text[:200]}")
    oid_c = op_id_for(op_c, officer)
    track_evidence(op_row(op_id=oid_c)[C_EVIDENCE])
    clone_c = adopt_clone(oid_c, 1000)
    ev2, accepted2 = evidence_total(), audit_count("FIELD_SYNC_ACCEPTED")
    responses_c = burst(2, lambda i, base: sync(officer, op_c, session_id=sid,
                                               data=PAYLOAD, base=base, **METADATA))
    codes_c = sorted(r.status_code for r in responses_c)
    created = evidence_total() - ev2
    note(f"S2c codes={codes_c} evidence_created={created}")
    check("S2c2.adoption-race-makes-no-500", 500 not in codes_c and -1 not in codes_c,
          str(codes_c))
    check("S2c2b.adoption-race-stays-in-the-declared-vocabulary",
          set(codes_c) <= {201, 200, 503} and codes_c.count(201) == 1,
          f"codes={codes_c} "
          f"sync_statuses={sorted({detail_of(r).get('sync_status') for r in responses_c})}")
    check("S2c3.stale-reservation-race-ingests-exactly-once", created == 1,
          f"evidence rows created by two simultaneous adopters: {created}")
    check("S2c4.one-accepted-event-for-the-identity",
          audit_count("FIELD_SYNC_ACCEPTED") - accepted2 == 1,
          str(audit_count("FIELD_SYNC_ACCEPTED") - accepted2))
    final_c = op_row(op_id=clone_c)
    if final_c:
        track_evidence(final_c[C_EVIDENCE])
    check("S2c5.identity-resolves-to-exactly-one-accepted-row",
          final_c is not None and final_c[C_STATUS] == "ACCEPTED"
          and n_ops(op_c, officer) == 1,
          f"{str(final_c)[:120]} rows={n_ops(op_c, officer)}")
    delete_operation(clone_c)
    restore_identity(oid_c, op_c)

    # (d) simultaneous distinct captures from two different officers
    ids_d = [f"se-{LABEL}-s2d-{i}" for i in range(6)]
    ev3 = evidence_total()
    rows3 = n_ops_total()

    def fire_d(i, base):
        who, sess = ((officer, sid) if i % 2 == 0
                     else (w["colleague"], w["session_colleague"]))
        return sync(who, ids_d[i], session_id=sess, data=PAYLOAD, base=base, **METADATA)

    responses_d = burst(6, fire_d)
    codes_d = sorted(r.status_code for r in responses_d)
    for who, op in zip([officer, w["colleague"]] * 3, ids_d):
        oid = op_id_for(op, who)
        if oid:
            track_evidence(op_row(op_id=oid)[C_EVIDENCE])
    check("S2d1.parallel-distinct-captures-all-accepted",
          codes_d == [201] * 6 and evidence_total() == ev3 + 6,
          f"codes={codes_d} evidence_delta={evidence_total() - ev3}")
    check("S2d2.six-identities-six-rows",
          all(n_ops(op, officer if i % 2 == 0 else w["colleague"]) == 1
              for i, op in enumerate(ids_d))
          and n_ops_total() == rows3 + 6,
          str([n_ops(op, officer) for op in ids_d]))
    check("S2d3.no-officer-can-see-the-others-row",
          all(n_ops(op, w["colleague"]) == 0 for op in ids_d[::2])
          and all(n_ops(op, officer) == 0 for op in ids_d[1::2]),
          "identity is scoped to (officer, client_operation_id)")

    # (e) four simultaneous attempts against a foreign session
    op_e = f"se-{LABEL}-s2e"
    rows_before, ev_before = n_ops_total(), evidence_total()
    sec_before = audit_count("FIELD_ASSIGNMENT_SECURITY_FAILURE")
    rej_before = audit_count("FIELD_SYNC_REJECTED")
    responses_e = burst(4, lambda i, base: sync(w["colleague"], op_e, session_id=sid,
                                               data=PAYLOAD, base=base, **METADATA))
    codes_e = sorted(r.status_code for r in responses_e)
    statuses_e = sorted({detail_of(r).get("sync_status") for r in responses_e})
    check("S2e1.foreign-session-burst-uniformly-404", codes_e == [404] * 4, str(codes_e))
    check("S2e2.denied-burst-wrote-no-domain-rows",
          n_ops_total() == rows_before and evidence_total() == ev_before,
          f"operations {rows_before}->{n_ops_total()}, evidence {ev_before}->{evidence_total()}")
    check("S2e3.denied-burst-uses-the-denial-vocabulary",
          all(detail_of(r).get("sync_status") == "authorization_denied"
              for r in responses_e),
          f"distinct={statuses_e} per-response="
          f"{[detail_of(r).get('sync_status') for r in responses_e]}")
    check("S2e4.security-failures-were-audited",
          audit_count("FIELD_ASSIGNMENT_SECURITY_FAILURE") - sec_before == 4
          and audit_count("FIELD_SYNC_REJECTED") - rej_before == 4,
          f"security={audit_count('FIELD_ASSIGNMENT_SECURITY_FAILURE') - sec_before}"
          f" rejected={audit_count('FIELD_SYNC_REJECTED') - rej_before}")
    check("S2e5.foreign-identity-never-stored", n_ops(op_e, w["colleague"]) == 0,
          str(n_ops(op_e, w["colleague"])))
    return oid_a, op_a


# ---------------------------------------------------------------------------
# S3 timeout / retry
# ---------------------------------------------------------------------------

def s3_retry(w, op_a, oid_a):
    section("S3 timeout / retry: a client that never saw the answer")
    officer = w["officer"]

    r = get_capture(op_a, actor=officer)
    check("S3.1.recovery-endpoint-returns-the-stored-outcome",
          r.status_code == 200 and r.json().get("status") == "ACCEPTED",
          f"{r.status_code} {r.text[:200]}")
    body = r.json() if r.ok else {}
    stored = op_row(op_id=oid_a)
    check("S3.2.recovered-fields-match-the-row",
          s(body.get("id")) == oid_a and s(body.get("evidence_id")) == s(stored[C_EVIDENCE])
          and body.get("sync_count") == int(stored[C_SYNC_COUNT])
          and body.get("request_hash") == stored[C_HASH]
          and body.get("payload_sha256") == stored[C_SHA], json.dumps(body)[:300])
    foreign = get_capture(op_a, actor=w["colleague"])
    check("S3.3.another-officer-cannot-read-it", foreign.status_code == 404,
          str(foreign.status_code))
    check("S3.4.unknown-identity-404",
          get_capture(f"se-{LABEL}-never-used", actor=officer).status_code == 404)
    check("S3.5.too-short-identity-422", get_capture("short", actor=officer).status_code == 422)

    # a reservation that is still in flight: refuse without mutating anything
    clone = adopt_clone(oid_a, None)
    in_flight = op_row(op_id=clone)
    ops_before, ev_before = n_ops_total(), evidence_total()
    dup_before = audit_count("FIELD_SYNC_DUPLICATE")
    r = sync(officer, op_a, session_id=w["session"], data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S3.6.in-flight-reservation-answers-503", r.status_code == 503,
          f"{r.status_code} {r.text[:200]}")
    check("S3.7.503-uses-the-sync-vocabulary",
          det.get("sync_status") == "temporarily_unavailable", json.dumps(det)[:250])
    check("S3.8.no-stack-trace-in-the-refusal",
          "Traceback" not in r.text and 'File "' not in r.text, r.text[:200])
    after = op_row(op_id=clone)
    check("S3.9.reservation-untouched",
          after is not None and after[C_STATUS] == "PENDING"
          and int(after[C_SYNC_COUNT]) == int(in_flight[C_SYNC_COUNT])
          and after[C_EVIDENCE] is None,
          str(after)[:200])
    check("S3.10.refusal-created-no-rows-and-no-replay-event",
          n_ops_total() == ops_before and evidence_total() == ev_before
          and audit_count("FIELD_SYNC_DUPLICATE") == dup_before,
          f"operations {ops_before}->{n_ops_total()}")
    delete_operation(clone)
    restore_identity(oid_a, op_a)

    # a leftover reservation is adopted: one identity, one outcome
    clone2 = adopt_clone(oid_a, 1000)
    ev_before = evidence_total()
    r = sync(officer, op_a, session_id=w["session"], data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S3.11.stale-reservation-recovers-to-one-decision",
          r.status_code in (200, 201)
          and det.get("sync_status") in ("accepted", "already_synchronized"),
          f"{r.status_code} {json.dumps(det)[:250]}")
    recovered = op_row(op_id=clone2)
    if recovered:
        track_evidence(recovered[C_EVIDENCE])
    check("S3.12.adopted-row-is-accepted-and-linked",
          recovered is not None and recovered[C_STATUS] == "ACCEPTED"
          and recovered[C_EVIDENCE] is not None,
          str(recovered)[:200])
    check("S3.13.adoption-ingested-exactly-one-evidence", evidence_total() == ev_before + 1,
          f"before={ev_before} after={evidence_total()}")
    delete_operation(clone2)
    restore_identity(oid_a, op_a)
    check("S3.14.identity-still-resolves-to-one-row", n_ops(op_a, officer) == 1,
          str(n_ops(op_a, officer)))

    # an identical retry after every rejection is answered from the ledger
    r = sync(officer, op_a, session_id=w["session"], data=PAYLOAD, **METADATA)
    check("S3.15.retry-after-recovery-is-200", r.status_code == 200,
          f"{r.status_code} {r.text[:200]}")
    check("S3.16.recovery-read-is-owner-scoped-and-not-a-count-oracle",
          get_capture(f"se-{LABEL}-s2e", actor=officer).status_code == 404)


# ---------------------------------------------------------------------------
# S4 conflicting client payload
# ---------------------------------------------------------------------------

def s4_conflicting_payload(w, op_a, oid_a):
    section("S4 conflicting client payload (same identity, different content)")
    officer, sid = w["officer"], w["session"]
    stored = op_row(op_id=oid_a)
    ev0, conflict0 = evidence_total(), audit_count("FIELD_SYNC_CONFLICT")
    rows0 = n_ops_total()

    r = sync(officer, op_a, session_id=sid, data=jpeg(size=32, color=(200, 0, 0)),
             **{**METADATA, "client_capture_id": "cap-DIFFERENT"})
    det = detail_of(r)
    check("S4.1.different-content-409-conflict",
          r.status_code == 409 and det.get("sync_status") == "conflict",
          f"{r.status_code} {json.dumps(det)[:250]}")
    check("S4.2.reason-is-payload-mismatch", det.get("conflict_reason") == "PAYLOAD_MISMATCH",
          json.dumps(det)[:300])
    check("S4.3.replay-carries-the-stored-identity",
          s(det.get("operation_id")) == oid_a
          and s(det.get("evidence_id")) == s(stored[C_EVIDENCE])
          and det.get("status") == "ACCEPTED"
          and det.get("file_size") == int(stored[C_FILE_SIZE]), json.dumps(det)[:300])
    check("S4.4.stored-row-completely-untouched", op_row(op_id=oid_a) == stored,
          f"before={str(stored)[:180]} after={str(op_row(op_id=oid_a))[:180]}")
    check("S4.5.no-evidence-for-a-conflict", evidence_total() == ev0,
          f"before={ev0} after={evidence_total()}")
    check("S4.6.conflict-audited-exactly-once",
          audit_count("FIELD_SYNC_CONFLICT") - conflict0 == 1,
          str(audit_count("FIELD_SYNC_CONFLICT") - conflict0))
    events = audit_events("FIELD_SYNC_CONFLICT", oid_a)
    payload = payload_of(events[-1][0]) if events else {}
    check("S4.7.conflict-event-explains-both-sides",
          payload.get("conflict_reason") == "PAYLOAD_MISMATCH"
          and payload.get("stored_request_hash") == stored[C_HASH]
          and payload.get("submitted_request_hash") not in (None, stored[C_HASH])
          and payload.get("server_state", {}).get("status") == "ACCEPTED",
          json.dumps(payload)[:350])
    check("S4.8.conflict-event-names-actor-and-affected-resource",
          bool(events) and s(events[-1][1]) == officer
          and payload.get("affected_resource") == s(stored[C_EVIDENCE]),
          str(events[-1][1:5])[:200] if events else "no event")
    check("S4.9.conflict-carries-client-identity-and-operation",
          payload.get("client_operation_id") == op_a and s(payload.get("operation_id")) == oid_a,
          json.dumps(payload)[:250])

    r = sync(officer, op_a, session_id=sid, data=PAYLOAD,
             **{**METADATA, "captured_at": "2026-09-02T10:00:00+00:00"})
    det = detail_of(r)
    check("S4.10.metadata-only-change-is-also-a-conflict",
          r.status_code == 409 and det.get("conflict_reason") == "PAYLOAD_MISMATCH",
          f"{r.status_code} {json.dumps(det)[:220]}")

    r = sync(officer, op_a, session_id=w["session_colleague"], data=PAYLOAD, **METADATA)
    det = detail_of(r)
    note(f"S4.11 same bytes + another session -> {r.status_code} {det.get('conflict_reason')}"
         " (session_id is inside request_hash, so the hash path answers first)")
    check("S4.12.session-swap-is-caught-by-the-request-hash",
          r.status_code == 409 and det.get("conflict_reason") == "PAYLOAD_MISMATCH",
          f"{r.status_code} {json.dumps(det)[:220]}")

    r = sync(officer, op_a, session_id=sid, data=PAYLOAD, **METADATA)
    check("S4.13.original-payload-still-replays-as-synchronized",
          r.status_code == 200 and r.json().get("sync_status") == "already_synchronized",
          f"{r.status_code} {r.text[:200]}")
    after = op_row(op_id=oid_a)
    check("S4.14.server-state-never-overwritten-by-the-client",
          [v for i, v in enumerate(after) if i != C_SYNC_COUNT]
          == [v for i, v in enumerate(stored) if i != C_SYNC_COUNT],
          f"after={str(after)[:180]} stored={str(stored)[:180]}")
    check("S4.14b.only-the-replay-counter-moved",
          int(after[C_SYNC_COUNT]) == int(stored[C_SYNC_COUNT]) + 1,
          f"sync_count {stored[C_SYNC_COUNT]} -> {after[C_SYNC_COUNT]}")
    check("S4.15.conflicts-never-rewrite-the-stored-decision",
          scalar("select count(*) from field_capture_operations where id=:i"
                 " and status='ACCEPTED'", i=oid_a) == 1
          and scalar("select count(*) from field_capture_operations"
                     " where client_operation_id=:c and user_id=:u", c=op_a, u=officer) == 1,
          "a payload mismatch must not rewrite or duplicate the accepted row")
    final = sync(officer, op_a, session_id=sid, data=PAYLOAD[:10], **METADATA)
    check("S4.16.conflict-tells-the-client-to-resubmit-under-a-new-identity",
          "new client_operation_id" in final.text, final.text[:250])
    check("S4.17.conflicting-attempts-added-no-operation-rows", n_ops_total() == rows0,
          f"rows {rows0}->{n_ops_total()}")
    check("S4.18.conflicting-attempts-created-no-evidence", evidence_total() == ev0,
          f"expected={ev0} actual={evidence_total()}")


# ---------------------------------------------------------------------------
# S5 revoked assignment
# ---------------------------------------------------------------------------

def s5_revoked(w):
    section("S5 revoked assignment")
    colleague, aid, sid = w["colleague"], w["assignment_colleague"], w["session_colleague"]
    op = f"se-{LABEL}-s5"

    r = patch_assignment(aid, w["admin"], "REVOKED", "redeployed to another site")
    check("S5.1.manager-revokes-200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    row = assignment_row(aid)
    check("S5.2.revoked-with-reason",
          row is not None and row[A_STATUS] == "REVOKED"
          and row[A_CLOSED_REASON] == "redeployed to another site", str(row)[:220])
    attribution = q1("select revoked_by, revoked_at from field_assignments where id=:i", i=aid)
    check("S5.3.revocation-attributed-to-the-actor",
          attribution is not None and s(attribution[0]) == w["admin"]
          and attribution[1] is not None, str(attribution))
    check("S5.4.status-change-audited", audit_count("FIELD_ASSIGNMENT_STATUS_CHANGED", aid) == 1,
          "missing FIELD_ASSIGNMENT_STATUS_CHANGED")
    check("S5.5.revocation-does-not-delete-history",
          scalar("select count(*) from field_assignments where id=:i", i=aid) == 1,
          "the row must survive revocation")
    check("S5.6.claim-and-activity-links-survive", row is not None
          and s(row[A_CLAIM]) == s(w["claim_a2"]) and s(row[A_ACTIVITY]) == s(w["activity_a2"]),
          str(row)[:200])
    r = patch_assignment(aid, w["admin"], "REVOKED", "again")
    check("S5.7.double-revocation-409", r.status_code == 409, f"{r.status_code} {r.text[:150]}")
    r = patch_assignment(aid, w["admin"], "ACTIVE", "un-revoke")
    check("S5.8.cannot-reopen-a-closed-assignment", r.status_code == 422,
          f"{r.status_code} {r.text[:150]}")

    ev0 = evidence_total()
    r = sync(colleague, op, session_id=sid, data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S5.9.queued-capture-after-revocation-conflicts",
          r.status_code == 409 and det.get("sync_status") == "conflict",
          f"{r.status_code} {json.dumps(det)[:250]}")
    check("S5.10.reason-is-assignment-revoked",
          det.get("conflict_reason") == "ASSIGNMENT_REVOKED", json.dumps(det)[:250])
    orow = op_row(client_op=op, user=colleague)
    check("S5.11.durable-conflict-row-created",
          orow is not None and orow[C_STATUS] == "CONFLICT"
          and orow[C_CONFLICT] == "ASSIGNMENT_REVOKED", str(orow)[:250])
    check("S5.12.nothing-ingested",
          orow is not None and orow[C_EVIDENCE] is None and evidence_total() == ev0,
          f"evidence {ev0}->{evidence_total()}")
    detail_json = q1("select conflict_detail from field_capture_operations where id=:i",
                     i=orow[C_ID])[0] if orow else None
    check("S5.13.conflict-explains-server-state",
          isinstance(detail_json, dict)
          and detail_json.get("assignment_status") == "REVOKED"
          and detail_json.get("assignment_id") == aid,
          json.dumps(detail_json)[:300] if isinstance(detail_json, dict)
          else str(detail_json)[:200])
    check("S5.14.conflict-starts-unresolved", orow is not None
          and orow[C_RESOLUTION] == "UNRESOLVED", str(orow)[:200])
    check("S5.15.open-conflict-audited", audit_count("FIELD_SYNC_CONFLICT", orow[C_ID]) == 1,
          "missing FIELD_SYNC_CONFLICT")

    ids = feed_assignment_ids(colleague)
    check("S5.16.revoked-assignment-leaves-the-feed",
          ids is not None and aid not in ids, str(ids)[:200])
    r = open_session_http(colleague, aid, device=f"late-{LABEL}")
    check("S5.17.no-session-on-a-revoked-assignment", r.status_code == 409,
          f"{r.status_code} {r.text[:150]}")

    r = resolve(orow[C_ID], w["orgadmin_a"], outcome="RESUBMISSION_REQUIRED",
                note="officer must re-capture under a new identity")
    check("S5.18.manager-resolves-conflict", r.status_code == 200,
          f"{r.status_code} {r.text[:250]}")
    after = op_row(op_id=orow[C_ID])
    check("S5.19.resolution-annotates-and-preserves",
          after is not None and after[C_RESOLUTION] == "RESOLVED"
          and after[C_CONFLICT] == "ASSIGNMENT_REVOKED" and after[C_STATUS] == "CONFLICT",
          str(after)[:250])
    check("S5.20.resolution-audited",
          audit_count("FIELD_SYNC_CONFLICT_RESOLVED", orow[C_ID]) == 1,
          "missing FIELD_SYNC_CONFLICT_RESOLVED")
    check("S5.21.resolution-still-ingests-nothing", evidence_total() == ev0,
          f"{ev0}->{evidence_total()}")
    r = resolve(orow[C_ID], w["orgadmin_a"], outcome="DISMISSED", note="second attempt")
    check("S5.22.second-resolution-409", r.status_code == 409, f"{r.status_code} {r.text[:150]}")
    r = resolve(orow[C_ID], w["orgadmin_a"], outcome="NOT_A_THING", note="bad")
    check("S5.23.invalid-outcome-422", r.status_code == 422,
          f"{r.status_code} {r.text[:150]}")
    r = resolve(orow[C_ID], colleague, outcome="DISMISSED", note="officer cannot resolve")
    check("S5.24.officer-cannot-resolve-403", r.status_code == 403,
          f"{r.status_code} {r.text[:150]}")

    # a capture queued before the revocation, replayed after resolution, stays a
    # conflict: revocation is never silently undone
    r = sync(colleague, op, session_id=sid, data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S5.25.resolved-conflict-replays-the-same-decision",
          r.status_code == 409 and det.get("sync_status") == "conflict"
          and det.get("conflict_reason") == "ASSIGNMENT_REVOKED",
          f"{r.status_code} {json.dumps(det)[:220]}")
    check("S5.26.still-one-conflict-row-for-the-identity", n_ops(op, colleague) == 1,
          str(n_ops(op, colleague)))
    return orow[C_ID] if orow else None


# ---------------------------------------------------------------------------
# S6 expired assignment
# ---------------------------------------------------------------------------

def s6_expired(w):
    section("S6 expired assignment")
    colleague = w["colleague"]

    before_assignments = scalar("select count(*) from field_assignments")
    r = create_assignment(w["admin"], colleague, w["project_a"],
                          valid_from=iso(minutes=-180), expires_at=iso(minutes=-120))
    check("S6.1.past-window-assignment-created", r.status_code == 201,
          f"{r.status_code} {r.text[:200]}")
    aid = r.json().get("id") if r.ok else None
    if aid:
        tracked["assignments"].append(aid)

    ids = feed_assignment_ids(colleague)
    check("S6.2.lazy-expiry-hides-it-from-the-feed",
          aid is not None and ids is not None and aid not in ids, str(ids)[:220])
    row = assignment_row(aid) if aid else None
    check("S6.3.server-marked-it-expired", row is not None and row[A_STATUS] == "EXPIRED",
          str(row)[:200])
    check("S6.4.expiry-audited", audit_count("FIELD_ASSIGNMENT_EXPIRED", aid) == 1,
          "missing FIELD_ASSIGNMENT_EXPIRED")
    check("S6.5.expiry-reason-recorded",
          row is not None and row[A_CLOSED_REASON]
          and "window" in str(row[A_CLOSED_REASON]).lower(), str(row[A_CLOSED_REASON])[:120])
    check("S6.6.expiry-kept-its-validity-window",
          row is not None and row[A_EXPIRES] is not None, str(row)[:200])
    r = open_session_http(colleague, aid, device=f"exp-{LABEL}")
    check("S6.7.no-session-on-an-expired-assignment", r.status_code == 409,
          f"{r.status_code} {r.text[:150]}")

    # a capture queued inside the window but uploaded after it closed
    r = create_assignment(w["admin"], colleague, w["project_a"], claim_id=w["claim_a2"],
                          activity_id=w["activity_a2"],
                          valid_from=iso(seconds=-5), expires_at=iso(seconds=3))
    check("S6.8.short-window-assignment-created", r.status_code == 201,
          f"{r.status_code} {r.text[:200]}")
    live_id = r.json().get("id") if r.ok else None
    if live_id:
        tracked["assignments"].append(live_id)
    s = open_session_http(colleague, live_id, device=f"tick-{LABEL}")
    check("S6.9.session-opened-inside-the-window", s.status_code == 201,
          f"{s.status_code} {s.text[:200]}")
    sid_tick = s.json().get("id") if s.ok else None
    if sid_tick:
        tracked["sessions"].append(sid_tick)
    ev0 = evidence_total()
    time.sleep(4)
    live_op = f"se-{LABEL}-s6-live"
    r = sync(colleague, live_op, session_id=sid_tick, data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S6.10.upload-after-window-closes-conflicts",
          r.status_code == 409 and det.get("conflict_reason") == "ASSIGNMENT_EXPIRED",
          f"{r.status_code} {json.dumps(det)[:250]}")
    check("S6.11.expired-sync-ingests-nothing", evidence_total() == ev0,
          f"{ev0}->{evidence_total()}")
    check("S6.12.expired-sync-is-one-durable-conflict",
          scalar("select count(*) from field_capture_operations where client_operation_id=:c"
                 " and user_id=:u and status='CONFLICT'", c=live_op, u=colleague) == 1,
          "expected one CONFLICT row")
    check("S6.13.server-recorded-the-expiry-of-the-live-assignment",
          assignment_row(live_id)[A_STATUS] == "EXPIRED"
          and audit_count("FIELD_ASSIGNMENT_EXPIRED", live_id) == 1,
          str(assignment_row(live_id))[:200])

    # window validation at creation time
    r = create_assignment(w["admin"], colleague, w["project_a"],
                          valid_from=iso(minutes=-5), expires_at=iso(minutes=-10))
    check("S6.14.expiry-before-start-422", r.status_code == 422, f"{r.status_code} {r.text[:200]}")
    check("S6.15.expiry-error-message-surface",
          "expires_at must be after valid_from" in str(detail_of(r).get("detail")),
          r.text[:200])
    note("S6.15/S6.17: administrative refusals carry {\"detail\": message} only; the stable "
         "codes EXPIRY_NOT_AFTER_START / VALID_FROM_NAIVE_TIMESTAMP are carried by the service "
         "error and asserted in the shipped unit suite, not on this HTTP envelope "
         "(validation_errors is a synchronization-path field). Probe expectation corrected "
         "in run seA4; no product requirement was weakened.")
    naive = create_assignment(w["admin"], colleague, w["project_a"],
                              valid_from="2026-09-01T10:00:00")
    check("S6.16.naive-window-422", naive.status_code == 422,
          f"{naive.status_code} {naive.text[:200]}")
    check("S6.17.naive-window-error-message",
          "valid_from must be timezone-aware" in str(detail_of(naive).get("detail")),
          naive.text[:200])
    check("S6.18.rejected-windows-wrote-no-rows",
          scalar("select count(*) from field_assignments") == before_assignments + 2,
          f"expected 2 new rows (S6.1, S6.8), total went"
          f" {before_assignments} -> {scalar('select count(*) from field_assignments')}")

    # an assignment whose window has no expiry at all never expires
    forever = create_assignment(w["admin"], colleague, w["project_a"],
                                claim_id=new_claim(w["project_a"], w["citizen"],
                                                   f"se {LABEL} s6 forever"))
    fid = forever.json().get("id") if forever.ok else None
    if fid:
        tracked["assignments"].append(fid)
    check("S6.19.open-ended-assignment-stays-active",
          forever.status_code == 201 and assignment_row(fid)[A_STATUS] == "ACTIVE",
          f"{forever.status_code} {str(assignment_row(fid))[:150]}")
    check("S6.20.open-ended-assignment-is-in-the-feed",
          fid in (feed_assignment_ids(colleague) or []), str(feed_assignment_ids(colleague))[:200])


# ---------------------------------------------------------------------------
# S7 session / context closure
# ---------------------------------------------------------------------------

def s7_closure(w):
    section("S7 activity and context closure")
    officer, officer_b = w["officer"], w["officer_b"]

    # (a) closed session under an ACTIVE assignment
    r = open_session_http(officer, w["assignment"], device=f"close-{LABEL}")
    sid = r.json().get("id") if r.ok else None
    if sid:
        tracked["sessions"].append(sid)
    check("S7.1.session-opened", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    r = sync(officer, f"se-{LABEL}-s7-a", session_id=sid, data=PAYLOAD, **METADATA)
    check("S7.2.capture-accepted-while-open", r.status_code == 201,
          f"{r.status_code} {r.text[:200]}")
    if r.ok:
        track_evidence(r.json().get("evidence_id"))
    ev0 = evidence_total()
    r = close(sid, officer, reason="shift finished")
    check("S7.3.session-closed", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    check("S7.4.closure-audited", audit_count("FIELD_SESSION_CLOSED", sid) == 1, "missing event")
    closed = q1("select status, close_reason, closed_at from field_sessions where id=:i", i=sid)
    check("S7.5.closure-reason-and-time-stored",
          closed is not None and closed[0] == "CLOSED" and closed[1] == "shift finished"
          and closed[2] is not None, str(closed)[:200])
    r = close(sid, officer, reason="again")
    check("S7.6.second-close-409", r.status_code == 409, f"{r.status_code} {r.text[:150]}")
    r = sync(officer, f"se-{LABEL}-s7-b", session_id=sid, data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S7.7.capture-on-closed-session-conflicts",
          r.status_code == 409 and det.get("conflict_reason") == "SESSION_CLOSED",
          f"{r.status_code} {json.dumps(det)[:250]}")
    check("S7.8.closed-session-conflicts-ingest-nothing", evidence_total() == ev0,
          f"{ev0}->{evidence_total()}")
    check("S7.9.closed-session-conflict-is-durable",
          scalar("select count(*) from field_capture_operations where client_operation_id=:c"
                 " and user_id=:u and status='CONFLICT'", c=f"se-{LABEL}-s7-b",
                 u=officer) == 1, "expected a CONFLICT row")
    check("S7.10.closing-a-session-does-not-close-the-assignment",
          assignment_row(w["assignment"])[A_STATUS] == "ACTIVE",
          str(assignment_row(w["assignment"]))[:150])
    r = close(sid, w["colleague"], reason="not mine")
    check("S7.11.foreign-session-close-is-404", r.status_code == 404,
          f"{r.status_code} {r.text[:150]}")

    # (b) released assignment with an ACTIVE session -> superseded
    claim_r = new_claim(w["project_a"], w["citizen"], f"se {LABEL} s7 release claim")
    act_r = new_activity(w["project_a"], officer)
    r = create_assignment(w["admin"], officer, w["project_a"], claim_id=claim_r,
                          activity_id=act_r)
    rel_id = r.json().get("id") if r.ok else None
    if rel_id:
        tracked["assignments"].append(rel_id)
    check("S7.12.release-fixture-created", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    s2 = open_session_http(officer, rel_id, device=f"rel-{LABEL}")
    sid2 = s2.json().get("id") if s2.ok else None
    if sid2:
        tracked["sessions"].append(sid2)
    check("S7.13.session-on-release-fixture", s2.status_code == 201,
          f"{s2.status_code} {s2.text[:150]}")
    r = patch_assignment(rel_id, w["admin"], "RELEASED", "work complete")
    check("S7.14.assignment-released", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    ev1 = evidence_total()
    r = sync(officer, f"se-{LABEL}-s7-c", session_id=sid2, data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S7.15.released-assignment-sync-is-superseded",
          r.status_code == 409 and det.get("conflict_reason") == "ASSIGNMENT_SUPERSEDED",
          f"{r.status_code} {json.dumps(det)[:250]}")
    check("S7.16.superseded-sync-ingests-nothing", evidence_total() == ev1,
          f"{ev1}->{evidence_total()}")
    check("S7.17.release-does-not-rewrite-the-session",
          q1("select status from field_sessions where id=:i", i=sid2)[0] == "ACTIVE",
          "release must not silently close the session row")

    # (c) same claim, replaced assignment: the queued capture cannot land on a
    # dead context even though current state now allows a fresh one
    r = create_assignment(w["admin"], officer, w["project_a"], claim_id=claim_r,
                          activity_id=act_r)
    check("S7.18.replacement-assignment-allowed-after-release", r.status_code == 201,
          f"{r.status_code} {r.text[:200]}")
    repl_id = r.json().get("id") if r.ok else None
    if repl_id:
        tracked["assignments"].append(repl_id)
    r = sync(officer, f"se-{LABEL}-s7-d", session_id=sid2, data=PAYLOAD, **METADATA)
    check("S7.19.superseded-session-capture-still-refused", r.status_code == 409,
          f"{r.status_code} {r.text[:200]}")
    new_sid = open_session_http(officer, repl_id, device=f"repl-{LABEL}")
    nsid = new_sid.json().get("id") if new_sid.ok else None
    if nsid:
        tracked["sessions"].append(nsid)
    replacement = sync(officer, f"se-{LABEL}-s7-repl", session_id=nsid, data=PAYLOAD,
                       **METADATA)
    check("S7.20.replacement-assignment-can-be-worked",
          new_sid.status_code == 201 and replacement.status_code == 201,
          f"{new_sid.status_code}/{replacement.status_code} {replacement.text[:150]}")
    if replacement.ok:
        track_evidence(replacement.json().get("evidence_id"))

    # (d) two ACTIVE assignments for the same work key cannot coexist
    r = create_assignment(w["admin"], officer, w["project_a"], claim_id=claim_r)
    check("S7.21.duplicate-active-claim-assignment-409", r.status_code == 409,
          f"{r.status_code} {r.text[:200]}")
    gen1 = create_assignment(w["admin"], officer_b, w["project_b"], claim_id=None)
    check("S7.22.general-assignment-created", gen1.status_code == 201,
          f"{gen1.status_code} {gen1.text[:200]}")
    gen1_id = gen1.json().get("id") if gen1.ok else None
    if gen1_id:
        tracked["assignments"].append(gen1_id)
    gen2 = create_assignment(w["admin"], officer_b, w["project_b"], claim_id=None)
    check("S7.23.duplicate-general-active-assignment-409", gen2.status_code == 409,
          f"{gen2.status_code} {gen2.text[:200]}")

    # (e) ambiguity is a refusal, never a guess
    ev_amb, rows_amb = evidence_total(), n_ops_total()
    r = sync(officer_b, f"se-{LABEL}-s7-f", data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S7.24.two-active-assignments-refuse-to-guess",
          r.status_code == 422 and "AMBIGUOUS_ACTIVE_ASSIGNMENT" in json.dumps(det),
          f"{r.status_code} {json.dumps(det)[:250]}")
    check("S7.25.ambiguity-refusal-writes-no-operation-row",
          n_ops(f"se-{LABEL}-s7-f", officer_b) == 0, str(n_ops(f"se-{LABEL}-s7-f", officer_b)))
    check("S7.26.ambiguity-refusal-is-stable-on-retry",
          sync(officer_b, f"se-{LABEL}-s7-f", data=PAYLOAD,
               **METADATA).status_code == 422)
    check("S7.27.ambiguity-refusals-ingest-and-store-nothing",
          evidence_total() == ev_amb and n_ops_total() == rows_amb,
          f"evidence {ev_amb}->{evidence_total()}, rows {rows_amb}->{n_ops_total()}")
    released = patch_assignment(w["assignment_b"], w["admin"], "RELEASED",
                                "moved to general coverage")
    check("S7.28.prior-claim-assignment-released", released.status_code == 200,
          f"{released.status_code} {released.text[:200]}")
    r = sync(officer_b, f"se-{LABEL}-s7-g", data=PAYLOAD, **METADATA)
    det = detail_of(r)
    check("S7.29.single-active-assignment-syncs-without-a-session",
          r.status_code == 201 and det.get("sync_status") == "accepted",
          f"{r.status_code} {json.dumps(det)[:250]}")
    check("S7.30.session-less-sync-still-resolves-server-side-scope",
          det.get("project_id") == w["project_b"] and det.get("assignment_id") == gen1_id
          and det.get("claim_id") is None, json.dumps(det)[:300])
    if r.ok:
        track_evidence(det.get("evidence_id"))
    check("S7.31.session-less-accept-still-lands-the-postgis-location",
          scalar("select count(*) from evidence where id=:i and location is not null",
                 i=det.get("evidence_id")) == 1, str(det.get("evidence_id")))
    extra = create_assignment(w["admin"], officer_b, w["project_b"], claim_id=w["claim_b"])
    if extra.ok:
        tracked["assignments"].append(extra.json().get("id"))
    check("S7.32.re-ambiguous-officer-refuses-again",
          extra.status_code == 201
          and sync(officer_b, f"se-{LABEL}-s7-h", data=PAYLOAD,
                   **METADATA).status_code == 422,
          f"{extra.status_code} {extra.text[:150]}")

    # (f) context resources cannot be deleted underneath an ACTIVE assignment
    ok, err = try_delete("claims", claim_r)
    check("S7.33.referenced-claim-cannot-be-deleted", not ok, f"delete succeeded: {err}")
    check("S7.34.deletion-refused-by-referential-integrity",
          not ok and "foreign key" in err.lower(), err[:250])
    ok2, err2 = try_delete("activities", act_r)
    check("S7.35.referenced-activity-cannot-be-deleted", not ok2, f"delete succeeded: {err2}")
    note("S7.33-35: CONTEXT_RESOURCE_MISSING is a defensive branch. Claim/Activity "
         "have no lifecycle column and referential integrity refuses deletion of a "
         "referenced row, so no HTTP path can make a bound context resource vanish; "
         "the shipped suite reaches that branch by forcing the context lookup.")
    return sid, sid2


# ---------------------------------------------------------------------------

def main():
    print(f"part=A label={LABEL} base={BASE} base2={BASE2}"
          f" db={scalar('select current_database()')}")
    assert wait_ready(), "primary server not reachable"
    assert wait_ready(BASE2), "second server not reachable"
    chain0 = chain()
    check("A0.chain-valid-before", chain0["valid"], str(chain0["failures"][:2]))
    w = build_world("pa")
    try:
        s1_duplicate(w)
        oid_a, op_a = s2_concurrent(w)
        s3_retry(w, op_a, oid_a)
        s4_conflicting_payload(w, op_a, oid_a)
        s5_revoked(w)
        s6_expired(w)
        s7_closure(w)
    finally:
        r = list_ops(w["admin"], limit=1)
        check("A98.manager-listing-serves", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        chain1 = chain()
        check("A99.chain-valid-after-part-A", chain1["valid"], str(chain1["failures"][:2]))
        note(f"part-A ledger {chain0['checked_events']} -> {chain1['checked_events']}")
        teardown()
    return summary()


if __name__ == "__main__":
    sys.exit(main())
