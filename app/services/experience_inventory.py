from pathlib import Path
import re
from typing import Dict, List, Optional

from app.services.parsing import read_text, normalize, SUPPORTED

_SECTION_HEADERS = {
    "PROFESSIONAL EXPERIENCE": "experience",
    "EXPERIENCE": "experience",
    "WORK EXPERIENCE": "experience",
    "PROFESSIONAL BACKGROUND": "experience",
    "EDUCATION": "education",
}

_BULLET_RE = re.compile(r"^(?:[-*\\u2022]|\d+\.)\s+")
_MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}"
_DATE_RANGE_RE = re.compile(rf"({_MONTH_RE})\s*(?:-|to)\s*(Present|Current|{_MONTH_RE})", re.IGNORECASE)


def extract_experience_inventory(resumes_dir: Path) -> Dict:
    """Extract education lines and role bullets from resumes in the directory."""
    roles: List[Dict] = []
    education_lines: List[str] = []

    for path in sorted(resumes_dir.glob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        text = read_text(path)
        if not text:
            continue
        normalized = normalize(text)
        if not normalized:
            continue
        file_roles, file_education = _extract_from_text(normalized)
        if file_roles:
            roles.extend(file_roles)
        if file_education and not education_lines:
            education_lines = file_education

    if not roles:
        fallback_bullets = _fallback_bullets(resumes_dir)
        roles = [{
            "company": "Unknown",
            "title": "Unknown Role",
            "start": None,
            "end": None,
            "location": None,
            "bullets": fallback_bullets,
        }]

    return {
        "education": education_lines,
        "roles": roles,
    }


def _extract_from_text(text: str) -> tuple[list[dict], list[str]]:
    """Extract roles and education lines from a single resume text."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    roles: List[Dict] = []
    education: List[str] = []
    current_section: Optional[str] = None
    current_role: Optional[Dict] = None
    header_buffer: List[str] = []

    def flush_role() -> None:
        nonlocal current_role
        if current_role and current_role.get("bullets"):
            roles.append(current_role)
        current_role = None

    for line in lines:
        heading = _detect_heading(line)
        if heading:
            if current_section == "experience":
                flush_role()
            current_section = heading
            header_buffer = []
            continue

        if current_section == "education":
            education.append(line)
            continue

        if current_section != "experience":
            continue

        if _is_role_header(line):
            flush_role()
            current_role = _parse_role_header(line, header_buffer)
            header_buffer = []
            continue

        if current_role is None:
            if not _BULLET_RE.match(line):
                header_buffer.append(line)
            continue

        if _BULLET_RE.match(line):
            current_role["bullets"].append(_strip_bullet(line))
        else:
            current_role["bullets"].append(line)

    if current_section == "experience":
        flush_role()

    education = _dedupe_lines(education)
    return roles, education


def _detect_heading(line: str) -> Optional[str]:
    """Return normalized section key for a heading line."""
    key = line.strip().upper()
    return _SECTION_HEADERS.get(key)


def _is_role_header(line: str) -> bool:
    """Return True if a line appears to contain a date range."""
    return bool(_DATE_RANGE_RE.search(line))


def _parse_role_header(line: str, buffer_lines: List[str]) -> Dict:
    """Parse a role header line into structured fields."""
    match = _DATE_RANGE_RE.search(line)
    start = None
    end = None
    company = None
    title = None
    location = None

    if match:
        start = match.group(1)
        end = match.group(2)
        pre = line[:match.start()].strip(" -|,")
        post = line[match.end():].strip(" -|,")
        if pre:
            company = pre
        if post:
            title, location = _split_title_location(post)

    if not company and buffer_lines:
        company = buffer_lines[-1]
    if not title and len(buffer_lines) >= 2:
        title = _strip_title_parenthetical(buffer_lines[-2])

    return {
        "company": company or "Unknown",
        "title": title or "Unknown Role",
        "start": start,
        "end": end,
        "location": location,
        "bullets": [],
    }


def _split_title_location(text: str) -> tuple[str, Optional[str]]:
    """Split a title/location line into title and location components."""
    for sep in [" | ", " - ", ","]:
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            title = parts[0] if parts else text
            location = parts[1] if len(parts) > 1 else None
            return _strip_title_parenthetical(title), location
    return _strip_title_parenthetical(text), None


def _strip_bullet(line: str) -> str:
    """Strip a bullet marker from a line."""
    return _BULLET_RE.sub("", line).strip()


def _strip_title_parenthetical(title: str) -> str:
    """Remove trailing parenthetical phrases from titles."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()


def _dedupe_lines(lines: List[str]) -> List[str]:
    """Deduplicate lines while preserving order."""
    seen = set()
    deduped = []
    for line in lines:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(line)
    return deduped


def _fallback_bullets(resumes_dir: Path) -> List[str]:
    """Collect bullet lines across resumes as a fallback."""
    bullets: List[str] = []
    for path in sorted(resumes_dir.glob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        text = read_text(path)
        normalized = normalize(text)
        for line in normalized.splitlines():
            if _BULLET_RE.match(line):
                bullets.append(_strip_bullet(line))
    return _dedupe_lines(bullets)
