from fastapi import APIRouter

from app.config import settings
from app.services.llm_client import get_active_model
from app.services.indexing import index_exists

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "index_ready": index_exists(settings.index_dir),
        "resumes_dir": str(settings.resumes_dir),
        "index_dir": str(settings.index_dir),
        "provider": settings.llm_provider,
        "model": get_active_model(),
    }
