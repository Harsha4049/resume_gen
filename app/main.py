from fastapi import FastAPI

from app.logging import setup_logging
from app.routers.health import router as health_router
from app.routers.ingest import router as ingest_router
from app.routers.jd import router as jd_router
from app.routers.generate import router as generate_router
from app.routers.export_docx import router as export_docx_router
from app.routers.resume_edit import router as resume_edit_router
from app.routers.ats_score import router as ats_score_router
from app.routers.resume_overrides import router as resume_overrides_router
from app.routers.blocked_plan import router as blocked_plan_router
from app.routers.overrides_from_blocked import router as overrides_from_blocked_router

setup_logging()

app = FastAPI(title="Resume RAG Generator (Phase 1)")
app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(jd_router)
app.include_router(generate_router)
app.include_router(export_docx_router)
app.include_router(resume_edit_router)
app.include_router(ats_score_router)
app.include_router(resume_overrides_router)
app.include_router(blocked_plan_router)
app.include_router(overrides_from_blocked_router)
