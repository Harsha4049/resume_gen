from __future__ import annotations

from typing import Dict, List, Tuple
import re

from app.models.schemas import ResumeState, SkillCoverage, SkillEvidence, AtsScoreResponse


_SECTION_REQUIRED = {"required", "requirements", "must have", "must-have", "qualifications"}
_SECTION_PREFERRED = {"preferred", "nice to have", "nice-to-have", "preferred qualifications"}
_SECTION_RESP = {"responsibilities", "responsibility"}

_SKILL_DICTIONARY = [
    "SQL", "Python", "DBT", "Tableau", "Power BI", "Snowflake", "Fivetran", "Airflow",
    "Databricks", "Spark", "PySpark", "AWS", "Azure", "GCP", "Git", "Docker", "Kubernetes",
    "ETL", "ELT", "Data Warehouse", "Data Modeling", "Dimensional Modeling",
    "Star Schema", "Snowflake Schema", "Data Governance", "Data Quality", "Data Validation",
    "Analytics", "Dashboarding", "Looker", "Redshift", "BigQuery", "PostgreSQL", "MySQL",
    "SQL Server", "Oracle", "NoSQL", "Kafka", "API", "REST", "CI/CD", "Linux",
    "Monitoring", "Data Pipelines", "DBA", "Data Engineering", "Analytics Engineering",
    "Machine Learning", "NLP", "Jupyter", "Terraform", "Jira", "Agile", "Scrum",
    "Unit Testing", "Data Lake", "Delta Lake", "MLflow", "SSIS", "SSRS", "SSAS",
]

_SYNONYMS = {
    "dbt": ["data build tool", "data build tools"],
    "power bi": ["powerbi"],
    "data modeling": ["data model", "relational modeling"],
    "dimensional modeling": ["star schema", "snowflake schema", "dimensional model"],
    "data warehouse": ["data warehousing", "cloud data warehouse"],
    "etl": ["extract transform load"],
    "elt": ["extract load transform"],
    "sql": ["structured query language"],
    "airflow": ["apache airflow"],
    "spark": ["apache spark"],
    "kubernetes": ["k8s"],
    "ci/cd": ["cicd", "ci cd"],
    "rest": ["rest api", "restful"],
}

_MUST_HAVE_DOMAINS = [
    "mqtt",
    "opc ua",
    "opc-ua",
    "opcua",
    "modbus",
    "bacnet",
    "scada",
    "mes",
    "historian",
    "pi",
    "osisoft",
    "ignition",
    "plc",
    "iiot",
    "ot",
    "influxdb",
    "timescaledb",
    "opc",
]


def extract_skills_from_jd(jd_text: str, top_n_skills: int = 25) -> Dict[str, List[str]]:
    """Extract required/preferred skills from JD using deterministic heuristics."""
    required: List[str] = []
    preferred: List[str] = []
    current = "required"

    lines = [line.strip() for line in jd_text.splitlines() if line.strip()]
    for line in lines:
        lower = line.lower()
        if any(key in lower for key in _SECTION_REQUIRED):
            current = "required"
        elif any(key in lower for key in _SECTION_PREFERRED):
            current = "preferred"
        elif any(key in lower for key in _SECTION_RESP):
            current = "required"

        found = find_skills_in_text(line)
        if current == "preferred":
            preferred.extend(found)
        else:
            required.extend(found)

    required = _dedupe_preserve(required)
    preferred = [s for s in _dedupe_preserve(preferred) if s not in required]

    if not required and not preferred:
        required = _dedupe_preserve(find_skills_in_text(jd_text))

    if top_n_skills and top_n_skills > 0:
        required, preferred = _truncate_skills(required, preferred, top_n_skills)

    return {"required": required, "preferred": preferred}


def score_resume_against_jd(
    jd_text: str,
    state: ResumeState,
    top_n_skills: int = 25,
    strict_mode: bool = True,
) -> AtsScoreResponse:
    """Compute ATS score and evidence map with keyword + credibility blend and hard caps for missing must-haves."""
    skills = extract_skills_from_jd(jd_text, top_n_skills=top_n_skills)
    required = skills.get("required", [])
    preferred = skills.get("preferred", [])

    req_coverage = _coverage_for_skills(required, state, strict_mode)
    pref_coverage = _coverage_for_skills(preferred, state, strict_mode)

    req_covered = _count_covered(req_coverage, strict_mode)
    pref_covered = _count_covered(pref_coverage, strict_mode)

    req_total = len(required) or 0
    pref_total = len(preferred) or 0

    keyword_score = 0
    if req_total or pref_total:
        req_ratio = (req_covered / req_total) if req_total else 0
        pref_ratio = (pref_covered / pref_total) if pref_total else 0
        if pref_total == 0:
            keyword_score = round(req_ratio * 100)
        else:
            keyword_score = round(req_ratio * 70 + pref_ratio * 30)
    keyword_score = max(0, min(100, keyword_score))

    # Role-fit / credibility: count direct evidence on required skills only
    direct_req = sum(1 for item in req_coverage if item.status == "direct")
    role_score = round((direct_req / req_total) * 100) if req_total else keyword_score

    final_score = round(keyword_score * 0.6 + role_score * 0.4)
    capped_reason = None

    missing_must_have: List[str] = []
    must_have_hit = _must_have_gates(jd_text)
    if must_have_hit:
        for skill in must_have_hit:
            if not has_direct_evidence(state, skill):
                missing_must_have.append(skill)
    if missing_must_have:
        capped_reason = "Missing domain must-have evidence"
        final_score = min(final_score, 40)

    missing_required = [item.skill for item in req_coverage if item.status == "missing"]
    missing_preferred = [item.skill for item in pref_coverage if item.status == "missing"]

    return AtsScoreResponse(
        ats_score=final_score,
        keyword_score=keyword_score,
        role_score=role_score,
        capped_reason=capped_reason,
        missing_must_have=_dedupe_preserve(missing_must_have) if missing_must_have else None,
        required=req_coverage,
        preferred=pref_coverage,
        missing_required=missing_required,
        missing_preferred=missing_preferred,
    )


def _coverage_for_skills(skills: List[str], state: ResumeState, strict_mode: bool) -> List[SkillCoverage]:
    coverage: List[SkillCoverage] = []

    summary_lines = [line for line in state.sections.professional_summary.splitlines() if line.strip()]
    skills_lines = state.sections.technical_skills or []

    for skill in skills:
        direct_evidence = _find_evidence(skill, state, summary_lines, skills_lines, strict_mode, direct_only=True)
        if direct_evidence:
            coverage.append(SkillCoverage(skill=skill, status="direct", evidence=direct_evidence, direct_from_resume=True))
            continue

        if not strict_mode:
            partial_evidence = _find_evidence(skill, state, summary_lines, skills_lines, strict_mode, direct_only=False)
            if partial_evidence:
                coverage.append(SkillCoverage(skill=skill, status="partial", evidence=partial_evidence, direct_from_resume=False))
                continue

        coverage.append(SkillCoverage(skill=skill, status="missing", evidence=[], direct_from_resume=False))

    return coverage


def _find_evidence(
    skill: str,
    state: ResumeState,
    summary_lines: List[str],
    skills_lines: List[str],
    strict_mode: bool,
    direct_only: bool,
) -> List[SkillEvidence]:
    evidence: List[SkillEvidence] = []
    canonical = skill.lower()

    def match(text: str) -> bool:
        if direct_only:
            return _matches_direct(canonical, text)
        return _matches_direct(canonical, text) or (_matches_partial(canonical, text) if not strict_mode else False)

    for line in summary_lines:
        if match(line):
            evidence.append(SkillEvidence(section="summary", snippet=line))

    for line in skills_lines:
        if match(line):
            evidence.append(SkillEvidence(section="technical_skills", snippet=line))

    for role in state.sections.experience:
        for idx, bullet in enumerate(role.bullets):
            if match(bullet):
                evidence.append(
                    SkillEvidence(
                        section="experience",
                        role_id=role.role_id,
                        bullet_index=idx,
                        snippet=bullet,
                    )
                )

    return evidence


def _matches_direct(skill: str, text: str) -> bool:
    return _has_token(text, skill)


def _matches_partial(skill: str, text: str) -> bool:
    synonyms = _SYNONYMS.get(skill, [])
    return any(_has_token(text, variant) for variant in synonyms)


def _has_token(text: str, token: str) -> bool:
    if not token:
        return False
    pattern = r"(?<!\w)" + re.escape(token) + r"(?!\w)"
    return bool(re.search(pattern, text, re.IGNORECASE))


def find_skills_in_text(text: str) -> List[str]:
    found: List[str] = []
    lower = text.lower()
    for skill in _SKILL_DICTIONARY:
        if _has_token(text, skill):
            found.append(skill)
            continue
        synonyms = _SYNONYMS.get(skill.lower(), [])
        if any(_has_token(text, variant) for variant in synonyms):
            found.append(skill)

    caps = re.findall(r"\b[A-Z][A-Za-z0-9+.#-]{2,}\b", text)
    for token in caps:
        if any(token.lower() == skill.lower() for skill in _SKILL_DICTIONARY):
            found.append(token)

    return _dedupe_preserve(found)


def has_direct_evidence(state: ResumeState, skill: str) -> bool:
    token = skill.strip().lower()
    if not token:
        return False
    if any(_has_token(line, token) for line in state.sections.technical_skills):
        return True
    if any(_has_token(line, token) for line in state.sections.professional_summary.splitlines() if line.strip()):
        return True
    for role in state.sections.experience:
        if any(_has_token(bullet, token) for bullet in role.bullets):
            return True
    return False


def _must_have_gates(jd_text: str) -> List[str]:
    lower = jd_text.lower()
    hits = [kw for kw in _MUST_HAVE_DOMAINS if kw in lower]
    return _dedupe_preserve(hits)


def _dedupe_preserve(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in values:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _truncate_skills(required: List[str], preferred: List[str], limit: int) -> Tuple[List[str], List[str]]:
    if len(required) >= limit:
        return required[:limit], []
    remaining = limit - len(required)
    return required, preferred[:remaining]


def _count_covered(coverage: List[SkillCoverage], strict_mode: bool) -> float:
    total = 0.0
    for item in coverage:
        if item.status == "direct":
            total += 1.0
        elif item.status == "partial" and not strict_mode:
            total += 0.5
    return total
