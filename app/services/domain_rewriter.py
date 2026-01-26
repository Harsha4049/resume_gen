from typing import List, Optional, Dict
import re

from sentence_transformers import SentenceTransformer
import numpy as np


_DOMAIN_MAP = {
    "healthcare": [
        (r"\bsystems\b", "healthcare systems"),
        (r"\bworkflow(s)?\b", "clinical workflow\1"),
        (r"\bdata\b", "healthcare data"),
    ],
    "banking": [
        (r"\btransactions\b", "financial transactions"),
        (r"\bpayments\b", "payment flows"),
        (r"\baccounts\b", "financial accounts"),
    ],
    "fintech": [
        (r"\btransactions\b", "financial transactions"),
        (r"\bpayments\b", "payment flows"),
        (r"\baccounts\b", "financial accounts"),
    ],
    "retail": [
        (r"\busers\b", "customers"),
        (r"\borders\b", "customer orders"),
        (r"\bcheckout\b", "checkout experience"),
    ],
    "e-commerce": [
        (r"\busers\b", "customers"),
        (r"\borders\b", "customer orders"),
        (r"\bcheckout\b", "checkout experience"),
    ],
    "saas": [
        (r"\bplatform\b", "SaaS platform"),
        (r"\btenants\b", "SaaS tenants"),
        (r"\bsubscriptions\b", "subscription billing"),
    ],
    "platform": [
        (r"\bplatform\b", "platform"),
        (r"\btenants\b", "tenants"),
    ],
}

_DOMAIN_INDICATORS = {
    "healthcare": ["health", "clinical", "patient", "hospital", "medical"],
    "banking": ["bank", "financial", "transaction", "payment", "account"],
    "fintech": ["payment", "wallet", "financial"],
    "retail": ["order", "customer", "cart"],
    "e-commerce": ["order", "checkout", "cart"],
    "saas": ["tenant", "subscription", "platform"],
}


_COMPANY_TRIGGERS = {
    "startup": ["mvp", "prototype", "rapid", "iterat", "agile"],
    "enterprise": ["stakeholder", "cross-team", "governance", "sla"],
    "regulated": ["compliance", "audit", "policy", "risk"],
    "bigtech": ["scale", "distributed", "high traffic", "latency"],
}


def _apply_domain_terms(text: str, domain: str) -> str:
    """Apply conservative domain terminology substitutions to the given text."""
    replacements = _DOMAIN_MAP.get(domain, [])
    updated = text
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, updated, flags=re.IGNORECASE)
    return updated


def _has_domain_evidence(text: str, domain: str) -> bool:
    """Return True when the chunk already contains domain evidence."""
    indicators = _DOMAIN_INDICATORS.get(domain, [])
    lowered = text.lower()
    return any(term in lowered for term in indicators)


def _apply_company_framing(text: str, company_type: str) -> str:
    """Apply minimal company framing if the text already implies the context."""
    triggers = _COMPANY_TRIGGERS.get(company_type, [])
    lowered = text.lower()
    if not any(trigger in lowered for trigger in triggers):
        return text

    if company_type == "startup":
        return re.sub(r"\bagile\b", "agile (startup)", text, flags=re.IGNORECASE)
    if company_type == "enterprise":
        return re.sub(r"\bcross-team\b", "cross-team (enterprise)", text, flags=re.IGNORECASE)
    if company_type == "regulated":
        return re.sub(r"\bcompliance\b", "regulated compliance", text, flags=re.IGNORECASE)
    if company_type == "bigtech":
        return re.sub(r"\bscale\b", "large-scale", text, flags=re.IGNORECASE)
    return text


def rewrite_chunks(
    chunks: List[Dict],
    domain: Optional[str],
    company_type: Optional[str],
) -> List[Dict]:
    """Return chunks with conservative domain/company rewrites when possible."""
    if not domain and not company_type:
        return chunks

    rewritten = []
    normalized_domain = (domain or "").lower()
    for chunk in chunks:
        base_text = chunk.get("rewrite_text", chunk.get("text", ""))
        updated = base_text
        if normalized_domain and _has_domain_evidence(base_text, normalized_domain):
            updated = _apply_domain_terms(updated, normalized_domain)
        if company_type:
            updated = _apply_company_framing(updated, company_type)

        new_chunk = dict(chunk)
        if updated != base_text:
            new_chunk["rewrite_text"] = updated
        rewritten.append(new_chunk)

    return rewritten


def dedupe_chunks(
    chunks: List[Dict],
    embed_model_name: str,
    threshold: float = 0.9,
) -> List[Dict]:
    """Deduplicate semantically similar chunks using embedding similarity."""
    if not chunks:
        return chunks

    model = SentenceTransformer(embed_model_name)
    texts = [item.get("text", "") for item in chunks]
    embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)

    kept: List[Dict] = []
    kept_vecs: List[np.ndarray] = []
    for idx, item in enumerate(chunks):
        vector = embeddings[idx]
        if not kept_vecs:
            kept.append(item)
            kept_vecs.append(vector)
            continue

        sims = np.dot(np.stack(kept_vecs), vector)
        if np.max(sims) >= threshold:
            continue

        kept.append(item)
        kept_vecs.append(vector)

    return kept


def grade_skills(structured_jd: Optional[Dict], chunks: List[Dict]) -> Dict[str, List[str]]:
    """Grade skills into strong/working/exposure using frequency and support level."""
    if not structured_jd:
        return {
            "required": [],
            "important": [],
            "optional": [],
            "strong": [],
            "working": [],
            "exposure": [],
            "required_direct": [],
            "required_derived": [],
            "required_missing": [],
        }

    required = structured_jd.get("must_have_skills", []) or []
    important = structured_jd.get("nice_to_have_skills", []) or []
    optional: List[str] = []

    skill_candidates = required + important
    skill_candidates = [s for s in skill_candidates if isinstance(s, str) and s.strip()]
    if not skill_candidates:
        return {
            "required": required,
            "important": important,
            "optional": optional,
            "strong": [],
            "working": [],
            "exposure": [],
            "required_direct": [],
            "required_derived": [],
            "required_missing": required,
        }

    strong = []
    working = []
    exposure = []
    required_direct = []
    required_derived = []
    required_missing = []

    for skill in skill_candidates:
        token = skill.lower()
        total = 0
        direct_hits = 0
        for chunk in chunks:
            text = chunk.get("text", "").lower()
            if token in text:
                total += 1
                if chunk.get("support_level") == "direct":
                    direct_hits += 1

        if direct_hits >= 2 or (direct_hits == 1 and total >= 2):
            strong.append(skill)
        elif direct_hits == 1:
            working.append(skill)
        elif total >= 2:
            working.append(skill)
        elif total == 1:
            exposure.append(skill)

        if skill in required:
            if direct_hits >= 1:
                required_direct.append(skill)
            elif total >= 1:
                required_derived.append(skill)
            else:
                required_missing.append(skill)

    return {
        "required": required,
        "important": important,
        "optional": optional,
        "strong": strong,
        "working": working,
        "exposure": exposure,
        "required_direct": required_direct,
        "required_derived": required_derived,
        "required_missing": required_missing,
    }
