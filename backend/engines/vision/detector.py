"""BE-009 real object-detection engine (Ultralytics YOLO).

The model performs genuine inference on the supplied image bytes. Nothing
is hardcoded, simulated, or fabricated: if the model cannot be loaded or
inference fails, a ``VisionModelError`` is raised and callers must treat
the analysis as failed — never as a successful empty result.
"""

import logging
import threading
import time
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from backend.core.config import settings


logger = logging.getLogger(__name__)


class VisionModelError(RuntimeError):
    """Raised when the vision model cannot load or inference fails."""


@dataclass(frozen=True)
class RawDetection:
    class_id: int
    class_name: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float


@dataclass(frozen=True)
class VisionInference:
    detections: list[RawDetection]
    image_width: int
    image_height: int
    model_name: str
    model_version: str | None
    device: str
    invalid_boxes_dropped: int = 0
    duration_ms: float = 0.0


_model_lock = threading.Lock()
_model: object | None = None
_model_version: str | None = None


def normalize_box(
    x_min_px: float,
    y_min_px: float,
    x_max_px: float,
    y_max_px: float,
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float] | None:
    """Normalize pixel coordinates to 0..1; return None if degenerate.

    Pixel values slightly outside the frame (floating-point overshoot) are
    clamped. Boxes that remain degenerate (``x_min >= x_max`` or
    ``y_min >= y_max``) are reported as None so the caller can count and
    disclose them instead of persisting invalid geometry.
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image dimensions must be positive")
    x_min = min(max(float(x_min_px) / image_width, 0.0), 1.0)
    y_min = min(max(float(y_min_px) / image_height, 0.0), 1.0)
    x_max = min(max(float(x_max_px) / image_width, 0.0), 1.0)
    y_max = min(max(float(y_max_px) / image_height, 0.0), 1.0)
    if not (x_min < x_max and y_min < y_max):
        return None
    return (x_min, y_min, x_max, y_max)


def resolve_device() -> str:
    """Resolve the configured execution device (CPU-first, CUDA if available)."""
    configured = (settings.vision_device or "auto").strip().lower()
    if configured == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"
    if configured in {"cpu", "cuda"} or configured.startswith("cuda:"):
        return configured
    raise ValueError(f"Invalid VISION_DEVICE: {settings.vision_device!r} (expected auto, cpu, or cuda)")


def get_model() -> object:
    """Load the YOLO model once per worker process (thread-safe singleton)."""
    global _model, _model_version
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise VisionModelError(
                "Vision model dependency 'ultralytics' is not installed; "
                "vision analysis is unavailable"
            ) from error
        try:
            import ultralytics

            _model_version = getattr(ultralytics, "__version__", None)
        except ImportError:  # pragma: no cover - defensive
            _model_version = None
        try:
            _model = YOLO(settings.vision_model_name)
        except Exception as error:
            raise VisionModelError(
                f"Unable to load vision model {settings.vision_model_name!r}: {error}"
            ) from error
        logger.info(
            "vision model initialized name=%s version=%s",
            settings.vision_model_name,
            _model_version,
        )
        return _model


def reset_model_cache() -> None:
    """Forget the cached model (tests only)."""
    global _model, _model_version
    with _model_lock:
        _model = None
        _model_version = None


def run_inference(image_bytes: bytes) -> VisionInference:
    """Run real YOLO inference on raw image bytes."""
    if not image_bytes:
        raise VisionModelError("Cannot run vision inference on empty image data")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            width, height = image.size
        pil_image = Image.open(BytesIO(image_bytes)).convert("RGB")
        pil_image.load()
    except Exception as error:
        raise VisionModelError(f"Cannot decode image for vision analysis: {error}") from error
    if width <= 0 or height <= 0:
        raise VisionModelError("Image has invalid dimensions for vision analysis")

    model = get_model()
    device = resolve_device()
    started = time.perf_counter()
    try:
        results = model.predict(
            pil_image,
            conf=settings.vision_conf_threshold,
            iou=settings.vision_iou_threshold,
            max_det=settings.vision_max_detections,
            imgsz=settings.vision_imgsz,
            device=device,
            verbose=False,
        )
    except Exception as error:
        raise VisionModelError(f"Vision inference failed: {error}") from error
    finally:
        pil_image.close()
    duration_ms = (time.perf_counter() - started) * 1000.0

    names: dict = getattr(model, "names", {}) or {}
    detections: list[RawDetection] = []
    dropped = 0
    for result in results or []:
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            continue
        for box in boxes:
            try:
                class_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
            except (AttributeError, IndexError, TypeError, ValueError) as error:
                raise VisionModelError(f"Malformed model output: {error}") from error
            normalized = normalize_box(x1, y1, x2, y2, width, height)
            if normalized is None:
                dropped += 1
                continue
            detections.append(
                RawDetection(
                    class_id=class_id,
                    class_name=str(names.get(class_id, str(class_id))),
                    confidence=confidence,
                    x_min=normalized[0],
                    y_min=normalized[1],
                    x_max=normalized[2],
                    y_max=normalized[3],
                )
            )
    return VisionInference(
        detections=detections,
        image_width=width,
        image_height=height,
        model_name=settings.vision_model_name,
        model_version=_model_version,
        device=device,
        invalid_boxes_dropped=dropped,
        duration_ms=duration_ms,
    )
