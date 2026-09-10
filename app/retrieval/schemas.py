from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

RetrievalMode = Literal["hybrid", "lexical", "vector"]


class SearchFiltersIn(BaseModel):
    document_id: UUID | None = None
    filename_contains: str | None = None
    uploaded_after: datetime | None = None
    uploaded_before: datetime | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    mode: RetrievalMode = "hybrid"
    filters: SearchFiltersIn | None = None


class Citation(BaseModel):
    """Provenance for a single result — enough for a caller to verify the
    claim independently, per CLAUDE.md rule 7 (preserve evidence/
    provenance). No generation happens in Phase 2; this is what a later
    generation step (Phase 3) would cite.
    """

    document_id: UUID
    document_filename: str
    document_content_hash: str
    chunk_id: UUID
    chunk_index: int
    chunk_content_hash: str
    start_offset: int | None
    end_offset: int | None


class SearchResultItem(BaseModel):
    text: str
    citation: Citation
    score: float
    lexical_rank: int | None = None
    vector_rank: int | None = None
    retrieval_methods: list[str]


class SearchResponse(BaseModel):
    query: str
    mode: RetrievalMode
    result_count: int
    results: list[SearchResultItem]
