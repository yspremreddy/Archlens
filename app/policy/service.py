"""Architecture Review / Policy Engine service — orchestrates the
bounded agent (app/agent/controller.py) for evidence gathering across
text, graph, and multimodal sources (multimodal chunks need no special
handling here: they already live in the same `chunks` table as prose,
per docs/DECISIONS.md ADR-008, so the agent's search tool retrieves them
automatically), evaluates a PASS/FAIL/UNKNOWN/CONFLICT verdict
(app/policy/engine.py), and persists it as a `Finding` — a review
verdict IS a finding, just with the `verdict`/`severity` columns
(migration `9fbf4e4d16c0`) populated instead of left null.

This is a new, separate endpoint (`POST /review`) rather than a change
to `/answer` — `/answer` (app/generation/service.py) is untouched by
this phase, so its existing behavior and tests are unaffected
(backward compatibility by construction, not by careful patching).
"""

import time

from sqlalchemy.orm import Session

from app.agent.controller import run_agent
from app.config import get_settings
from app.graph.schemas import GraphHopOut, GraphPathOut
from app.logging_config import get_logger, log_event
from app.models import AuditLog, Finding, FindingEvidence
from app.policy.engine import evaluate
from app.policy.schemas import ReviewRequest, ReviewResponse
from app.retrieval.core import citation_for
from app.retrieval.filters import filters_from_schema

logger = get_logger("policy")

MAX_FINDING_TITLE_LEN = 200


def _graph_path_out(paths) -> list[GraphPathOut]:
    return [
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
    ]


def review_question(db: Session, request: ReviewRequest) -> ReviewResponse:
    settings = get_settings()
    filters = filters_from_schema(request.filters)

    log_event(logger, "review.agent.start", question=request.question)
    t0 = time.monotonic()
    agent_result = run_agent(
        db,
        request.question,
        top_k=request.top_k,
        max_hops=request.max_hops,
        max_steps=request.max_steps,
        filters=filters,
    )
    agent_ms = (time.monotonic() - t0) * 1000
    log_event(
        logger,
        "review.agent.completed",
        evidence_count=len(agent_result.evidence),
        graph_path_count=len(agent_result.graph_paths),
        steps=len(agent_result.steps),
        hit_step_bound=agent_result.hit_step_bound,
        hit_time_bound=agent_result.hit_time_bound,
        latency_ms=round(agent_ms, 1),
    )

    evidence_texts = [r.chunk.text for r in agent_result.evidence]
    # Graph facts are folded in as short synthetic sentences so a
    # question answerable only via the graph (e.g. an ownership/
    # dependency fact with no matching prose) isn't invisible to the
    # marker scan — the graph is evidence too, per "integrate graph +
    # multimodal evidence into the review pipeline."
    graph_texts = [
        f"{h.source_name} {h.relationship_type} {h.target_name}"
        for p in agent_result.graph_paths
        for h in p.hops
    ]

    verdict = evaluate(
        request.question,
        evidence_texts + graph_texts,
        min_relevance_overlap=settings.policy_min_relevance_overlap,
    )
    log_event(
        logger,
        "review.verdict.evaluated",
        verdict=verdict.verdict,
        severity=verdict.severity,
        confidence=verdict.confidence,
    )

    finding = Finding(
        title=request.question[:MAX_FINDING_TITLE_LEN],
        statement=verdict.recommendation,
        status="open",
        confidence=verdict.confidence,
        verdict=verdict.verdict,
        severity=verdict.severity,
    )
    db.add(finding)
    db.flush()

    for result in agent_result.evidence:
        db.add(
            FindingEvidence(
                finding_id=finding.id,
                chunk_id=result.chunk.id,
                relevance_note=f"agent evidence via {','.join(result.retrieval_methods)}",
            )
        )

    db.add(
        AuditLog(
            event_type="review.created",
            entity_type="finding",
            entity_id=finding.id,
            detail={
                "question": request.question,
                "verdict": verdict.verdict,
                "severity": verdict.severity,
                "confidence": verdict.confidence,
                "evidence_count": len(agent_result.evidence),
                "graph_path_count": len(agent_result.graph_paths),
                "agent_steps": len(agent_result.steps),
                "hit_step_bound": agent_result.hit_step_bound,
                "hit_time_bound": agent_result.hit_time_bound,
            },
        )
    )
    db.commit()
    db.refresh(finding)
    log_event(logger, "review.finding.persisted", finding_id=str(finding.id))

    return ReviewResponse(
        question=request.question,
        verdict=verdict.verdict,
        severity=verdict.severity,
        confidence=verdict.confidence,
        recommendation=verdict.recommendation,
        citations=[citation_for(r.chunk) for r in agent_result.evidence],
        graph_paths=_graph_path_out(agent_result.graph_paths),
        agent_steps=len(agent_result.steps),
        hit_step_bound=agent_result.hit_step_bound,
        finding_id=finding.id,
    )
