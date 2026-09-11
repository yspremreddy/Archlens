# ArchLens — Target Architecture

## 1. What ArchLens is

ArchLens ingests architecture artifacts — design docs, diagrams, ADRs,
infra-as-code, API specs, and (later) live repos — and answers questions
about risk and compliance ("does this design store PII in a region that
violates GDPR data residency?", "what services are in the blast radius if
the payments DB is compromised?", "which components lack an owner or a
threat model?"). Every answer must cite the evidence it's based on.

This document describes the **target** system. It is intentionally larger
than the MVP — see §7 for what's in scope now versus later, and §8 for
things that may never be needed.

## 2. Design principles

- **Evidence over assertion.** The system is a reviewer, not an oracle. Its
  value is in surfacing grounded, citable findings — not confident-sounding
  prose. Every retrieval hit and every generated claim carries provenance
  (source doc, chunk id, content hash, retrieval method) end to end.
- **Untrusted input by default.** Ingested content (docs, diagrams, repo
  files) is data, never instructions. Parsing, chunking, and any agentic
  step must be structurally incapable of treating ingested text as commands
  to the system (see §6 Security).
- **Bounded reasoning.** Where multi-step/agentic reasoning is used, it
  runs inside a hard step/tool-call/time budget with a deterministic
  fallback (return best-evidence-so-far), never an open-ended loop.
- **Simple first, justified complexity after.** Each moving part below is
  justified against what it buys over a simpler alternative. Several are
  explicitly flagged for postponement.

## 3. High-level components

```
                         ┌─────────────────────┐
                         │   FastAPI service    │
                         │  (API, auth, orches-  │
                         │   tration, agent loop)│
                         └─────────┬────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
   ┌──────▼──────┐        ┌────────▼────────┐        ┌──────▼───────┐
   │ Ingestion &  │        │  Retrieval layer  │        │  Reasoning /  │
   │ chunking     │        │ (hybrid + struct-  │        │  agent layer  │
   │ pipeline     │        │  ured + rerank +   │        │ (bounded loop,│
   │              │        │  GraphRAG)         │        │  tool calls)  │
   └──────┬───────┘        └───┬───────────┬────┘        └───────────────┘
          │                    │           │
   ┌──────▼───────┐    ┌───────▼──────┐ ┌──▼─────────┐
   │  PostgreSQL   │    │  PostgreSQL   │ │   Neo4j     │
   │  (structured  │    │  + pgvector   │ │ (component/ │
   │  metadata,    │    │  (chunk       │ │  data-flow  │
   │  provenance,  │    │  embeddings)  │ │  graph)     │
   │  audit log)   │    └───────────────┘ └─────────────┘
   └───────────────┘
```

A single FastAPI service exposes ingestion, query, and review endpoints.
Everything downstream of it (Postgres, pgvector, Neo4j) is a store the
service reads/writes; there is no separate "backend" — FastAPI *is* the
orchestration layer.

## 4. Components and why each is used

### FastAPI
The API and orchestration layer: ingestion endpoints, query endpoints,
retrieval orchestration, the bounded agent loop, and auth. Chosen over
alternatives because it's a thin, typed, async-friendly layer with good
OpenAPI support — no framework magic to fight when the real complexity is
in retrieval/reasoning, not the web layer. **Not yet implemented** — this
doc describes its responsibilities, not its code.

### PostgreSQL
System of record for structured data: documents, chunks, components,
findings, compliance mappings, users/roles, and — critically — the
**provenance/audit log** (every finding links back to source rows here).
Postgres is the boring, correct choice for anything that needs
transactions, referential integrity, and durability. It is *not* used as a
vector-only store; pgvector is an extension on top of the same database
rather than a second system.

### pgvector (extension on PostgreSQL, not a separate service)
Stores chunk embeddings and does approximate nearest-neighbor search
alongside the structured data it's describing. Chosen over a standalone
vector DB (e.g. Qdrant, Pinecone) because at ArchLens's expected scale
(one org's architecture corpus — thousands to tens of thousands of chunks,
not billions) a dedicated vector service adds an operational system for no
retrieval-quality benefit, and keeping vectors in the same transactional
store as their metadata means a chunk and its embedding can never drift
out of sync. Revisit only if corpus size or query volume outgrows it.

### Neo4j (graph store, for GraphRAG)
**First milestone implemented, Phase 5** (`app/graph/`). Runs locally via
Docker (Community Edition — free, no license, same pattern as
Postgres/Ollama). Models the architecture as a graph: `:Component` nodes
(service/datastore/queue/external_system, matching Postgres
`components.type`) and `:Owner` nodes, connected by `SENDS_DATA_TO`,
`DEPENDS_ON`, and `OWNED_BY` relationships — this is what makes
relationship questions answerable ("what's downstream of this component,
three hops out") which are structurally graph traversals, not similarity
search. Nodes/relationships are populated by a rule-based (regex)
extractor over the existing sample documents (`app/graph/extraction.py`)
— not an LLM extractor; see docs/DECISIONS.md ADR-007 for what this
milestone does and deliberately doesn't cover (`TrustBoundary`,
`ComplianceTag`, and general-purpose doc-to-graph extraction remain
future work). Every node and relationship carries `pg_document_id`/
`pg_chunk_id` (and components additionally `pg_component_id`) linking
back to Postgres evidence, and graph query results are returned using
the same `Citation` shape `/search` and `/answer` use
(`app/graph/retrieval.py`) — the graph is an additional retrieval mode,
not a parallel evidence model.

### Hybrid retrieval
Combines vector similarity (pgvector) with lexical/keyword search
(Postgres full-text / BM25-style) and merges results (e.g. reciprocal rank
fusion). Justified because compliance/risk queries mix fuzzy semantic
intent ("anything that looks like a data-retention risk") with exact-term
lookups ("find every mention of 'us-east-1'" or a specific control ID like
"SOC2 CC6.1") that pure embedding search is bad at. This is core to the
MVP, not a later enhancement.

### Structured retrieval
Filtering/querying by explicit metadata — document type, component,
compliance framework tag, date, owner — as SQL predicates rather than
similarity search. Necessary because many real questions ("show me every
component without an assigned owner") have nothing to do with semantic
similarity at all. Built directly on the Postgres schema; no new
infrastructure.

### GraphRAG
**First milestone implemented, Phase 5** — `app/graph/retrieval.py`
(`find_paths`) traverses the Neo4j graph for bounded multi-hop
dependency/data-flow questions ("what's downstream of X"), returning
paths with full Postgres-backed citations per hop. Exposed via
`POST /graph/query`. **Not yet done:** feeding graph results into the
`/answer` generation prompt alongside text chunks — this milestone keeps
graph retrieval and the existing hybrid-retrieval RAG pipeline separate
(`app/generation/service.py` is unchanged), so graph facts are queryable
and fully cited but not yet part of single-shot answer generation. That
integration is a natural next milestone, not done here to keep this
one's blast radius small and to avoid risking the already-working
`/answer` pipeline and its passing tests.

### Multimodal retrieval
**Implemented, Phase 6** (`app/multimodal/`). Diagrams (PNG/JPEG) and
PDF pages are OCR'd (RapidOCR, ONNX runtime — local, free, always on)
and optionally captioned by a local vision model (Ollama +
`moondream`, off by default). Landed exactly as this section originally
recommended: as an additional ingestion path into the *same*
Postgres/pgvector `chunks` table, not a parallel system — OCR text and
vision captions are embedded with the *same* text-embedding model used
for prose, so they are retrieved by the existing hybrid/lexical/vector
search and are eligible as `/answer` evidence with zero changes to
retrieval or generation code. `chunks.modality` (`text`/`image_ocr`/
`image_caption`) and `chunks.bbox` (pixel-region provenance) are the
only schema additions — see docs/SCHEMA.md §2 and docs/DECISIONS.md
ADR-008 for what this milestone found empirically (including the small
vision model's real limits for structured relationship extraction, not
glossed over).

### Reranking
**Implemented, Phase 4** (`app/retrieval/rerank.py`). A local cross-encoder
(`Xenova/ms-marco-MiniLM-L-6-v2`, via fastembed/ONNX — same local,
no-API-key approach as the embedding model) re-scores the top-N hybrid
retrieval candidates before they're passed to generation, trading a small
latency cost (~1-1.5s for 20 candidates on CPU) for materially better
precision at the top of the result list — important here because a wrong
top result becomes a wrongly-cited compliance "finding." Only the top-N
candidates are reranked (not the full retrieved set or corpus), since a
cross-encoder scores each (query, passage) pair individually and doesn't
scale to arbitrary result-set sizes the way lexical/vector retrieval does.
Verified empirically (docs/DECISIONS.md ADR-006) to correct real
misrankings on the synthetic dataset, not just in theory.

### Bounded agentic reasoning
**Implemented, Phase 7** (`app/agent/`). For questions that need
multiple retrieval/tool steps (e.g. "what does event-collector send
data to downstream?"), `app/agent/controller.py::run_agent` always
searches first, then — only if the question reads as a relationship/
dependency question and names a known component — traverses the graph,
capped by a hard max step count (`agent_max_steps`), a wall-clock budget
(`agent_time_budget_seconds`), and a fixed tool allowlist
(`app/agent/tools.py::TOOL_REGISTRY`, exactly two read-only tools). No
open-ended autonomy: on hitting either bound, it returns the evidence
gathered so far rather than continuing or guessing. The control flow
itself is deterministic (rules, not an LLM plan) — see
docs/DECISIONS.md ADR-009 for why.

### Architecture Review / Policy Engine
**Implemented, Phase 7** (`app/policy/`, `POST /review`). Runs the
bounded agent to gather text, graph, and multimodal evidence (all three
land in the same `chunks` table or the same graph, so one retrieval call
already spans all of them), then evaluates a PASS/FAIL/UNKNOWN/CONFLICT
verdict by scanning that evidence for negation vs. affirmation phrasing
(`app/policy/markers.py`) — rule-based, not LLM-judged, for the same
reason the agent's control flow is (ADR-009). Scanning is sentence/
bullet-granular, not chunk-granular (ADR-010) — an unrelated bullet in
the same retrieved chunk can no longer contaminate a verdict. CONFLICT is a first-class
outcome (both a negation and an affirmation found in relevant evidence
— contradiction detection) and UNKNOWN is a genuine abstention (no
evidence, or no evidence relevant enough to judge) rather than a forced
guess. Every verdict is persisted as a `Finding` with full
`FindingEvidence` citations, exactly like `/answer`'s findings, and
`POST /review` is a separate endpoint from `/answer` — the existing
single-shot RAG pipeline is unmodified by this phase.

### Evidence / provenance
Not a component but a requirement threaded through every other one: every
chunk stored keeps its source document, offset/region, ingestion
timestamp, and content hash; every retrieval result keeps its
score/method; every generated finding stores the exact chunk ids and
graph paths it was built from. This lives in Postgres as first-class
tables (not as an afterthought log), because findings are only useful if
an auditor can walk back to source.

### Security
Threaded throughout, not a bolt-on module:
- Ingested content (docs, diagrams, repo files) is parsed as data; nothing
  extracted from it is ever concatenated into a system/control prompt in a
  way that lets it issue instructions (prompt-injection resistance).
- Authn/authz on every endpoint; row-level scoping in Postgres so one
  org's architecture corpus is never visible to another.
- Secrets via environment/secrets manager only (see CLAUDE.md), never
  committed.
- Audit log of who queried what and which findings were shown to whom.

### Evaluation
**Compact version implemented, Phase 7/8** (`app/evaluation/`,
`tests/test_evaluation.py`). A golden set of (query, expected document)
and (question, expected verdict) pairs — every expected value verified
empirically before being written down (ADR-011) — spanning both the
synthetic dataset and a small real public corpus
(`data/samples/public/`: Kubernetes, NIST, OWASP excerpts, each with
recorded URL/license). Measures Recall@5/10, MRR, nDCG@5 (`app/evaluation/metrics.py`,
generic binary-relevance IR metrics), finding correctness/completeness,
citation accuracy against real Postgres rows, groundedness, and
abstention/false-confidence rate on genuinely unanswerable questions —
plus a baseline-RAG-vs-ArchLens comparison
(`app/evaluation/baseline.py`: lexical-only retrieval vs. the real
hybrid+rerank production path). Grows with real usage rather than being
built exhaustively up front.

### Observability
Structured tracing of the retrieval → rerank → (graph) → reasoning
pipeline per request: what was retrieved, what was dropped by reranking,
what the agent loop's steps were, latency per stage. This is what makes
the evidence/provenance requirement debuggable, not just enforceable at
the data-model level. Start with structured logs; add tracing
instrumentation once there's a pipeline worth tracing.

## 5. Data model

The detailed, column-level Phase 1 schema (tables, constraints, indexes,
provenance/hash fields) lives in **docs/SCHEMA.md** — that document is
the source of truth as of Phase 1; this section stays as a high-level
summary only.

Postgres (system of record), Phase 1 tables:
- `documents` — uploaded source artifacts and ingestion status
- `chunks` — retrieval-unit text slices with embeddings (pgvector) and
  content hashes
- `components` — structured architecture facts (name, type, owner, tags),
  with provenance links back to the document/chunk they came from. As of
  Phase 5, actually populated — by the rule-based graph extractor
  (`extraction_method = 'rule_based'`); Phase 1 shipped the columns with
  nothing writing to them yet.
- `compliance_controls` — the control set findings are checked against
  (a small custom set initially, per current decision)
- `findings` — risk/compliance claims, linked to their evidence via a
  `finding_evidence` join table (many-to-many with `chunks`)
- `audit_log` — append-only system event log

No `tenant_id` column exists yet (single-tenant MVP, per current
decision) — see docs/SCHEMA.md §0 for how the schema stays extensible to
multi-tenancy without adding unused columns now.

Neo4j — **first milestone implemented, Phase 5** (`app/graph/`), via
Docker (Community Edition). What this originally-sketched schema became
in practice, and why, is recorded in docs/DECISIONS.md ADR-007:
- Nodes: `Component` (single label, `type` property — not separate
  `Component`/`DataStore` labels), `Owner`
- Edges: `SENDS_DATA_TO`, `DEPENDS_ON`, `OWNED_BY`
- Reserved, not yet populated: `TrustBoundary`, `ComplianceTag`,
  `TAGGED_WITH`, `CROSSES_BOUNDARY` — the sample data doesn't state
  either concept explicitly, and extraction only ever encodes facts
  actually present in source text (CLAUDE.md rule 3).
- Every node/relationship carries `pg_document_id`/`pg_chunk_id`
  (components also `pg_component_id`) linking back to Postgres.

## 6. Security model (summary)

- Trust boundary is drawn around the FastAPI service + its stores.
  Everything ingested from outside that boundary (uploaded docs, repo
  contents, URLs) is untrusted content, full stop.
- LLM calls use a strict separation between system/control instructions
  (never influenced by ingested content) and retrieved context (always
  passed as data, labeled as such, never as instructions).
- Multi-tenancy (if/when multiple orgs use one deployment) is enforced at
  the schema level (tenant_id on every row + row-level security), not just
  in application logic.
- No destructive or irreversible tool exists in the agent loop's toolset —
  it can only read/retrieve, never mutate the source systems it's
  reviewing.

## 7. What's in the MVP vs. postponed

**MVP (build first):**
- FastAPI service, Postgres schema, pgvector for embeddings
- Text ingestion + chunking for docs (markdown, PDF text, plain text)
- Hybrid (vector + lexical) retrieval
- Structured retrieval (metadata filters)
- Reranking (local cross-encoder, top-N candidates only) — **implemented,
  Phase 4**
- Basic evidence/provenance model end to end
- Single-shot RAG (retrieve → answer with citations), no agent loop yet
- GraphRAG (Neo4j, rule-based extraction, bounded multi-hop traversal) —
  **first milestone implemented, Phase 5**
- Multimodal retrieval (OCR always on; vision captioning optional/local)
  — **implemented, Phase 6**
- Bounded agentic reasoning + Architecture Review / Policy Engine
  (PASS/FAIL/UNKNOWN/CONFLICT, severity, confidence, citations,
  recommendations) — **implemented, Phase 7**
- Minimal eval set + structured logging — **compact version implemented,
  Phase 7** (`tests/test_evaluation.py`: retrieval, groundedness,
  citation accuracy, completeness, abstention, latency)

**Postponed until justified by real usage:**
- **Feeding graph results into `/answer` generation specifically** —
  `/answer` (Phase 3) remains single-shot RAG without graph evidence;
  `/review` (Phase 7) is the endpoint that combines text + graph +
  multimodal evidence. Merging that capability into `/answer` itself,
  rather than keeping it a separate endpoint, is deferred (ADR-009).
- **General-purpose (LLM-based) graph extraction** — Phase 5's extractor
  is rule-based, tuned to the existing sample documents' structure, not
  a general architecture-doc-to-graph extraction step. Revisit once
  real, structurally-varied documents need extraction.
- **Reliable vision-based relationship extraction** — Phase 6's small
  local vision model (`moondream`) produces coherent captions but rarely
  the strict parseable format relationship extraction needs; component
  names (via OCR) are reliable, diagram relationships mostly aren't yet.
  Revisit with a larger/better local vision model once one is practical
  on typical hardware, or once relationship extraction is genuinely
  needed rather than nice-to-have.
- **Multimodal retrieval** — real need (diagrams matter) but a distinct
  extraction problem; land as an additional ingestion path once text
  retrieval is solid.
- **Bounded agentic reasoning** — add once single-shot retrieval+generation
  demonstrably can't answer a class of real multi-hop questions.

**Explicitly flag for reconsideration (may not be needed at all):**
- A standalone vector database — pgvector should suffice unless corpus
  scale proves otherwise.
- Any managed/hosted LLM-ops or vector-DB SaaS — conflicts with the
  "prefer simple, open-source/local" rule unless a concrete requirement
  (e.g. a hard latency/scale SLA) forces it.

## 8. Decisions (resolved) and remaining open items

Resolved, as of Phase 1 start:
- **Tenancy:** single-tenant MVP. Schema kept extensible for later
  multi-tenancy (surrogate keys, no implicit single-tenant uniqueness
  constraints) without adding an unused `tenant_id` column now — see
  docs/SCHEMA.md §0. §6's "tenant_id on every row" description is the
  eventual multi-tenant target, not the Phase 1 state.
- **Compliance frameworks:** a small custom control set to start (seeded
  into `compliance_controls` with `framework = 'archlens-custom'`),
  rather than importing SOC2/HIPAA/GDPR/PCI up front.
- **Primary artifact source:** uploaded files. `documents.source_type` is
  constrained to `'upload'` for now; a connected-repo source is a later
  additive change (see docs/SCHEMA.md §1).
- **Local Postgres + pgvector:** runs via Docker for local development.
  No Docker Compose file exists yet (out of scope until Phase 1
  implementation work begins) — this is a deployment decision, not an
  artifact created so far.

Resolved during Phase 1 implementation (see docs/SCHEMA.md §8 for full
rationale):
- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` (384
  dimensions) via `fastembed` — local, open-source, ONNX-based (no
  torch), no API key, no network calls after the one-time model-weight
  download.
- **UUID generation:** PostgreSQL's built-in `gen_random_uuid()` (native
  since PG13) — no `pgcrypto`/`uuid-ossp` extension needed.
