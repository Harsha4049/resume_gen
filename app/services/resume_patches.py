from __future__ import annotations

from typing import List, Tuple, Optional
import re

from app.models.schemas import ResumeState, PatchOperation, BlockedSuggestion, SkillCoverage, AtsScoreResponse
from app.services.ats_scoring import find_skills_in_text, has_direct_evidence


_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-•*]|\d+\.)\s+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9+#.-]+")
_STOPWORDS = {
    "and",
    "or",
    "the",
    "a",
    "an",
    "to",
    "of",
    "for",
    "with",
    "in",
    "on",
    "by",
    "from",
    "as",
    "at",
}


def suggest_roles_for_skill(
    resume_state: ResumeState,
    skill: str,
    jd_context: Optional[str] = None,
) -> List[str]:
    """Suggest top role_ids for a skill using deterministic keyword overlap."""
    skill = (skill or "").strip()
    if not resume_state.sections.experience:
        return []

    tokens = _tokenize(f"{skill} {jd_context or ''}")
    scored: List[Tuple[int, str]] = []

    for role in resume_state.sections.experience:
        role_text = " ".join(
            part
            for part in [
                role.company,
                role.title or "",
                role.location or "",
                role.dates or "",
                " ".join(role.bullets),
            ]
            if part
        )
        role_tokens = _tokenize(role_text)
        overlap = len(tokens & role_tokens)
        if skill and _contains_token(role_text, skill):
            overlap += 3
        scored.append((overlap, role.role_id))

    scored.sort(key=lambda item: (-item[0], item[1]))
    top = [role_id for score, role_id in scored if score > 0][:2]
    if not top:
        top = [role_id for _, role_id in scored][:2]
    return top


def proof_bullet_template(skill: str, jd_text: Optional[str]) -> str:
    """Return a neutral proof-bullet template for overrides."""
    skill = (skill or "").strip()
    context = _choose_context(jd_text or "")
    return f"Used {skill} to support {context} workflows, improving consistency and reliability."


def apply_patches_to_state(state: ResumeState, patches: List[PatchOperation]) -> None:
    """Apply patch operations to the in-memory ResumeState."""
    for patch in patches:
        if patch.section == "technical_skills":
            _apply_skill_patch(state, patch)
        else:
            _apply_experience_patch(state, patch)


def apply_truth_guardrails(
    suggestions: List[PatchOperation],
    ats_report: AtsScoreResponse,
    overrides,
    truth_mode: str,
    resume_state: ResumeState,
    jd_text: Optional[str] = None,
) -> tuple[List[PatchOperation], List[BlockedSuggestion]]:
    if truth_mode == "off":
        return suggestions, []

    missing_required = {skill.lower() for skill in ats_report.missing_required}
    override_skills = {entry.skill.strip().lower() for entry in (overrides.skills if overrides else [])}
    direct_skills = {cov.skill.strip().lower() for cov in ats_report.required if cov.direct_from_resume}

    filtered: List[PatchOperation] = []
    blocked: List[BlockedSuggestion] = []

    for patch in suggestions:
        skill = (patch.skill or "").strip()
        skill_key = skill.lower() if skill else ""
        has_override = skill_key in override_skills
        has_direct = skill_key in direct_skills or (skill_key and has_direct_evidence(resume_state, skill_key))

        if truth_mode == "strict":
            if patch.section == "experience" and skill_key in missing_required and not has_override:
                blocked.append(
                    _build_blocked_suggestion(
                        skill=skill or "unknown",
                        reason="Missing required skill without override; cannot insert into experience in strict mode.",
                        recommended_action="add_override",
                        resume_state=resume_state,
                        jd_text=jd_text,
                    )
                )
                continue
            if patch.section == "technical_skills" and not (has_direct or has_override):
                blocked.append(
                    _build_blocked_suggestion(
                        skill=skill or "unknown",
                        reason="No direct or override evidence; cannot add to technical skills in strict mode.",
                        recommended_action="downgrade_to_exposure",
                        resume_state=resume_state,
                        jd_text=jd_text,
                    )
                )
                continue

        if truth_mode == "balanced":
            if patch.section == "experience" and skill_key in missing_required and not has_override:
                blocked.append(
                    _build_blocked_suggestion(
                        skill=skill or "unknown",
                        reason="Missing required skill without override; cannot insert into experience in balanced mode.",
                        recommended_action="add_override",
                        resume_state=resume_state,
                        jd_text=jd_text,
                    )
                )
                continue

        filtered.append(patch)

    return filtered, blocked


def validate_patches_truth_mode(
    patches: List[PatchOperation],
    resume_state: ResumeState,
    overrides,
    truth_mode: str,
) -> None:
    if truth_mode == "off":
        return

    override_skills = {entry.skill.strip().lower() for entry in (overrides.skills if overrides else [])}

    for patch in patches:
        if patch.section != "experience":
            continue
        skills_in_patch = []
        if patch.skill:
            skills_in_patch.append(patch.skill)
        else:
            skills_in_patch = find_skills_in_text(patch.new_bullet)

        for skill in skills_in_patch:
            key = skill.strip().lower()
            if not key:
                continue
            if key in override_skills:
                continue
            if not has_direct_evidence(resume_state, key):
                raise ValueError(
                    f"Truth mode '{truth_mode}' blocks experience patch without direct or override evidence for skill: {skill}"
                )


def _build_blocked_suggestion(
    skill: str,
    reason: str,
    recommended_action: str,
    resume_state: ResumeState,
    jd_text: Optional[str],
) -> BlockedSuggestion:
    suggested_roles = suggest_roles_for_skill(resume_state, skill, jd_text)
    example_payload = None
    if recommended_action == "add_override":
        template = proof_bullet_template(skill, jd_text)
        target_roles = suggested_roles[:1] if suggested_roles else []
        example_payload = {
            "skills": [
                {
                    "skill": skill,
                    "level": "worked_with",
                    "target_roles": target_roles,
                    "proof_bullets": [template],
                }
            ]
        }
    return BlockedSuggestion(
        skill=skill,
        reason=reason,
        recommended_action=recommended_action,
        suggested_role_ids=suggested_roles,
        example_override_payload=example_payload,
    )


def _tokenize(text: str) -> set[str]:
    tokens = {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 2}
    return {t for t in tokens if t not in _STOPWORDS}


def _contains_token(text: str, token: str) -> bool:
    if not token:
        return False
    pattern = r"(?<!\w)" + re.escape(token.lower()) + r"(?!\w)"
    return bool(re.search(pattern, text or "", re.IGNORECASE))


def _choose_context(jd_text: str) -> str:
    text = jd_text.lower()
    if any(word in text for word in ["dashboard", "report", "tableau", "visualization"]):
        return "reporting and analytics"
    if any(word in text for word in ["pipeline", "ingest", "ingestion", "etl", "elt"]):
        return "data ingestion and transformation"
    if any(word in text for word in ["model", "schema", "dbt", "dimensional"]):
        return "data modeling"
    return "data processing"


def _apply_experience_patch(state: ResumeState, patch: PatchOperation) -> None:
    role = _find_role(state, patch.role_id)
    bullet = _clean_bullet(patch.new_bullet)
    if patch.action == "replace":
        if patch.bullet_index is None or patch.bullet_index >= len(role.bullets) or patch.bullet_index < 0:
            raise IndexError("bullet_index out of range")
        role.bullets[patch.bullet_index] = bullet
        return

    if patch.action == "insert":
        idx = patch.after_index if patch.after_index is not None else len(role.bullets) - 1
        if idx < -1 or idx >= len(role.bullets):
            raise IndexError("after_index out of range")
        insert_at = idx + 1
        role.bullets.insert(insert_at, bullet)


def _apply_skill_patch(state: ResumeState, patch: PatchOperation) -> None:
    if patch.action != "insert":
        raise ValueError("Only insert is supported for technical_skills")
    skills = state.sections.technical_skills
    bullet = _clean_bullet(patch.new_bullet)
    idx = patch.after_index if patch.after_index is not None else len(skills) - 1
    if idx < -1 or idx >= len(skills):
        raise IndexError("after_index out of range")
    insert_at = idx + 1
    skills.insert(insert_at, bullet)


def _find_role(state: ResumeState, role_id: str | None):
    if not role_id:
        raise ValueError("role_id is required")
    for role in state.sections.experience:
        if role.role_id == role_id:
            return role
    raise ValueError("role_id not found")


def _clean_bullet(text: str) -> str:
    cleaned = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    cleaned = _BULLET_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned
