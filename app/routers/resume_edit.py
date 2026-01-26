from fastapi import APIRouter, HTTPException
from pathlib import Path
import re

from app.config import settings
from app.models.schemas import BulletEditRequest, BulletEditResponse, ResumeStateResponse
from app.services.resume_store import (
    load_resume_state,
    append_resume_version,
    update_version_docx_path,
)
from app.services.docx_exporter import export_docx_from_state


router = APIRouter()


@router.get("/resumes/{resume_id}", response_model=ResumeStateResponse)
def get_resume(resume_id: str) -> ResumeStateResponse:
    try:
        state, version = load_resume_state(settings.generated_resumes_dir, resume_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="resume_id not found")

    return ResumeStateResponse(resume_id=resume_id, version=version, state=state)


@router.patch("/resumes/{resume_id}/bullet", response_model=BulletEditResponse)
def edit_bullet(resume_id: str, payload: BulletEditRequest) -> BulletEditResponse:
    try:
        state, _ = load_resume_state(settings.generated_resumes_dir, resume_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="resume_id not found")

    role_index = _select_role_index(state.sections.experience, payload.role_selector)
    role = state.sections.experience[role_index]

    if payload.bullet_index < 0 or payload.bullet_index >= len(role.bullets):
        raise HTTPException(status_code=422, detail="bullet_index out of range")

    cleaned = _clean_bullet(payload.new_bullet)
    if not cleaned:
        raise HTTPException(status_code=422, detail="new_bullet is invalid")

    role.bullets[payload.bullet_index] = cleaned

    meta = append_resume_version(
        settings.generated_resumes_dir,
        resume_id,
        state,
    )
    version = meta.get("latest_version")
    version_dir = settings.generated_resumes_dir / resume_id / version
    resume_docx_path = None

    if payload.export_docx:
        template_path = Path(settings.docx_template_path)
        if not template_path.exists():
            raise HTTPException(
                status_code=400,
                detail="DOCX template not found. Put template at storage/resumes/template/template.docx",
            )
        resume_docx_path = version_dir / "resume.docx"
        export_docx_from_state(state, template_path, resume_docx_path)
        update_version_docx_path(settings.generated_resumes_dir, resume_id, version, resume_docx_path)

    return BulletEditResponse(
        resume_id=resume_id,
        version=version,
        updated_role={
            "role_id": role.role_id,
            "company": role.company,
            "title": role.title,
            "dates": role.dates,
        },
        updated_bullet_index=payload.bullet_index,
        paths={
            "resume_json": str((version_dir / "resume.json").as_posix()),
            "resume_docx": str(resume_docx_path.as_posix()) if resume_docx_path else None,
        },
    )


def _select_role_index(roles, selector) -> int:
    role_id = (selector.role_id or "").strip()
    company = (selector.company or "").strip()
    dates = (selector.dates or "").strip()

    if role_id:
        for idx, role in enumerate(roles):
            if role.role_id == role_id:
                return idx
        raise HTTPException(status_code=404, detail="role_id not found")

    if not company or not dates:
        raise HTTPException(status_code=422, detail="Provide role_id or company + dates")

    matches = [
        idx for idx, role in enumerate(roles)
        if role.company.strip().lower() == company.lower()
        and (role.dates or "").strip().lower() == dates.lower()
    ]

    if not matches:
        raise HTTPException(status_code=404, detail="role not found for company + dates")
    if len(matches) > 1:
        role_ids = [roles[idx].role_id for idx in matches]
        raise HTTPException(status_code=409, detail={"message": "multiple roles matched", "role_ids": role_ids})

    return matches[0]


def _clean_bullet(text: str) -> str:
    cleaned = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(r"^\s*(?:[-•*]|\d+\.)\s+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 10 or len(cleaned) > 300:
        return ""
    return cleaned
