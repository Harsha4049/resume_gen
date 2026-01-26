import json
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from app.services.parsing import (
    read_text,
    normalize,
    chunk_resume,
    infer_resume_type,
    SUPPORTED,
)


def build_and_save_index(
    resumes_dir: Path,
    index_dir: Path,
    embed_model_name: str,
) -> tuple[int, list[str]]:
    model = SentenceTransformer(embed_model_name)

    metas: list[dict] = []
    texts: list[str] = []
    saved_files: list[str] = []

    for path in sorted(resumes_dir.glob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        saved_files.append(path.name)

        raw = read_text(path)
        text = normalize(raw)
        chunks = chunk_resume(text)
        resume_type = infer_resume_type(path.name)

        for ch in chunks:
            metas.append({
                "source_file": path.name,
                "resume_type": resume_type,
                "text": ch,
            })
            texts.append(ch)

    if not texts:
        raise ValueError("No valid resume chunks found. Upload resumes first.")

    embs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    embs = embs.astype(np.float32)
    dim = embs.shape[1]

    index = faiss.IndexFlatIP(dim)
    index.add(embs)

    index_path = index_dir / "faiss.index"
    meta_path = index_dir / "meta.jsonl"

    faiss.write_index(index, str(index_path))
    with meta_path.open("w", encoding="utf-8") as f:
        for m in metas:
            f.write(json.dumps(m, ensure_ascii=True) + "\n")

    return len(metas), saved_files


def index_exists(index_dir: Path) -> bool:
    return (index_dir / "faiss.index").exists() and (index_dir / "meta.jsonl").exists()
