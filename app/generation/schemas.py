from uuid import UUID

from pydantic import BaseModel, Field

from app.retrieval.schemas import Citation, RetrievalMode, SearchFiltersIn


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: RetrievalMode = "hybrid"
    filters: SearchFiltersIn | None = None


class AnswerResponse(BaseModel):
    question: str
    answer: str
    mode: RetrievalMode
    llm_provider: str
    llm_model: str
    citations: list[Citation]
    groundedness_score: float
    is_grounded: bool
    is_abstention: bool
    finding_id: UUID | None
    retrieved_count: int
