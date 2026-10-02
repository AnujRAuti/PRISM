"""BE-026 unit tests: synchronization identity, vocabulary, metadata rules.

Everything here is decision logic that must not depend on a database: the
request hash that makes offline synchronization idempotent, the conflict and
status vocabularies the task fixes (§11/§12), and the metadata rules that
decide what the server is allowed to vouch for. Runtime behaviour (rows,
audits, denials against real scope) is covered by the integration suite.
"""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from backend.db.models import (
    FIELD_CONFLICT_REASONS,
    FIELD_LOCATION_SOURCES,
    FIELD_OPERATION_STATUSES,
    FIELD_SYNC_STATUSES,
    FieldCaptureOperation,
)
from backend.schemas.field_operations import (
    FieldConflictReason,
    FieldLocationSource,
    FieldOperationStatus,
    FieldSyncStatus,
)
from backend.services import field_operations as svc
from backend.services.authorization import Principal
from backend.services.storage import StorageError

BYTES_A = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
BYTES_B = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x02\x00\x00"


def officer() -> Principal:
    return Principal(
        principal_id=str(uuid4()),
        principal_type="USER",
        authenticated=True,
        status="ACTIVE",
    )


#: Fixed once per run: two calls must describe the *same* submission, so the
#: client-asserted timestamps cannot be recomputed each time.
BASE = datetime.now(timezone.utc) - timedelta(hours=6)


def past(minutes: int) -> str:
    """An aware ISO timestamp `minutes` before the fixed capture time.

    Client-asserted times are always in the past here so that a test never
    depends on when the suite happens to run.
    """
    return (BASE - timedelta(minutes=minutes)).isoformat()


def request_from(principal: Principal | None = None, *, data: bytes = BYTES_A, **overrides):
    """One well-formed synchronization request, with fields overridable."""
    fields = {
        "client_operation_id": "op-offline-0001",
        "client_capture_id": "cap-0001",
        "client_device_id": "pixel-7-a",
        "captured_at": past(120),
        "queued_at": past(118),
        "uploaded_at": past(5),
        "latitude": "53.3498",
        "longitude": "-6.2603",
        "capture_accuracy_m": "8.5",
        "altitude_m": "54.0",
        "location_source": "DEVICE_GPS",
    }
    fields.update(overrides)
    return svc.build_sync_request(
        principal=principal or officer(),
        data=data,
        filename="capture.jpg",
        declared_content_type="image/jpeg",
        **fields,
    )


def validate(**overrides):
    return svc._validate_metadata(request_from(**overrides))


# ---------------------------------------------------------------------------
# vocabularies (task §11 / §12)
# ---------------------------------------------------------------------------

def test_sync_status_vocabulary_matches_the_locked_lists():
    assert set(svc.SYNC_STATUS_VOCABULARY) == set(FIELD_SYNC_STATUSES)
    assert {item.value for item in FieldSyncStatus} == set(FIELD_SYNC_STATUSES)


def test_failure_vocabulary_is_not_collapsed_into_one_status():
    required = {
        "accepted",
        "already_synchronized",
        "rejected",
        "conflict",
        "authorization_denied",
        "validation_failed",
        "temporarily_unavailable",
    }
    assert required <= set(svc.SYNC_STATUS_VOCABULARY)


def test_pending_reservation_is_never_a_public_sync_status():
    # PENDING is a real persisted status (the reservation) but not a vocabulary
    # word, so no client can ever be told "pending".
    assert "PENDING" in FIELD_OPERATION_STATUSES
    assert "pending" not in set(FIELD_SYNC_STATUSES)
    assert FieldOperationStatus.PENDING.value not in {item.value for item in FieldSyncStatus}


def test_conflict_reason_vocabulary_matches_schema():
    assert set(FIELD_CONFLICT_REASONS) == {item.value for item in FieldConflictReason}


def test_location_source_vocabulary_matches_schema():
    assert set(FIELD_LOCATION_SOURCES) == {item.value for item in FieldLocationSource}
    assert set(svc.LOCATION_SOURCES) == set(FIELD_LOCATION_SOURCES)


def test_unknown_sync_status_is_a_programming_error():
    with pytest.raises(ValueError):
        svc.FieldOperationError(500, "nope", sync_status="exploded")


# ---------------------------------------------------------------------------
# denial mapping mirrors BE-016's enforce() exactly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("reason", "status_code"),
    [
        ("SCOPE_DENIED", 404),
        ("RESOURCE_UNSCOPEABLE", 404),
        ("UNAUTHENTICATED", 401),
        ("NO_PERMISSION", 403),
        ("PRINCIPAL_DISABLED", 403),
        ("UNKNOWN_PERMISSION", 403),
    ],
)
def test_denial_error_mapping(reason, status_code):
    error = svc._denial_error(reason)
    assert error.status_code == status_code
    assert error.sync_status == "authorization_denied"


def test_denial_never_maps_to_server_error():
    for reason in (
        "SCOPE_DENIED",
        "RESOURCE_UNSCOPEABLE",
        "UNAUTHENTICATED",
        "NO_PERMISSION",
        "PRINCIPAL_DISABLED",
        "UNKNOWN_PERMISSION",
    ):
        assert svc._denial_error(reason).status_code in (401, 403, 404)


# ---------------------------------------------------------------------------
# identifier handling: never timestamps alone, never malformed ids
# ---------------------------------------------------------------------------

def test_require_uuid_accepts_uppercase_and_rejects_junk():
    value = str(uuid4()).upper()
    assert svc._require_uuid(value, "user_id") == value.lower()
    with pytest.raises(svc.FieldOperationError) as excinfo:
        svc._require_uuid("not-a-uuid", "user_id")
    assert excinfo.value.status_code == 422
    assert excinfo.value.validation_errors == ["USER_ID_INVALID"]


def test_sync_identity_is_the_client_operation_id_not_a_timestamp():
    req = request_from()
    identity = req.identity_fields()
    assert identity["client_operation_id"] == "op-offline-0001"
    assert "captured_at" not in identity
    assert identity["payload_sha256"] == sha256(BYTES_A).hexdigest()
    assert identity["file_size"] == len(BYTES_A)


def test_anonymous_principal_cannot_own_a_capture():
    anonymous = Principal(
        principal_id=None,
        principal_type="ANONYMOUS",
        authenticated=False,
        status="ANONYMOUS",
    )
    with pytest.raises(svc.FieldOperationError) as excinfo:
        request_from(anonymous)
    assert excinfo.value.status_code == 401


# ---------------------------------------------------------------------------
# request hash: stable for the same submission, different for any change
# ---------------------------------------------------------------------------

def test_request_hash_is_stable_for_the_same_submission():
    assert request_from().request_hash == request_from().request_hash


def test_request_hash_ignores_cosmetic_formatting():
    plain = request_from(latitude="53.3498", longitude="-6.2603",
                         capture_accuracy_m="8.5", location_source="DEVICE_GPS")
    messy = request_from(latitude=" 53.34980 ", longitude="-6.26030",
                         capture_accuracy_m="8.500", location_source="device_gps")
    assert plain.request_hash == messy.request_hash


def test_request_hash_treats_equivalent_timezone_offsets_as_equal():
    iso = (datetime.now(timezone.utc) - timedelta(minutes=120)).replace(microsecond=0)
    base = request_from(captured_at=iso.isoformat())
    zulu = request_from(captured_at=iso.strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert base.request_hash == zulu.request_hash


def test_request_hash_covers_the_payload_bytes():
    same_metadata = request_from(data=BYTES_A)
    different_bytes = request_from(data=BYTES_B)
    assert same_metadata.request_hash != different_bytes.request_hash
    assert same_metadata.payload_sha256 != different_bytes.payload_sha256


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("client_operation_id", "op-offline-9999"),
        ("client_capture_id", "cap-9999"),
        ("client_device_id", "pixel-7-b"),
        ("captured_at", "2027-01-01T00:00:00+00:00"),
        ("queued_at", "2027-01-01T00:00:00+00:00"),
        ("uploaded_at", "2027-01-01T00:00:00+00:00"),
        ("latitude", "12.25"),
        ("longitude", "12.25"),
        ("capture_accuracy_m", "100"),
        ("altitude_m", "100"),
        ("location_source", "DEVICE_MANUAL"),
        ("zero_island_confirmed", "true"),
    ],
)
def test_every_metadata_field_changes_the_request_hash(field, replacement):
    assert (
        request_from(**{field: replacement}).request_hash
        != request_from().request_hash
    )


def test_blank_form_values_count_as_absent_not_as_empty_strings():
    req = request_from(client_capture_id="", client_device_id="   ", latitude="")
    assert req.client_capture_id is None
    assert req.client_device_id is None
    assert req.latitude is None
    # Absent and explicitly-missing must hash the same way.
    assert req.request_hash == request_from(
        client_capture_id=None, client_device_id=None, latitude=None
    ).request_hash


def test_session_id_is_canonicalised_before_hashing():
    session_id = str(uuid4())
    lower = request_from(session_id=session_id)
    upper = request_from(session_id=session_id.upper())
    spaced = request_from(session_id=f"  {session_id}  ")
    assert lower.request_hash == upper.request_hash == spaced.request_hash
    assert lower.session_id == session_id


# ---------------------------------------------------------------------------
# form bounds: the multipart synchronization form has no schema, so its limits
# come from the columns that store it. Stage E found both guards missing -- an
# over-wide text and an unparseable session id reached Postgres as free text
# and surfaced as a 500 for what is a client mistake, which design §12 forbids.
# ---------------------------------------------------------------------------

def build(**overrides):
    """`build_sync_request` with every argument defaulted to a valid value.

    `request_from` pins the upload name and declared type because the hashing
    tests above need them stable; the width probes have to vary them.
    """
    args = {
        "principal": officer(),
        "data": BYTES_A,
        "filename": "capture.jpg",
        "declared_content_type": "image/jpeg",
        "client_operation_id": "op-offline-0001",
        "captured_at": past(120),
        "queued_at": past(118),
        "uploaded_at": past(5),
    }
    args.update(overrides)
    return svc.build_sync_request(**args)


def refusal(**overrides) -> svc.FieldOperationError:
    with pytest.raises(svc.FieldOperationError) as caught:
        build(**overrides)
    return caught.value


@pytest.mark.parametrize("field", sorted(svc.SYNC_FORM_WIDTHS))
def test_over_wide_form_text_is_a_deterministic_422_not_a_driver_error(field):
    error = refusal(**{field: "x" * (svc.SYNC_FORM_WIDTHS[field] + 1)})
    assert error.status_code == 422
    assert error.sync_status == "validation_failed"
    assert error.validation_errors == [f"{field.upper()}_TOO_LONG"]


@pytest.mark.parametrize("field", sorted(svc.SYNC_FORM_WIDTHS))
def test_the_form_bound_is_the_column_width_and_no_tighter(field):
    assert build(**{field: "x" * svc.SYNC_FORM_WIDTHS[field]}) is not None


def test_a_malformed_sync_session_id_is_refused_before_it_reaches_a_query():
    error = refusal(session_id="not-a-session-uuid")
    assert error.status_code == 422
    assert error.sync_status == "validation_failed"
    assert error.validation_errors == ["SESSION_ID_MALFORMED"]


def test_session_identifier_tolerates_formatting_and_absence_only():
    session_id = str(uuid4())
    assert svc._session_identifier(f"  {session_id.upper()}  ") == session_id
    assert svc._session_identifier(None) is None
    assert svc._session_identifier("") is None


def test_recovery_labels_are_bounded_by_the_same_column_width():
    """`captures/{client_operation_id}` is compared against the column, so an
    over-wide label is refused here rather than in the driver."""
    with pytest.raises(svc.FieldOperationError) as caught:
        svc.get_capture_by_client_id(
            None,
            principal=officer(),
            client_operation_id="x" * (
                svc.SYNC_FORM_WIDTHS["client_operation_id"] + 1
            ),
        )
    assert caught.value.status_code == 422
    assert caught.value.validation_errors == ["CLIENT_OPERATION_ID_TOO_LONG"]


# ---------------------------------------------------------------------------
# metadata validation: never invent, never coerce, never half-store
# ---------------------------------------------------------------------------

def test_a_complete_fix_validates_without_errors_or_flags():
    checked = validate()
    assert checked.errors == []
    assert checked.flags == []
    assert str(checked.latitude) == "53.3498"
    assert str(checked.longitude) == "-6.2603"
    assert checked.location_source == "DEVICE_GPS"


def test_missing_gps_is_accepted_as_unlocated_not_zero_island():
    checked = validate(latitude=None, longitude=None, capture_accuracy_m=None,
                       altitude_m=None, location_source=None)
    assert checked.errors == []
    assert checked.latitude is None
    assert checked.longitude is None
    assert checked.location_source is None


def test_naive_timestamps_are_refused_not_assumed_utc():
    assert "CAPTURED_AT_NAIVE_TIMESTAMP" in validate(captured_at="2026-10-01T12:00:00").errors


def test_unparseable_values_are_labelled_per_field():
    checked = validate(captured_at="last tuesday", latitude="north",
                       capture_accuracy_m="tight")
    assert "CAPTURED_AT_UNPARSEABLE" in checked.errors
    assert "LATITUDE_UNPARSEABLE" in checked.errors
    assert "LONGITUDE_UNPARSEABLE" not in checked.errors
    assert "GPS_UNPARSEABLE" in checked.errors


def test_out_of_range_coordinates_are_refused():
    assert "LATITUDE_OUT_OF_RANGE" in validate(latitude="91.5", longitude="-6.2603").errors
    assert "LONGITUDE_OUT_OF_RANGE" in validate(latitude="53.3498", longitude="-180.5").errors


def test_half_a_fix_is_refused_and_never_stored_partially():
    checked = validate(longitude=None, location_source="DEVICE_GPS")
    assert "GPS_PARTIAL_FIX" in checked.errors
    # The unusable fix is dropped wholesale rather than stored as one number.
    assert checked.latitude is None
    assert checked.longitude is None
    assert checked.capture_accuracy_m is None


def test_unconfirmed_zero_island_is_refused_but_confirmed_is_kept():
    refused = validate(latitude="0.0", longitude="0.0", location_source="DEVICE_MANUAL")
    assert "ZERO_ISLAND_UNCONFIRMED" in refused.errors
    assert refused.latitude is None
    accepted = validate(
        latitude="0.0", longitude="0.0", location_source="DEVICE_MANUAL",
        zero_island_confirmed="true",
    )
    assert accepted.errors == []
    assert str(accepted.latitude) == "0"


def test_accuracy_requires_a_fix():
    assert "ACCURACY_WITHOUT_FIX" in validate(
        latitude=None, longitude=None, location_source=None
    ).errors


def test_a_fix_requires_a_provenance_source():
    assert "LOCATION_SOURCE_REQUIRED" in validate(location_source=None).errors


def test_unknown_location_source_is_named_not_silently_dropped():
    assert "LOCATION_SOURCE_INVALID" in validate(location_source="SATSUITE").errors


def test_impossible_timestamp_orderings_are_flagged_without_rejecting_the_capture():
    future = validate(captured_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    assert "FUTURE_CAPTURE" in future.flags
    assert future.errors == []

    inverted = validate(captured_at=past(5), queued_at=past(120))
    assert "QUEUE_BEFORE_CAPTURE" in inverted.flags

    early_upload = validate(captured_at=past(120), queued_at=past(10), uploaded_at=past(20))
    assert "UPLOAD_BEFORE_QUEUE" in early_upload.flags


def test_upload_after_receipt_is_flagged_not_rewritten():
    checked = validate(
        uploaded_at=(datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    )
    assert "UPLOAD_AFTER_RECEIPT" in checked.flags
    assert checked.uploaded_at is not None


def test_timestamps_are_never_derived_from_each_other():
    checked = validate(captured_at=None, queued_at=None, uploaded_at=None)
    assert checked.errors == []
    assert checked.captured_at is None
    assert checked.queued_at is None
    assert checked.uploaded_at is None
    # received_at is the server's own clock and is set independently.
    req = request_from(captured_at=None, queued_at=None, uploaded_at=None)
    assert req.received_at is not None
    assert req.received_at.tzinfo is not None


# ---------------------------------------------------------------------------
# assignment window rules
# ---------------------------------------------------------------------------

def test_assignment_window_rejects_naive_bounds():
    with pytest.raises(svc.FieldOperationError) as excinfo:
        svc._check_window(datetime(2026, 10, 1), None)
    assert excinfo.value.validation_errors == ["VALID_FROM_NAIVE_TIMESTAMP"]


def test_assignment_window_requires_expiry_after_start():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with pytest.raises(svc.FieldOperationError) as excinfo:
        svc._check_window(start, start)
    assert excinfo.value.validation_errors == ["EXPIRY_NOT_AFTER_START"]
    svc._check_window(start, start + timedelta(hours=1))


# ---------------------------------------------------------------------------
# response payload shape
# ---------------------------------------------------------------------------

def test_sync_payload_reports_location_only_for_a_complete_fix():
    row = FieldCaptureOperation(
        id=str(uuid4()),
        user_id=str(uuid4()),
        client_operation_id="op-0001",
        status="ACCEPTED",
        resolution_status="UNRESOLVED",
        file_size=len(BYTES_A),
        request_hash="x" * 64,
        sync_count=1,
        received_at=datetime.now(timezone.utc),
    )
    payload = svc._sync_payload(row, sync_status="accepted", message="ok")
    assert payload["location"]["reported"] is False
    assert payload["location"]["latitude"] is None
    assert payload["sync_status"] == "accepted"
    assert payload["evidence_id"] is None

    row.latitude = 53.3498
    row.longitude = -6.2603
    located = svc._sync_payload(row, sync_status="accepted", message="ok")
    assert located["location"]["reported"] is True
    assert located["location"]["latitude"] == pytest.approx(53.3498)


def test_sync_payload_preserves_the_five_timestamps_separately():
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    row = FieldCaptureOperation(
        id=str(uuid4()),
        user_id=str(uuid4()),
        client_operation_id="op-0002",
        status="ACCEPTED",
        resolution_status="UNRESOLVED",
        file_size=1,
        request_hash="y" * 64,
        sync_count=1,
        captured_at=now,
        queued_at=now + timedelta(minutes=2),
        uploaded_at=now + timedelta(minutes=90),
        received_at=now + timedelta(minutes=120),
        processed_at=now + timedelta(minutes=121),
    )
    payload = svc._sync_payload(row, sync_status="accepted", message="ok")
    assert [
        payload[key]
        for key in ("captured_at", "queued_at", "uploaded_at", "received_at", "processed_at")
    ] == [
        now,
        now + timedelta(minutes=2),
        now + timedelta(minutes=90),
        now + timedelta(minutes=120),
        now + timedelta(minutes=121),
    ]


def test_dependency_failure_maps_to_the_documented_storage_error_type():
    # _execute turns StorageError into temporarily_unavailable; the class it
    # catches must be the one the storage layer actually raises.
    assert svc.StorageError is StorageError


# ---------------------------------------------------------------------------
# dependency failure vocabulary (Stage E, F-SE-06)
# ---------------------------------------------------------------------------

class _DeadDatabase:
    """A session whose every statement fails, the way a lost Postgres does."""

    def __init__(self) -> None:
        self.rolled_back = False

    def _gone(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("database is gone"))

    execute = _gone
    query = _gone

    def rollback(self) -> None:
        self.rolled_back = True


def test_a_lost_database_on_the_sync_path_is_temporarily_unavailable_not_a_crash():
    """Design 6/12: Postgres unavailable answers 503 and never collapses to 500."""
    db = _DeadDatabase()
    with pytest.raises(svc.FieldOperationError) as caught:
        svc.sync_capture(db, request_from(), officer())
    assert caught.value.status_code == 503
    assert caught.value.sync_status == "temporarily_unavailable"
    assert caught.value.sync_status in FIELD_SYNC_STATUSES
    assert db.rolled_back is True, "the failed transaction must be released"""


def test_a_dependency_failure_never_reaches_the_caller_as_a_raw_orm_error():
    """An ORM exception escaping here is what produced a 500 before the fix."""
    try:
        svc.sync_capture(_DeadDatabase(), request_from(), officer())
    except svc.FieldOperationError:
        return
    except Exception as error:  # noqa: BLE001 - the escaping type is the point
        pytest.fail(f"a raw dependency failure escaped: {type(error).__name__}")
    pytest.fail("a lost database reported success")
