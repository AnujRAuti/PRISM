"""BE-009 vision engine (Ultralytics YOLO object detection)."""

from backend.engines.vision.detector import (
    RawDetection,
    VisionInference,
    VisionModelError,
    get_model,
    normalize_box,
    reset_model_cache,
    resolve_device,
    run_inference,
)

__all__ = [
    "RawDetection",
    "VisionInference",
    "VisionModelError",
    "get_model",
    "normalize_box",
    "reset_model_cache",
    "resolve_device",
    "run_inference",
]
