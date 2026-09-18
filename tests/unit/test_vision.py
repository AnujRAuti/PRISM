"""BE-009 unit tests (no model weights, no database, no storage)."""

from io import BytesIO

import pytest
from PIL import Image

from backend.core.config import settings
from backend.engines.vision.detector import (
    VisionModelError,
    normalize_box,
    resolve_device,
)
from backend.schemas.vision import (
    VisionBoundingBox,
    VisionDetectionItem,
    VisionResultPayload,
)


def test_normalize_box_converts_pixels_to_unit_coordinates():
    assert normalize_box(12.0, 25.0, 63.0, 81.0, 100, 100) == pytest.approx(
        (0.12, 0.25, 0.63, 0.81)
    )


def test_normalize_box_clamps_epsilon_overshoot():
    assert normalize_box(-2.0, -1.0, 102.0, 101.0, 100, 100) == (0.0, 0.0, 1.0, 1.0)


def test_normalize_box_rejects_degenerate_boxes():
    assert normalize_box(50.0, 10.0, 50.0, 90.0, 100, 100) is None
    assert normalize_box(10.0, 80.0, 90.0, 80.0, 100, 100) is None
    assert normalize_box(90.0, 10.0, 10.0, 90.0, 100, 100) is None


def test_normalize_box_rejects_non_positive_dimensions():
    with pytest.raises(ValueError):
        normalize_box(0.0, 0.0, 10.0, 10.0, 0, 100)
    with pytest.raises(ValueError):
        normalize_box(0.0, 0.0, 10.0, 10.0, 100, -5)


def test_resolve_device_supports_cpu_and_rejects_garbage(monkeypatch):
    monkeypatch.setattr(settings, "vision_device", "cpu")
    assert resolve_device() == "cpu"
    monkeypatch.setattr(settings, "vision_device", "auto")
    assert resolve_device() in {"cpu", "cuda"}
    monkeypatch.setattr(settings, "vision_device", "tpu")
    with pytest.raises(ValueError):
        resolve_device()


def test_run_inference_rejects_empty_and_corrupt_bytes():
    from backend.engines.vision.detector import run_inference

    with pytest.raises(VisionModelError):
        run_inference(b"")
    with pytest.raises(VisionModelError):
        run_inference(b"this is not an image")


def test_run_inference_reports_malformed_model_output(monkeypatch):
    import backend.engines.vision.detector as detector

    output = BytesIO()
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(output, format="JPEG")

    class BadBox:
        cls = [object()]
        conf = [object()]
        xyxy = [[object()]]

    class BadResult:
        boxes = [BadBox()]

    class FakeModel:
        names = {0: "person"}

        def predict(self, *args, **kwargs):
            return [BadResult()]

    monkeypatch.setattr(detector, "get_model", lambda: FakeModel())
    with pytest.raises(VisionModelError):
        detector.run_inference(output.getvalue())


def test_run_inference_handles_empty_detections(monkeypatch):
    import backend.engines.vision.detector as detector

    output = BytesIO()
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(output, format="JPEG")

    class EmptyResult:
        boxes = None

    class FakeModel:
        names = {}

        def predict(self, *args, **kwargs):
            return [EmptyResult()]

    monkeypatch.setattr(detector, "get_model", lambda: FakeModel())
    inference = detector.run_inference(output.getvalue())
    assert inference.detections == []
    assert (inference.image_width, inference.image_height) == (32, 32)
    assert inference.invalid_boxes_dropped == 0


def test_missing_ultralytics_fails_clearly(monkeypatch):
    import builtins
    import backend.engines.vision.detector as detector

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "ultralytics":
            raise ImportError("No module named 'ultralytics'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    detector.reset_model_cache()
    try:
        with pytest.raises(VisionModelError, match="ultralytics"):
            detector.get_model()
    finally:
        detector.reset_model_cache()


def test_detection_serialization_round_trip():
    item = VisionDetectionItem(
        class_id=0,
        class_name="person",
        confidence=0.91,
        bounding_box={"x_min": 0.12, "y_min": 0.18, "x_max": 0.43, "y_max": 0.94},
    )
    assert item.bounding_box.x_min < item.bounding_box.x_max
    assert item.model_dump()["confidence"] == 0.91


def test_bounding_box_validation_rejects_bad_geometry():
    with pytest.raises(ValueError):
        VisionBoundingBox(x_min=0.5, y_min=0.1, x_max=0.5, y_max=0.9)
    with pytest.raises(ValueError):
        VisionBoundingBox(x_min=0.1, y_min=0.1, x_max=1.5, y_max=0.9)
    with pytest.raises(ValueError):
        VisionDetectionItem(
            class_id=0,
            class_name="person",
            confidence=1.5,
            bounding_box={"x_min": 0.1, "y_min": 0.1, "x_max": 0.2, "y_max": 0.2},
        )


def test_result_payload_has_no_fraud_risk_or_authenticity_fields():
    fields = set(VisionResultPayload.model_fields)
    assert fields == {
        "analysis_type",
        "model",
        "image",
        "detection_count",
        "invalid_boxes_dropped",
        "duration_ms",
        "status",
    }
    assert not (fields & {"fraud_score", "risk_score", "authenticity_score", "trust_score", "compliance_score"})


def test_vision_configuration_is_sane():
    assert 0.0 < settings.vision_conf_threshold < 1.0
    assert 0.0 < settings.vision_iou_threshold < 1.0
    assert settings.vision_max_detections >= 1
    assert settings.vision_imgsz >= 32
    assert settings.vision_model_name
