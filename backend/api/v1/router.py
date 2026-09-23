from fastapi import APIRouter

from backend.api.v1.endpoints.evidence import router as evidence_router
from backend.api.v1.endpoints.analysis import router as analysis_router
from backend.api.v1.endpoints.context import router as context_router
from backend.api.v1.endpoints.temporal import router as temporal_router
from backend.api.v1.endpoints.vision import router as vision_router
from backend.api.v1.endpoints.evidence_graph import router as graph_router
from backend.api.v1.endpoints.fusion import router as fusion_router
from backend.api.v1.endpoints.explainability import router as explainability_router
from backend.api.v1.endpoints.review_case import router as review_case_router
from backend.api.v1.endpoints.evidence_request import router as evidence_request_router
from backend.api.v1.endpoints.audit_ledger import router as audit_ledger_router
from backend.api.v1.endpoints.auth import router as auth_router
from backend.api.v1.endpoints.retention import router as retention_router

router = APIRouter()
# NOTE: context_router owns GET /evidence/nearby and must precede
# evidence_router, whose GET /evidence/{evidence_id} would otherwise
# shadow it (Starlette matches in registration order).
router.include_router(context_router)
router.include_router(evidence_router)
router.include_router(analysis_router)
router.include_router(temporal_router)
router.include_router(vision_router)
router.include_router(graph_router)
router.include_router(fusion_router)
router.include_router(explainability_router)
router.include_router(review_case_router)
router.include_router(evidence_request_router)
router.include_router(audit_ledger_router)
router.include_router(auth_router)
router.include_router(retention_router)
