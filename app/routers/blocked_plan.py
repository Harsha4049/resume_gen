from fastapi import APIRouter, HTTPException
import re

from app.config import settings
from app.models.schemas import BlockedPlanRequest, BlockedPlanResponse, PatchOperation, OverridesRequest
from app.services.resume_store import load_latest_state
from app.services.resume_overrides import load_overrides
from app.services.ats_scoring import score_resume_against_jd
from app.services.resume_patches import apply_truth_guardrails


router = APIRouter()


@router.post("/resumes/{resume_id}/blocked-plan", response_model=BlockedPlanResponse)
def blocked_plan(resume_id: str, payload: BlockedPlanRequest) -> BlockedPlanResponse:
    try:
        state, _ = load_latest_state(settings.generated_resumes_dir, resume_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="resume_id not found")

    ats = score_resume_against_jd(
        payload.jd_text,
        state,
        strict_mode=payload.strict_mode,
    )

    overrides = load_overrides(settings.generated_resumes_dir, resume_id)

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

    _, blocked = apply_truth_guardrails(
        suggested,
        ats,
        overrides,
        payload.truth_mode,
        state,
        jd_text=payload.jd_text,
    )

    if payload.top_n and payload.top_n > 0:
        blocked = blocked[: payload.top_n]

    return BlockedPlanResponse(blocked=blocked)


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
