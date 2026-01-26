import json
import re
from collections import Counter
from typing import Optional

from app.models.schemas import JDParseResponse
from app.services.claude_client import generate_with_claude


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}


def _normalize_list(values: list[str]) -> list[str]:
    """Normalize list values by stripping, de-duping, and removing empties."""
    cleaned = []
    seen = set()
    for value in values:
        item = value.strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


def _extract_keywords(text: str, limit: int = 12) -> list[str]:
    """Extract keyword-like tokens from text using a simple frequency heuristic."""
    tokens = re.findall(r"[A-Za-z0-9+#.]+", text)
    candidates = [t for t in tokens if len(t) >= 3 and t.lower() not in _STOPWORDS]
    counts = Counter(t.lower() for t in candidates)
    return [word for word, _ in counts.most_common(limit)]


def _fallback_parse(jd_text: str) -> dict:
    """Fallback rule-based JD parsing when LLM parsing fails."""
    lower = jd_text.lower()
    seniority = None
    if "lead" in lower:
        seniority = "lead"
    elif "senior" in lower:
        seniority = "senior"
    elif "mid" in lower or "mid-level" in lower:
        seniority = "mid"
    elif "junior" in lower:
        seniority = "junior"

    role_match = re.search(r"\b([a-zA-Z ]{2,40})(engineer|developer|architect|analyst|manager|scientist)\b", jd_text, re.I)
    role = role_match.group(0).strip() if role_match else "unknown"

    domain = None
    for candidate in ["fintech", "healthcare", "e-commerce", "banking", "education", "retail", "saas", "security", "cloud"]:
        if candidate in lower:
            domain = candidate
            break

    must_have_skills: list[str] = []
    nice_to_have_skills: list[str] = []
    responsibilities: list[str] = []

    for line in jd_text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        lower_line = clean.lower()
        if "must" in lower_line or "required" in lower_line:
            must_have_skills.extend(re.split(r"[,/;]", clean))
        elif "nice to have" in lower_line or "preferred" in lower_line:
            nice_to_have_skills.extend(re.split(r"[,/;]", clean))
        elif "responsibil" in lower_line or lower_line.startswith("you will"):
            responsibilities.append(clean)

    if not must_have_skills:
        must_have_skills = _extract_keywords(jd_text)

    if not responsibilities:
        responsibilities = [line.strip() for line in jd_text.splitlines() if line.strip().startswith(('-', '*'))][:8]

    return {
        "role": role,
        "domain": domain,
        "seniority": seniority,
        "must_have_skills": _normalize_list(must_have_skills),
        "nice_to_have_skills": _normalize_list(nice_to_have_skills),
        "responsibilities": _normalize_list(responsibilities),
    }


def parse_jd(
    jd_text: str,
    api_key: str,
    model: str,
    use_claude: bool = True,
) -> JDParseResponse:
    """Parse a JD into structured fields using Claude with a rule-based fallback."""
    if use_claude:
        system_prompt = (
            "You are a strict JSON extraction engine. "
            "Return ONLY valid JSON matching the schema, no prose."
        )
        user_prompt = (
            "Extract a structured JD in this schema:\n"
            "{\n"
            "  \"role\": \"string\",\n"
            "  \"domain\": \"string | null\",\n"
            "  \"seniority\": \"junior | mid | senior | lead | null\",\n"
            "  \"must_have_skills\": [\"skill1\"],\n"
            "  \"nice_to_have_skills\": [\"skill2\"],\n"
            "  \"responsibilities\": [\"resp1\"]\n"
            "}\n\n"
            f"JOB DESCRIPTION:\n{jd_text}"
        )
        try:
            raw = generate_with_claude(
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=600,
                temperature=0.0,
            )
            data = json.loads(raw)
        except Exception:
            data = _fallback_parse(jd_text)
    else:
        data = _fallback_parse(jd_text)

    normalized = {
        "role": data.get("role", "unknown") or "unknown",
        "domain": data.get("domain"),
        "seniority": data.get("seniority"),
        "must_have_skills": _normalize_list(data.get("must_have_skills", [])),
        "nice_to_have_skills": _normalize_list(data.get("nice_to_have_skills", [])),
        "responsibilities": _normalize_list(data.get("responsibilities", [])),
    }

    return JDParseResponse(**normalized)
