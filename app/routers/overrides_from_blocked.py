from fastapi import APIRouter, HTTPException
import re

from app.config import settings
from app.models.schemas import (
    OverridesFromBlockedRequest,
    OverridesFromBlockedResponse,
    OverridesRequest,
    OverrideSkill,
)
from app.services.resume_store import load_latest_state
from app.services.resume_overrides import load_overrides, save_overrides


router = APIRouter()

_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-•*]|\d+\.)\s+")


@router.post("/resumes/{resume_id}/overrides/from-blocked", response_model=OverridesFromBlockedResponse)
def overrides_from_blocked(resume_id: str, payload: OverridesFromBlockedRequest) -> OverridesFromBlockedResponse:
    try:
        state, _ = load_latest_state(settings.generated_resumes_dir, resume_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="resume_id not found")

    overrides = load_overrides(settings.generated_resumes_dir, resume_id) or OverridesRequest()

    for item in payload.items:
        if not _role_exists(state, item.role_id):
            raise HTTPException(status_code=422, detail=f"role_id not found: {item.role_id}")

        cleaned = _clean_bullet(item.proof_bullet)
        if len(cleaned) < 5:
            raise HTTPException(status_code=422, detail="proof_bullet is too short after sanitization")

        entry = _find_override(overrides, item.skill)
        if entry:
            entry.level = item.level
            if item.role_id not in entry.target_roles:
                entry.target_roles.append(item.role_id)
            if cleaned not in entry.proof_bullets:
                entry.proof_bullets.append(cleaned)
            if len(entry.proof_bullets) > 3:
                entry.proof_bullets = entry.proof_bullets[:3]
        else:
            overrides.skills.append(
                OverrideSkill(
                    skill=item.skill,
                    level=item.level,
                    target_roles=[item.role_id],
                    proof_bullets=[cleaned],
                )
            )

    path = save_overrides(settings.generated_resumes_dir, resume_id, overrides)
    return OverridesFromBlockedResponse(resume_id=resume_id, overrides_path=str(path.as_posix()), overrides=overrides)


def _find_override(overrides: OverridesRequest, skill: str):
    for entry in overrides.skills:
        if entry.skill.strip().lower() == skill.strip().lower():
            return entry
    return None


def _role_exists(state, role_id: str) -> bool:
    return any(role.role_id == role_id for role in state.sections.experience)


def _clean_bullet(text: str) -> str:
    cleaned = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    cleaned = _BULLET_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
