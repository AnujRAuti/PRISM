"""BE-032R F-04 / D-CHAIN: the historical-gap classifier and writer policy.

These are deliberately *pure* tests: the classifier is fed ``verify_chain``'s
failure strings directly, never a live database. Creating a real gap would mean
deleting ledger rows, and ``pofa_test`` is a protected database (§10, the BE-030
append-only guard). What is under test is the labelling logic — the thing that
decides whether a symptom is preserved history or a fresh anomaly — so the
synthetic-string form exercises every branch without touching any chain.

The invariants the task (§10) calls non-negotiable:
  * a hash mismatch / missing predecessor is NEVER blessable as historical;
  * a gap matching a baseline must agree on BOTH boundary numbers (a one-off
    shift is a new anomaly, not history);
  * with no baseline, default-deny: every gap is new.
"""

from __future__ import annotations

import pytest

from backend.services import audit_ledger as audit_service
from backend.services.audit_integrity_baseline import (
    BASELINES,
    EMPTY_BASELINE,
    POFA_DEV_HISTORICAL_BASELINE,
    classify_findings,
    resolve_baseline,
)


def gap(before: int, expected: int) -> str:
    return f"sequence gap before {before} (expected {expected})"


# ---------------------------------------------------------------------------
# resolve_baseline: default-deny, closed registry
# ---------------------------------------------------------------------------


def test_no_baseline_resolves_to_the_safe_empty_one():
    assert resolve_baseline(None) is EMPTY_BASELINE
    assert resolve_baseline("") is EMPTY_BASELINE


def test_unknown_baseline_name_falls_back_to_empty_rather_than_guessing():
    assert resolve_baseline("made-up-baseline") is EMPTY_BASELINE


def test_registered_baseline_resolves_by_name():
    assert (resolve_baseline(POFA_DEV_HISTORICAL_BASELINE.name)
            is POFA_DEV_HISTORICAL_BASELINE)


def test_a_baseline_object_passes_through_unchanged():
    assert resolve_baseline(POFA_DEV_HISTORICAL_BASELINE) is POFA_DEV_HISTORICAL_BASELINE


# ---------------------------------------------------------------------------
# classify_findings: clean / known / new / degraded
# ---------------------------------------------------------------------------


def test_empty_findings_are_clean():
    result = classify_findings([])
    assert result["status"] == "clean"
    assert result["degraded"] is False
    assert result["known_historical_gaps"] == []
    assert result["new_gaps"] == []
    assert result["hard_anomalies"] == []


def test_without_a_baseline_every_gap_is_new():
    result = classify_findings([gap(5350, 5344)])
    assert result["status"] == "new_anomaly"
    assert result["new_gaps"] == [gap(5350, 5344)]
    assert result["known_historical_gaps"] == []


def test_known_pofa_dev_gaps_classify_as_historical_only():
    findings = [
        gap(5350, 5344), gap(5380, 5374), gap(5385, 5381), gap(5392, 5386),
        gap(5397, 5393), gap(5677, 5671), gap(5682, 5678),
    ]
    result = classify_findings(findings, POFA_DEV_HISTORICAL_BASELINE)
    assert result["status"] == "known_historical_only"
    assert result["degraded"] is False
    assert result["new_gaps"] == []
    assert set(result["known_historical_gaps"]) == set(findings)
    assert result["baseline_name"] == POFA_DEV_HISTORICAL_BASELINE.name


def test_a_gap_shifted_by_one_is_not_blessed_as_history():
    # Same count of holes, different boundaries: a tamper that reshuffles history
    # must not be excused by a baseline keyed to the original ranges.
    result = classify_findings([gap(5351, 5344)], POFA_DEV_HISTORICAL_BASELINE)
    assert result["status"] == "new_anomaly"
    assert result["new_gaps"] == [gap(5351, 5344)]
    assert result["known_historical_gaps"] == []


def test_mixed_known_and_new_gaps_report_new_anomaly_with_both_visible():
    result = classify_findings(
        [gap(5350, 5344), gap(9999, 9990)], POFA_DEV_HISTORICAL_BASELINE
    )
    assert result["status"] == "new_anomaly"
    assert result["known_historical_gaps"] == [gap(5350, 5344)]
    assert result["new_gaps"] == [gap(9999, 9990)]


@pytest.mark.parametrize("hard", [
    "event_hash mismatch at sequence 5344",
    "missing predecessor for sequence 5344",
    "previous_hash mismatch at sequence 5344",
])
def test_a_hash_mismatch_is_never_blessable_even_alongside_known_gaps(hard):
    result = classify_findings(
        [gap(5350, 5344), hard], POFA_DEV_HISTORICAL_BASELINE
    )
    assert result["status"] == "new_anomaly"
    assert result["degraded"] is True
    assert result["hard_anomalies"] == [hard]


def test_classification_never_mutates_or_hides_the_input_findings():
    findings = [gap(5350, 5344), "event_hash mismatch at sequence 5344"]
    original = list(findings)
    result = classify_findings(findings, POFA_DEV_HISTORICAL_BASELINE)
    assert findings == original  # input untouched
    # every finding still surfaces somewhere in the output
    assert set(result["known_historical_gaps"]) | set(result["new_gaps"]) | set(
        result["hard_anomalies"]) == set(original)


# ---------------------------------------------------------------------------
# D-CHAIN writer policy statement
# ---------------------------------------------------------------------------


def test_writer_policy_is_controlled_continuation_and_forbids_repair():
    policy = audit_service.writer_policy_statement()
    assert policy["policy"] == audit_service.LEDGER_WRITER_POLICY == "controlled_continuation"
    assert policy["history_repair_permitted"] is False
    assert "known_historical_only" in policy["continuation_allowed_when"]
    assert "clean" in policy["continuation_allowed_when"]
    assert "new_anomaly" in policy["fail_closed_when"]
    assert "degraded" in policy["fail_closed_when"]
    # the writer's own guard is the immediate-predecessor check, not the walk
    assert "immediate-predecessor" in policy["writer_guards"]


def test_baseline_registry_contains_the_pinned_pofa_dev_artifact():
    assert BASELINES[POFA_DEV_HISTORICAL_BASELINE.name] is POFA_DEV_HISTORICAL_BASELINE
    assert len(POFA_DEV_HISTORICAL_BASELINE.known_gaps) == 7
