"""Phase 5 (GraphRAG, first milestone) tests: graph creation, traversal,
provenance, and multi-hop queries.

Note on isolation: unlike Postgres (a dedicated `archlens_test` database,
truncated before every test — see conftest.py), this project's local
Neo4j does not have a separate test database (Community Edition's simple
single-database setup — see docs/DECISIONS.md ADR-007). The autouse
`_clean_graph` fixture below wipes the *entire* local graph before every
test in this file, so running this suite clears any dev graph data too.
Documented, not hidden — see TODO.md.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.graph.client import get_graph_session
from app.graph.extraction import ExtractedRelationship, extract
from app.graph.retrieval import find_paths
from app.models import Component


@pytest.fixture(autouse=True)
def _clean_graph():
    with get_graph_session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield


def _extract_all_samples(client: TestClient, ingested_samples: dict[str, str]) -> None:
    for document_id in ingested_samples.values():
        resp = client.post(f"/documents/{document_id}/graph")
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# extraction (pure unit tests, no DB/network — already covered against
# real sample data during development; these pin specific known facts)
# ---------------------------------------------------------------------------


def test_extraction_finds_the_known_multi_hop_chain_in_data_pipeline():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1] / "data" / "samples" / "data-pipeline.md"
    ).read_text(encoding="utf-8")
    result = extract(text)

    names = {c.name for c in result.components}
    assert names == {"event-collector", "event-bus", "etl-worker", "analytics-warehouse"}

    rels = set(result.relationships)
    assert ExtractedRelationship("event-collector", "event-bus", "SENDS_DATA_TO") in rels
    assert ExtractedRelationship("event-bus", "etl-worker", "SENDS_DATA_TO") in rels
    assert ExtractedRelationship("etl-worker", "analytics-warehouse", "SENDS_DATA_TO") in rels


# ---------------------------------------------------------------------------
# graph creation: Postgres components + Neo4j nodes, with provenance
# ---------------------------------------------------------------------------


def test_extraction_creates_postgres_components_with_provenance(
    client: TestClient, ingested_samples: dict[str, str], db_session
):
    document_id = ingested_samples["payment-service.md"]
    resp = client.post(f"/documents/{document_id}/graph")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["components_upserted"] == 4
    assert body["relationships_upserted"] == 2
    assert body["owner_linked"] is True

    components = (
        db_session.query(Component)
        .filter_by(source_document_id=uuid.UUID(document_id))
        .all()
    )
    assert len(components) == 4
    by_name = {c.name: c for c in components}

    assert by_name["payment-api"].type == "service"
    assert by_name["payment-db"].type == "datastore"
    assert by_name["settlement-queue"].type == "queue"
    for c in components:
        assert c.extraction_method == "rule_based"
        assert c.source_document_id == uuid.UUID(document_id)
        assert c.source_chunk_id is not None  # real provenance, not null

    # owner extracted and attached to the primary (first-listed) component
    assert by_name["payment-api"].owner == "Payments Platform"


def test_extraction_creates_neo4j_nodes_linked_to_postgres(
    client: TestClient, ingested_samples: dict[str, str], db_session
):
    document_id = ingested_samples["payment-service.md"]
    client.post(f"/documents/{document_id}/graph")

    pg_components = (
        db_session.query(Component).filter_by(source_document_id=uuid.UUID(document_id)).all()
    )
    pg_ids_by_name = {c.name: str(c.id) for c in pg_components}

    with get_graph_session() as session:
        records = list(
            session.run(
                "MATCH (c:Component) WHERE c.pg_document_id = $doc_id "
                "RETURN c.name AS name, c.pg_component_id AS pg_id, c.type AS type",
                doc_id=document_id,
            )
        )
    graph_by_name = {r["name"]: r for r in records}

    assert set(graph_by_name) == set(pg_ids_by_name)
    for name, pg_id in pg_ids_by_name.items():
        assert graph_by_name[name]["pg_id"] == pg_id  # graph node -> Postgres row, verified


def test_extraction_is_idempotent(
    client: TestClient, ingested_samples: dict[str, str], db_session
):
    document_id = ingested_samples["data-pipeline.md"]

    first = client.post(f"/documents/{document_id}/graph").json()
    second = client.post(f"/documents/{document_id}/graph").json()

    assert first["components_upserted"] == second["components_upserted"] == 4
    assert first["relationships_upserted"] == second["relationships_upserted"] == 4

    pg_count = (
        db_session.query(Component).filter_by(source_document_id=uuid.UUID(document_id)).count()
    )
    assert pg_count == 4  # not 8 — re-extraction updated, did not duplicate

    with get_graph_session() as session:
        node_count = session.run(
            "MATCH (c:Component) WHERE c.pg_document_id = $doc_id RETURN count(c) AS n",
            doc_id=document_id,
        ).single()["n"]
        rel_count = session.run(
            "MATCH (:Component)-[r]->(:Component) WHERE r.pg_document_id = $doc_id "
            "RETURN count(r) AS n",
            doc_id=document_id,
        ).single()["n"]
    assert node_count == 4
    assert rel_count == 4


def test_extraction_404s_for_unknown_document(client: TestClient):
    resp = client.post(f"/documents/{uuid.uuid4()}/graph")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# multi-hop traversal + provenance
# ---------------------------------------------------------------------------


def test_multi_hop_downstream_query_finds_the_full_chain(
    client: TestClient, ingested_samples: dict[str, str], db_session
):
    _extract_all_samples(client, ingested_samples)

    resp = client.post(
        "/graph/query",
        json={"component": "event-collector", "direction": "downstream", "max_hops": 3},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["component_found"] is True
    assert body["path_count"] > 0

    path_component_lists = [tuple(p["components"]) for p in body["paths"]]
    # the full 3-hop chain: event-collector -> event-bus -> etl-worker ->
    # analytics-warehouse must be among the returned paths.
    assert (
        "event-collector",
        "event-bus",
        "etl-worker",
        "analytics-warehouse",
    ) in path_component_lists

    # every hop on that path is a real 2-step traversal with 3 hops
    full_path = next(
        p
        for p in body["paths"]
        if tuple(p["components"])
        == ("event-collector", "event-bus", "etl-worker", "analytics-warehouse")
    )
    assert len(full_path["hops"]) == 3
    assert [h["relationship_type"] for h in full_path["hops"]] == [
        "SENDS_DATA_TO",
        "SENDS_DATA_TO",
        "SENDS_DATA_TO",
    ]


def test_multi_hop_upstream_query_reverses_direction(
    client: TestClient, ingested_samples: dict[str, str]
):
    _extract_all_samples(client, ingested_samples)

    resp = client.post(
        "/graph/query",
        json={"component": "analytics-warehouse", "direction": "upstream", "max_hops": 3},
    )
    body = resp.json()
    assert body["component_found"] is True
    path_component_lists = [tuple(p["components"]) for p in body["paths"]]
    assert ("analytics-warehouse", "etl-worker") in path_component_lists
    assert ("analytics-warehouse", "etl-worker", "event-bus") in path_component_lists


def test_graph_query_respects_max_hops_bound(
    client: TestClient, ingested_samples: dict[str, str]
):
    _extract_all_samples(client, ingested_samples)

    resp = client.post(
        "/graph/query",
        json={"component": "event-collector", "direction": "downstream", "max_hops": 1},
    )
    body = resp.json()
    for p in body["paths"]:
        assert len(p["hops"]) <= 1


def test_graph_query_unknown_component_returns_empty(
    client: TestClient, ingested_samples: dict[str, str]
):
    _extract_all_samples(client, ingested_samples)
    resp = client.post(
        "/graph/query", json={"component": "does-not-exist", "direction": "downstream"}
    )
    body = resp.json()
    assert body["component_found"] is False
    assert body["path_count"] == 0
    assert body["paths"] == []


def test_graph_hop_citation_matches_real_postgres_evidence(
    client: TestClient, ingested_samples: dict[str, str], db_session
):
    _extract_all_samples(client, ingested_samples)

    resp = client.post(
        "/graph/query",
        json={"component": "payment-api", "direction": "downstream", "max_hops": 2},
    )
    body = resp.json()
    assert body["path_count"] > 0
    hop = body["paths"][0]["hops"][0]
    citation = hop["citation"]
    assert citation is not None
    assert citation["document_filename"] == "payment-service.md"
    assert citation["chunk_content_hash"].startswith("sha256:")

    # cross-check: the cited chunk id genuinely exists in Postgres with a
    # matching content hash (not a fabricated/stale reference).
    from app.models import Chunk

    chunk = db_session.get(Chunk, uuid.UUID(citation["chunk_id"]))
    assert chunk is not None
    assert chunk.content_hash == citation["chunk_content_hash"]


def test_find_paths_rejects_invalid_direction(db_session):
    with pytest.raises(ValueError):
        find_paths(db_session, "payment-api", direction="sideways")


# ---------------------------------------------------------------------------
# existing retrieval/RAG behavior unaffected by graph extraction
# ---------------------------------------------------------------------------


def test_search_and_answer_still_work_after_graph_extraction(
    client: TestClient, ingested_samples: dict[str, str]
):
    _extract_all_samples(client, ingested_samples)

    search_resp = client.post(
        "/search", json={"query": "billing postal code", "top_k": 3, "mode": "hybrid"}
    )
    assert search_resp.status_code == 200
    assert search_resp.json()["result_count"] > 0

    answer_resp = client.post(
        "/answer",
        json={"question": "what happens to billing postal codes?", "top_k": 3, "mode": "hybrid"},
    )
    assert answer_resp.status_code == 200
    assert answer_resp.json()["retrieved_count"] > 0
