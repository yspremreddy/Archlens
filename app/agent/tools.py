"""Read-only tools available to the bounded agent
(app/agent/controller.py).

Every tool here only SELECTs — no tool in this registry writes to
Postgres or Neo4j (engineering guideline 6/ARCHITECTURE.md §6: agent tools are
read-only). The final review verdict is persisted exactly once, after
the agent loop ends, by app/policy/service.py — outside the tool-calling
loop itself, so a bug in step control can never accidentally cause
runaway writes.

Both tools are thin wrappers over already-existing, already-tested
modules (app.retrieval.core.retrieve, app.graph.retrieval) — the agent
does not reimplement retrieval or graph traversal, it only sequences
calls to them.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.graph.retrieval import GraphPath, component_exists, find_paths
from app.retrieval.core import RetrievedResult, retrieve
from app.retrieval.filters import SearchFilters


@dataclass(frozen=True)
class SearchToolResult:
    results: list[RetrievedResult]


@dataclass(frozen=True)
class GraphToolResult:
    component: str
    found: bool
    paths: list[GraphPath]


def search_tool(
    db: Session, query: str, *, top_k: int = 8, filters: SearchFilters | None = None
) -> SearchToolResult:
    """Hybrid retrieval (app.retrieval.core.retrieve) — read-only."""
    return SearchToolResult(results=retrieve(db, query, top_k=top_k, mode="hybrid", filters=filters))


def graph_tool(
    db: Session, component: str, *, direction: str = "downstream", max_hops: int = 3
) -> GraphToolResult:
    """Bounded multi-hop graph traversal (app.graph.retrieval) — read-only."""
    found = component_exists(component)
    paths = find_paths(db, component, direction=direction, max_hops=max_hops) if found else []
    return GraphToolResult(component=component, found=found, paths=paths)


# The allowlist: the agent controller only ever calls tools listed here
# by name — this dict is the single point that would need to change to
# add a new capability, making "what can the agent do" auditable at a
# glance. No tool that mutates state may be added to this registry
# without also updating docs/ARCHITECTURE.md §6 (security model) and
# tests/test_security.py's read-only assertions.
TOOL_REGISTRY = {
    "search": search_tool,
    "graph": graph_tool,
}
