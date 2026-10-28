"""BE-026 Stage E, part B: negative-surface hardening probes (S8-S14).

Every expectation is read from the shipped contract (endpoint code, service
validation, migration CHECKs, Stage B design sections 5 and 12), not assumed:

* design 12: "No failure collapses to 500; no stack trace in any response body"
* structural refusals (unknown field, malformed identifier, short operation id)
  answer ``{detail: {sync_status, message, validation_errors}}` and write NO row;
* metadata refusals (naive timestamp, half a GPS fix) write a durable
  ``VALIDATION_FAILED`` row and replay unchanged;
* 400/413/415 propagate the reused ingestion validator's own contract;
* out-of-scope reads answer exactly like absent ones (404 "Not found").

Fault injection and dependency outages live in hardening_c.py, not here.
"""

import base64
import io
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import requests
from sqlalchemy import text

from backend.services import audit_ledger as audit_service

from h import (BASE, LABEL, RUN_STARTED, audit_count, audit_events, chain, check,
               create_assignment, engine, evidence_row, grant, hdr,
               iso, jpeg, new_user, note, op_row, payload_of, png_bytes, q, q1,
               residue, scalar, section, set_status, summary, sync, sync_raw,
               teardown, track_evidence, tracked, wait_ready)
from h import client_hdr
from fixtures import (build_world, close, get_capture, list_assignments,
                      list_ops, open_session_http, patch_assignment, resolve,
                      work)


def evidence_total():
    """Total evidence rows — used for before/after deltas around each probe."""
    return scalar("select count(*) from evidence")

C_ID, C_STATUS, C_SYNC, C_EVIDENCE, C_HASH = 0, 1, 2, 3, 4
C_PROJECT, C_CLAIM, C_SESSION, C_ASSIGNMENT = 6, 7, 8, 9
C_CONFLICT, C_RESOLUTION, C_LAT, C_LNG = 10, 11, 12, 13
C_CAPTURED, C_QUEUED, C_UPLOADED, C_FLAGS, C_SIZE = 14, 15, 16, 17, 18

LOC = {"latitude": "53.3498", "longitude": "-6.2603",
       "location_source": "DEVICE_GPS", "capture_accuracy_m": "8.5"}
PAYLOAD = jpeg(size=24, color=(9, 99, 199))


def ts(seconds_back):
    return iso(seconds=seconds_back)


#: Frozen once, in the right order and in the server's past. Recomputing these from
#: the live clock per call makes two otherwise identical captures differ, so an
#: exact-replay probe would report a payload conflict it never sent.
_CAPTURED_AT = (RUN_STARTED - timedelta(minutes=10)).isoformat()
_QUEUED_AT = (RUN_STARTED - timedelta(minutes=5)).isoformat()
_UPLOADED_AT = (RUN_STARTED - timedelta(minutes=1)).isoformat()


def meta(**over):
    """A complete, valid capture: real fix + real ordered timestamps."""
    base = {"captured_at": _CAPTURED_AT, "queued_at": _QUEUED_AT,
            "uploaded_at": _UPLOADED_AT}
    base.update(LOC)
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def op(name):
    return f"se-{LABEL}-b-{name}"


def rows_named(name):
    return scalar("select count(*) from field_capture_operations"
                  " where client_operation_id = :c", c=op(name))


def body(response):
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text[:300]}


def detail_of(response):
    b = body(response)
    if isinstance(b, dict) and isinstance(b.get("detail"), dict):
        return b["detail"]
    return b if isinstance(b, dict) else {"raw": str(b)[:200]}


def get(path, actor=None, client=None, **params):
    headers = client_hdr(client) if client else ({} if actor is None else hdr(actor))
    return requests.get(f"{BASE}{path}", headers=headers, params=params, timeout=60)


def post_json(path, actor, payload):
    return requests.post(f"{BASE}{path}", json=payload, headers=hdr(actor), timeout=60)


def do_sync(name, actor, session_id=None, base=None, metadata=None, **over):
    """One synchronization of a fresh identity; tracks any Evidence it creates."""
    fields = meta(**over) if metadata is None else {**metadata, **over}
    r = sync(actor, op(name), session_id=session_id, data=PAYLOAD, base=base, **fields)
    if r.status_code == 201:
        try:
            track_evidence(r.json().get("evidence_id"))
        except ValueError:
            pass
    return r


# ---------------------------------------------------------------------------
# S8 malformed identifiers on all eleven routes
# ---------------------------------------------------------------------------

BAD_IDS = ["not-a-uuid", "1", "550e8400-e29b-41d4-a716-44665544000",
           "550e8400e29b41d4a71644665544000x", "null", "%20",
           "550e8400-e29b-41d4-a716-446655440000/../x"]
GOOD_UNKNOWN = "550e8400-e29b-41d4-a716-446655440000"


def s8_malformed_ids(w):
    section("S8 malformed identifiers (all eleven field routes)")
    officer, sid, aid = w["officer"], w["session"], w["assignment"]
    admin, project_a = w["admin"], w["project_a"]

    # 1-2. administrative path parameters
    codes = []
    for bad in BAD_IDS:
        codes.append(get(f"/api/v1/field/assignments/{bad}", admin).status_code)
        codes.append(requests.patch(f"{BASE}/api/v1/field/assignments/{bad}/status",
                                     json={"status": "RELEASED", "reason": "probe"},
                                     headers=hdr(admin), timeout=60).status_code)
    check("S8.1.assignment-path-ids-never-500", 500 not in codes and -1 not in codes,
          str(sorted(set(codes))))
    check("S8.2.assignment-path-ids-422", set(codes) == {422}, str(sorted(set(codes))))

    # 3. unknown-but-well-formed administrative ids read as absent, identically
    r = get(f"/api/v1/field/assignments/{GOOD_UNKNOWN}", admin)
    check("S8.3.wellformed-unknown-assignment-id-404", r.status_code == 404,
          f"{r.status_code} {r.text[:120]}")
    foreign = list_assignments(w["orgadmin_b"], project_id=w["project_a"])
    missing = list_assignments(w["orgadmin_b"], project_id=GOOD_UNKNOWN)
    check("S8.4.out-of-scope-indistinguishable-from-absent",
          foreign.status_code == missing.status_code and foreign.text == missing.text,
          f"foreign {foreign.status_code} vs absent {missing.status_code}")

    # 4. assignment creation body identifiers
    for field in ("user_id", "project_id", "claim_id", "activity_id"):
        payload = {"user_id": officer, "project_id": project_a,
                   "claim_id": w["claim_a"], "activity_id": w["activity_a"]}
        payload[field] = "not-a-uuid"
        r = post_json("/api/v1/field/assignments", admin, payload)
        check(f"S8.5.body-{field}-malformed-422", r.status_code == 422,
              f"{r.status_code} {r.text[:160]}")
    r = post_json("/api/v1/field/assignments", admin,
                  {"user_id": GOOD_UNKNOWN, "project_id": project_a})
    check("S8.6.unknown-user-404-not-crash", r.status_code in (404, 422),
          f"{r.status_code} {r.text[:160]}")
    check("S8.6b.unknown-user-denial-is-silent-on-existence",
          r.text == post_json("/api/v1/field/assignments", admin,
                              {"user_id": GOOD_UNKNOWN,
                               "project_id": GOOD_UNKNOWN}).text,
          "two different unknown ids must answer identically")
    r = post_json("/api/v1/field/assignments", admin,
                  {"user_id": officer, "project_id": GOOD_UNKNOWN})
    check("S8.7.unknown-project-404", r.status_code == 404, f"{r.status_code} {r.text[:120]}")

    # 5. list filters
    for key in ("user_id", "project_id"):
        codes = [get("/api/v1/field/assignments", admin, **{key: bad}).status_code
                 for bad in BAD_IDS[:4]]
        check(f"S8.8.assignments-list-{key}-malformed-422",
              set(codes) == {422}, str(codes))
    r = get("/api/v1/field/assignments", admin, status="NOT_A_STATUS")
    check("S8.9.assignment-status-enum-422", r.status_code == 422,
          f"{r.status_code} {r.text[:120]}")

    # 6. work feed
    r = get("/api/v1/field/work", officer, assignment_id="not-a-uuid")
    check("S8.10.work-feed-malformed-assignment-422", r.status_code == 422,
          f"{r.status_code} {r.text[:120]}")

    # 7. session open / close
    codes = [post_json("/api/v1/field/sessions", officer, {"assignment_id": bad}).status_code
             for bad in BAD_IDS[:4]]
    check("S8.11.session-open-malformed-422", set(codes) == {422}, str(codes))
    r = post_json("/api/v1/field/sessions", officer, {"assignment_id": GOOD_UNKNOWN})
    check("S8.12.session-open-unknown-assignment-404", r.status_code == 404,
          f"{r.status_code} {r.text[:120]}")
    codes = [requests.post(f"{BASE}/api/v1/field/sessions/{bad}/close",
                           json={"reason": "probe"}, headers=hdr(officer),
                           timeout=60).status_code for bad in BAD_IDS[:4]]
    check("S8.13.session-close-malformed-422", set(codes) == {422}, str(codes))

    # 8. synchronization form identifiers: session_id is free text, so this is
    #    the route where a malformed uuid can reach the database.
    before = (scalar("select count(*) from field_capture_operations"), evidence_total())
    codes = {}
    malformed_session_responses = []
    for index, bad in enumerate(("not-a-uuid", "550e8400e29b41d4a71644665544000x",
                                 "1", "null")):
        r = do_sync(f"s8-session-{index}", officer, session_id=bad)
        malformed_session_responses.append(r)
        codes[bad] = r.status_code
    check("S8.14.sync-malformed-session-id-never-500", 500 not in set(codes.values()),
          str(codes))
    check("S8.15.sync-malformed-session-id-is-a-deterministic-refusal",
          set(codes.values()) <= {404, 422}, str(codes))
    check("S8.15b.sync-malformed-session-id-names-its-code",
          all("SESSION_ID_MALFORMED" in json.dumps(detail_of(r))
              for r in malformed_session_responses if r.status_code == 422),
          str(codes))
    after = (scalar("select count(*) from field_capture_operations"), evidence_total())
    check("S8.16.sync-malformed-session-id-wrote-nothing", after == before,
          f"{before} -> {after}")
    r = do_sync("s8-session-unknown", officer, session_id=GOOD_UNKNOWN)
    check("S8.17.sync-unknown-session-id-404", r.status_code == 404
          and detail_of(r).get("sync_status") == "authorization_denied",
          f"{r.status_code} {r.text[:160]}")

    # 9. owner-side recovery route takes a free-text identifier by design
    r = get("/api/v1/field/captures/abc", officer)
    check("S8.18.capture-recovery-short-id-422", r.status_code == 422,
          f"{r.status_code} {r.text[:120]}")
    r = get(f"/api/v1/field/captures/{GOOD_UNKNOWN}", officer)
    check("S8.19.capture-recovery-unknown-id-404", r.status_code == 404,
          f"{r.status_code} {r.text[:120]}")
    r = get(f"/api/v1/field/captures/{'x' * 300}", officer)
    check("S8.19b.capture-recovery-overlong-label-never-500",
          r.status_code in (404, 422), f"{r.status_code} {r.text[:140]}")

    # 10. manager routes
    for key in ("user_id", "project_id", "session_id"):
        r = get("/api/v1/field/operations", admin, **{key: "not-a-uuid"})
        check(f"S8.20.operations-list-{key}-malformed-422", r.status_code == 422,
              f"{r.status_code} {r.text[:120]}")
    r = get("/api/v1/field/operations", admin, status="NOT_A_STATUS")
    check("S8.21.operations-status-enum-422", r.status_code == 422,
          f"{r.status_code} {r.text[:120]}")
    r = get("/api/v1/field/operations", admin, resolution_status="NOT_A_STATUS")
    check("S8.22.operations-resolution-enum-422", r.status_code == 422,
          f"{r.status_code} {r.text[:120]}")
    codes = [post_json(f"/api/v1/field/operations/{bad}/resolve", admin,
                       {"outcome": "DISMISSED", "note": "probe"}).status_code
             for bad in BAD_IDS[:4]]
    check("S8.23.resolve-malformed-id-422", set(codes) == {422}, str(codes))
    r = resolve(GOOD_UNKNOWN, admin, outcome="DISMISSED")
    check("S8.24.resolve-unknown-operation-404", r.status_code == 404,
          f"{r.status_code} {r.text[:120]}")
    r = post_json(f"/api/v1/field/operations/{GOOD_UNKNOWN}/resolve", admin,
                  {"outcome": "NOT_A_OUTCOME", "note": "probe"})
    check("S8.25.resolve-invalid-outcome-enum-422", r.status_code == 422,
          f"{r.status_code} {r.text[:120]}")

    # 11. pagination bounds are validated, not clamped
    for path, actor in (("/api/v1/field/assignments", admin),
                        ("/api/v1/field/operations", admin),
                        ("/api/v1/field/work", officer)):
        name = path.rsplit("/")[-1]
        codes = {limit: get(path, actor, limit=limit).status_code for limit in (0, 101)}
        check(f"S8.26.{name}-limit-bounds-422", set(codes.values()) == {422}, str(codes))
        check(f"S8.27.{name}-offset-bounds-422",
              get(path, actor, offset=-1).status_code == 422,
              str(get(path, actor, offset=-1).status_code))

    # no probe in this section may leave a row behind
    check("S8.28.malformed-identifier-probes-left-no-capture-rows",
          rows_named("s8-session-not-a-uuid") == 0
          and scalar("select count(*) from field_capture_operations"
                     " where client_operation_id like :p", p=f"se-{LABEL}-b-s8%") == 0,
          str(scalar("select count(*) from field_capture_operations"
                     " where client_operation_id like :p", p=f"se-{LABEL}-b-s8%")))
    check("S8.29.malformed-ids-created-no-assignments-or-sessions",
          scalar("select count(*) from field_assignments where instructions like :p",
                 p="%malformed%") == 0
          and scalar("select count(*) from field_sessions where client_device_id like :p",
                     p="%xfer-bad%") == 0,
          "a malformed identifier must never become a durable row")


# ---------------------------------------------------------------------------
# S9 malformed payloads and smuggled scope
# ---------------------------------------------------------------------------

SMUGGLED = ["project_id", "claim_id", "assignment_id", "organization_id",
            "organizational_unit_id", "role", "permission", "user_id",
            "evidence_id", "status", "resolution_status", "request_hash",
            "payload_sha256", "actor_id"]


def s9_malformed_payloads(w):
    section("S9 malformed payloads, smuggled scope, unknown fields")
    officer, sid = w["officer"], w["session"]
    rows0, ev0 = scalar("select count(*) from field_capture_operations"), evidence_total()

    for field in SMUGGLED:
        name = f"s9-{field}"
        r = sync_raw(op(name), officer=officer,
                     raw_form=[("client_operation_id", op(name)),
                               ("session_id", sid), (field, GOOD_UNKNOWN)],
                     data=PAYLOAD)
        det = detail_of(r)
        check(f"S9.1.{field}-smuggling-refused-not-ignored",
              r.status_code == 422
              and det.get("sync_status") == "validation_failed"
              and f"UNEXPECTED_FIELD_{field.upper()}" in (det.get("validation_errors") or []),
              f"{r.status_code} {json.dumps(det)[:200]}")
    rows1, ev1 = (scalar("select count(*) from field_capture_operations"),
                  evidence_total())
    check("S9.2.smuggling-probes-wrote-no-rows", (rows1, ev1) == (rows0, ev0),
          f"{(rows0, ev0)} -> {(rows1, ev1)}")

    # operation identity validation (floor)
    for label, value in (("missing", None), ("empty", ""), ("blank", "   "),
                         ("short", "abc"), ("seven", "1234567")):
        form = [("session_id", sid)]
        if value is not None:
            form.append(("client_operation_id", value))
        name = f"s9-id-{label}"
        r = sync_raw(op(name), officer=officer, raw_form=form, data=PAYLOAD)
        det = detail_of(r)
        check(f"S9.3.identity-{label}-422",
              r.status_code == 422
              and "CLIENT_OPERATION_ID_TOO_SHORT" in (det.get("validation_errors") or []),
              f"{r.status_code} {json.dumps(det)[:180]}")
        check(f"S9.4.identity-{label}-wrote-no-row", rows_named(name) == 0,
              str(rows_named(name)))

    # the column is VARCHAR(128) with a CHECK on its floor: the ceiling is the
    # server's problem, not the client's
    name = "s9-long"
    long_id = op(name) + "-" + "z" * 200
    r = sync(officer, long_id, session_id=sid, data=PAYLOAD, **meta())
    check("S9.5.overlong-identity-never-500", r.status_code not in (500, -1),
          f"{r.status_code} {r.text[:200]}")
    check("S9.6.overlong-identity-is-a-deterministic-refusal",
          r.status_code == 422
          and "CLIENT_OPERATION_ID_TOO_LONG" in json.dumps(detail_of(r)),
          f"{r.status_code} {json.dumps(detail_of(r))[:220]}")

    # every other bounded text field: the multipart body carries no schema, so an
    # over-long value reaches the column unless the server refuses it first
    long_cases = {"client_capture_id": 128, "client_device_id": 128, "filename": 512}
    for field, width in long_cases.items():
        name = f"s9-over-{field}"
        value = "L" * (width + 40)
        kwargs = {"filename": value} if field == "filename" else {field: value}
        r = sync(officer, op(name), session_id=sid, data=PAYLOAD, **kwargs, **meta())
        if r.status_code == 201:
            track_evidence(r.json().get("evidence_id"))
        check(f"S9.7.{field}-over-column-width-never-500", r.status_code not in (500, -1),
              f"{r.status_code} {r.text[:200]}")
        check(f"S9.8.{field}-over-column-width-refused-deterministically",
              r.status_code == 422
              and f"{field.upper()}_TOO_LONG" in json.dumps(detail_of(r)),
              f"{r.status_code} {json.dumps(detail_of(r))[:220]}")
        check(f"S9.9.{field}-overflow-wrote-no-row", rows_named(name) == 0,
              str(rows_named(name)))
    name = "s9-over-content-type"
    r = sync(officer, op(name), session_id=sid, data=PAYLOAD,
             content_type="image/" + "e" * 130, **meta())
    if r.status_code == 201:
        track_evidence(r.json().get("evidence_id"))
    check("S9.10.overlong-declared-content-type-never-500", r.status_code not in (500, -1),
          f"{r.status_code} {r.text[:200]}")
    check("S9.11.overlong-declared-content-type-refused",
          r.status_code == 422
          and "DECLARED_CONTENT_TYPE_TOO_LONG" in json.dumps(detail_of(r)),
          f"{r.status_code} {json.dumps(detail_of(r))[:220]}")
    check("S9.12.width-overflows-wrote-no-rows",
          scalar("select count(*) from field_capture_operations"
                 " where client_operation_id like :p", p=f"se-{LABEL}-b-s9-over%") == 0,
          str(scalar("select count(*) from field_capture_operations"
                     " where client_operation_id like :p", p=f"se-{LABEL}-b-s9-over%")))

    # parsed metadata has no column-width exposure, but an absurd value must still
    # stay inside the documented vocabulary instead of collapsing to a 500
    parsed_over = {}
    for field in ("latitude", "captured_at", "location_source"):
        name = f"s9-over-parse-{field}"
        r = do_sync(name, officer, session_id=sid, **{field: "9" * 300})
        parsed_over[field] = r.status_code
        if r.status_code == 201:
            track_evidence(r.json().get("evidence_id"))
    note(f"S9.12b: over-long parsed metadata answered {parsed_over}")
    check("S9.12b.overlong-parsed-metadata-never-500",
          all(code != 500 for code in parsed_over.values()), str(parsed_over))
    check("S9.12c.overlong-parsed-metadata-stays-in-vocabulary",
          all(code in (403, 404, 409, 413, 415, 422, 503)
              for code in parsed_over.values()), str(parsed_over))
    check("S9.12d.overlong-parsed-metadata-accepted-nothing",
          not q("select id from field_capture_operations where status='ACCEPTED'"
                " and client_operation_id like :p", p=f"se-{LABEL}-b-s9-over-parse%"),
          "an absurd value was stored as a real capture")

    # duplicate form keys must stay deterministic
    name = "s9-dup"
    second = "duplicate-second-value"
    dup_form = [("client_operation_id", op(name)), ("client_operation_id", second),
                ("session_id", sid)]
    r1 = sync_raw(op(name), officer=officer, raw_form=dup_form, data=PAYLOAD)
    if r1.status_code == 201:
        track_evidence(r1.json().get("evidence_id"))
    r2 = sync_raw(op(name), officer=officer, raw_form=dup_form, data=PAYLOAD)
    label_1 = (r1.json() or {}).get("client_operation_id") if r1.ok else None
    label_2 = (r2.json() or {}).get("client_operation_id") if r2.ok else None
    stored = q("select client_operation_id from field_capture_operations"
               " where user_id = :u and client_operation_id = any(:c)", u=officer,
               c=[op(name), second])
    note(f"S9.13: duplicate client_operation_id resolved to {label_1!r}")
    check("S9.13a.duplicate-keys-never-500",
          r1.status_code not in (500, -1) and r2.status_code not in (500, -1),
          f"{r1.status_code}/{r2.status_code}")
    check("S9.13.duplicate-keys-are-deterministic-and-idempotent",
          r1.status_code == 201 and r2.status_code == 200,
          f"{r1.status_code}/{r2.status_code} {json.dumps(detail_of(r2))[:180]}")
    check("S9.13b.duplicate-keys-landed-exactly-one-row", len(stored) == 1,
          str([r[0] for r in stored])[:200])
    check("S9.13c.stored-label-is-one-of-the-sent-values",
          bool(stored) and str(stored[0][0]) in (op(name), second),
          str(stored[:1]))
    check("S9.13d.replay-reports-the-same-label", label_1 is not None
          and label_1 == label_2, f"{label_1} vs {label_2}")

    # the reused validator keeps its own contract
    cases = {
        "empty": (b"", "image/jpeg", 400),
        "declared-png-actual-jpeg": (PAYLOAD, "image/png", 415),
        "declared-pdf": (PAYLOAD, "application/pdf", 415),
        "text-bytes-as-jpeg": (b"not an image at all", "image/jpeg", 415),
        "real-png": (png_bytes(32), "image/png", 201),
    }
    for label, (data, ctype, expected) in cases.items():
        name = f"s9-file-{label}"
        r = sync(officer, op(name), session_id=sid, data=data,
                 content_type=ctype, **meta())
        if r.status_code == 201:
            track_evidence(r.json().get("evidence_id"))
        check(f"S9.14.{label}-validator-contract", r.status_code == expected,
              f"expected={expected} got={r.status_code} {r.text[:180]}")
        if expected != 201:
            check(f"S9.15.{label}-no-row-and-no-evidence", rows_named(name) == 0,
                  str(rows_named(name)))

    # filename is client data: stored verbatim, never used as a storage path
    traversal = "../../../../etc/passwd"
    name = "s9-filename"
    r = sync(officer, op(name), session_id=sid, data=PAYLOAD, filename=traversal, **meta())
    check("S9.16.filename-is-assertion-data-only", r.status_code == 201,
          f"{r.status_code} {r.text[:200]}")
    if r.status_code == 201:
        eid = r.json().get("evidence_id")
        track_evidence(eid)
        row = evidence_row(eid)
        stored = op_row(client_op=op(name), user=officer)
        check("S9.17.storage-key-is-server-generated",
              row is not None and "passwd" not in str(row[4])
              and str(eid).lower() in str(row[4]).lower(),
              str(row[4]) if row else "no evidence row")
        check("S9.18.filename-stored-not-interpreted",
              stored is not None and q1(
                  "select filename from field_capture_operations where id=:i",
                  i=str(stored[C_ID]))[0] == traversal,
              str(q1("select filename from field_capture_operations where id=:i",
                     i=str(stored[C_ID])))[:120] if stored else "no operation row")

    # refusal bodies stay structured and carry no stack trace
    r = sync_raw(op("s9-trace"), officer=officer,
                 raw_form=[("client_operation_id", op("s9-trace")),
                           ("session_id", sid), ("project_id", GOOD_UNKNOWN)],
                 data=PAYLOAD)
    check("S9.19.refusal-body-has-no-stack-trace",
          "Traceback" not in r.text and "File \"" not in r.text, r.text[:200])
    check("S9.20.refusal-body-names-the-vocabulary",
          detail_of(r).get("sync_status") == "validation_failed"
          and isinstance(detail_of(r).get("validation_errors"), list),
          json.dumps(detail_of(r))[:200])


# ---------------------------------------------------------------------------
# S10 oversized evidence
# ---------------------------------------------------------------------------

def _noise_jpeg(side):
    """A genuinely incompressible JPEG: random pixels cannot be encoded smaller."""
    import os

    from PIL import Image
    buf = io.BytesIO()
    Image.frombytes("RGB", (side, side), os.urandom(side * side * 3)).save(
        buf, "JPEG", quality=100)
    return buf.getvalue()


def _jpeg_of_exact_size(limit):
    """A valid JPEG padded to exactly ``limit`` bytes.

    Trailing bytes after the end-of-image marker are ignored by the decoder, so
    the payload stays a real image at a size the probe controls: the only way to
    test the boundary of a bounded read at 10 MiB is to stand exactly on it.
    """
    side = 1200
    data = _noise_jpeg(side)
    while len(data) >= limit and side > 8:
        side = max(8, side // 2)
        data = _noise_jpeg(side)
    return data + b"\x00" * (limit - len(data))


def s10_oversized(w):
    section("S10 oversized evidence (bounded read, retryable identity)")
    from backend.core.config import settings
    from h import quarantine_keys
    limit = int(settings.max_upload_size)
    officer, sid = w["officer"], w["session"]
    note(f"S10 configured max_upload_size={limit}")

    at_limit = _jpeg_of_exact_size(limit)
    over = at_limit + b"\x00"
    check("S10.0.boundary-payload-is-a-real-jpeg", at_limit[:2] == b"\xff\xd8"
          and at_limit[-2:] == b"\x00\x00",
          f"head={at_limit[:2]!r} tail={at_limit[-2:]!r}")
    check("S10.1.boundary-payload-is-exactly-at-the-limit",
          len(over) == limit + 1 and len(at_limit) == limit,
          f"at_limit={len(at_limit)} over={len(over)}")

    # objects already unreferenced before this section ran are not BE-026's
    # residue: earlier suite runs removed rows without removing objects
    keys_before = set(quarantine_keys())
    referenced_before = {str(r[0]) for r in q("select storage_key from evidence")}
    pre_existing = sorted(keys_before - referenced_before)
    note(f"S10 pre-existing unreferenced quarantine objects: {len(pre_existing)}")

    ev0 = evidence_total()
    rows0 = scalar("select count(*) from field_capture_operations")
    name_at, name_over = "s10-at-limit", "s10-over"
    r_at = sync(officer, op(name_at), session_id=sid, data=at_limit, **meta())
    check("S10.2.exactly-at-limit-is-accepted", r_at.status_code == 201,
          f"{r_at.status_code} {r_at.text[:200]}")
    if r_at.status_code == 201:
        track_evidence(r_at.json().get("evidence_id"))
        check("S10.3.at-limit-file-size-recorded",
              int(r_at.json().get("file_size") or 0) == len(at_limit),
              str(r_at.json().get("file_size")))

    r_over = sync(officer, op(name_over), session_id=sid, data=over, **meta())
    check("S10.4.one-byte-over-is-413", r_over.status_code == 413,
          f"{r_over.status_code} {r_over.text[:200]}")
    check("S10.5.413-uses-the-ingestion-contract",
          "too large" in str(body(r_over).get("detail", "")).lower(),
          json.dumps(body(r_over))[:200])
    check("S10.6.oversize-leaves-no-operation-row", rows_named(name_over) == 0,
          str(rows_named(name_over)))
    check("S10.7.oversize-creates-no-evidence", evidence_total() == ev0 + 1,
          f"ev0={ev0} now={evidence_total()}")

    # R1: a refusal that reached no decision must leave the identity retryable
    r_retry = sync(officer, op(name_over), session_id=sid, data=PAYLOAD, **meta())
    check("S10.8.identity-stays-retryable-after-413", r_retry.status_code == 201,
          f"{r_retry.status_code} {r_retry.text[:200]}")
    if r_retry.status_code == 201:
        track_evidence(r_retry.json().get("evidence_id"))
    check("S10.9.retry-landed-exactly-one-row", rows_named(name_over) == 1,
          str(rows_named(name_over)))

    # well over the limit: still 413, still no row, and the read stayed bounded
    huge = over + b"\x00" * (2 * limit)
    name_huge = "s10-huge"
    r_huge = sync(officer, op(name_huge), session_id=sid, data=huge, **meta())
    check("S10.10.much-oversize-is-413-not-500", r_huge.status_code == 413,
          f"{r_huge.status_code} {r_huge.text[:160]}")
    check("S10.11.much-oversize-wrote-nothing",
          rows_named(name_huge) == 0 and evidence_total() == ev0 + 2,
          f"rows={rows_named(name_huge)} evidence={evidence_total()} vs {ev0 + 2}")

    # a refused upload must not leave an object this run created
    keys_after = set(quarantine_keys())
    referenced_after = {str(r[0]) for r in q("select storage_key from evidence")}
    new_orphans = sorted((keys_after - keys_before) - referenced_after)
    check("S10.12.oversize-refusals-left-no-orphan-objects", not new_orphans,
          f"new orphans={new_orphans[:5]}")
    check("S10.13.oversize-section-landed-exactly-two-captures",
          scalar("select count(*) from field_capture_operations") == rows0 + 2,
          f"rows0={rows0} now="
          f"{scalar('select count(*) from field_capture_operations')}")


# ---------------------------------------------------------------------------
# S11 missing GPS and missing timestamps
# ---------------------------------------------------------------------------

def s11_location_and_time(w):
    section("S11 missing GPS / missing timestamps: asserted, never invented")
    officer, sid = w["officer"], w["session"]

    # (a) no fix at all is a legitimate capture, not a 0,0 capture
    r = do_sync("s11-no-fix", officer, session_id=sid, metadata=meta(**{
        "latitude": None, "longitude": None, "location_source": None,
        "capture_accuracy_m": None}))
    check("S11.1.unlocated-capture-accepted", r.status_code == 201,
          f"{r.status_code} {r.text[:200]}")
    if r.status_code == 201:
        payload = r.json()
        check("S11.2.location-reported-is-false",
              payload.get("location", {}).get("reported") is False,
              json.dumps(payload.get("location"))[:200])
        check("S11.3.no-coordinates-invented",
              payload.get("location", {}).get("latitude") is None
              and payload.get("location", {}).get("longitude") is None,
              json.dumps(payload.get("location"))[:200])
        row = op_row(client_op=op("s11-no-fix"), user=officer)
        check("S11.4.stored-fix-is-null", row[C_LAT] is None and row[C_LNG] is None,
              f"{row[C_LAT]} {row[C_LNG]}")
        ev = evidence_row(payload.get("evidence_id"))
        check("S11.5.postgis-location-stays-null", ev is not None and ev[6] is None,
              str(ev[6])[:120] if ev else "no evidence row")

    # (b) half a fix is refused explicitly and durably
    for label, over in (("lat-only", {"longitude": None}), ("lng-only", {"latitude": None})):
        name = f"s11-half-{label}"
        r = do_sync(name, officer, session_id=sid, metadata=meta(**over))
        det = r.json() if r.status_code == 422 else detail_of(r)
        check(f"S11.6.{label}-422", r.status_code == 422,
              f"{r.status_code} {r.text[:180]}")
        check(f"S11.6.{label}-names-the-code",
              "GPS_PARTIAL_FIX" in json.dumps(det), json.dumps(det)[:200])
    row = op_row(client_op=op("s11-half-lat-only"), user=officer)
    check("S11.7.partial-fix-is-a-durable-validation-failure",
          row is not None and row[C_STATUS] == "VALIDATION_FAILED"
          and row[C_EVIDENCE] is None,
          str(row)[:160] if row else "no row")
    r_retry = do_sync("s11-half-lat-only", officer, session_id=sid,
                      metadata=meta(longitude=None))
    check("S11.8.validation-failure-replays-unchanged",
          r_retry.status_code == 422
          and r_retry.json().get("sync_status") == "validation_failed"
          and rows_named("s11-half-lat-only") == 1,
          f"{r_retry.status_code} {r_retry.text[:160]} "
          f"rows={rows_named('s11-half-lat-only')}")

    # (c) zero island needs an explicit confirmation, never a default
    r = do_sync("s11-zero-unconfirmed", officer, session_id=sid,
                metadata=meta(latitude="0", longitude="0", zero_island_confirmed=None))
    check("S11.9.zero-island-needs-confirmation",
          r.status_code == 422 and "ZERO_ISLAND_UNCONFIRMED" in json.dumps(detail_of(r)),
          f"{r.status_code} {json.dumps(detail_of(r))[:200]}")
    r = do_sync("s11-zero-confirmed", officer, session_id=sid,
                metadata=meta(latitude="0", longitude="0", zero_island_confirmed="true"))
    check("S11.10.confirmed-zero-island-is-stored", r.status_code == 201,
          f"{r.status_code} {r.text[:180]}")
    if r.status_code == 201:
        row = op_row(client_op=op("s11-zero-confirmed"), user=officer)
        check("S11.11.zero-island-preserved-not-replaced",
              str(row[C_LAT]) == "0.000000" and str(row[C_LNG]) == "0.000000",
              f"{row[C_LAT]} {row[C_LNG]}")

    # (d) source and range rules
    for label, over, code in (
            ("no-source", {"location_source": None}, "LOCATION_SOURCE_REQUIRED"),
            ("bad-source", {"location_source": "SATELLITE_GUESS"}, "LOCATION_SOURCE_INVALID"),
            ("accuracy-no-fix", {"latitude": None, "longitude": None,
                                 "location_source": None, "capture_accuracy_m": "5"},
             "ACCURACY_WITHOUT_FIX"),
            ("accuracy-out-of-range", {"capture_accuracy_m": "100001"},
             "CAPTURE_ACCURACY_M_OUT_OF_RANGE"),
            ("lat-out-of-range", {"latitude": "91"}, "LATITUDE_OUT_OF_RANGE"),
            ("lng-unparseable", {"longitude": "east-of-eden"}, "LONGITUDE_UNPARSEABLE")):
        name = f"s11-src-{label}"
        r = do_sync(name, officer, session_id=sid, metadata=meta(**over))
        check(f"S11.12.{label}-422-with-code",
              r.status_code == 422 and code in json.dumps(detail_of(r)),
              f"{r.status_code} {json.dumps(detail_of(r))[:200]}")
        check(f"S11.13.{label}-stored-no-partial-fix",
              scalar("select count(*) from field_capture_operations where"
                     " client_operation_id=:c and status='ACCEPTED'", c=op(name)) == 0,
              "an unusable fix must never be persisted as if it were usable")

    # (e) timestamps: absent stays absent, impossible is refused, odd is flagged
    r = do_sync("s11-no-time", officer, session_id=sid, metadata=meta(
        captured_at=None, queued_at=None, uploaded_at=None))
    check("S11.14.capture-without-any-client-time-accepted", r.status_code == 201,
          f"{r.status_code} {r.text[:180]}")
    if r.status_code == 201:
        payload = r.json()
        check("S11.15.client-times-echoed-as-null",
              payload.get("captured_at") is None and payload.get("queued_at") is None
              and payload.get("uploaded_at") is None,
              json.dumps({k: payload.get(k) for k in
                          ("captured_at", "queued_at", "uploaded_at")}))
        check("S11.16.server-times-are-present-and-separate",
              payload.get("received_at") and payload.get("processed_at")
              and payload["received_at"] != payload["processed_at"],
              json.dumps({k: payload.get(k) for k in ("received_at", "processed_at")}))
        row = op_row(client_op=op("s11-no-time"), user=officer)
        check("S11.17.nothing-was-backfilled-from-server-time",
              row[C_CAPTURED] is None and row[C_QUEUED] is None
              and row[C_UPLOADED] is None,
              str(row[C_CAPTURED:C_UPLOADED + 1]))

    for label, field, value, code in (
            ("naive", "captured_at", "2026-09-01T10:00:00", "CAPTURED_AT_NAIVE_TIMESTAMP"),
            ("garbage", "captured_at", "yesterday", "CAPTURED_AT_UNPARSEABLE"),
            ("naive-queue", "queued_at", "2026-09-01T10:00:00", "QUEUED_AT_NAIVE_TIMESTAMP"),
            ("bad-upload", "uploaded_at", "soon", "UPLOADED_AT_UNPARSEABLE")):
        name = f"s11-time-{label}"
        r = do_sync(name, officer, session_id=sid, metadata=meta(**{field: value}))
        check(f"S11.18.{label}-refused-with-code",
              r.status_code == 422 and code in json.dumps(detail_of(r)),
              f"{r.status_code} {json.dumps(detail_of(r))[:200]}")
        check(f"S11.19.{label}-never-stored-a-guessed-time",
              scalar("select count(*) from field_capture_operations where client_operation_id"
                     "=:c and status='ACCEPTED'", c=op(name)) == 0, str(op(name)))

    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = do_sync("s11-future", officer, session_id=sid, metadata=meta(captured_at=future))
    check("S11.20.far-future-capture-flagged-not-rejected", r.status_code == 201,
          f"{r.status_code} {r.text[:180]}")
    if r.status_code == 201:
        flags = r.json().get("timestamp_flags") or []
        row = op_row(client_op=op("s11-future"), user=officer)
        check("S11.21.future-flag-recorded-and-returned",
              "FUTURE_CAPTURE" in flags and "FUTURE_CAPTURE" in json.dumps(row[C_FLAGS]),
              f"{flags} row={row[C_FLAGS]}")
        check("S11.22.flagged-value-was-not-rewritten",
              row[C_CAPTURED] is not None
              and row[C_CAPTURED].isoformat().startswith(future[:19]),
              f"stored={row[C_CAPTURED]} sent={future}")

    r = do_sync("s11-backwards", officer, session_id=sid,
                metadata=meta(captured_at=ts(-60), queued_at=ts(-600)))
    check("S11.23.queue-before-capture-flagged",
          r.status_code == 201 and "QUEUE_BEFORE_CAPTURE"
          in (r.json().get("timestamp_flags") or []),
          f"{r.status_code} {json.dumps(detail_of(r))[:200]}")
    future_upload = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    r = do_sync("s11-upload-future", officer, session_id=sid,
                metadata=meta(uploaded_at=future_upload))
    check("S11.24.upload-after-receipt-flagged",
          r.status_code == 201 and "UPLOAD_AFTER_RECEIPT"
          in (r.json().get("timestamp_flags") or []),
          f"{r.status_code} {json.dumps(detail_of(r))[:200]}")
    check("S11.25.anomaly-is-visible-in-the-stored-row-too",
          scalar("select count(*) from field_capture_operations"
                 " where client_operation_id = :c and timestamp_flags <> '[]'::jsonb",
                 c=op("s11-upload-future")) == 1,
          "a flag must be durable, not only a response field")
    check("S11.26.every-anomalous-capture-kept-its-own-row",
          all(op_row(client_op=op(n), user=officer) is not None
              for n in ("s11-future", "s11-backwards", "s11-upload-future")),
          "flagged captures must still be durable rows")


# ---------------------------------------------------------------------------
# S12 authorization bypass attempts
# ---------------------------------------------------------------------------

def s12_bypass(w):
    section("S12 authorization bypass attempts (enforcing mode, no bypass)")
    officer, sid, aid, admin = w["officer"], w["session"], w["assignment"], w["admin"]

    routes = ["/api/v1/field/work", "/api/v1/field/assignments",
              f"/api/v1/field/assignments/{aid}", "/api/v1/field/operations",
              f"/api/v1/field/captures/{op('s12-anonymous-unknown')}"]
    bad = [(path, get(path, None).status_code) for path in routes
           if get(path, None).status_code != 401]
    check("S12.1.anonymous-refused-on-every-read-route", not bad, str(bad))
    r = requests.post(f"{BASE}/api/v1/field/assignments", json={"user_id": officer,
                  "project_id": w["project_a"]}, headers={}, timeout=60)
    check("S12.2.anonymous-cannot-create-assignment", r.status_code == 401,
          f"{r.status_code} {r.text[:120]}")
    r = requests.patch(f"{BASE}/api/v1/field/assignments/{aid}/status",
                       json={"status": "REVOKED", "reason": "attempt"}, headers={},
                       timeout=60)
    check("S12.3.anonymous-cannot-revoke", r.status_code == 401, f"{r.status_code} {r.text[:120]}")
    r = requests.post(f"{BASE}/api/v1/field/operations/{GOOD_UNKNOWN}/resolve",
                      json={"outcome": "DISMISSED", "note": "attempt"}, headers={},
                      timeout=60)
    check("S12.3b.anonymous-cannot-resolve", r.status_code == 401,
          f"{r.status_code} {r.text[:120]}")
    r = requests.post(f"{BASE}/api/v1/field/sessions", json={"assignment_id": aid},
                      headers={}, timeout=60)
    check("S12.4.anonymous-cannot-open-a-session", r.status_code == 401,
          f"{r.status_code} {r.text[:120]}")
    r = requests.post(f"{BASE}/api/v1/field/sessions/{sid}/close",
                      json={"reason": "attempt"}, headers={}, timeout=60)
    check("S12.5.anonymous-cannot-close-a-session", r.status_code == 401,
          f"{r.status_code} {r.text[:120]}")
    r = requests.post(f"{BASE}/api/v1/field/sync", headers={},
                      files={"file": ("c.jpg", PAYLOAD, "image/jpeg")},
                      data={"client_operation_id": op("s12-anon"), "session_id": sid},
                      timeout=60)
    check("S12.6.anonymous-sync-401", r.status_code == 401, f"{r.status_code} {r.text[:160]}")
    r = get(f"/api/v1/field/captures/{op('s12-anon')}", None)
    check("S12.7.anonymous-recovery-401", r.status_code == 401, f"{r.status_code} {r.text[:140]}")
    check("S12.8.anonymous-probes-wrote-nothing",
          rows_named("s12-anon") == 0
          and scalar("select count(*) from field_capture_operations"
                     " where user_id = :u", u="00000000-0000-0000-0000-000000000000") == 0,
          str(rows_named("s12-anon")))

    # the development bypass cannot stand in for an identified officer
    r = requests.post(f"{BASE}/api/v1/field/sync",
                      headers={"Authorization": "Bearer dev-anonymous"},
                      files={"file": ("c.jpg", PAYLOAD, "image/jpeg")},
                      data={"client_operation_id": op("s12-bypass"), "session_id": sid},
                      timeout=60)
    check("S12.9.development-bypass-token-cannot-capture", r.status_code == 401,
          f"{r.status_code} {r.text[:160]}")
    r = requests.post(f"{BASE}/api/v1/field/sync",
                      headers={"Authorization": "Bearer whatever"},
                      files={"file": ("c.jpg", PAYLOAD, "image/jpeg")},
                      data={"client_operation_id": op("s12-token"), "session_id": sid},
                      timeout=60)
    check("S12.10.unrecognized-token-401", r.status_code == 401,
          f"{r.status_code} {r.text[:160]}")
    ghost = GOOD_UNKNOWN
    r = get("/api/v1/field/work", ghost)
    check("S12.11.dev-token-for-nonexistent-principal-refused", r.status_code == 401,
          f"{r.status_code} {r.text[:160]}")
    r = post_json("/api/v1/field/sessions", ghost, {"assignment_id": aid})
    check("S12.12.ghost-cannot-open-a-session", r.status_code == 401,
          f"{r.status_code} {r.text[:160]}")

    # roles that hold neither new permission
    for role_user, role_name in ((w["citizen"], "CITIZEN"), (w["reviewer"], "REVIEWER"),
                                 (w["supervisor"], "SUPERVISOR")):
        for path in ("/api/v1/field/work", "/api/v1/field/assignments",
                     "/api/v1/field/operations"):
            r = get(path, role_user)
            check(f"S12.13.{role_name}-403-on-{path.rsplit('/')[-1]}", r.status_code == 403,
                  f"{r.status_code} {r.text[:120]}")
        r = post_json("/api/v1/field/assignments", role_user,
                      {"user_id": officer, "project_id": w["project_a"]})
        check(f"S12.14.{role_name}-cannot-create-assignment", r.status_code == 403,
              f"{r.status_code} {r.text[:120]}")
        r = patch_assignment(aid, role_user, "REVOKED", "attempt")
        check(f"S12.15.{role_name}-cannot-revoke", r.status_code == 403,
              f"{r.status_code} {r.text[:120]}")
        r = sync(role_user, op(f"s12-{role_name}"), data=PAYLOAD, **meta())
        check(f"S12.16.{role_name}-cannot-sync", r.status_code == 403,
              f"{r.status_code} {r.text[:140]}")
        check(f"S12.17.{role_name}-sync-wrote-nothing", rows_named(f"s12-{role_name}") == 0,
              str(rows_named(f"s12-{role_name}")))

    # an assignment without any role grant confers nothing
    orphan = new_user(f"{LABEL}-orphan")
    r = create_assignment(admin, orphan, w["project_a"])
    check("S12.18.assignment-created-for-ungranted-officer", r.status_code == 201,
          f"{r.status_code} {r.text[:160]}")
    orphan_assignment = r.json().get("id")
    tracked["assignments"].append(orphan_assignment)
    r = open_session_http(orphan, orphan_assignment, device=f"orphan-{LABEL}")
    check("S12.19.assignment-grants-no-authority", r.status_code == 403,
          f"{r.status_code} {r.text[:160]}")
    check("S12.20.denial-opened-no-session",
          scalar("select count(*) from field_sessions where assignment_id=:i",
                 i=orphan_assignment) == 0,
          str(scalar("select count(*) from field_sessions where assignment_id=:i",
                     i=orphan_assignment)))
    r = sync(orphan, op("s12-orphan"), data=PAYLOAD, **meta())
    check("S12.21.ungranted-officer-cannot-sync", r.status_code == 403,
          f"{r.status_code} {r.text[:160]}")

    # API credentials: field.sync without an officer's scope never captures
    rows0, ev0 = scalar("select count(*) from field_capture_operations"), evidence_total()
    rej0 = audit_count("FIELD_SYNC_REJECTED")
    client_codes = {}
    for label, client in (("narrow", w["client_narrow"]), ("broad", w["client_sync"])):
        name = f"s12-client-{label}"
        r = sync(None, op(name), client=client, data=PAYLOAD, filename="c.jpg", **meta())
        det = detail_of(r)
        client_codes[label] = r.status_code
        check(f"S12.22.{label}-api-client-sync-denied",
              r.status_code in (403, 404)
              and det.get("sync_status") == "authorization_denied",
              f"{r.status_code} {json.dumps(det)[:200]}")
        check(f"S12.23.{label}-api-client-wrote-no-rows",
              (scalar("select count(*) from field_capture_operations"), evidence_total())
              == (rows0, ev0), f"{(rows0, ev0)} -> current")
    note(f"S12.22: API client syncs answered {client_codes}")
    check("S12.24.api-client-denials-were-audited",
          audit_count("FIELD_SYNC_REJECTED") - rej0 == 2,
          f"delta={audit_count('FIELD_SYNC_REJECTED') - rej0}")
    latest = audit_events("FIELD_SYNC_REJECTED")
    failure = payload_of(latest[-1][0]).get("failure") if latest else None
    note(f"S12.22-24: API client captures were refused by gate {failure!r}")
    check("S12.25.denial-names-a-real-gate",
          failure in ("NO_ACTIVE_ASSIGNMENT", "SCOPE_GATE_DENIED", "FOREIGN_OR_MISSING_SESSION",
                      "UNAUTHENTICATED"),
          str(failure))
    # an API credential cannot reach the administrative plane either
    r = list_ops(client=w["client_sync"])
    check("S12.26.api-client-cannot-list-operations", r.status_code == 403,
          f"{r.status_code} {r.text[:140]}")
    r = get("/api/v1/field/assignments", client=w["client_sync"])
    check("S12.27.api-client-cannot-list-assignments", r.status_code == 403,
          f"{r.status_code} {r.text[:140]}")

    # header smuggling cannot add authority
    headers = dict(hdr(officer))
    headers["X-Dev-User-Id"] = admin
    headers["X-Role"] = "ADMINISTRATOR"
    r = requests.get(f"{BASE}/api/v1/field/work", headers=headers, timeout=60)
    clean = get("/api/v1/field/work", officer)
    check("S12.28.injected-headers-change-nothing",
          r.status_code == clean.status_code and r.text == clean.text,
          f"{r.status_code} vs {clean.status_code}")
    r = requests.get(f"{BASE}/api/v1/field/assignments", headers=headers, timeout=60)
    check("S12.29.injected-headers-do-not-reach-admin-routes", r.status_code == 403,
          f"{r.status_code} {r.text[:120]}")

    # an officer cannot administer or read another officer's rows
    r = get(f"/api/v1/field/assignments/{w['assignment_colleague']}", officer)
    check("S12.30.officer-cannot-read-foreign-assignment", r.status_code == 403,
          f"{r.status_code} {r.text[:120]}")
    r = close(w["session_colleague"], officer, reason="attempt")
    check("S12.31.officer-cannot-close-foreign-session", r.status_code == 404,
          f"{r.status_code} {r.text[:120]}")
    check("S12.32.foreign-session-still-active",
          q1("select status from field_sessions where id=:i",
             i=w["session_colleague"])[0] == "ACTIVE",
          str(q1("select status from field_sessions where id=:i", i=w["session_colleague"])[0]))
    accepted_foreign = q("select id from field_capture_operations where user_id=:u"
                         " and status='ACCEPTED'", u=w["colleague"])
    if accepted_foreign:
        r = resolve(str(accepted_foreign[0][0]), officer, outcome="DISMISSED")
        check("S12.33.officer-cannot-resolve", r.status_code == 403,
              f"{r.status_code} {r.text[:140]}")

    # a deactivated principal loses access immediately
    dormant = new_user(f"{LABEL}-dormant")
    grant(dormant, "FIELD_OFFICER", "ORGANIZATION", w["org_a"])
    aid2 = create_assignment(admin, dormant, w["project_a"]).json().get("id")
    tracked["assignments"].append(aid2)
    r = open_session_http(dormant, aid2, device=f"dormant-{LABEL}")
    check("S12.34.active-officer-can-open", r.status_code == 201,
          f"{r.status_code} {r.text[:160]}")
    dormant_session = r.json().get("id") if r.ok else None
    if dormant_session:
        tracked["sessions"].append(dormant_session)
    set_status(dormant, "SUSPENDED")
    check("S12.35.suspended-principal-loses-the-feed",
          get("/api/v1/field/work", dormant).status_code in (401, 403),
          str(get("/api/v1/field/work", dormant).status_code))
    r = sync(dormant, op("s12-dormant"), session_id=dormant_session, data=PAYLOAD, **meta())
    check("S12.36.suspended-principal-cannot-sync", r.status_code in (401, 403),
          f"{r.status_code} {r.text[:160]}")
    check("S12.37.suspended-sync-wrote-nothing", rows_named("s12-dormant") == 0,
          str(rows_named("s12-dormant")))
    check("S12.38.suspended-principal-cannot-close-its-own-session",
          close(dormant_session, dormant, reason="attempt").status_code in (401, 403, 404)
          if dormant_session else True,
          str(close(dormant_session, dormant, reason="attempt").status_code)
          if dormant_session else "no session")
    set_status(dormant, "ACTIVE")


# ---------------------------------------------------------------------------
# S13 cross-organization access
# ---------------------------------------------------------------------------

def s13_cross_org(w):
    section("S13 cross-organization access and count-oracle absence")
    officer, admin = w["officer"], w["admin"]
    officer_b, orgadmin_a, orgadmin_b = w["officer_b"], w["orgadmin_a"], w["orgadmin_b"]
    project_a, project_b = w["project_a"], w["project_b"]

    # an org B officer cannot act inside org A
    r = open_session_http(officer_b, w["assignment"], device=f"xorg-{LABEL}")
    check("S13.1.foreign-user-cannot-open-org-A-assignment", r.status_code == 404,
          f"{r.status_code} {r.text[:140]}")
    check("S13.2.foreign-open-audited-as-security-failure",
          audit_count("FIELD_ASSIGNMENT_SECURITY_FAILURE") >= 1,
          str(audit_count("FIELD_ASSIGNMENT_SECURITY_FAILURE")))
    rows0, ev0 = scalar("select count(*) from field_capture_operations"), evidence_total()
    r = sync(officer_b, op("s13-xorg-sync"), session_id=w["session"], data=PAYLOAD, **meta())
    check("S13.3.foreign-session-id-404", r.status_code == 404
          and detail_of(r).get("sync_status") == "authorization_denied",
          f"{r.status_code} {json.dumps(detail_of(r))[:180]}")
    check("S13.4.cross-org-sync-wrote-nothing",
          (scalar("select count(*) from field_capture_operations"), evidence_total())
          == (rows0, ev0), "domain rows moved under a cross-org attempt")

    # an assignment alone never carries a capture across the org boundary
    r = create_assignment(admin, officer, project_b)
    check("S13.5.admin-can-assign-across-orgs", r.status_code == 201,
          f"{r.status_code} {r.text[:160]}")
    foreign_assignment = r.json().get("id")
    tracked["assignments"].append(foreign_assignment)
    security0 = audit_count("FIELD_ASSIGNMENT_SECURITY_FAILURE")
    rejected0 = audit_count("FIELD_SYNC_REJECTED")
    sid_foreign = open_session_http(officer, foreign_assignment, device=f"xfer-{LABEL}")
    denied_at = "session-open" if sid_foreign.status_code != 201 else "sync"
    if sid_foreign.status_code == 201:
        tracked["sessions"].append(sid_foreign.json().get("id"))
        r = do_sync("s13-xfer", officer, session_id=sid_foreign.json().get("id"))
        det, code = detail_of(r), r.status_code
    else:
        det, code = detail_of(sid_foreign), sid_foreign.status_code
    check("S13.6.evidence-create-scope-gate-refuses-the-cross-org-capture",
          code in (403, 404)
          and det.get("sync_status") == "authorization_denied"
          and rows_named("s13-xfer") == 0,
          f"{code} {json.dumps(det)[:200]} rows={rows_named('s13-xfer')}")
    check("S13.6b.cross-org-capture-attempt-was-audited",
          audit_count("FIELD_SYNC_REJECTED") > rejected0
          or audit_count("FIELD_ASSIGNMENT_SECURITY_FAILURE") > security0,
          f"rejected {rejected0} -> {audit_count('FIELD_SYNC_REJECTED')}, "
          f"security {security0} -> "
          f"{audit_count('FIELD_ASSIGNMENT_SECURITY_FAILURE')}")
    scope_denials = [payload_of(e[0]) for e in
                     audit_events("FIELD_ASSIGNMENT_SECURITY_FAILURE")
                     if payload_of(e[0]).get("failure") == "SCOPE_GATE_DENIED"]
    check("S13.6c.scope-denied-session-open-names-the-foreign-context",
          any(str(p.get("assignment_id")) == str(foreign_assignment)
              and str(p.get("project_id")) == str(project_b) for p in scope_denials),
          json.dumps(scope_denials[-1:] , default=str)[:240])
    note("S13.5-6: the org A officer acting inside org B was refused at "
         f"{denied_at} with {code}; an assignment never confers authority")

    # administrators see only their own organization
    r = list_assignments(orgadmin_b, project_id=project_a)
    r_missing = list_assignments(orgadmin_b, project_id=GOOD_UNKNOWN)
    check("S13.7.foreign-project-filter-is-404", r.status_code == 404,
          f"{r.status_code} {r.text[:140]}")
    check("S13.8.no-existence-oracle",
          r.status_code == r_missing.status_code and r.text == r_missing.text,
          f"foreign-existing {r.status_code} vs never-existing {r_missing.status_code}")
    r = list_assignments(orgadmin_a, project_id=project_a)
    check("S13.9.own-org-admin-can-filter", r.status_code == 200
          and r.json().get("total", 0) >= 1, f"{r.status_code} {r.text[:160]}")
    mine = list_assignments(orgadmin_b)
    ids = [item["id"] for item in mine.json().get("items", [])] if mine.ok else []
    check("S13.10.org-B-admin-list-contains-no-org-A-assignment",
          w["assignment"] not in ids and w["assignment_colleague"] not in ids,
          f"ids={ids[:8]}")
    check("S13.11.listed-total-never-exceeds-visible-items-across-pages",
          mine.json().get("total", 0) >= len(ids),
          f"total={mine.json().get('total')} items={len(ids)}")
    paged = list_assignments(orgadmin_b, limit=1, offset=0)
    check("S13.12.pagination-stays-inside-the-scope",
          paged.status_code == 200 and len(paged.json().get("items", [])) <= 1,
          f"{paged.status_code} {paged.text[:120]}")

    # operations: no cross-org read, no count leak
    r = list_ops(orgadmin_b, project_id=project_a)
    check("S13.13.operations-filter-across-org-404", r.status_code == 404,
          f"{r.status_code} {r.text[:140]}")
    r = list_ops(orgadmin_b)
    listed = [item["id"] for item in r.json().get("items", [])] if r.ok else []
    foreign_ids = {str(x[0]) for x in q("select id from field_capture_operations"
                                        " where project_id = :p", p=project_a)}
    check("S13.14.operations-list-hides-org-A-rows", not set(listed) & foreign_ids,
          f"leak={sorted(set(listed) & foreign_ids)[:5]}")
    check("S13.15.org-B-admin-can-read-own-org-operations", r.status_code == 200,
          f"{r.status_code} {r.text[:140]}")
    leaked_ops = {str(item["id"]) for item in r.json().get("items", [])} & foreign_ids
    visible_in_b = scalar(
        "select count(*) from field_capture_operations o join projects p"
        " on p.id = o.project_id where p.organization_id = :org", org=w["org_b"])
    check("S13.16.operations-total-reflects-only-visible-rows",
          r.json().get("total", 0) == scalar(
              "select count(*) from field_capture_operations o"
              " join projects p on p.id = o.project_id"
              " where p.organization_id = :org", org=w["org_b"])
          or r.json().get("total", 0) >= len(listed),
          f"total={r.json().get('total')} visible-in-org-B={visible_in_b}")

    # status changes and resolutions respect the boundary
    r = patch_assignment(w["assignment"], orgadmin_b, "REVOKED", "cross-org attempt")
    check("S13.17.foreign-admin-cannot-revoke", r.status_code in (403, 404),
          f"{r.status_code} {r.text[:140]}")
    check("S13.18.attempt-left-the-assignment-active",
          q1("select status from field_assignments where id=:i",
             i=w["assignment"])[0] == "ACTIVE",
          str(q1("select status from field_assignments where id=:i", i=w["assignment"])[0]))
    accepted = q("select id from field_capture_operations where status='ACCEPTED'"
                 " and project_id=:p", p=project_a)
    if accepted:
        r = resolve(str(accepted[0][0]), orgadmin_b, outcome="DISMISSED")
        check("S13.19.foreign-admin-cannot-resolve", r.status_code in (403, 404),
              f"{r.status_code} {r.text[:140]}")
        check("S13.20.operation-remains-unresolved",
              q1("select resolution_status from field_capture_operations where id=:i",
                 i=str(accepted[0][0]))[0] == "UNRESOLVED",
              "resolution leaked across the boundary")
    r = create_assignment(orgadmin_b, officer_b, project_a)
    check("S13.21.foreign-admin-cannot-assign-into-org-A", r.status_code in (403, 404),
          f"{r.status_code} {r.text[:140]}")
    check("S13.22.attempt-created-no-assignment",
          scalar("select count(*) from field_assignments where project_id=:p"
                 " and user_id=:u", p=project_a, u=officer_b) == 0,
          str(scalar("select count(*) from field_assignments where project_id=:p and user_id=:u",
                     p=project_a, u=officer_b)))

    # the work feed is scoped to the caller and reveals nothing else
    r = work(officer_b)
    feed = [item["assignment_id"] for item in r.json().get("items", [])] if r.ok else []
    check("S13.23.work-feed-shows-only-own-assignments",
          w["assignment"] not in feed and w["assignment_colleague"] not in feed,
          f"feed={feed[:6]}")
    r = work(officer_b, assignment_id=w["assignment"])
    check("S13.24.foreign-assignment-filter-is-not-a-window",
          r.status_code == 404 or (r.ok and not r.json().get("items")),
          f"{r.status_code} {r.text[:140]}")
    r = get_capture(op("s13-victim"), actor=officer_b)
    victim = q("select client_operation_id from field_capture_operations"
               " where user_id=:u limit 1", u=officer)
    if victim:
        r = get_capture(str(victim[0][0]), actor=officer_b)
        check("S13.25.foreign-officer-cannot-recover-another-capture", r.status_code == 404,
              f"{r.status_code} {r.text[:140]}")

    # an accepted capture stays bound to its own project and organization
    rows = q("select distinct o.project_id, p.organization_id from field_capture_operations o"
             " join projects p on p.id = o.project_id where o.user_id = :u", u=officer)
    check("S13.26.captures-land-only-in-projects-the-officer-is-granted-for",
          all(str(p) == project_a for p, _ in rows),
          str([(str(p), str(o)) for p, o in rows])[:220])
    check("S13.27.no-org-A-project-ever-appears-for-org-B-only-principals",
          not q("select id from field_capture_operations where project_id=:p and user_id=:u",
                p=project_a, u=officer_b),
          "an org B officer captured into org A")


# ---------------------------------------------------------------------------
# S14 audit integrity
# ---------------------------------------------------------------------------

FIELD_EVENTS = [
    "FIELD_ASSIGNMENT_CREATED", "FIELD_ASSIGNMENT_ACCESSED",
    "FIELD_ASSIGNMENT_STATUS_CHANGED", "FIELD_ASSIGNMENT_EXPIRED",
    "FIELD_ASSIGNMENT_SECURITY_FAILURE", "FIELD_SESSION_OPENED",
    "FIELD_SESSION_CLOSED", "FIELD_SYNC_ACCEPTED", "FIELD_SYNC_DUPLICATE",
    "FIELD_SYNC_CONFLICT", "FIELD_SYNC_CONFLICT_RESOLVED", "FIELD_SYNC_REJECTED",
    "FIELD_EVIDENCE_ASSOCIATED",
]

SECRET_KEYS = {"data", "file", "bytes", "content", "content_b64", "image",
               "payload_bytes", "password", "token", "secret", "authorization",
               "jwt", "cookie"}


def tamper_update_with_rollback(seq, payload_json):
    """Controlled ledger UPDATE inside a rollback-guarded block (BE-023 §4).

    ``tests/audit_guard.py`` is the shipped statement of the rule: DELETE and
    TRUNCATE of ledger rows are *always* violations, and UPDATE is legitimate
    only when the block guarantees rollback -- that is how tamper detection is
    exercised. An earlier revision of this probe deleted a row instead, and was
    withdrawn after it destroyed one harness event (see the Stage E results
    document). This helper can therefore never destroy history.
    """
    with engine.connect() as c:
        txn = c.begin()
        try:
            c.execute(text("UPDATE audit_ledger_events SET payload = CAST(:p AS json)"
                           " WHERE sequence_number = :s"), {"p": payload_json, "s": seq})
            return None
        except Exception as error:  # noqa: BLE001 - the refusal is the result
            return str(error).splitlines()[0][:260]
        finally:
            txn.rollback()


def tamper_insert_with_rollback(seq):
    """Attempt to reuse a live sequence number; always rolled back.

    Every NOT NULL column is supplied so the only thing that can refuse this
    insert is ``uq_audit_ledger_sequence`` -- an earlier revision omitted them
    and "passed" on a NOT NULL violation instead of the constraint it claimed.
    """
    with engine.connect() as c:
        txn = c.begin()
        try:
            c.execute(text(
                "INSERT INTO audit_ledger_events (id, sequence_number, event_type,"
                " action, resource_type, resource_id, actor_id, project_id, payload,"
                " metadata, previous_hash, event_hash, hash_algorithm, ledger_version,"
                " created_at) VALUES (:i, :s, 'PROBE_TAMPER', 'probe', 'probe', NULL,"
                " NULL, NULL, '{}', '{}', 'p', 'h', 'SHA-256', 'audit-v1', now())"),
                {"i": str(uuid.uuid4()), "s": seq})
            return None
        except Exception as error:  # noqa: BLE001 - the refusal is the result
            return str(error).splitlines()[0][:260]
        finally:
            txn.rollback()


def s14_audit_integrity(w):
    section("S14 audit integrity (coverage, linkage, no secrets, append-only)")
    admin, officer, project_a = w["admin"], w["officer"], w["project_a"]

    check("S14.1.chain-valid-before-lifecycle", chain(), "verify_chain reported invalid")
    before = scalar("select count(*) from audit_ledger_events")
    max_seq = scalar("select coalesce(max(sequence_number),0) from audit_ledger_events")
    check("S14.2.rows-equal-max-sequence", before == max_seq,
          f"rows={before} max_sequence={max_seq}")

    # one full lifecycle, every step audited
    grant(w["reviewer"], "FIELD_OFFICER", "ORGANIZATION", w["org_a"])
    r = create_assignment(admin, w["reviewer"], project_a, instructions="audit probe")
    check("S14.3.lifecycle-assignment-created", r.status_code == 201,
          f"{r.status_code} {r.text[:160]}")
    aid_l = r.json().get("id") if r.ok else None
    if aid_l:
        tracked["assignments"].append(aid_l)
    s = open_session_http(w["reviewer"], aid_l, device=f"audit-{LABEL}")
    check("S14.4.lifecycle-session-opened", s.status_code == 201,
          f"{s.status_code} {s.text[:160]}")
    sid_l = s.json().get("id") if s.ok else None
    if sid_l:
        tracked["sessions"].append(sid_l)

    accepted = do_sync("s14-lifecycle", w["reviewer"], session_id=sid_l)
    check("S14.5.lifecycle-capture-accepted", accepted.status_code == 201,
          f"{accepted.status_code} {accepted.text[:180]}")
    evidence_id = accepted.json().get("evidence_id") if accepted.ok else None
    op_id = accepted.json().get("operation_id") if accepted.ok else None
    replay = do_sync("s14-lifecycle", w["reviewer"], session_id=sid_l)
    check("S14.6.lifecycle-replay-was-a-duplicate", replay.status_code == 200,
          f"{replay.status_code} {replay.text[:160]}")
    read = get(f"/api/v1/field/assignments/{aid_l}", admin)
    check("S14.7.lifecycle-assignment-read-allowed", read.status_code == 200,
          f"{read.status_code} {read.text[:140]}")
    closed = close(sid_l, w["reviewer"], reason="probe complete") if sid_l else None
    check("S14.8.lifecycle-session-closed",
          closed is not None and closed.status_code == 200,
          f"{getattr(closed, 'status_code', None)} {getattr(closed, 'text', '')[:140]}")
    revoked = patch_assignment(aid_l, admin, "REVOKED", "audit probe")
    check("S14.9.lifecycle-assignment-revoked", revoked.status_code == 200,
          f"{revoked.status_code} {revoked.text[:140]}")

    conflict = do_sync("s14-conflict", w["reviewer"], session_id=sid_l)
    check("S14.10.lifecycle-conflict-created",
          conflict.status_code == 409 and detail_of(conflict).get("sync_status") == "conflict",
          f"{conflict.status_code} {json.dumps(detail_of(conflict))[:200]}")
    conflict_row = op_row(client_op=op("s14-conflict"), user=w["reviewer"])
    conflict_id = str(conflict_row[C_ID]) if conflict_row else None
    resolved = (resolve(conflict_id, admin, outcome="DISMISSED",
                        note="stage e audit probe") if conflict_id else None)
    check("S14.11.lifecycle-conflict-resolved",
          resolved is not None and resolved.status_code == 200,
          f"{getattr(resolved, 'status_code', None)} {getattr(resolved, 'text', '')[:160]}")

    exp = create_assignment(admin, w["reviewer"], project_a,
                            valid_from=iso(minutes=-120), expires_at=iso(minutes=-60))
    if exp.ok:
        tracked["assignments"].append(exp.json().get("id"))
    feed = work(w["reviewer"])
    check("S14.12.lifecycle-expiry-evaluated-through-the-feed",
          exp.status_code == 201 and feed.status_code == 200,
          f"{exp.status_code} {feed.status_code} {feed.text[:120]}")

    present = {t: audit_count(t) for t in FIELD_EVENTS}
    missing = [t for t, n in present.items() if n == 0]
    check("S14.13.every-field-event-type-was-produced", not missing,
          json.dumps(present)[:400])

    rows = q("select event_type, actor_id, resource_type, resource_id, payload"
             " from audit_ledger_events where event_type like 'FIELD_%' and created_at >= :s",
             s=RUN_STARTED)
    no_actor = sorted({str(r[0]) for r in rows if r[1] is None})
    no_type = sorted({str(r[0]) for r in rows if not r[2]})
    check("S14.14a.every-field-event-names-an-actor-and-a-resource-type",
          not no_actor and not no_type, f"no_actor={no_actor} no_type={no_type}")
    # resource_id is NULL exactly when no single server row was identified: a list
    # read, or a denial that must not confirm that a foreign row exists (R2).
    unlocatable = sorted({
        str(r[0]) for r in rows if r[3] is None and not (
            set(payload_of(r[4]) or {}) & {"operation_id", "client_operation_id",
                                           "assignment_id", "session_id", "project_id",
                                           "access"})})
    check("S14.14b.null-resource-events-are-still-investigable", not unlocatable,
          f"unlocatable={unlocatable[:6]}")
    check("S14.14c.row-scoped-events-carry-their-resource-id",
          all(r[3] is not None for r in rows
              if r[0] in ("FIELD_SYNC_ACCEPTED", "FIELD_EVIDENCE_ASSOCIATED",
                          "FIELD_ASSIGNMENT_CREATED", "FIELD_SESSION_OPENED")),
          "an event naming a created row lost its resource link")
    bad_payload = sorted({str(r[0]) for r in rows if not isinstance(payload_of(r[4]), dict)})
    check("S14.15.every-event-payload-is-a-json-object", not bad_payload, str(bad_payload[:6]))

    # no secrets, no raw bytes, no encoded image anywhere in the payloads
    encoded = base64.b64encode(PAYLOAD).decode()
    offenders = []
    for r in rows:
        payload = payload_of(r[4])
        blob = json.dumps(payload, default=str)
        if encoded[:32] in blob:
            offenders.append(f"{r[0]}:raw-image")
        for key, value in payload.items():
            if key.lower() in SECRET_KEYS:
                offenders.append(f"{r[0]}:{key}")
            if isinstance(value, (bytes, bytearray)):
                offenders.append(f"{r[0]}:bytes-value")
            if isinstance(value, str) and len(value) > 4000:
                offenders.append(f"{r[0]}:oversize-string")
            if isinstance(value, dict) and any(k.lower() in SECRET_KEYS for k in value):
                offenders.append(f"{r[0]}:nested-secret-key")
    check("S14.16.audit-payloads-carry-no-payload-bytes-or-secrets",
          not offenders, str(sorted(set(offenders))[:8]))

    accepted_events = audit_events("FIELD_SYNC_ACCEPTED")
    linked = sum(1 for row in accepted_events
                 if all(payload_of(row[0]).get(k) for k in
                        ("evidence_id", "operation_id", "request_hash", "payload_sha256")))
    check("S14.17.accepted-events-link-operation-evidence-and-hashes",
          linked == len(accepted_events) and linked > 0,
          f"linked={linked} of={len(accepted_events)}")
    dup_counters = [payload_of(d[0]).get("sync_count") for d in audit_events("FIELD_SYNC_DUPLICATE")]
    check("S14.18.duplicate-events-carry-a-monotonic-counter",
          dup_counters == sorted(dup_counters) and len(dup_counters) > 0,
          str(dup_counters)[:200])
    conflict_events = audit_events("FIELD_SYNC_CONFLICT")
    check("S14.19.conflict-events-explain-themselves",
          bool(conflict_events) and all(
              payload_of(c[0]).get("conflict_reason")
              and payload_of(c[0]).get("client_operation_id") for c in conflict_events),
          str([sorted(payload_of(c[0])) for c in conflict_events[-1:]])[:250])
    resolved_events = audit_events("FIELD_SYNC_CONFLICT_RESOLVED")
    check("S14.20.resolution-events-name-actor-outcome-and-operation",
          bool(resolved_events) and all(
              e[1] and payload_of(e[0]).get("operation_id")
              and payload_of(e[0]).get("resolution_outcome")
              in ("DISMISSED", "RESUBMISSION_REQUIRED")
              for e in resolved_events),
          str([payload_of(e[0]) for e in resolved_events[-1:]])[:250])
    if conflict_id:
        # GET /field/operations caps limit at 100, so a manager page must stay
        # inside the shipped bound; over-max is itself a contract.
        pages = [list_ops(admin, project_id=project_a, limit=100, offset=o)
                 for o in (0, 100)]
        items = [item for r in pages if r.ok for item in (r.json().get("items") or [])]
        stored = next((item for item in items if str(item.get("id")) == conflict_id), {})
        check("S14.20a.manager-operations-list-read-succeeded",
              all(r.status_code == 200 for r in pages),
              str([(r.status_code, r.text[:120]) for r in pages if r.status_code != 200]))
        check("S14.20b.the-managers-note-is-durable-on-the-row",
              "stage e audit probe" in str(stored.get("resolution_note") or "")
              and str(stored.get("resolved_by") or "") == str(admin),
              json.dumps({k: stored.get(k) for k in
                          ("resolution_note", "resolved_by", "resolution_outcome")})[:220])
        check("S14.20c.resolution-kept-the-conflict-visible",
              stored.get("conflict_reason") and stored.get("resolution_status") == "RESOLVED",
              json.dumps({k: stored.get(k) for k in
                          ("conflict_reason", "resolution_status")})[:200])
        too_many = list_ops(admin, project_id=project_a, limit=200)
        check("S14.20d.over-max-page-size-is-refused", too_many.status_code == 422,
              f"{too_many.status_code} {too_many.text[:140]}")

    evidence_ids = {payload_of(r[0]).get("evidence_id") for r in accepted_events}
    evidence_ids.discard(None)
    twins = scalar("select count(distinct resource_id::text) from audit_ledger_events"
                   " where event_type='EVIDENCE_UPLOADED'"
                   " and resource_id::text = any(:ids)",
                   ids=sorted(evidence_ids)) if evidence_ids else 0
    check("S14.21.every-accepted-capture-has-an-evidence-upload-twin",
          bool(evidence_ids) and twins == len(evidence_ids),
          f"twins={twins} distinct_evidence={len(evidence_ids)}")

    # Append-only enforcement lives in three places, not in a trigger: the
    # application has no ledger UPDATE/DELETE path, uq_audit_ledger_sequence
    # forbids sequence reuse, and the hash chain makes any tampering detectable.
    # The BE-023 guard (tests/audit_guard.py) additionally scans the test tree.
    sample = q("select id, sequence_number, event_type, action, actor_id,"
               " resource_type, resource_id, payload, created_at, previous_hash,"
               " event_hash from audit_ledger_events"
               " where event_type like 'FIELD_%' order by sequence_number desc limit 1")
    if sample:
        columns = ("id", "sequence_number", "event_type", "action", "actor_id",
                   "resource_type", "resource_id", "payload", "created_at",
                   "previous_hash", "event_hash")
        row = SimpleNamespace(**dict(zip(columns, sample[0])))
        seq = int(row.sequence_number)
        ok, err = audit_service.verify_event(row)
        check("S14.22.stored-field-event-hash-recomputes-with-shipped-code", ok,
              str(err)[:200])
        tampered = SimpleNamespace(**{**row.__dict__,
                                      "payload": {**(row.payload or {}),
                                                  "probe": "EVIL"}})
        detected_ok, detected_err = audit_service.verify_event(tampered)
        check("S14.23.tampering-is-detectable-by-the-chain",
              detected_ok is False and "mismatch" in str(detected_err),
              str(detected_err)[:200])

        # controlled mutation, rollback guaranteed (BE-023 §4 shape) -- no damage
        before_json = json.dumps(row.payload, sort_keys=True)
        update_err = tamper_update_with_rollback(seq, '{"probe": "EVIL"}')
        after_json = json.dumps(
            q1("select payload from audit_ledger_events where sequence_number=:s",
               s=seq)[0], sort_keys=True)
        note(f"S14.24 controlled UPDATE under rollback: "
             f"{'refused at the driver' if update_err else 'applied then rolled back'}"
             f"{' -- ' + update_err if update_err else ''}")
        check("S14.24.ledger-row-unchanged-after-rolled-back-update",
              after_json == before_json, f"{after_json[:120]} != {before_json[:120]}")

        # sequence numbers are never reusable
        collision = tamper_insert_with_rollback(seq)
        check("S14.25.sequence-number-collision-is-refused",
              collision is not None and "uq_audit_ledger_sequence" in collision,
              str(collision)[:220])
        check("S14.25b.probe-event-still-present-exactly-once",
              scalar("select count(*) from audit_ledger_events where sequence_number=:s",
                     s=seq) == 1, "the mutation probes must leave history intact")
        check("S14.25c.chain-valid-after-tamper-probes", chain(),
              "verify_chain reported invalid")

    after = scalar("select count(*) from audit_ledger_events")
    check("S14.26.ledger-only-grew", after > before, f"{before} -> {after}")
    max_seq = scalar("select coalesce(max(sequence_number),0) from audit_ledger_events")
    check("S14.27.contiguity-still-holds",
          after == scalar("select coalesce(max(sequence_number),0) from audit_ledger_events"),
          f"rows={after} max={max_seq}")
    check("S14.28.chain-valid-after-lifecycle", chain(), "verify_chain reported invalid")
    note(f"S14 event coverage: {json.dumps(present)[:400]}")


def main():
    wait_ready()
    world = build_world("b")
    check("S0.audit-chain-valid-at-start", chain(), "verify_chain reported invalid")
    ledger0 = scalar("select count(*) from audit_ledger_events")
    try:
        for section_fn in (s8_malformed_ids, s9_malformed_payloads, s10_oversized,
                           s11_location_and_time, s12_bypass, s13_cross_org,
                           s14_audit_integrity):
            section_fn(world)
    except Exception as error:  # a probe crash must not orphan harness rows
        check("S98.no-probe-crashed-the-harness", False,
              f"{type(error).__name__}: {str(error)[:300]}")
        raise
    finally:
        ledger_end = scalar("select count(*) from audit_ledger_events")
        note(f"part-B ledger {ledger0} -> {ledger_end}")
        check("S99.audit-chain-valid-at-end", chain(), "verify_chain reported invalid")
        teardown()
        print("teardown_remaining=" + json.dumps(residue()))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
