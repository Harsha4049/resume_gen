from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.schemas import AtsScoreRequest, AtsScoreResponse
from app.services.ats_scoring import score_resume_against_jd
from app.services.resume_store import load_latest_state
from app.services.resume_state import parse_resume_text_to_state


router = APIRouter()


@router.post("/ats-score", response_model=AtsScoreResponse)
def ats_score(payload: AtsScoreRequest) -> AtsScoreResponse:
    if not payload.resume_id and not payload.resume_text:
        raise HTTPException(status_code=422, detail="resume_id or resume_text is required")

    if payload.resume_id:
        try:
            state, _ = load_latest_state(settings.generated_resumes_dir, payload.resume_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="resume_id not found")
    else:
        state = parse_resume_text_to_state(payload.resume_text or "")

    return score_resume_against_jd(
        payload.jd_text,
        state,
        top_n_skills=payload.top_n_skills,
        strict_mode=payload.strict_mode,
    )
