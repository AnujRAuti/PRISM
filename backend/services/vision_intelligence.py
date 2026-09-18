"""BE-009 Vision Intelligence service.

Real YOLO object detection over the stored evidence image. Produces raw
visual observations only — no fraud, risk, authenticity, trust, or
compliance scores. Failures raise (real failures); they are never
converted into successful empty detections.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import AnalysisJob, AnalysisResult, Evidence, VisionDetection
from backend.engines.vision.detector import run_inference
from backend.services.storage import StorageService


logger = logging.getLogger(__name__)

ANALYSIS_TYPE = "vision_detection"


@dataclass(frozen=True)
class VisionAnalysis:
    result_id: str
    evidence_id: str
    job_id: str
    model_name: str
    model_version: str | None
    device: str
    image_width: int
    image_height: int
    detection_count: int
    invalid_boxes_dropped: int
    duration_ms: float
    status: str


def analyze_vision(
    evidence_id: str,
    db: Session,
    storage: StorageService | None = None,
    job_id: str | None = None,
) -> VisionAnalysis:
    """Run vision analysis for one evidence item under one analysis job.

    Idempotency: re-running for the same ``job_id`` replaces that job's
    detections (delete + re-insert) and updates its ``AnalysisResult`` —
    no uncontrolled duplicate rows. A new job creates a new historical
    result, preserving provenance.
    """
    if job_id is None:
        raise ValueError("Vision analysis requires a job_id for result attribution")
    if not settings.vision_enabled:
        raise RuntimeError("Vision analysis is disabled by configuration")
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one_or_none()
    if evidence is None:
        raise LookupError("Evidence not found")

    storage = storage or StorageService()
    logger.info("vision analysis started job_id=%s evidence_id=%s", job_id, evidence_id)
    # Storage/read/decode/inference errors propagate: the worker maps them
    # to retry/failed via existing job semantics. They must never become
    # a successful empty detection set.
    image_bytes = storage.get_object_bytes(storage.quarantine_bucket, evidence.storage_key)
    inference = run_inference(image_bytes)

    result = db.query(AnalysisResult).filter(AnalysisResult.job_id == job_id).one_or_none()
    if result is None:
        result = AnalysisResult(job_id=job_id)
        db.add(result)
        db.flush()
    else:
        db.query(VisionDetection).filter(
            VisionDetection.analysis_result_id == result.id
        ).delete(synchronize_session=False)
        db.flush()

    for detection in inference.detections:
        db.add(
            VisionDetection(
                analysis_result_id=result.id,
                class_id=detection.class_id,
                class_name=detection.class_name,
                confidence=detection.confidence,
                x_min=detection.x_min,
                y_min=detection.y_min,
                x_max=detection.x_max,
                y_max=detection.y_max,
            )
        )
    result_payload = {
        "analysis_type": ANALYSIS_TYPE,
        "model": {
            "name": inference.model_name,
            "version": inference.model_version,
            "conf_threshold": settings.vision_conf_threshold,
            "iou_threshold": settings.vision_iou_threshold,
            "max_detections": settings.vision_max_detections,
            "device": inference.device,
        },
        "image": {"width": inference.image_width, "height": inference.image_height},
        "detection_count": len(inference.detections),
        "invalid_boxes_dropped": inference.invalid_boxes_dropped,
        "duration_ms": inference.duration_ms,
        "status": "success",
    }
    result.result = result_payload
    db.commit()
    db.refresh(result)
    logger.info(
        "vision analysis completed job_id=%s evidence_id=%s model=%s device=%s "
        "duration_ms=%.1f detection_count=%d",
        job_id,
        evidence_id,
        inference.model_name,
        inference.device,
        inference.duration_ms,
        len(inference.detections),
    )
    return VisionAnalysis(
        result_id=result.id,
        evidence_id=evidence_id,
        job_id=job_id,
        model_name=inference.model_name,
        model_version=inference.model_version,
        device=inference.device,
        image_width=inference.image_width,
        image_height=inference.image_height,
        detection_count=len(inference.detections),
        invalid_boxes_dropped=inference.invalid_boxes_dropped,
        duration_ms=inference.duration_ms,
        status="success",
    )


def get_latest_vision_result(evidence_id: str, db: Session) -> AnalysisResult | None:
    """Latest vision ``AnalysisResult`` for an evidence item, if any.

    Deterministic under timestamp ties (``created_at DESC, id DESC``),
    mirroring the BE-006 latest-embedding selection.
    """
    return (
        db.query(AnalysisResult)
        .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
        .filter(
            AnalysisJob.evidence_id == evidence_id,
            AnalysisJob.job_type == "vision",
        )
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
        .first()
    )
