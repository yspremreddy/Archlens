"""Mode-dispatching retrieval core, shared by the /search API and the
Phase 3 retrieve->generate pipeline (app/generation/), so RAG generation
reuses the exact same retrieval logic rather than a second copy of it.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ingestion.embedding import embed_text
from app.models import Chunk
from app.retrieval.filters import SearchFilters
from app.retrieval.hybrid import hybrid_search
from app.retrieval.lexical import lexical_search
from app.retrieval.schemas import Citation
from app.retrieval.vector import vector_search

RetrievalMode = str  # "hybrid" | "lexical" | "vector" — see app.retrieval.schemas


@dataclass(frozen=True)
class RetrievedResult:
    chunk: Chunk
    score: float
    lexical_rank: int | None
    vector_rank: int | None
    retrieval_methods: list[str]


def citation_for(chunk: Chunk) -> Citation:
    """Shared by /search and /answer — every retrieval result, in either
    API, carries this same provenance shape (CLAUDE.md rule 7)."""
    return Citation(
        document_id=chunk.document_id,
        document_filename=chunk.document.original_filename,
        document_content_hash=chunk.document.content_hash,
        chunk_id=chunk.id,
        chunk_index=chunk.chunk_index,
        chunk_content_hash=chunk.content_hash,
        start_offset=chunk.start_offset,
        end_offset=chunk.end_offset,
        modality=chunk.modality,
        page_number=chunk.page_number,
        bbox=chunk.bbox,
        text=chunk.text,
    )


def retrieve(
    db: Session,
    query: str,
    *,
    top_k: int,
    mode: RetrievalMode = "hybrid",
    filters: SearchFilters | None = None,
) -> list[RetrievedResult]:
    if mode == "lexical":
        hits = lexical_search(db, query, limit=top_k, filters=filters)
        return [
            RetrievedResult(
                chunk=hit.chunk,
                score=hit.rank,
                lexical_rank=rank,
                vector_rank=None,
                retrieval_methods=["lexical"],
            )
            for rank, hit in enumerate(hits, start=1)
        ]

    if mode == "vector":
        query_embedding = embed_text(query)
        hits = vector_search(db, query_embedding, limit=top_k, filters=filters)
        return [
            RetrievedResult(
                chunk=hit.chunk,
                # Reported as similarity (1 - cosine distance): higher is
                # better, consistent with the other two modes.
                score=1.0 - hit.distance,
                lexical_rank=None,
                vector_rank=rank,
                retrieval_methods=["vector"],
            )
            for rank, hit in enumerate(hits, start=1)
        ]

    hits = hybrid_search(db, query, limit=top_k, filters=filters)
    return [
        RetrievedResult(
            chunk=hit.chunk,
            score=hit.rrf_score,
            lexical_rank=hit.lexical_rank,
            vector_rank=hit.vector_rank,
            retrieval_methods=[
                m
                for m, present in (
                    ("lexical", hit.lexical_rank is not None),
                    ("vector", hit.vector_rank is not None),
                )
                if present
            ],
        )
        for hit in hits
    ]
