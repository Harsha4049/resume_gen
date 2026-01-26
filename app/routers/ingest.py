from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import shutil

from app.models.schemas import IngestResponse
from app.services.indexing import build_and_save_index
from app.config import settings

router = APIRouter()


@router.post("/upload-resumes", response_model=IngestResponse)
async def upload_resumes(files: list[UploadFile] = File(...)) -> IngestResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    saved = []
    for f in files:
        suffix = Path(f.filename).suffix.lower()
        if suffix not in {".pdf", ".docx", ".txt"}:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {f.filename}")

        dest = settings.resumes_dir / Path(f.filename).name
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append(dest.name)

    try:
        indexed_chunks, saved_files = build_and_save_index(
            resumes_dir=settings.resumes_dir,
            index_dir=settings.index_dir,
            embed_model_name=settings.embed_model,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return IngestResponse(indexed_chunks=indexed_chunks, saved_files=saved_files)


@router.post("/reindex", response_model=IngestResponse)
def reindex() -> IngestResponse:
    try:
        indexed_chunks, saved_files = build_and_save_index(
            resumes_dir=settings.resumes_dir,
            index_dir=settings.index_dir,
            embed_model_name=settings.embed_model,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return IngestResponse(indexed_chunks=indexed_chunks, saved_files=saved_files)
