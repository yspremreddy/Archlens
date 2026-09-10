"""Phase 3 retrieve -> generate pipeline, now with Phase 4 reranking.

Reuses app.retrieval.core.retrieve() (the same logic /search uses) for
retrieval, optionally reranks the top candidates with a local
cross-encoder (app/retrieval/rerank.py, between retrieval and prompt
building — "after hybrid retrieval and before generation"), then: builds
a prompt with a strict system/user split (app/generation/prompts.py),
calls the configured LLM provider (app/generation/providers.py), scores
groundedness (app/generation/groundedness.py), and persists the answer
as a `Finding` with `FindingEvidence` rows citing every chunk shown to
the model —
"every chunk shown to the model" rather than parsing which bracket
numbers the model's answer actually used, since Phase 3 is single-shot
and unparsed citation-tracking would add complexity beyond what
"minimal groundedness evaluation" calls for; this is a documented
simplification, not silent under-citation (every fact the model *could*
have used is recorded as evidence).

Every stage logs a structured event (app/logging_config.py) so a request
can be reconstructed after the fact: what was retrieved, what the model
saw, how it scored, and what got persisted.
"""

import time

from sqlalchemy.orm import Session

from app.config import get_settings
from app.generation.groundedness import score_groundedness
from app.generation.providers import LLMProvider, LLMProviderError, get_llm_provider
from app.generation.prompts import SYSTEM_PROMPT, ContextItem, build_user_prompt
from app.generation.schemas import AnswerRequest, AnswerResponse
from app.logging_config import get_logger, log_event
from app.models import AuditLog, Finding, FindingEvidence
from app.retrieval.core import citation_for, retrieve
from app.retrieval.filters import filters_from_schema
from app.retrieval.rerank import rerank_results

logger = get_logger("generation")

MAX_FINDING_TITLE_LEN = 200


def answer_question(
    db: Session, request: AnswerRequest, *, provider: LLMProvider | None = None
) -> AnswerResponse:
    provider = provider or get_llm_provider()
    settings = get_settings()

    # When reranking is on, retrieve a larger candidate pool than the
    # caller's requested top_k — reranking needs candidates beyond top_k
    # to be able to promote a lower-ranked-but-more-relevant result into
    # the final top_k; asking retrieve() for exactly top_k would give the
    # reranker nothing to work with.
    candidate_k = (
        max(request.top_k, settings.rerank_candidate_pool)
        if settings.rerank_enabled
        else request.top_k
    )

    log_event(
        logger,
        "answer.retrieval.start",
        question=request.question,
        mode=request.mode,
        top_k=request.top_k,
        candidate_k=candidate_k,
    )
    t0 = time.monotonic()
    filters = filters_from_schema(request.filters)
    results = retrieve(db, request.question, top_k=candidate_k, mode=request.mode, filters=filters)
    retrieval_ms = (time.monotonic() - t0) * 1000
    log_event(
        logger,
        "answer.retrieval.completed",
        result_count=len(results),
        latency_ms=round(retrieval_ms, 1),
    )

    reranked = False
    if settings.rerank_enabled and results:
        log_event(
            logger,
            "answer.rerank.start",
            candidate_count=min(len(results), settings.rerank_candidate_pool),
        )
        t0 = time.monotonic()
        results = rerank_results(request.question, results, top_n=settings.rerank_candidate_pool)
        rerank_ms = (time.monotonic() - t0) * 1000
        reranked = True
        log_event(logger, "answer.rerank.completed", latency_ms=round(rerank_ms, 1))

    # Reranking (or a plain hybrid/lexical/vector retrieve() without it)
    # may have returned more candidates than requested — trim to top_k
    # now, after reranking has had the chance to reorder the full pool.
    results = results[: request.top_k]

    context_items = [
        ContextItem(
            index=i,
            source=r.chunk.document.original_filename,
            chunk_index=r.chunk.chunk_index,
            text=r.chunk.text,
        )
        for i, r in enumerate(results, start=1)
    ]
    user_prompt = build_user_prompt(request.question, context_items)

    log_event(logger, "answer.generation.start", provider=type(provider).__name__)
    t0 = time.monotonic()
    try:
        llm_result = provider.generate(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt)
    except LLMProviderError as exc:
        log_event(logger, "answer.generation.failed", error=str(exc))
        raise
    generation_ms = (time.monotonic() - t0) * 1000
    log_event(
        logger,
        "answer.generation.completed",
        provider=llm_result.provider,
        model=llm_result.model,
        latency_ms=round(generation_ms, 1),
        answer_length=len(llm_result.text),
    )

    cited_texts = [r.chunk.text for r in results]
    groundedness = score_groundedness(
        llm_result.text, cited_texts, min_score=settings.groundedness_min_score
    )
    log_event(
        logger,
        "answer.groundedness.evaluated",
        score=round(groundedness.score, 3),
        is_grounded=groundedness.is_grounded,
        is_abstention=groundedness.is_abstention,
    )

    finding = Finding(
        title=request.question[:MAX_FINDING_TITLE_LEN],
        statement=llm_result.text,
        status="open",
        confidence=round(groundedness.score, 2),
    )
    db.add(finding)
    db.flush()  # assign finding.id

    for rank, result in enumerate(results, start=1):
        note = f"retrieved via {request.mode} search"
        if reranked:
            note += ", reranked by cross-encoder"
        note += f", final rank {rank}"
        db.add(
            FindingEvidence(
                finding_id=finding.id,
                chunk_id=result.chunk.id,
                relevance_note=note,
            )
        )

    db.add(
        AuditLog(
            event_type="finding.created",
            entity_type="finding",
            entity_id=finding.id,
            detail={
                "question": request.question,
                "mode": request.mode,
                "reranked": reranked,
                "llm_provider": llm_result.provider,
                "llm_model": llm_result.model,
                "groundedness_score": round(groundedness.score, 3),
                "is_abstention": groundedness.is_abstention,
                "evidence_count": len(results),
            },
        )
    )
    db.commit()
    db.refresh(finding)
    log_event(
        logger, "answer.finding.persisted", finding_id=str(finding.id), evidence_count=len(results)
    )

    return AnswerResponse(
        question=request.question,
        answer=llm_result.text,
        mode=request.mode,
        llm_provider=llm_result.provider,
        llm_model=llm_result.model,
        citations=[citation_for(r.chunk) for r in results],
        groundedness_score=groundedness.score,
        is_grounded=groundedness.is_grounded,
        is_abstention=groundedness.is_abstention,
        finding_id=finding.id,
        retrieved_count=len(results),
    )
