from pathlib import Path
from typing import Optional, List
import re
import random

from app.services.parsing import read_text, normalize, SUPPORTED

_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)"
_MONTH_YEAR = rf"{_MONTH}\s+\d{{4}}"
_DATE_RANGE_RE = re.compile(rf"({_MONTH_YEAR})\s*(?:-|\u2013|to)\s*(Present|Current|{_MONTH_YEAR})", re.IGNORECASE)
_BULLET_RE = re.compile(r"^(?:[-*\u2022]|\d+\.)\s+")


def select_master_resume(resumes_dir: Path) -> Optional[Path]:
    """
    Picks the master resume automatically.
    Selection rules:
      1) Only consider files that contain 'PROFESSIONAL EXPERIENCE' (case-insensitive) after parsing text.
      2) Score each file by (date_count + bullet_count). Prefer higher score.
         - date_count: number of month-year ranges like 'May 2021 - Jun 2023' or 'May 2021 - Present'
         - bullet_count: lines starting with '-', '•', '*', or numbered bullets.
      3) If score ties, choose the resume with the shortest filename length.
      4) If still tied, choose randomly among tied resumes, but use stable randomness seeded by joined filenames.
    """
    candidates: List[tuple[Path, int, int]] = []

    for path in sorted(resumes_dir.glob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        text = read_text(path)
        if not text:
            continue
        normalized = normalize(text)
        if "PROFESSIONAL EXPERIENCE" not in normalized.upper():
            continue

        date_count = len(_DATE_RANGE_RE.findall(normalized))
        bullet_count = sum(1 for line in normalized.splitlines() if _BULLET_RE.match(line.strip()))
        score = date_count + bullet_count
        candidates.append((path, score, len(path.name)))

    if not candidates:
        return None

    max_score = max(item[1] for item in candidates)
    top = [item for item in candidates if item[1] == max_score]

    min_len = min(item[2] for item in top)
    shortest = [item for item in top if item[2] == min_len]

    if len(shortest) == 1:
        return shortest[0][0]

    names = sorted(item[0].name for item in shortest)
    seed = ",".join(names)
    rng = random.Random(seed)
    return rng.choice([item[0] for item in shortest])


def extract_experience_headers(master_text: str) -> List[str]:
    """
    Extract role header lines from PROFESSIONAL EXPERIENCE section.
    Output: list[str] of header strings in display format, e.g.
      'Company - Title | May 2021 - Jun 2023'
    """
    normalized = normalize(master_text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]

    start_idx = _find_section_index(lines, ["PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE", "EXPERIENCE"])
    if start_idx is None:
        return []

    end_idx = _find_section_index(lines[start_idx + 1:], ["EDUCATION"])
    if end_idx is None:
        section_lines = lines[start_idx + 1:]
    else:
        section_lines = lines[start_idx + 1:start_idx + 1 + end_idx]

    headers: List[str] = []
    seen = set()

    for idx, line in enumerate(section_lines):
        if _BULLET_RE.match(line):
            continue
        match = _DATE_RANGE_RE.search(line)
        if not match:
            continue

        start = match.group(1)
        end = match.group(2)
        pre = line[:match.start()].strip(" -|,")
        post = line[match.end():].strip(" -|,")

        company = None
        title = None

        if pre and post:
            company = pre
            title = post
        elif pre and not post:
            company, title = _split_company_title(pre)
            if not title:
                next_line = _next_non_bullet(section_lines, idx)
                if next_line:
                    title = next_line
        elif post and not pre:
            prev_line = _prev_non_bullet(section_lines, idx)
            if prev_line:
                company, title = _split_company_title(prev_line)
                if not title:
                    company = prev_line
                    title = post

        if not company or not title:
            continue

        title = _strip_title_parenthetical(title)
        header = f"{company} - {title} | {start} - {end}"
        header = header.replace("\u2013", "-").replace("\u2014", "-")
        header = re.sub(r"\s+", " ", header).strip()
        key = header.lower()
        if key not in seen:
            seen.add(key)
            headers.append(header)

    return headers


def _find_section_index(lines: List[str], headers: List[str]) -> Optional[int]:
    header_set = {h.upper() for h in headers}
    for idx, line in enumerate(lines):
        if line.upper() in header_set:
            return idx
    return None


def _split_company_title(text: str) -> tuple[str, Optional[str]]:
    for sep in [" | ", " - ", ","]:
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            company = parts[0] if parts else text
            title = parts[1] if len(parts) > 1 else None
            return company, title
    return text, None


def _strip_title_parenthetical(title: str) -> str:
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()


def _prev_non_bullet(lines: List[str], idx: int) -> Optional[str]:
    for j in range(idx - 1, -1, -1):
        if not lines[j] or _BULLET_RE.match(lines[j]):
            continue
        return lines[j]
    return None


def _next_non_bullet(lines: List[str], idx: int) -> Optional[str]:
    for j in range(idx + 1, len(lines)):
        if not lines[j] or _BULLET_RE.match(lines[j]):
            continue
        return lines[j]
    return None
