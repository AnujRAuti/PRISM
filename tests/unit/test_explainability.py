"""BE-012 unit tests: explanation assembly (no database).

Persisted fusion rows are stubbed; repository lookups are monkeypatched.
"""

import itertools
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.schemas import explainability as explain_schemas
from backend.services import explainability as explain_service
from backend.services import fusion as fusion_service


BANNED_TOKENS = (
    "probability",
    "likelihood",
    "fraud",
    "authentic",
    "chance of",
    "% chance",
    "guilty",
    "innocent",
    "fake",
)


def make_signal(signal_type="GRAPH_SUPPORT", state="POSITIVE", **overrides):
    payload = {
        "signal_type": signal_type,
        "state": state,
        "source": "evidence_graph",
        "source_entity_id": str(uuid4()),
        "source_analysis_run_id": str(uuid4()),
        "raw_value": {"relationship": "SUPPORTS"},
        "normalized_value": {"POSITIVE": 1.0, "NEGATIVE": -1.0}.get(state),
        "weight": 0.30,
        "method": fusion_service.METHOD,
        "method_version": fusion_service.METHOD_VERSION,
        "details": {},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def make_bundle(signals, assessment_value="MIXED", score=0.0, priority="HIGH",
                priority_score=0.7, run_status="COMPLETED"):
    run_id, target_id = str(uuid4()), str(uuid4())
    run = SimpleNamespace(
        id=run_id, target_type="CLAIM", target_id=target_id, status=run_status,
        method=fusion_service.METHOD, method_version=fusion_service.METHOD_VERSION,
        configuration_version="v1", started_at=None, completed_at=None,
        error=None if run_status != "FAILED" else "boom",
    )
    assessment = SimpleNamespace(
        assessment_value=assessment_value, assessment_status="ACTIVE",
        integrity_score=score,
    )
    priority_row = SimpleNamespace(priority=priority, priority_score=priority_score)
    config = SimpleNamespace(
        version="v1", method_version=fusion_service.METHOD_VERSION,
        weights={"GRAPH_SUPPORT": 0.30, "GRAPH_CONTRADICT": 0.30,
                 "LOCATION_UNKNOWN": 0.0, "VISION_OBSERVED": 0.0},
        thresholds={"low_max": 0.25, "normal_max": 0.5, "high_max": 0.75},
        priority={"base": 0.10,
                  "contributions": {"GRAPH_CONTRADICT": 0.25},
                  "unknown_each": 0.05, "unknown_cap": 0.20},
    )
    return run, signals, assessment, priority_row, config


def build_with(signals, monkeypatch, **bundle_kwargs):
    run, rows, assessment, priority_row, config = make_bundle(signals, **bundle_kwargs)
    monkeypatch.setattr(
        explain_service.explain_repo, "get_fusion_bundle",
        lambda db, run_id: (run, rows, assessment, priority_row, config),
    )
    monkeypatch.setattr(explain_service.explain_repo, "bulk_relationships", lambda db, ids: {})
    monkeypatch.setattr(explain_service.explain_repo, "bulk_nodes", lambda db, ids: {})
    return explain_service.build_explanation(object(), run.id)


def test_explanation_has_all_sections(monkeypatch):
    content = build_with([make_signal()], monkeypatch, assessment_value="SUPPORTED",
                         score=1.0, priority="LOW", priority_score=0.1)
    for section in ("fusion_run_id", "target", "integrity_assessment", "review_priority",
                    "methodology", "configuration", "summary", "signals", "rules",
                    "priority_trace", "unknowns", "provenance", "generated_at"):
        assert section in content, section
    assert content["methodology"]["explanation_method_version"] == "explanation-v1"
    assert content["methodology"]["fusion_method_version"] == "fusion-v1"


def test_contribution_rendering_uses_persisted_values(monkeypatch):
    content = build_with(
        [make_signal("GRAPH_CONTRADICT", "NEGATIVE", normalized_value=-1.0, weight=0.30)],
        monkeypatch, assessment_value="CONTRADICTED", score=-1.0,
        priority="NORMAL", priority_score=0.35,
    )
    entry = content["signals"][0]
    assert entry["normalized_value"] == -1.0
    assert entry["weight"] == 0.30
    assert entry["contribution"] == -0.3
    assert entry["included"] is True
    assert entry["reason"] == "APPLIED_TO_SCORE"


def test_rule_mirror_matches_fusion_rule():
    states_pool = ["POSITIVE", "NEGATIVE", "NEUTRAL", "UNKNOWN",
                   "UNAVAILABLE", "CONFLICTING", "NOT_APPLICABLE", "NOT_GENERATED"]
    checked = 0
    for size in (0, 1, 2, 3):
        for combo in itertools.combinations_with_replacement(states_pool, size):
            states = list(combo)
            rule_id, rule_version, outcome = explain_service.describe_rule(states)
            expected = fusion_service.decide_assessment([{"state": s} for s in states])
            assert outcome == expected, states
            assert rule_version == fusion_service.METHOD_VERSION
            checked += 1
    assert checked > 100


def test_rule_labels_are_documented():
    assert explain_service.describe_rule([])[0] == "NO_SIGNALS"
    assert explain_service.describe_rule(["POSITIVE", "NEGATIVE"])[0] == "POSITIVE_AND_NEGATIVE"
    assert explain_service.describe_rule(["CONFLICTING"])[0] == "CONFLICTING_INPUTS"
    assert explain_service.describe_rule(["NEGATIVE"])[0] == "NEGATIVE_ONLY"
    assert explain_service.describe_rule(["POSITIVE"])[0] == "POSITIVE_ONLY"
    assert explain_service.describe_rule(["UNKNOWN"])[0] == "UNKNOWN_INPUTS_ONLY"
    assert explain_service.describe_rule(["NEUTRAL"])[0] == "NEUTRAL_ONLY"


def test_drift_detection_rejects_mismatched_assessment(monkeypatch):
    with pytest.raises(RuntimeError, match="drift"):
        build_with([make_signal("GRAPH_SUPPORT", "POSITIVE")], monkeypatch,
                   assessment_value="CONTRADICTED", score=-1.0)


def test_unknown_and_unavailable_rendering(monkeypatch):
    entity = str(uuid4())
    content = build_with(
        [make_signal("LOCATION_UNKNOWN", "UNKNOWN", source_entity_id=entity,
                     normalized_value=None, weight=0.0),
         make_signal("VISION_OBSERVED", "NEUTRAL", normalized_value=None, weight=0.0)],
        monkeypatch, assessment_value="UNKNOWN", score=None,
        priority="LOW", priority_score=0.15,
    )
    assert len(content["unknowns"]) == 1
    unknown = content["unknowns"][0]
    assert unknown["signal_type"] == "LOCATION_UNKNOWN"
    assert entity in unknown["sentence"]
    assert "negative" in unknown["sentence"]
    zero = next(e for e in content["signals"] if e["signal_type"] == "VISION_OBSERVED")
    assert zero["included"] is True
    assert zero["reason"] == "RECORDED_ZERO_WEIGHT"
    assert "negative" in content["summary"]["text"]


def test_conflicting_signal_rendering(monkeypatch):
    content = build_with(
        [make_signal("GRAPH_CONFLICT", "CONFLICTING", normalized_value=None, weight=0.30)],
        monkeypatch, assessment_value="MIXED", score=None,
        priority="NORMAL", priority_score=0.35,
    )
    assert content["rules"][0]["rule_id"] == "CONFLICTING_INPUTS"
    assert content["rules"][0]["result"] == "MIXED"
    entry = content["signals"][0]
    assert entry["contribution"] == 0.0
    assert "conflict" in content["summary"]["text"].lower() or "MIXED" in content["summary"]["text"]


def test_zero_signal_explanation(monkeypatch):
    content = build_with([], monkeypatch, assessment_value="INSUFFICIENT_EVIDENCE",
                         score=None, priority="LOW", priority_score=0.1)
    assert content["signals"] == []
    assert content["rules"][0]["rule_id"] == "NO_SIGNALS"
    assert content["rules"][0]["result"] == "INSUFFICIENT_EVIDENCE"
    assert "INSUFFICIENT_EVIDENCE" in content["summary"]["text"]


def test_failed_fusion_has_no_successful_explanation(monkeypatch):
    run, rows, assessment, priority_row, config = make_bundle(
        [make_signal()], run_status="FAILED")
    monkeypatch.setattr(
        explain_service.explain_repo, "get_fusion_bundle",
        lambda db, run_id: (run, rows, assessment, priority_row, config))
    with pytest.raises(ValueError, match="EXPLANATION_UNAVAILABLE"):
        explain_service.build_explanation(object(), run.id)


def test_missing_run_and_missing_outputs(monkeypatch):
    monkeypatch.setattr(explain_service.explain_repo, "get_fusion_bundle",
                        lambda db, run_id: None)
    with pytest.raises(LookupError):
        explain_service.build_explanation(object(), str(uuid4()))
    run, rows, _, _, config = make_bundle([make_signal()])
    monkeypatch.setattr(explain_service.explain_repo, "get_fusion_bundle",
                        lambda db, run_id: (run, rows, None, None, config))
    with pytest.raises(ValueError, match="EXPLANATION_UNAVAILABLE"):
        explain_service.build_explanation(object(), run.id)


def test_deterministic_ordering_and_summary(monkeypatch):
    signals = [
        make_signal("LOCATION_UNKNOWN", "UNKNOWN", normalized_value=None, weight=0.0),
        make_signal("GRAPH_CONTRADICT", "NEGATIVE", normalized_value=-1.0, weight=0.30),
        make_signal("GRAPH_SUPPORT", "POSITIVE", normalized_value=1.0, weight=0.30),
    ]
    bundle = make_bundle(signals, assessment_value="MIXED", score=0.0,
                         priority="NORMAL", priority_score=0.4)
    monkeypatch.setattr(explain_service.explain_repo, "get_fusion_bundle",
                        lambda db, run_id: bundle)
    monkeypatch.setattr(explain_service.explain_repo, "bulk_relationships", lambda db, ids: {})
    monkeypatch.setattr(explain_service.explain_repo, "bulk_nodes", lambda db, ids: {})
    first = explain_service.build_explanation(object(), bundle[0].id)
    second = explain_service.build_explanation(object(), bundle[0].id)
    strip = lambda content: {k: v for k, v in content.items() if k != "generated_at"}
    assert strip(first) == strip(second)
    assert first["summary"]["text"] == second["summary"]["text"]
    # Contribution magnitude first, deterministic tie-breaks after.
    assert [e["signal_type"] for e in first["signals"]][:2] == ["GRAPH_CONTRADICT", "GRAPH_SUPPORT"]
    assert first["summary"]["state_counts"] == {"NEGATIVE": 1, "POSITIVE": 1, "UNKNOWN": 1}


def test_no_duplicate_signals_and_no_probability_language(monkeypatch):
    signals = [make_signal("GRAPH_SUPPORT", "POSITIVE"),
               make_signal("LOCATION_UNKNOWN", "UNKNOWN", normalized_value=None, weight=0.0)]
    content = build_with(signals, monkeypatch, assessment_value="SUPPORTED", score=1.0,
                         priority="LOW", priority_score=0.15)
    assert len(content["signals"]) == len(signals)
    # No sentence may affirmatively claim probability/truth/fraud: banned
    # tokens are allowed only inside explicit negations (the required
    # "this determines neither ..." disclaimer).
    negations = ("not", "neither", "nor", "never", "no ")
    text = content["summary"]["text"]
    assert "neither determines truth, fraud, or authenticity" in text
    for sentence in text.lower().replace(";", ".").split("."):
        for token in BANNED_TOKENS:
            if token in sentence:
                assert any(neg in sentence for neg in negations), sentence


def test_configuration_trace_is_scoped(monkeypatch):
    content = build_with([make_signal("GRAPH_SUPPORT", "POSITIVE")], monkeypatch,
                         assessment_value="SUPPORTED", score=1.0,
                         priority="LOW", priority_score=0.1)
    assert content["configuration"]["version"] == "v1"
    assert content["configuration"]["weights"] == {"GRAPH_SUPPORT": 0.30}
    assert content["configuration"]["thresholds"]["high_max"] == 0.75
    assert content["methodology"]["configuration_version"] == "v1"


def test_response_schemas_have_no_forbidden_fields():
    for model in (explain_schemas.ExplanationResponse, explain_schemas.ExplanationSignalItem,
                  explain_schemas.ExplanationRuleItem, explain_schemas.ExplanationRunItem):
        fields = set(model.model_fields)
        assert not (fields & {"fraud_score", "authenticity_score", "truth_score",
                              "risk_score", "probability", "confidence"})
