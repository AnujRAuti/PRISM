"""BE-011 unit tests: pure fusion calculation (no database, no services)."""

import pytest

from backend.schemas import fusion as fusion_schemas
from backend.services import fusion as fusion_service
from backend.services.fusion import DEFAULT_CONFIG_V1


def weights():
    return dict(DEFAULT_CONFIG_V1["weights"])


def priority_cfg():
    priority = DEFAULT_CONFIG_V1["priority"]
    return {
        "base": priority["base"],
        "contributions": dict(priority["contributions"]),
        "unknown_each": priority["unknown_each"],
        "unknown_cap": priority["unknown_cap"],
    }


def thresholds():
    return dict(DEFAULT_CONFIG_V1["thresholds"])


def sig(signal_type, state):
    return {
        "signal_type": signal_type,
        "state": state,
        "source": "test",
        "source_entity_id": None,
        "source_analysis_run_id": None,
        "raw_value": None,
        "normalized_value": None,
        "weight": 0.0,
        "method": fusion_service.METHOD,
        "method_version": fusion_service.METHOD_VERSION,
        "details": {},
    }


def test_normalize_state_values():
    assert fusion_service.normalize_state_value("POSITIVE") == 1.0
    assert fusion_service.normalize_state_value("NEGATIVE") == -1.0
    assert fusion_service.normalize_state_value("NEUTRAL") is None
    assert fusion_service.normalize_state_value("UNKNOWN") is None
    assert fusion_service.normalize_state_value("UNAVAILABLE") is None
    assert fusion_service.normalize_state_value("CONFLICTING") is None
    assert fusion_service.normalize_state_value("BOGUS") is None


def test_weighted_score_exact_values():
    signals = [sig("GRAPH_SUPPORT", "POSITIVE"), sig("TEMPORAL_CONSISTENT", "POSITIVE")]
    assert fusion_service.compute_integrity_score(signals, weights()) == 1.0
    mixed = [sig("GRAPH_SUPPORT", "POSITIVE"), sig("GRAPH_CONTRADICT", "NEGATIVE")]
    assert fusion_service.compute_integrity_score(mixed, weights()) == 0.0
    assert fusion_service.compute_integrity_score([sig("GRAPH_CONTRADICT", "NEGATIVE")], weights()) == -1.0
    # Rounding is documented (3 decimals): (0.1 - 0.2) / 0.3 = -0.333.
    assert (
        fusion_service.compute_integrity_score(
            [sig("GRAPH_SUPPORT", "POSITIVE"), sig("GRAPH_CONTRADICT", "NEGATIVE")],
            {"GRAPH_SUPPORT": 0.1, "GRAPH_CONTRADICT": 0.2},
        )
        == -0.333
    )


def test_score_none_when_nothing_applies():
    assert fusion_service.compute_integrity_score([], weights()) is None
    assert fusion_service.compute_integrity_score([sig("LOCATION_UNKNOWN", "UNKNOWN")], weights()) is None
    assert fusion_service.compute_integrity_score([sig("VISION_OBSERVED", "NEUTRAL")], weights()) is None


def test_assessment_rule_exact_values():
    assert fusion_service.decide_assessment([]) == "INSUFFICIENT_EVIDENCE"
    assert fusion_service.decide_assessment([sig("GRAPH_SUPPORT", "POSITIVE")]) == "SUPPORTED"
    assert fusion_service.decide_assessment([sig("GRAPH_CONTRADICT", "NEGATIVE")]) == "CONTRADICTED"
    assert (
        fusion_service.decide_assessment(
            [sig("GRAPH_SUPPORT", "POSITIVE"), sig("GRAPH_CONTRADICT", "NEGATIVE")]
        )
        == "MIXED"
    )
    assert fusion_service.decide_assessment([sig("GRAPH_CONFLICT", "CONFLICTING")]) == "MIXED"
    assert fusion_service.decide_assessment([sig("LOCATION_UNKNOWN", "UNKNOWN")]) == "UNKNOWN"
    assert fusion_service.decide_assessment([sig("VISION_OBSERVED", "NEUTRAL")]) == "INSUFFICIENT_EVIDENCE"


def test_missing_is_not_negative_by_default():
    assert fusion_service.decide_assessment([sig("LOCATION_UNKNOWN", "UNKNOWN")]) != "CONTRADICTED"
    assert fusion_service.compute_integrity_score([sig("LOCATION_UNKNOWN", "UNKNOWN")], weights()) is None
    empty_priority = fusion_service.compute_priority([], priority_cfg(), thresholds())
    unknown_priority = fusion_service.compute_priority(
        [sig("LOCATION_UNKNOWN", "UNKNOWN")], priority_cfg(), thresholds()
    )
    # Uncertainty may add a small review allocation, never a negative assessment.
    assert unknown_priority[1] >= empty_priority[1]


def test_priority_bands_exact_values():
    assert fusion_service.compute_priority([], priority_cfg(), thresholds()) == ("LOW", 0.1)
    assert fusion_service.compute_priority(
        [sig("GRAPH_CONTRADICT", "NEGATIVE")], priority_cfg(), thresholds()
    ) == ("NORMAL", 0.35)
    assert fusion_service.compute_priority(
        [sig("DUPLICATE_EXACT", "NEGATIVE"), sig("TEMPORAL_INCONSISTENT", "NEGATIVE")],
        priority_cfg(),
        thresholds(),
    ) == ("HIGH", 0.7)
    urgent = fusion_service.compute_priority(
        [
            sig("DUPLICATE_EXACT", "NEGATIVE"),
            sig("TEMPORAL_INCONSISTENT", "NEGATIVE"),
            sig("GRAPH_CONTRADICT", "NEGATIVE"),
        ],
        priority_cfg(),
        thresholds(),
    )
    assert urgent == ("URGENT", 0.95)
    # Unknown contribution is capped: 10 unknowns add at most 0.20.
    capped = fusion_service.compute_priority(
        [sig("LOCATION_UNKNOWN", "UNKNOWN") for _ in range(10)], priority_cfg(), thresholds()
    )
    assert capped == ("NORMAL", 0.3)


def test_configuration_validation():
    valid = {
        "version": "v1",
        "name": "t",
        "method_version": fusion_service.METHOD_VERSION,
        "weights": {"GRAPH_SUPPORT": 0.3},
        "thresholds": {"low_max": 0.25, "normal_max": 0.5, "high_max": 0.75},
        "priority": {"base": 0.1, "contributions": {}, "unknown_each": 0.05, "unknown_cap": 0.2},
        "signals": {"enabled": ["GRAPH_SUPPORT"]},
    }
    assert fusion_service.validate_configuration(valid) is valid
    assert fusion_service.validate_configuration(DEFAULT_CONFIG_V1) is DEFAULT_CONFIG_V1
    bad_method = dict(valid, method_version="fusion-v9")
    with pytest.raises(ValueError):
        fusion_service.validate_configuration(bad_method)
    bad_type = dict(valid, weights={"MIND_READING": 0.5})
    with pytest.raises(ValueError):
        fusion_service.validate_configuration(bad_type)
    for bad_weight in (-0.1, 1.5, "lots"):
        with pytest.raises(ValueError):
            fusion_service.validate_configuration(dict(valid, weights={"GRAPH_SUPPORT": bad_weight}))
    with pytest.raises(ValueError):
        fusion_service.validate_configuration(dict(valid, weights={}))
    bad_thresholds = dict(valid, thresholds={"low_max": 0.5, "normal_max": 0.5, "high_max": 0.75})
    with pytest.raises(ValueError):
        fusion_service.validate_configuration(bad_thresholds)
    bad_contrib = dict(
        valid, priority={"base": 0.1, "contributions": {"GRAPH_CONTRADICT": -1.0}}
    )
    with pytest.raises(ValueError):
        fusion_service.validate_configuration(bad_contrib)
    with pytest.raises(ValueError):
        fusion_service.validate_configuration("not-a-mapping")


def test_signal_construction_rejects_unknown_vocab():
    with pytest.raises(ValueError):
        fusion_service._signal("MIND_READING", "POSITIVE", "test")
    with pytest.raises(ValueError):
        fusion_service._signal("GRAPH_SUPPORT", "GLOWING", "test")


def test_summarize_signals_exact_shape():
    summary = fusion_service.summarize_signals(
        [sig("GRAPH_SUPPORT", "POSITIVE"), sig("GRAPH_SUPPORT", "POSITIVE"),
         sig("LOCATION_UNKNOWN", "UNKNOWN")]
    )
    assert summary == {
        "signal_count": 3,
        "by_type": {
            "GRAPH_SUPPORT": {"count": 2, "states": {"POSITIVE": 2}},
            "LOCATION_UNKNOWN": {"count": 1, "states": {"UNKNOWN": 1}},
        },
    }


def test_assessment_and_priority_are_computed_independently():
    signals = [sig("GRAPH_SUPPORT", "POSITIVE")]
    value = fusion_service.decide_assessment(signals)
    score = fusion_service.compute_integrity_score([dict(s) for s in signals], weights())
    priority = fusion_service.compute_priority([dict(s) for s in signals], priority_cfg(), thresholds())
    assert value == "SUPPORTED"
    assert score == 1.0
    # Positive integrity does not force low priority; they are separate outputs.
    assert priority[0] in {"LOW", "NORMAL", "HIGH", "URGENT"}
    assert isinstance(priority[1], float)


def test_determinism_same_inputs_same_outputs():
    signals = [
        sig("GRAPH_SUPPORT", "POSITIVE"),
        sig("GRAPH_CONTRADICT", "NEGATIVE"),
        sig("LOCATION_UNKNOWN", "UNKNOWN"),
    ]
    first = (
        fusion_service.decide_assessment([dict(s) for s in signals]),
        fusion_service.compute_integrity_score([dict(s) for s in signals], weights()),
        fusion_service.compute_priority([dict(s) for s in signals], priority_cfg(), thresholds()),
    )
    second = (
        fusion_service.decide_assessment([dict(s) for s in signals]),
        fusion_service.compute_integrity_score([dict(s) for s in signals], weights()),
        fusion_service.compute_priority([dict(s) for s in signals], priority_cfg(), thresholds()),
    )
    assert first == second == ("MIXED", 0.0, ("NORMAL", 0.4))


def test_response_schemas_have_no_forbidden_fields():
    for model in (
        fusion_schemas.IntegrityAssessmentItem,
        fusion_schemas.ReviewPriorityItem,
        fusion_schemas.FusionSignalItem,
        fusion_schemas.FusionRunItem,
    ):
        fields = set(model.model_fields)
        assert not (
            fields
            & {
                "fraud_score",
                "fraud_probability",
                "authenticity_score",
                "truth_score",
                "truth_probability",
                "risk_score",
            }
        )
