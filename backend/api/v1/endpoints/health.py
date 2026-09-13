from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.db.session import get_engine

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready():
    # basic readiness: database engine creatable
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # perform a simple lightweight query to verify DB responsiveness
            conn.execute("SELECT 1")
        return JSONResponse({"status": "ok"})
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
