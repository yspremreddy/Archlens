"""Adapts app.retrieval.core.retrieve() to the /search API's pydantic
schemas. No generation happens here — see app/generation/ for Phase 3
retrieve->generate.
"""

from sqlalchemy.orm import Session

from app.retrieval.core import RetrievedResult, citation_for, retrieve
from app.retrieval.filters import filters_from_schema
from app.retrieval.schemas import SearchRequest, SearchResponse, SearchResultItem


def _to_result_item(result: RetrievedResult) -> SearchResultItem:
    return SearchResultItem(
        text=result.chunk.text,
        citation=citation_for(result.chunk),
        score=result.score,
        lexical_rank=result.lexical_rank,
        vector_rank=result.vector_rank,
        retrieval_methods=result.retrieval_methods,
    )


def search(db: Session, request: SearchRequest) -> SearchResponse:
    filters = filters_from_schema(request.filters)
    results = retrieve(db, request.query, top_k=request.top_k, mode=request.mode, filters=filters)
    return SearchResponse(
        query=request.query,
        mode=request.mode,
        result_count=len(results),
        results=[_to_result_item(r) for r in results],
    )
