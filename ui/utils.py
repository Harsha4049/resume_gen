from __future__ import annotations

from typing import Any


def role_label(role: dict) -> str:
    company = role.get("company") or "Unknown Company"
    title = role.get("title") or ""
    location = role.get("location") or ""
    dates = role.get("dates") or ""
    parts = []
    if title:
        parts.append(title)
    if location:
        parts.append(location)
    line2 = " | ".join([p for p in parts if p])
    header = company
    if dates:
        header = f"{company} ({dates})"
    if line2:
        return f"{header} - {line2}"
    return header


def role_options(state: dict) -> list[tuple[str, str, dict]]:
    roles = state.get("sections", {}).get("experience", []) if state else []
    options: list[tuple[str, str, dict]] = []
    for role in roles:
        label = role_label(role)
        role_id = role.get("role_id") or ""
        options.append((label, role_id, role))
    return options


def extract_resume_text(state: dict) -> str:
    if not state:
        return ""
    summary = state.get("sections", {}).get("professional_summary") or ""
    skills = state.get("sections", {}).get("technical_skills") or []
    experience = state.get("sections", {}).get("experience") or []
    education = state.get("sections", {}).get("education") or []

    lines = []
    if summary:
        lines.append("PROFESSIONAL SUMMARY")
        lines.append(summary)
        lines.append("")

    if skills:
        lines.append("TECHNICAL SKILLS")
        lines.extend(skills)
        lines.append("")

    if experience:
        lines.append("PROFESSIONAL EXPERIENCE")
        for role in experience:
            header = role_label(role)
            lines.append(header)
            for bullet in role.get("bullets", []):
                lines.append(f"- {bullet}")
            lines.append("")

    if education:
        lines.append("EDUCATION")
        lines.extend(education)

    text = "\n".join(lines).strip()
    return text.replace("~", "").replace("∼", "").replace("˜", "").replace("～", "")


def safe_get(dct: dict, *keys: str, default: Any = "") -> Any:
    cur: Any = dct
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default
