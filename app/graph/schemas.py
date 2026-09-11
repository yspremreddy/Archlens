from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.retrieval.schemas import Citation

GraphDirection = Literal["downstream", "upstream", "both"]


class GraphExtractResponse(BaseModel):
    document_id: UUID
    components_upserted: int
    relationships_upserted: int
    owner_linked: bool


class GraphQueryRequest(BaseModel):
    component: str = Field(min_length=1)
    direction: GraphDirection = "downstream"
    max_hops: int = Field(default=3, ge=1, le=10)


class GraphHopOut(BaseModel):
    source: str
    target: str
    relationship_type: str
    citation: Citation | None


class GraphPathOut(BaseModel):
    components: list[str]
    hops: list[GraphHopOut]


class GraphQueryResponse(BaseModel):
    component: str
    direction: GraphDirection
    max_hops: int
    component_found: bool
    path_count: int
    paths: list[GraphPathOut]
