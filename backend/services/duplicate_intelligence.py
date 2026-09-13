from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models import AnalysisJob, AnalysisResult, DuplicateMatch, Evidence
from backend.engines.embeddings.clip import image_embedding
from backend.services.storage import StorageService


@dataclass(frozen=True)
class DuplicateAnalysis:
    exact_matches: list[str]
    perceptual_matches: list[dict[str, Any]]
    semantic_matches: list[dict[str, Any]]
    embedding_status: str
    embedding_error: str | None


def search_similar_embeddings(
    vector: list[float],
    db: Session,
    *,
    exclude_job_id: str | None = None,
    exclude_evidence_id: str | None = None,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    latest_embeddings = (
        db.query(
            AnalysisJob.evidence_id.label("evidence_id"),
            func.max(AnalysisResult.created_at).label("latest_created_at"),
        )
        .join(AnalysisResult, AnalysisResult.job_id == AnalysisJob.id)
        .filter(AnalysisResult.embedding.is_not(None))
        .group_by(AnalysisJob.evidence_id)
        .subquery()
    )
    query = (
        db.query(AnalysisResult.job_id, AnalysisJob.evidence_id, AnalysisResult.embedding.cosine_distance(vector).label("distance"))
        .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
        .join(
            latest_embeddings,
            and_(
                latest_embeddings.c.evidence_id == AnalysisJob.evidence_id,
                latest_embeddings.c.latest_created_at == AnalysisResult.created_at,
            ),
        )
        .filter(AnalysisResult.embedding.is_not(None))
    )
    if exclude_job_id is not None:
        query = query.filter(AnalysisResult.job_id != exclude_job_id)
    if exclude_evidence_id is not None:
        query = query.filter(AnalysisJob.evidence_id != exclude_evidence_id)
    rows = query.order_by("distance").limit(top_k or settings.embedding_top_k).all()
    return [
        {"job_id": row.job_id, "evidence_id": row.evidence_id, "distance": float(row.distance)}
        for row in rows
    ]


def phash_distance(left: str, right: str) -> int:
    if len(left) != len(right):
        raise ValueError("pHash values must have equal length")
    return (int(left, 16) ^ int(right, 16)).bit_count()


def analyze_duplicates(
    evidence_id: str,
    db: Session,
    storage: StorageService | None = None,
    job_id: str | None = None,
) -> DuplicateAnalysis:
    evidence = db.query(Evidence).filter(Evidence.id == evidence_id).one()
    exact = (
        db.query(Evidence)
        .filter(Evidence.sha256 == evidence.sha256, Evidence.id != evidence_id)
        .all()
        if evidence.sha256
        else []
    )
    perceptual: list[dict[str, Any]] = []
    if evidence.phash:
        candidates = (
            db.query(Evidence)
            .filter(Evidence.phash.is_not(None), Evidence.id != evidence_id)
            .all()
        )
        for candidate in candidates:
            distance = phash_distance(evidence.phash, candidate.phash)
            if distance <= settings.phash_max_hamming_distance:
                perceptual.append({"evidence_id": candidate.id, "distance": distance})

    for candidate in exact:
        _upsert_match(db, evidence.id, candidate.id, "sha256", signals={"sha256_match": True})
    for candidate in perceptual:
        _upsert_match(
            db,
            evidence.id,
            candidate["evidence_id"],
            "phash",
            phash_distance=candidate["distance"],
            signals={"phash_distance": candidate["distance"]},
        )

    embedding_status = "unavailable"
    embedding_error = None
    semantic_matches: list[dict[str, Any]] = []
    if storage is not None:
        try:
            data = storage.get_object_bytes(storage.quarantine_bucket, evidence.storage_key)
            vector = image_embedding(data)
            if job_id is not None:
                result = db.query(AnalysisResult).filter(AnalysisResult.job_id == job_id).one_or_none()
                if result is None:
                    result = AnalysisResult(job_id=job_id)
                    db.add(result)
                result.embedding = vector
                db.flush()
                semantic_candidates = search_similar_embeddings(
                    vector,
                    db,
                    exclude_job_id=job_id,
                    exclude_evidence_id=evidence_id,
                )
                semantic_matches = semantic_candidates
                for candidate in semantic_candidates:
                    distance = candidate["distance"]
                    _upsert_match(
                        db,
                        evidence.id,
                        candidate["evidence_id"],
                        "embedding",
                        embedding_similarity=1.0 - distance,
                        signals={
                            "embedding_distance": distance,
                            "embedding_similarity": 1.0 - distance,
                        },
                    )
            embedding_status = "success"
        except Exception as error:
            embedding_error = str(error)
    db.commit()
    return DuplicateAnalysis(
        [candidate.id for candidate in exact],
        perceptual,
        semantic_matches,
        embedding_status,
        embedding_error,
    )


def _upsert_match(
    db: Session,
    evidence_id: str,
    matched_id: str,
    match_type: str,
    *,
    phash_distance: int | None = None,
    embedding_similarity: float | None = None,
    signals: dict[str, Any],
) -> None:
    if evidence_id == matched_id:
        return
    first, second = sorted((evidence_id, matched_id))
    match = (
        db.query(DuplicateMatch)
        .filter(
            DuplicateMatch.evidence_id == first,
            DuplicateMatch.matched_evidence_id == second,
        )
        .one_or_none()
    )
    if match is None:
        db.add(
            DuplicateMatch(
                evidence_id=first,
                matched_evidence_id=second,
                match_type=match_type,
                phash_distance=phash_distance,
                embedding_similarity=embedding_similarity,
                signals=signals,
            )
        )
        db.flush()
    else:
        match.signals = {**(match.signals or {}), **signals}
        if phash_distance is not None:
            match.phash_distance = phash_distance
        if embedding_similarity is not None:
            match.embedding_similarity = embedding_similarity