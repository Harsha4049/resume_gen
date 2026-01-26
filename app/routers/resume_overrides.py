from fastapi import APIRouter, HTTPException
import re

from app.config import settings
from app.models.schemas import (
    OverridesRequest,
    OverridesResponse,
    SuggestPatchesRequest,
    SuggestPatchesResponse,
    PatchOperation,
    ApplyPatchesRequest,
    ApplyPatchesResponse,
)
from app.services.resume_store import load_latest_state, append_resume_version, update_version_docx_path
from app.services.resume_overrides import save_overrides, load_overrides
from app.services.ats_scoring import score_resume_against_jd
from app.services.resume_patches import apply_patches_to_state, apply_truth_guardrails, validate_patches_truth_mode
from pathlib import Path
from app.services.docx_exporter import export_docx_from_state


router = APIRouter()


@router.post("/resumes/{resume_id}/overrides", response_model=OverridesResponse)
def save_resume_overrides(resume_id: str, payload: OverridesRequest) -> OverridesResponse:
    _ensure_resume_exists(resume_id)
    path = save_overrides(settings.generated_resumes_dir, resume_id, payload)
    return OverridesResponse(resume_id=resume_id, overrides_path=str(path.as_posix()))


@router.post("/resumes/{resume_id}/suggest-patches", response_model=SuggestPatchesResponse)
def suggest_patches(resume_id: str, payload: SuggestPatchesRequest) -> SuggestPatchesResponse:
    state, _ = _load_state(resume_id)
    ats = score_resume_against_jd(payload.jd_text, state, strict_mode=payload.strict_mode)
    overrides = load_overrides(settings.generated_resumes_dir, resume_id) if payload.apply_overrides else None

    suggested: list[PatchOperation] = []
    inserts_per_role: dict[str, int] = {}

    for skill in ats.missing_required:
        override_entry = _find_override(overrides, skill) if overrides else None
        if override_entry:
            for role_id in override_entry.target_roles:
                if inserts_per_role.get(role_id, 0) >= 2:
                    continue
                role = _find_role(state, role_id)
                if not role:
                    continue
                for proof in override_entry.proof_bullets:
                    if inserts_per_role.get(role_id, 0) >= 2:
                        break
                    suggested.append(
                        PatchOperation(
                            role_id=role_id,
                            section="experience",
                            action="insert",
                            after_index=len(role.bullets) - 1,
                            new_bullet=proof,
                            skill=skill,
                        )
                    )
                    inserts_per_role[role_id] = inserts_per_role.get(role_id, 0) + 1
            continue

        if _skill_already_present(state, skill):
            continue

        suggested.append(
            PatchOperation(
                section="technical_skills",
                action="insert",
                after_index=len(state.sections.technical_skills) - 1,
                new_bullet=f"Exposure to {skill}",
                skill=skill,
            )
        )

    filtered, blocked = apply_truth_guardrails(
        suggested,
        ats,
        overrides,
        payload.truth_mode,
        state,
        jd_text=payload.jd_text,
    )

    return SuggestPatchesResponse(suggested_patches=filtered, blocked=blocked)


@router.post("/resumes/{resume_id}/apply-patches", response_model=ApplyPatchesResponse)
def apply_patches(resume_id: str, payload: ApplyPatchesRequest) -> ApplyPatchesResponse:
    state, _ = _load_state(resume_id)
    overrides = load_overrides(settings.generated_resumes_dir, resume_id)

    try:
        validate_patches_truth_mode(payload.patches, state, overrides, payload.truth_mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        apply_patches_to_state(state, payload.patches)
    except (IndexError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    meta = append_resume_version(settings.generated_resumes_dir, resume_id, state)
    version = meta.get("latest_version")
    version_dir = settings.generated_resumes_dir / resume_id / version
    resume_docx_path = None

    if payload.export_docx:
        template_path = Path(settings.docx_template_path)
        if not template_path.exists():
            raise HTTPException(status_code=400, detail="DOCX template not found")
        export_docx_from_state(state, template_path, version_dir / "resume.docx")
        resume_docx_path = version_dir / "resume.docx"
        update_version_docx_path(settings.generated_resumes_dir, resume_id, version, resume_docx_path)

    return ApplyPatchesResponse(
        resume_id=resume_id,
        version=version,
        paths={
            "resume_json": str((version_dir / "resume.json").as_posix()),
            "resume_docx": str(resume_docx_path.as_posix()) if resume_docx_path else None,
        },
    )


def _ensure_resume_exists(resume_id: str) -> None:
    path = settings.generated_resumes_dir / resume_id / "meta.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="resume_id not found")


def _load_state(resume_id: str):
    try:
        return load_latest_state(settings.generated_resumes_dir, resume_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="resume_id not found")


def _find_override(overrides: OverridesRequest | None, skill: str):
    if not overrides:
        return None
    for entry in overrides.skills:
        if entry.skill.strip().lower() == skill.strip().lower():
            return entry
    return None


def _find_role(state, role_id: str):
    for role in state.sections.experience:
        if role.role_id == role_id:
            return role
    return None


def _skill_already_present(state, skill: str) -> bool:
    token = skill.strip().lower()
    pattern = r"(?<!\\w)" + re.escape(token) + r"(?!\\w)"
    for line in state.sections.technical_skills:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    for bullet in state.sections.professional_summary.splitlines():
        if re.search(pattern, bullet, re.IGNORECASE):
            return True
    for role in state.sections.experience:
        for bullet in role.bullets:
            if re.search(pattern, bullet, re.IGNORECASE):
                return True
    return False
