from fastapi import APIRouter

from backend.api.v1.endpoints.evidence import router as evidence_router
from backend.api.v1.endpoints.analysis import router as analysis_router

router = APIRouter()
router.include_router(evidence_router)
router.include_router(analysis_router)
