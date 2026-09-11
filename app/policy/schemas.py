from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.graph.schemas import GraphPathOut
from app.retrieval.schemas import Citation, SearchFiltersIn

Verdict = Literal["PASS", "FAIL", "UNKNOWN", "CONFLICT"]
Severity = Literal["low", "medium", "high", "critical"]


class ReviewRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=8, ge=1, le=20)
    max_hops: int = Field(default=3, ge=1, le=6)
    max_steps: int = Field(default=4, ge=1, le=8)
    filters: SearchFiltersIn | None = None


class ReviewResponse(BaseModel):
    question: str
    verdict: Verdict
    severity: Severity
    confidence: float
    recommendation: str
    citations: list[Citation]
    graph_paths: list[GraphPathOut]
    agent_steps: int
    hit_step_bound: bool
    finding_id: UUID
