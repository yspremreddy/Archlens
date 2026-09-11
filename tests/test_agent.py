"""Phase 7 bounded agentic reasoning tests.

Verifies the controller (app/agent/controller.py): it always searches
first, only queries the graph when the question reads as a
relationship/dependency question, and never exceeds its step or time
budget — returning whatever evidence it has gathered so far when a
bound is hit (docs/ARCHITECTURE.md "Bounded agentic reasoning").
"""

import uuid

from app.agent.controller import run_agent
from app.models import Component


def _extract_graph_for_all(client, ingested_samples):
    for document_id in ingested_samples.values():
        resp = client.post(f"/documents/{document_id}/graph")
        assert resp.status_code == 200, resp.text


def test_agent_always_searches_first(db_session, ingested_samples):
    result = run_agent(db_session, "what happens to billing postal codes?")
    assert len(result.steps) >= 1
    assert result.steps[0].tool == "search"
    assert len(result.evidence) > 0


def test_agent_no_graph_call_without_relationship_intent(db_session, ingested_samples):
    result = run_agent(db_session, "what happens to billing postal codes?")
    assert all(step.tool != "graph" for step in result.steps)
    assert result.graph_paths == []


def test_agent_queries_graph_for_relationship_questions(
    client, db_session, ingested_samples
):
    _extract_graph_for_all(client, ingested_samples)
    result = run_agent(
        db_session, "what does event-collector send data to downstream?", max_hops=3
    )
    tool_names = [s.tool for s in result.steps]
    assert "graph" in tool_names
    assert len(result.graph_paths) > 0
    # the known 3-hop chain from Phase 5's tests should be reachable
    chains = [tuple(p.component_names) for p in result.graph_paths]
    assert any("analytics-warehouse" in c for c in chains)


def test_agent_respects_max_steps_bound(client, db_session, ingested_samples):
    _extract_graph_for_all(client, ingested_samples)
    # a question naming two components, forcing (without a bound) two
    # separate graph tool calls
    question = "how does payment-api connect to settlement-queue and does auth-api depend on email-service?"
    result = run_agent(db_session, question, max_steps=1)
    assert len(result.steps) <= 1
    assert result.hit_step_bound is True


def test_agent_respects_time_bound(db_session, ingested_samples):
    result = run_agent(db_session, "what happens to billing postal codes?", time_budget_seconds=0.0)
    assert result.hit_time_bound is True
    # still returns the first step's evidence rather than nothing at all
    assert len(result.steps) == 1


def test_agent_graph_calls_are_bounded_even_with_many_mentioned_components(
    client, db_session, ingested_samples
):
    _extract_graph_for_all(client, ingested_samples)
    # sanity: several components exist across the 3 ingested docs
    component_rows = db_session.query(Component).all()
    assert len(component_rows) >= 8

    # a question that could name many components — the controller caps
    # graph tool calls at _MAX_GRAPH_CANDIDATES regardless.
    names = [c.name for c in component_rows]
    question = "how do " + " and ".join(names) + " depend on each other?"
    result = run_agent(db_session, question, max_steps=10, time_budget_seconds=30)
    graph_steps = [s for s in result.steps if s.tool == "graph"]
    assert len(graph_steps) <= 2  # _MAX_GRAPH_CANDIDATES in app/agent/controller.py


def test_agent_result_evidence_has_no_duplicate_chunks(db_session, ingested_samples):
    result = run_agent(db_session, "what happens to billing postal codes?", top_k=10)
    chunk_ids = [r.chunk.id for r in result.evidence]
    assert len(chunk_ids) == len(set(chunk_ids))
