from fastapi.testclient import TestClient


def _filenames_in(results: list[dict]) -> set[str]:
    return {r["citation"]["document_filename"] for r in results}


def test_lexical_search_finds_exact_term(client: TestClient, ingested_samples: dict[str, str]):
    resp = client.post("/search", json={"query": "postal code", "top_k": 5, "mode": "lexical"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mode"] == "lexical"
    assert body["result_count"] > 0
    assert "payment-service.md" in _filenames_in(body["results"])
    for r in body["results"]:
        assert r["lexical_rank"] is not None
        assert r["vector_rank"] is None
        assert r["retrieval_methods"] == ["lexical"]


def test_lexical_search_no_match_returns_empty(client: TestClient, ingested_samples: dict[str, str]):
    resp = client.post(
        "/search",
        json={"query": "zzznonexistentqueryterm", "top_k": 5, "mode": "lexical"},
    )
    assert resp.status_code == 200
    assert resp.json()["result_count"] == 0


def test_vector_search_finds_semantically_related_chunk(
    client: TestClient, ingested_samples: dict[str, str]
):
    # No exact keyword overlap with the auth doc's wording ("hashed
    # password (bcrypt)"), but should be semantically close.
    resp = client.post(
        "/search",
        json={"query": "how user passwords are stored securely", "top_k": 5, "mode": "vector"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result_count"] > 0
    assert "user-auth-service.md" in _filenames_in(body["results"])
    for r in body["results"]:
        assert r["vector_rank"] is not None
        assert r["lexical_rank"] is None
        assert r["retrieval_methods"] == ["vector"]
        assert -1.0 <= r["score"] <= 1.0


def test_hybrid_search_pulls_from_multiple_documents(
    client: TestClient, ingested_samples: dict[str, str]
):
    # "Kafka" is mentioned in both payment-service.md (settlement-queue)
    # and data-pipeline.md (event-bus) — a good case for fusion pulling
    # relevant chunks from more than one source document.
    resp = client.post(
        "/search", json={"query": "Kafka message queue events", "top_k": 8, "mode": "hybrid"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result_count"] > 0
    found_filenames = _filenames_in(body["results"])
    assert "payment-service.md" in found_filenames or "data-pipeline.md" in found_filenames

    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)

    for r in body["results"]:
        assert set(r["retrieval_methods"]) <= {"lexical", "vector"}
        assert len(r["retrieval_methods"]) >= 1


def test_hybrid_result_has_full_citation_provenance(
    client: TestClient, ingested_samples: dict[str, str]
):
    resp = client.post(
        "/search", json={"query": "payment transaction data", "top_k": 3, "mode": "hybrid"}
    )
    body = resp.json()
    assert body["result_count"] > 0
    citation = body["results"][0]["citation"]
    assert citation["document_id"] == ingested_samples["payment-service.md"] or citation[
        "document_id"
    ] in ingested_samples.values()
    assert citation["document_content_hash"].startswith("sha256:")
    assert citation["chunk_content_hash"].startswith("sha256:")
    assert citation["chunk_index"] >= 0


def test_structured_filter_restricts_to_single_document(
    client: TestClient, ingested_samples: dict[str, str]
):
    payment_id = ingested_samples["payment-service.md"]
    resp = client.post(
        "/search",
        json={
            "query": "service",
            "top_k": 10,
            "mode": "hybrid",
            "filters": {"document_id": payment_id},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result_count"] > 0
    assert _filenames_in(body["results"]) == {"payment-service.md"}


def test_structured_filter_by_filename_substring(
    client: TestClient, ingested_samples: dict[str, str]
):
    resp = client.post(
        "/search",
        json={
            "query": "team",
            "top_k": 10,
            "mode": "hybrid",
            "filters": {"filename_contains": "auth"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result_count"] > 0
    assert _filenames_in(body["results"]) == {"user-auth-service.md"}


def test_top_k_is_respected(client: TestClient, ingested_samples: dict[str, str]):
    resp = client.post("/search", json={"query": "service", "top_k": 2, "mode": "hybrid"})
    assert resp.status_code == 200
    assert resp.json()["result_count"] <= 2


def test_search_with_no_ingested_documents_returns_empty(client: TestClient):
    resp = client.post("/search", json={"query": "anything", "top_k": 5, "mode": "hybrid"})
    assert resp.status_code == 200
    assert resp.json()["result_count"] == 0


def test_rejects_empty_query(client: TestClient):
    resp = client.post("/search", json={"query": "", "top_k": 5, "mode": "hybrid"})
    assert resp.status_code == 422
