"""Structured/metadata filtering shared by lexical and vector retrieval.

Phase 2 filters operate on what Phase 1's schema actually has: documents
and their metadata. Filtering by component/tag/framework is not included
yet — `components` and `compliance_controls` aren't populated by anything
in Phase 1/2 (no extraction step exists), so a filter on them would have
nothing to filter against. Extending `SearchFilters` when that data
exists is additive, not a redesign.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select

from app.models import Chunk, Document


@dataclass(frozen=True)
class SearchFilters:
    document_id: UUID | None = None
    filename_contains: str | None = None
    uploaded_after: datetime | None = None
    uploaded_before: datetime | None = None


def filters_from_schema(filters_in) -> "SearchFilters | None":
    """Converts the pydantic `SearchFiltersIn` (app.retrieval.schemas) into
    the plain `SearchFilters` used internally. Takes a duck-typed object
    rather than importing the pydantic type directly, to avoid a schemas
    <-> filters import cycle; both /search and /answer share this.
    """
    if filters_in is None:
        return None
    return SearchFilters(
        document_id=filters_in.document_id,
        filename_contains=filters_in.filename_contains,
        uploaded_after=filters_in.uploaded_after,
        uploaded_before=filters_in.uploaded_before,
    )


def apply_filters(stmt: Select, filters: SearchFilters | None) -> Select:
    """Apply structured filters to a Select that already selects from Chunk
    joined to Document. Always restricts to successfully ingested
    documents — chunks only ever exist for those, but this stays explicit
    rather than relying on that invariant silently.
    """
    stmt = stmt.where(Document.status == "ingested")
    if filters is None:
        return stmt
    if filters.document_id is not None:
        stmt = stmt.where(Chunk.document_id == filters.document_id)
    if filters.filename_contains:
        stmt = stmt.where(Document.original_filename.ilike(f"%{filters.filename_contains}%"))
    if filters.uploaded_after is not None:
        stmt = stmt.where(Document.uploaded_at >= filters.uploaded_after)
    if filters.uploaded_before is not None:
        stmt = stmt.where(Document.uploaded_at <= filters.uploaded_before)
    return stmt
