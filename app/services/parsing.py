from pathlib import Path
import re

import pdfplumber
import docx

SUPPORTED = {".pdf", ".docx", ".txt"}


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".docx":
        d = docx.Document(str(path))
        return "\n".join(p.text for p in d.paragraphs)

    if suffix == ".pdf":
        parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts)

    raise ValueError(f"Unsupported file type: {suffix}")


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_resume(text: str, max_chars: int = 900) -> list[str]:
    """
    MVP chunking:
    - bullet lines become their own chunks
    - non-bullet text grouped into paragraphs up to max_chars
    """
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]

    bullet_re = re.compile(r"^(\-|\u2022|\*|\d+\.)\s+")
    chunks: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf.strip():
            chunks.append(buf.strip())
        buf = ""

    for ln in lines:
        is_bullet = bool(bullet_re.match(ln))
        if is_bullet:
            flush()
            chunks.append(ln)
        else:
            if len(buf) + len(ln) + 1 > max_chars:
                flush()
            buf = (buf + " " + ln).strip()

    flush()
    chunks = [c for c in chunks if len(c) >= 25]
    return chunks


def infer_resume_type(filename: str) -> str:
    name = filename.lower()
    if "python" in name:
        return "python_fullstack"
    if "java" in name:
        return "java_fullstack"
    if "dotnet" in name or ".net" in name:
        return "dotnet_fullstack"
    if "devops" in name:
        return "devops"
    if "data" in name:
        return "data_engineer"
    if "ml" in name or "ai" in name:
        return "ai_ml"
    return "general"
