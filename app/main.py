import uuid

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.generation.providers import LLMProviderError
from app.generation.schemas import AnswerRequest, AnswerResponse
from app.generation.service import answer_question
from app.graph.retrieval import component_exists, find_paths
from app.graph.schemas import (
    GraphExtractResponse,
    GraphHopOut,
    GraphPathOut,
    GraphQueryRequest,
    GraphQueryResponse,
)
from app.graph.service import extract_graph_for_document
from app.ingestion.service import ingest_document
from app.models import Document
from app.multimodal.graph import extract_graph_for_visual_document
from app.multimodal.service import IMAGE_MIME_TYPES, PDF_MIME_TYPES, ingest_visual_document
from app.policy.schemas import ReviewRequest, ReviewResponse
from app.policy.service import review_question
from app.retrieval.schemas import SearchRequest, SearchResponse
from app.retrieval.service import search as run_search
from app.tracing import setup_tracing

app = FastAPI(title="ArchLens", version="0.1.0")
setup_tracing(app)  # no-op unless OTEL_ENABLED=true (see app/tracing.py)

# Phase 9: the frontend (Vite dev server) runs on a different origin than
# this API during local development. Only localhost dev-server ports are
# allowed; no wildcard, no production origin hardcoded here (CLAUDE.md
# rule 5 — nothing environment-specific/secret is embedded in source).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 1: text-only uploads (markdown / plain text). Phase 6 adds
# image/PDF diagram uploads (app/multimodal/) — a distinct suffix set,
# routed to a distinct ingestion pipeline, but through this same
# endpoint (one upload surface, dispatched by file type).
TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
VISUAL_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf"}
ALLOWED_SUFFIXES = TEXT_SUFFIXES | VISUAL_SUFFIXES
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB — generous for text docs, not unbounded
MAX_VISUAL_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MiB — diagrams/PDF pages are larger


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

    is_visual = suffix in VISUAL_SUFFIXES
    content = await file.read()
    max_bytes = MAX_VISUAL_UPLOAD_BYTES if is_visual else MAX_UPLOAD_BYTES
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="file too large")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="empty file")

    if is_visual:
        document = ingest_visual_document(
            db, filename=filename, content=content, mime_type=file.content_type
        )
    else:
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


@app.post("/documents/{document_id}/graph", response_model=GraphExtractResponse)
def extract_document_graph(
    document_id: uuid.UUID, db: Session = Depends(get_db)
) -> GraphExtractResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    if document.status != "ingested":
        raise HTTPException(
            status_code=409, detail=f"document is not ingested (status={document.status!r})"
        )
    is_visual = (
        document.mime_type in (PDF_MIME_TYPES | IMAGE_MIME_TYPES)
        or document.original_filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg"))
    )
    result = (
        extract_graph_for_visual_document(db, document)
        if is_visual
        else extract_graph_for_document(db, document)
    )
    return GraphExtractResponse(
        document_id=document.id,
        components_upserted=result.components_upserted,
        relationships_upserted=result.relationships_upserted,
        owner_linked=result.owner_linked,
    )


@app.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest, db: Session = Depends(get_db)) -> ReviewResponse:
    return review_question(db, request)


@app.post("/graph/query", response_model=GraphQueryResponse)
def query_graph(request: GraphQueryRequest, db: Session = Depends(get_db)) -> GraphQueryResponse:
    found = component_exists(request.component)
    paths = (
        find_paths(
            db, request.component, direction=request.direction, max_hops=request.max_hops
        )
        if found
        else []
    )
    return GraphQueryResponse(
        component=request.component,
        direction=request.direction,
        max_hops=request.max_hops,
        component_found=found,
        path_count=len(paths),
        paths=[
            GraphPathOut(
                components=p.component_names,
                hops=[
                    GraphHopOut(
                        source=h.source_name,
                        target=h.target_name,
                        relationship_type=h.relationship_type,
                        citation=h.citation,
                    )
                    for h in p.hops
                ],
            )
            for p in paths
        ],
    )
