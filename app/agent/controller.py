"""Bounded agentic reasoning: a small, deterministic controller that
calls read-only tools (app/agent/tools.py) for multi-hop questions,
under a hard step budget and wall-clock budget — never an open-ended
loop (docs/ARCHITECTURE.md "Bounded agentic reasoning").

Deliberately NOT LLM-driven planning. Earlier phases (docs/DECISIONS.md
ADR-005, ADR-008) found the local models practical on this machine
unreliable for structured, must-follow-exactly instructions (a compound
vision prompt degenerated into a repetition loop; a small text model
sometimes ignores explicit formatting instructions). The "planning"
decisions this controller makes are simple and few — should the graph
also be queried? should a newly-discovered component be searched next?
— so a small set of deterministic rules is more reliable than delegating
them to a small local LLM, and is fully inspectable/testable (docs/ENGINEERING_GUIDELINES.md
rule 3: a rule either fires or it doesn't, no hallucinated plan). An LLM
(if configured) is only used elsewhere, for final free-text answer
synthesis (app/generation/) — never for step-by-step planning here.

On hitting either bound, the controller returns whatever evidence it has
gathered so far rather than raising or continuing — a deterministic
fallback, per docs/ARCHITECTURE.md's bounded-reasoning principle.
"""

import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tools import graph_tool, search_tool
from app.graph.retrieval import GraphPath
from app.logging_config import get_logger, log_event
from app.models import Component
from app.retrieval.core import RetrievedResult
from app.retrieval.filters import SearchFilters

logger = get_logger("agent")

_RELATIONSHIP_INTENT_RE = re.compile(
    r"\b(depend|downstream|upstream|connect|flow|relies?\s+on|sends?\s+data|"
    r"receives?\s+data|calls|integrat)\w*",
    re.IGNORECASE,
)
_MAX_GRAPH_CANDIDATES = 2  # bounded: at most this many graph tool calls per run


@dataclass(frozen=True)
class AgentStep:
    tool: str
    input: str
    result_count: int


@dataclass(frozen=True)
class AgentResult:
    evidence: list[RetrievedResult]
    graph_paths: list[GraphPath]
    steps: list[AgentStep]
    hit_step_bound: bool
    hit_time_bound: bool


def _has_relationship_intent(question: str) -> bool:
    return bool(_RELATIONSHIP_INTENT_RE.search(question))


def _mentioned_component_names(question: str, known_names: list[str]) -> list[str]:
    q_lower = question.lower()
    return [name for name in known_names if name.lower() in q_lower]


def run_agent(
    db: Session,
    question: str,
    *,
    top_k: int = 8,
    max_hops: int = 3,
    max_steps: int = 4,
    time_budget_seconds: float = 20.0,
    filters: SearchFilters | None = None,
) -> AgentResult:
    start = time.monotonic()
    steps: list[AgentStep] = []
    evidence: list[RetrievedResult] = []
    graph_paths: list[GraphPath] = []
    seen_chunk_ids: set = set()

    def time_left() -> bool:
        return (time.monotonic() - start) < time_budget_seconds

    def bounds_hit() -> tuple[bool, bool]:
        return len(steps) >= max_steps, not time_left()

    # Step 1: always search (read-only, bounded top_k) — every review
    # question gets at least text/multimodal evidence.
    log_event(logger, "agent.step.start", step=1, tool="search", input=question)
    search_result = search_tool(db, question, top_k=top_k, filters=filters)
    for r in search_result.results:
        if r.chunk.id not in seen_chunk_ids:
            evidence.append(r)
            seen_chunk_ids.add(r.chunk.id)
    steps.append(AgentStep(tool="search", input=question, result_count=len(search_result.results)))
    log_event(logger, "agent.step.completed", step=1, result_count=len(search_result.results))

    hit_step_bound, hit_time_bound = bounds_hit()
    if hit_step_bound or hit_time_bound:
        return AgentResult(evidence, graph_paths, steps, hit_step_bound, hit_time_bound)

    # Step 2+: only if the question reads as a relationship/dependency
    # question, look up known component names (populated by Phase 5/6
    # graph extraction) mentioned in the question and traverse the graph
    # for each — bounded to _MAX_GRAPH_CANDIDATES calls regardless of how
    # many names match.
    if _has_relationship_intent(question):
        known_names = [row[0] for row in db.execute(select(Component.name).distinct()).all()]
        candidates = _mentioned_component_names(question, known_names)[:_MAX_GRAPH_CANDIDATES]
        for name in candidates:
            hit_step_bound, hit_time_bound = bounds_hit()
            if hit_step_bound or hit_time_bound:
                break
            log_event(logger, "agent.step.start", step=len(steps) + 1, tool="graph", input=name)
            graph_result = graph_tool(db, name, direction="both", max_hops=max_hops)
            graph_paths.extend(graph_result.paths)
            steps.append(AgentStep(tool="graph", input=name, result_count=len(graph_result.paths)))
            log_event(
                logger,
                "agent.step.completed",
                step=len(steps),
                tool="graph",
                result_count=len(graph_result.paths),
            )

    hit_step_bound, hit_time_bound = bounds_hit()
    return AgentResult(evidence, graph_paths, steps, hit_step_bound, hit_time_bound)
