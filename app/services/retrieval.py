import json
from pathlib import Path
import re
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


def _load_meta(meta_path: Path) -> list[dict]:
    metas = []
    with meta_path.open("r", encoding="utf-8") as f:
        for line in f:
            metas.append(json.loads(line))
    return metas


def _simple_keywords(text: str, limit: int = 20) -> list[str]:
    """Extract lightweight keywords from text for heuristics and fallback retrieval."""
    tokens = re.findall(r"[A-Za-z0-9+#.]+", text)
    keywords = [t.lower() for t in tokens if len(t) >= 3]
    seen = set()
    ordered = []
    for token in keywords:
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
        if len(ordered) >= limit:
            break
    return ordered


def _keywords_from_structured(jd: Optional[dict]) -> list[str]:
    """Build a keyword list from structured JD fields."""
    if not jd:
        return []
    values: list[str] = []
    for key in ["role", "domain", "seniority"]:
        val = jd.get(key)
        if val:
            values.append(val)
    for key in ["must_have_skills", "nice_to_have_skills", "responsibilities"]:
        values.extend(jd.get(key, []) or [])
    return [v.lower() for v in values if isinstance(v, str) and len(v) >= 3]


def _is_direct_support(text: str, keywords: list[str]) -> bool:
    """Return True when any JD keyword appears verbatim in the chunk text."""
    if not keywords:
        return False
    lower = text.lower()
    return any(keyword in lower for keyword in keywords)


def retrieve_topk(
    jd_text: str,
    index_dir: Path,
    embed_model_name: str,
    k: int = 25,
    multi_query: bool = False,
    structured_jd: Optional[dict] = None,
    per_query_k: int = 10,
) -> list[dict]:
    """Retrieve top-k chunks with optional multi-query retrieval and support tagging."""
    index_path = index_dir / "faiss.index"
    meta_path = index_dir / "meta.jsonl"

    index = faiss.read_index(str(index_path))
    metas = _load_meta(meta_path)

    model = SentenceTransformer(embed_model_name)

    keyword_pool = _keywords_from_structured(structured_jd)
    if not keyword_pool:
        keyword_pool = _simple_keywords(jd_text)

    if not multi_query:
        q_vec = model.encode([jd_text], convert_to_numpy=True, normalize_embeddings=True)
        q_vec = q_vec.astype(np.float32)
        scores, ids = index.search(q_vec, k)
        results: list[dict] = []
        for score, idx in zip(scores[0], ids[0]):
            if idx == -1:
                continue
            meta = metas[int(idx)]
            text = meta.get("text", "")
            results.append({
                "score": float(score),
                "resume_type": meta.get("resume_type", "unknown"),
                "source_file": meta.get("source_file", "unknown"),
                "text": text,
                "support_level": "direct" if _is_direct_support(text, keyword_pool) else "derived",
            })
        return results

    queries: list[str] = []
    if structured_jd:
        must = structured_jd.get("must_have_skills") or []
        if must:
            queries.append("Must have skills: " + ", ".join(must))
        responsibilities = structured_jd.get("responsibilities") or []
        if responsibilities:
            queries.append("Responsibilities: " + "; ".join(responsibilities))
        domain = structured_jd.get("domain")
        if domain:
            queries.append(f"Domain: {domain}")
    if not queries:
        keywords = _simple_keywords(jd_text)
        if keywords:
            queries = [
                "Must have skills: " + ", ".join(keywords[:8]),
                "Responsibilities: " + ", ".join(keywords[8:16]),
            ]
        else:
            queries = [jd_text]

    merged: dict[str, dict] = {}
    for query in queries:
        q_vec = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        q_vec = q_vec.astype(np.float32)
        scores, ids = index.search(q_vec, min(per_query_k, k))
        for score, idx in zip(scores[0], ids[0]):
            if idx == -1:
                continue
            meta = metas[int(idx)]
            text = meta.get("text", "")
            existing = merged.get(text)
            if existing and existing["score"] >= float(score):
                continue
            merged[text] = {
                "score": float(score),
                "resume_type": meta.get("resume_type", "unknown"),
                "source_file": meta.get("source_file", "unknown"),
                "text": text,
            }

    results = list(merged.values())
    results.sort(key=lambda item: item["score"], reverse=True)
    results = results[:k]
    for item in results:
        item["support_level"] = "direct" if _is_direct_support(item["text"], keyword_pool) else "derived"

    return results
