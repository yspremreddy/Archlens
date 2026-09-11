# TODO

Current phase: **Phase 9 — Frontend + portfolio finish**. See
docs/ROADMAP.md for the full phased plan.

## Done (Phase 9 implementation — frontend + portfolio finish)
- [x] `frontend/` — React 18+/TypeScript/Vite app. Tab-based view
  switching (no React Router — no new major framework for a small SPA):
  Dashboard, Upload, Review, Search, Graph, Evaluation.
- [x] `app/main.py` — added `CORSMiddleware`, localhost:5173-only
  allowlist, no wildcard. The only backend change this phase made.
- [x] `frontend/src/api/` — hand-written TypeScript types mirroring the
  backend Pydantic schemas, and a `fetch`-based client with
  `AbortController` cancellation and typed errors (`ApiError`).
- [x] `frontend/src/hooks/useAsyncAction.ts` — shared loading/error/
  cancel state for every API-backed action; aborts a stale in-flight
  request before starting a new one.
- [x] Web Storage (`frontend/src/storage/preferences.ts`) — theme and
  preferred retrieval mode, `localStorage`, best-effort (never throws if
  storage is unavailable).
- [x] IndexedDB (`frontend/src/storage/cache.ts`) — raw `indexedDB` API,
  no wrapper library; caches recent search/answer/review results
  client-side, capped at 50 entries, pruned oldest-first.
- [x] Service Worker (`frontend/public/sw.js`) — hand-rolled, no
  `vite-plugin-pwa`; caches only this app's own static assets, never API
  responses, so findings/evidence are always live.
- [x] Accessibility: semantic landmarks, a skip link, `role="tablist"`/
  `role="tab"`/`aria-selected` navigation, labeled form controls,
  `aria-live` regions for async results, visible focus outlines.
- [x] Responsive CSS, hand-written (no framework), light/dark theme via
  CSS custom properties + a toggle persisted to `localStorage`.
- [x] Graph visualization (`frontend/src/components/GraphPathView.tsx`)
  — hand-rolled inline SVG, no charting library.
- [x] Evaluation dashboard (`frontend/src/views/EvaluationView.tsx`) —
  displays the backend evaluation suite's last-measured numbers,
  explicitly labeled as a historical snapshot (not live-recomputed on
  page view — engineering guideline 3, don't misrepresent a static number as
  live).
- [x] Tests: 9 Vitest + Testing Library tests (component, storage
  round-trips with `fake-indexeddb`, a mocked-fetch form-submission
  test), 3 Playwright E2E tests (UI-only smoke test + a live-backend
  smoke test that auto-skips if the backend isn't running).
- [x] `npm run lint` (oxlint) clean, `npm run build` (tsc + vite build)
  succeeds.
- [x] `app/tracing.py` — optional OpenTelemetry tracing, off by default
  (`OTEL_ENABLED=false`), OTLP export to a local collector (e.g. a free,
  local Arize Phoenix instance) when enabled. No behavior change when
  disabled — full 127-test backend suite re-verified passing after
  adding it.
- [x] `.github/workflows/ci.yml` — frontend job (lint, unit tests,
  build, UI-only E2E smoke test) and backend job (pytest against real
  Postgres+pgvector and Neo4j GitHub Actions service containers).
- [x] `README.md` — architecture diagram, setup (backend + frontend +
  optional tracing), demo flow, security summary, evaluation results
  (the real last-measured numbers, unchanged from Phase 8), test/build
  commands, known limitations.
- [x] End-to-end smoke test performed manually against a live backend:
  uploaded `data/samples/payment-service.md` via `curl`, confirmed
  `/review` returns a correct FAIL verdict with real citations, then
  confirmed the frontend (real browser, via Playwright) renders live
  `/search` results from that same running backend.
- [x] Full backend suite re-run after all Phase 9 backend changes: 127
  passed.

## Done (Phase 8 implementation — backend hardening)
- [x] Fixed the ADR-009 evidence-granularity limitation: `app/policy/engine.py`
  now scans sentence/bullet-level units, not whole chunks (ADR-010) —
  the `data-pipeline.md` multi-bullet chunk that used to produce a false
  CONFLICT now correctly produces FAIL, verified by both a unit test and
  the end-to-end `/review` test. No schema/API/retrieval changes.
- [x] Real public evaluation corpus (`data/samples/public/`, 4 files,
  ~1-2KB each) — Kubernetes Pod Security Standards (CC BY 4.0), NIST
  CSF Five Functions (public domain, US govt work), OWASP Top 10:2021
  A01 + A02 (CC BY 3.0) — every file's URL/license/retrieval-date
  recorded in its own header and in `SOURCES.md`. Existing synthetic
  dataset kept unchanged.
- [x] `app/evaluation/` — `metrics.py` (generic Recall@k/MRR/nDCG,
  binary relevance), `golden.py` (ground truth verified empirically
  before being written down, spanning both corpora), `baseline.py`
  (lexical-only "baseline RAG" vs. the real hybrid+rerank "ArchLens"
  path — not a reimplemented strawman)
- [x] `tests/test_evaluation.py` rewritten/extended (10 tests, real
  measured numbers, not fabricated): Recall@5=1.00, Recall@10=1.00,
  MRR=1.00, nDCG@5=1.00 over 8 golden retrieval cases; baseline
  (lexical-only) Recall@5=0.125 vs ArchLens (hybrid+rerank) Recall@5=1.00
  — a real, measured demonstration of Phases 2/4's value; finding
  correctness=1.00 and completeness=1.00 over 5 golden review cases;
  34/34 citations verified against real Postgres rows; groundedness
  mean=1.00; false-confidence rate=0.00 over 4 genuinely-unanswerable
  questions; `/review` latency ≈0.15s, `/answer` latency ≈1.5s (template
  provider, default config)
- [x] Two more real marker-scanning bugs found and fixed testing against
  the real public corpus (see ADR-011): "cannot" removed (too
  context-dependent, same issue as the earlier "never" removal); five
  generic negation-of-permission words added ("forbidden", "disallowed",
  "prohibited", "not allowed", "denied") since official docs phrase
  prohibitions differently than the synthetic corpus.
- [x] Strengthened `tests/test_security.py` (17 tests, 7 new): Cypher
  injection attempts against `graph_tool`'s component-name input (3
  payloads, parameterized queries verified safe), SQL injection attempts
  against `search_tool`'s query input (3 payloads, parameterized queries
  verified safe), and confirmation that a maliciously-named component
  bullet is never even parsed as a component (regex-level rejection, not
  runtime sanitization)
- [x] All 127 tests passing (10 new evaluation-related + 7 new security
  + 1 new policy regression test + 109 pre-existing), re-run 3× clean

## Explicitly not done yet (Phase 8 scope, superseded by Phase 9 above)
- ~~No frontend~~ — done in Phase 9. No cloud deployment (still out of
  scope — see README.md "Known limitations").

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

## Done (Phase 5 implementation — first GraphRAG milestone)
- [x] Neo4j Community Edition via Docker (`docker-compose.yml`), free,
  local, no license — verified `ollama`-style: real Bolt connectivity
  test before building on top of it
- [x] Graph schema (`app/graph/schema.py`) adapted from
  docs/ARCHITECTURE.md §5's original sketch, deviations documented in
  docs/DECISIONS.md ADR-007 (single `:Component` label with a `type`
  property, no `DataFlow` node, `TrustBoundary`/`ComplianceTag` reserved
  but unpopulated)
- [x] Rule-based (regex) extraction (`app/graph/extraction.py`) of
  components + relationships + ownership from the existing sample docs —
  verified against real output, caught and fixed two type-inference bugs
  (keyword false-positives from mentions of *other* components) before
  relying on it
- [x] Postgres migration `540fcff68f20` — widens
  `components.extraction_method` CHECK to add `'rule_based'`
- [x] `components` table actually populated for the first time (Phase 1
  shipped the columns; nothing wrote to them until now)
- [x] Provenance preserved both directions: Postgres `components` rows
  carry `source_document_id`/`source_chunk_id`; Neo4j nodes/relationships
  carry `pg_document_id`/`pg_chunk_id` (+ `pg_component_id` on nodes) —
  verified by test that a returned citation's chunk id/hash matches a
  real Postgres row, not a fabricated reference
- [x] Multi-hop graph retrieval (`app/graph/retrieval.py`) — bounded
  variable-length Cypher traversal, upstream/downstream/both, results
  returned as the same `Citation` shape `/search`/`/answer` use
  ("integrate graph results with the existing retrieval/evidence model")
- [x] `POST /documents/{id}/graph` (trigger extraction) and
  `POST /graph/query` (multi-hop query) endpoints
- [x] Idempotent extraction — re-running for the same document updates
  existing rows/nodes rather than duplicating, verified by test
- [x] Tests (`tests/test_graph.py`, 12 tests) — extraction correctness
  against real sample data, Postgres+Neo4j creation, idempotency,
  provenance cross-checks, multi-hop downstream AND upstream traversal
  (including the specific chain event-collector → event-bus → etl-worker
  → analytics-warehouse), max-hops bound, unknown-component handling,
  and confirmation that `/search`/`/answer` are unaffected. 56/56 tests
  passing overall.
- [x] `/search` and `/answer` (Phases 2-4) verified unchanged and still
  passing — graph extraction does not touch ingestion, retrieval, or
  generation code paths

## Known limitation (documented, not hidden)
- Local Neo4j has no separate test database (Community Edition's simple
  single-database setup) — `tests/test_graph.py` wipes the *entire*
  local graph before each test, which also clears dev graph data when
  the suite runs. Fine for local single-developer use; would need real
  test/dev separation before a shared or CI environment. See
  docs/DECISIONS.md ADR-007.

## Done (Phase 6 implementation — multimodal retrieval)
- [x] `app/multimodal/` package: `ocr.py` (RapidOCR/ONNX), `pdf.py`
  (pypdfium2 page rendering), `vision.py` (NoOp/Ollama vision provider,
  mirrors `app/generation/providers.py`'s pattern), `graph.py`
  (OCR-verified relationship parsing + graph upsert), `service.py`
  (ingestion orchestration)
- [x] Image (PNG/JPEG) and PDF-page ingestion via the existing
  `POST /documents` endpoint (dispatched by suffix, same upload surface
  as text)
- [x] OCR always on (no opt-in) — verified >95% confidence against the
  real diagram fixtures with correct text and pixel bounding boxes
- [x] Vision captioning optional, off by default (`VISION_PROVIDER=none`)
  — mirrors `LLM_PROVIDER=template`'s default-safe pattern exactly.
  Verified with a real `moondream` model pulled via Ollama (~1.7GB); see
  docs/DECISIONS.md ADR-008 for what worked (coherent captions) and what
  didn't (strict-format relationship lists degenerate into repetition)
- [x] Schema: `chunks.modality` + `chunks.bbox` (migration
  `cc8e51c1a598`) — multimodal chunks live in the *same* `chunks` table
  as prose, embedded with the *same* text model, so `/search`, `/answer`,
  hybrid retrieval, and reranking all work on diagram content with
  **zero retrieval/generation code changes** — verified directly
- [x] Visual evidence provenance — `bbox` (pixel region) + `page_number`
  for image-derived chunks, surfaced in `Citation` (same shape `/search`
  and `/answer` already use)
- [x] `modality` structured filter (`app/retrieval/filters.py`) —
  restrict search to `image_ocr`/`image_caption`/`text`
- [x] Diagram component/relationship extraction
  (`app/multimodal/graph.py`) reuses Phase 5's graph upsert helpers
  (promoted from private to shared) — Postgres `components` +
  Neo4j `:Component` nodes, `extraction_method='vision_extracted'`.
  Relationships are cross-checked against OCR-confirmed names before
  being trusted (filters vision-model hallucinations)
- [x] Synthetic diagram fixtures (`data/samples/diagrams/`) — two PNG
  architecture diagrams (generated with PIL, matching the existing text
  samples' architectures) plus a PDF rendering of one, for real
  (non-mocked) OCR/PDF tests
- [x] Tests (`tests/test_multimodal.py`, 19 tests) — real OCR against
  the fixtures, real PDF rendering, mocked vision-provider unit tests
  (same pattern as `OllamaProvider`'s), ingestion (image + PDF, with
  bbox/modality/embedding assertions), corrupt-file handling, retrieval
  integration (hybrid search + modality filter + `/answer` grounding),
  graph extraction from a diagram, and confirmation that text ingestion/
  `/answer` are unaffected. 75/75 tests passing overall.
- [x] `/search`, `/answer`, hybrid retrieval, reranking, and GraphRAG
  (Phases 2-5) verified unchanged and still passing

## Done (Phase 7 implementation — bounded agent + policy engine)
- [x] `app/agent/` — `tools.py` (read-only `search`/`graph` allowlist,
  both thin wrappers over existing retrieval/graph code), `controller.py`
  (deterministic bounded loop: always search first, query the graph only
  for relationship-intent questions naming a known component, capped by
  `agent_max_steps`/`agent_time_budget_seconds`)
- [x] `app/policy/` — `markers.py` (negation/affirmation phrase scanning),
  `engine.py` (PASS/FAIL/UNKNOWN/CONFLICT verdict + severity + confidence
  + recommendation), `service.py` (orchestrates agent → verdict →
  persisted `Finding`), `schemas.py`
- [x] `POST /review` — new endpoint; `/answer` (Phase 3) has zero lines
  changed, so its behavior is backward-compatible by construction
- [x] Migration `9fbf4e4d16c0` — adds nullable `findings.verdict` +
  `findings.severity` (existing rows/behavior unaffected)
- [x] Graph + multimodal evidence integrated into `/review`: the agent's
  `search` tool already retrieves multimodal chunks (Phase 6, same
  table) and its `graph` tool contributes Neo4j facts as synthetic
  evidence sentences — verified by test that a multi-hop question's
  `/review` response has both non-empty `citations` and non-empty
  `graph_paths`
- [x] Contradiction detection — CONFLICT is a first-class verdict when
  relevant evidence contains both a negation and an affirmation
- [x] Insufficient-evidence abstention — UNKNOWN when no evidence is
  retrieved or relevant, with confidence reflecting how far off-topic
  the evidence was
- [x] **Three real bugs found and fixed via actual testing against real
  data, not assumed correct** (engineering guideline 4) — see docs/DECISIONS.md
  ADR-009: bare "documented" falsely matched as an affirmation inside
  negation phrases like "no documented X"; "never" falsely matched as a
  negation inside good-practice statements like "never persisted or
  logged"; and marker scanning originally ran over *all* retrieved
  evidence regardless of source document, letting an unrelated
  document's negation contaminate unrelated verdicts. All three have
  regression tests in `tests/test_policy.py`.
- [x] Security tests (`tests/test_security.py`, 10 tests) — ingested
  prompt-injection text verified to never reach the system prompt (real
  ingested document, not just a benign case); a poisoned document's
  false claim still carries full, verifiable citation provenance;
  document-id filtering verified to prevent cross-document evidence
  leakage; agent tools verified read-only both by static source
  inspection (no write-operation substrings) and behaviorally (DB row
  counts unchanged after running the agent); tool registry verified as
  a closed 2-item allowlist; API schemas verified to expose no
  raw-tool-selection field
- [x] Compact evaluation suite (`tests/test_evaluation.py`, 8 tests,
  real measured numbers — not fabricated): retrieval precision@5 = 1.00
  (3/3 golden cases), groundedness = 1.0 on a grounded case, 11/11
  citations verified against real Postgres rows, multi-hop completeness
  2/2 (both text and graph evidence used), correct UNKNOWN abstention on
  an unrelated question and an empty corpus, `/review` latency ≈0.14s
  and `/answer` latency ≈0.36s (template provider, no real LLM — default
  config)
- [x] Bounded agent tests (`tests/test_agent.py`, 7 tests) — always
  searches first, only queries the graph for relationship-intent
  questions, respects both the step bound and the (mocked) time bound,
  caps graph tool calls regardless of how many components a question
  names, no duplicate evidence chunks
- [x] Policy engine tests (`tests/test_policy.py`, 17 tests) — marker
  scanning unit tests (including the 3 regression cases above), verdict
  engine unit tests (UNKNOWN/PASS/FAIL/CONFLICT), end-to-end `/review`
  tests against the real synthetic dataset, citation/provenance checks,
  structured filtering, and confirmation `/answer` is unchanged
- [x] All 117 tests passing (42 new + 75 pre-existing), re-run 3× clean

## Known limitation (documented, not hidden)
- Marker scanning happens at chunk granularity (~1000 chars, often
  2-3 unrelated bullet points together from Phase 1's chunker) — a
  question relevant to one bullet can still pick up an unrelated
  bullet's marker within the same chunk. Observed with a multi-hop
  graph question against a multi-bullet "Known gaps" chunk; the
  relevant test deliberately does not assert a specific verdict for
  that case. See docs/DECISIONS.md ADR-009.

## Next (not started — beyond current portfolio scope)
- [ ] Feed graph results into `/answer` itself (currently only `/review`
  combines text + graph + multimodal evidence)
- [ ] LLM-based (or otherwise more general) extraction for text
  documents that don't match the rule-based extractor's patterns
- [ ] `TrustBoundary` / `ComplianceTag` extraction, once source documents
  state them explicitly
- [ ] A larger/better local vision model, if/when reliable diagram
  relationship extraction becomes a real need — see docs/DECISIONS.md
  ADR-008
- [ ] Cloud deployment

## Explicitly not done yet (per current phase scope)
- No cloud deployment
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

(Per docs/ENGINEERING_GUIDELINES.md: implement only the requested phase, explain major
architectural changes before implementation.)
