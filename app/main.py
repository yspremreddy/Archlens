from fastapi import Depends, FastAPI, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.generation.providers import LLMProviderError
from app.generation.schemas import AnswerRequest, AnswerResponse
from app.generation.service import answer_question
from app.ingestion.service import ingest_document
from app.retrieval.schemas import SearchRequest, SearchResponse
from app.retrieval.service import search as run_search

app = FastAPI(title="ArchLens", version="0.1.0")

# Phase 1 accepts text-only uploads (markdown / plain text), per
# docs/ROADMAP.md Phase 1 scope. Anything else is rejected up front
# rather than silently mis-ingested.
ALLOWED_SUFFIXES = {".md", ".markdown", ".txt"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB — generous for text docs, not unbounded


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok}


@app.post("/documents")
async def upload_document(file: UploadFile, db: Session = Depends(get_db)) -> dict:
    filename = file.filename or ""
    suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type '{suffix}'; allowed: {sorted(ALLOWED_SUFFIXES)}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="empty file")

    document = ingest_document(
        db, filename=filename, content=content, mime_type=file.content_type
    )

    return {
        "id": str(document.id),
        "status": document.status,
        "original_filename": document.original_filename,
        "content_hash": document.content_hash,
        "error_message": document.error_message,
    }


@app.post("/search", response_model=SearchResponse)
def search_documents(request: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    return run_search(db, request)


@app.post("/answer", response_model=AnswerResponse)
def answer(request: AnswerRequest, db: Session = Depends(get_db)) -> AnswerResponse:
    try:
        return answer_question(db, request)
    except LLMProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
