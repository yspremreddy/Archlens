# TODO

Current phase: **Phase 4 — Reranking**. See docs/ROADMAP.md for the full
phased plan.

## Done (Phase 1 implementation)
- [x] Decisions carried from Phase 0 (single-tenant MVP, custom control
  set, uploads-only, reuse `.venv`, Docker Postgres+pgvector)
- [x] Detailed Phase 1 schema designed — docs/SCHEMA.md
- [x] Embedding model/dimension chosen and documented:
  `sentence-transformers/all-MiniLM-L6-v2` (384-dim) via `fastembed` —
  see docs/SCHEMA.md §8
- [x] UUID approach chosen and documented: PostgreSQL's built-in
  `gen_random_uuid()`, no extension — see docs/SCHEMA.md §8
- [x] `docker-compose.yml` for local Postgres + pgvector
  (`pgvector/pgvector:pg16`)
- [x] `pyproject.toml` + dependencies installed into the existing `.venv`
  via `uv sync` (FastAPI, SQLAlchemy, psycopg, pgvector, alembic,
  fastembed, pytest — all open-source, no paid APIs, no API keys)
- [x] `.env.example` / `app/config.py` — environment-based configuration,
  no secrets committed
- [x] ORM models (`app/models.py`) mirroring docs/SCHEMA.md
- [x] Alembic migration (`alembic/versions/94683330bd76_initial_schema.py`)
  — creates the `vector` extension and all 7 tables/constraints/indexes;
  applied to the local dev database and verified against `\d`
- [x] FastAPI app (`app/main.py`): `GET /health` (checks DB
  connectivity), `POST /documents` (upload → ingest)
- [x] Ingestion foundation (`app/ingestion/`): chunking, local embedding,
  and a synchronous ingest-and-persist service with provenance
  (content hashes, audit_log entries) and untrusted-content handling
  (hash-derived storage filenames, no execution of ingested content)
- [x] Synthetic sample dataset — `data/samples/*.md` (3 fictional
  architecture docs with deliberate risk/compliance-relevant gaps, for
  future retrieval/findings testing)
- [x] Test suite (`tests/`) — health, ingestion round-trip (chunks +
  embeddings + provenance), file-type/size rejection, and schema
  constraint tests (CHECK constraints, uniqueness, cascade/restrict FK
  behavior). 12/12 passing against a dedicated `archlens_test` database.

## Done (Phase 2 implementation)
- [x] Lexical retrieval — PostgreSQL full-text search (`plainto_tsquery`
  / `ts_rank_cd`) over a functional GIN index (`app/retrieval/lexical.py`)
- [x] Vector retrieval — pgvector cosine distance over an HNSW index
  (`app/retrieval/vector.py`)
- [x] Hybrid fusion — Reciprocal Rank Fusion, k=60
  (`app/retrieval/hybrid.py`)
- [x] Structured/metadata filtering — document id, filename substring,
  upload date range (`app/retrieval/filters.py`)
- [x] `POST /search` — cited, ranked results API (`app/main.py`,
  `app/retrieval/schemas.py`, `app/retrieval/service.py`); every result
  carries full provenance (document + chunk id, both content hashes,
  offsets)
- [x] Migration `e3034b9b35ac_phase_2_retrieval_indexes` — adds
  `idx_chunks_text_fts` (GIN) and `idx_chunks_embedding_hnsw` (HNSW),
  applied and verified against `\d chunks`
- [x] Retrieval tests (`tests/test_retrieval.py`) against the existing
  synthetic dataset — lexical exact-match, vector semantic-match,
  hybrid multi-document fusion, structured filters, top_k, empty-corpus
  and empty-query edge cases. 22/22 tests passing overall.

## Done (Phase 3 implementation)
- [x] LLM provider abstraction (`app/generation/providers.py`):
  `TemplateExtractiveProvider` (default — zero-dependency, deterministic,
  quotes the top retrieved chunk) and `OllamaProvider` (real local LLM
  via a locally-running Ollama server). Both local/free, no API key, no
  paid API. Selected via `LLM_PROVIDER` env var.
- [x] Retrieve → generate pipeline (`app/generation/service.py`) reusing
  `app.retrieval.core.retrieve()` — the exact logic `/search` uses, not
  a second copy of it
- [x] Grounded answers with citations — every `/answer` response carries
  a `Citation` per retrieved chunk (same shape as `/search`)
- [x] Strict system/user separation (`app/generation/prompts.py`):
  `SYSTEM_PROMPT` is a fixed constant, never built with interpolated
  content; all retrieved/question content goes only into the user
  prompt, explicitly labeled as untrusted data with an instruction to
  ignore embedded commands. Verified by a test that inspects the exact
  strings passed to the LLM provider.
- [x] Persisted findings + provenance — each answer creates a `Finding`
  (statement = answer text, confidence = groundedness score) and one
  `FindingEvidence` row per chunk shown to the model, plus an
  `AuditLog` entry
- [x] Minimal groundedness evaluation (`app/generation/groundedness.py`)
  — lexical-overlap heuristic against cited chunk text; documented as a
  heuristic, not a real entailment/NLI check
- [x] Structured pipeline logging (`app/logging_config.py`) — JSON events
  for each stage (retrieval, generation, groundedness, persistence),
  verified against real server output
- [x] `POST /answer` endpoint (`app/main.py`)
- [x] Tests (`tests/test_generation.py`) — groundedness unit tests,
  provider unit tests (template + mocked Ollama, no real network), the
  system/user separation invariant, and end-to-end pipeline tests
  (grounded answer + persistence, empty-corpus abstention, structured
  filters, validation). 35/35 tests passing overall.

## Done (Phase 4 implementation)
- [x] Local cross-encoder reranker (`app/retrieval/rerank.py`) —
  `Xenova/ms-marco-MiniLM-L-6-v2` via fastembed/ONNX, same local/free
  approach as the embedding model. Modular: depends only on
  `RetrievedResult` (app/retrieval/core.py), not on hybrid retrieval or
  generation specifically.
- [x] Wired into the generation pipeline only (`app/generation/service.py`),
  between retrieval and prompt-building, per "after hybrid retrieval and
  before generation." `/search` (Phase 2) is unchanged.
- [x] Reranks only the top `RERANK_CANDIDATE_POOL` (default 20)
  candidates, not the full retrieved set or corpus — bounded, configurable
  cost.
- [x] Citation/provenance preserved — reranking only replaces `.score`
  and reorders; the underlying `Chunk` (and every citation field derived
  from it) is untouched. Verified by test.
- [x] Both `TemplateExtractiveProvider` and `OllamaProvider` unchanged —
  reranking sits entirely upstream of generation.
- [x] Structured logging extended with `answer.rerank.start` /
  `answer.rerank.completed` events (latency, candidate count).
- [x] Tests (`tests/test_rerank.py`) — unit tests (relevance ordering,
  citation preservation, top-N boundary, empty/single-result no-ops) and
  an evaluation test comparing real hybrid retrieval before vs after
  reranking against the synthetic dataset, verified empirically (not
  assumed) to correct a real hybrid misranking. 44/44 tests passing
  overall.

## Next (Phase 5+ — not started)
- [ ] GraphRAG / Neo4j, multimodal retrieval, bounded agentic reasoning —
  see docs/ROADMAP.md. Explicitly out of scope for Phase 4.

## Explicitly not done yet (per current phase scope)
- No GraphRAG / Neo4j
- No multimodal ingestion or retrieval
- No agentic reasoning
- No frontend
- No auth (endpoints are unauthenticated; `uploaded_by`/`actor`/
  `created_by` fields are stubs, per docs/SCHEMA.md)
- No real entailment-based groundedness check (lexical-overlap heuristic
  only — see app/generation/groundedness.py)
- Ollama 0.34.0 + `llama3.2:1b` are installed and verified working on
  this dev machine (confirmed via real `/answer` calls), but the
  automated test suite still exercises `OllamaProvider` only via a
  mocked HTTP layer, not a live model — `.env`'s `LLM_PROVIDER` stays
  `template` so tests remain deterministic and network-independent.
  Switch to `ollama` locally to use the real model.

(Per CLAUDE.md: implement only the requested phase, explain major
architectural changes before implementation.)
