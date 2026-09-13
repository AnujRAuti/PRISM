from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.api.v1.endpoints.health import router as health_router
from backend.core.logging import setup_logging


setup_logging()

app = FastAPI(title=settings.app_name)

# Basic CORS (allow dev origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


app.include_router(health_router, prefix="/api/v1")
