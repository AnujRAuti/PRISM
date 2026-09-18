from fastapi import APIRouter

from backend.api.v1.endpoints.evidence import router as evidence_router
from backend.api.v1.endpoints.analysis import router as analysis_router
from backend.api.v1.endpoints.context import router as context_router
from backend.api.v1.endpoints.temporal import router as temporal_router
from backend.api.v1.endpoints.vision import router as vision_router

router = APIRouter()
router.include_router(evidence_router)
router.include_router(analysis_router)
router.include_router(context_router)
router.include_router(temporal_router)
router.include_router(vision_router)
