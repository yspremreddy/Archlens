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
Models the architecture itself as a graph: services, data stores, data
flows, trust boundaries, ownership, and compliance tags as nodes and
edges. This is what makes relationship questions answerable — "what
downstream services touch this PII field," "what's the blast radius of
this component" — which are structurally graph traversals, not similarity
search. This is the component most worth scrutinizing before building: it
requires (a) an extraction step that reliably turns architecture docs into
a graph, which is its own hard problem, and (b) keeping two stores (Neo4j
+ Postgres) consistent. **Recommendation: postpone.** Build structured
retrieval over Postgres first; only add Neo4j once there's a concrete set
of relationship questions that structured SQL joins genuinely can't answer
well. See §7.

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
Retrieval that traverses the Neo4j graph (not just vector/lexical search)
to assemble context for relationship-aware questions, then feeds that
subgraph to the reasoning layer alongside text chunks. Depends entirely on
Neo4j existing and being trustworthy (§ above) — postponed with it.

### Multimodal retrieval
Retrieval over non-text artifacts: architecture diagrams (images),
diagram-as-PDF, scanned docs. Requires image embeddings and/or
OCR/vision-model extraction feeding into the same chunk store. Valuable
because architecture is often communicated primarily as diagrams, but it's
a distinct extraction problem from text ingestion and shouldn't block a
working text pipeline. **Recommendation: postpone to a phase after
text-only retrieval is solid**; land it as an additional ingestion path
into the *same* pgvector/Postgres schema (image chunks get their own
embedding column/table, not a parallel system).

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
For questions that need multiple retrieval/tool steps (e.g. "trace every
downstream consumer of this data store and check each against the
retention policy"), a loop that plans a step, calls a retrieval/graph
tool, observes, and decides whether to continue — capped by a hard max
step count, wall-clock budget, and tool-call allowlist. No open-ended
autonomy: on hitting the bound, it returns the best evidence gathered
rather than continuing indefinitely or guessing. This is explicitly the
*last* piece to build — single-shot retrieval + generation should handle
most queries first; the agent loop is for the residual multi-hop cases.

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
A golden set of (query, expected evidence, expected finding) triples used
to measure retrieval recall/precision and answer groundedness (does the
generated finding actually follow from the cited evidence — checkable
mechanically, not just by eye) before and after any retrieval/prompt
change. Needed early enough to catch regressions, but the *set itself*
can start small and grow with real usage rather than being built
exhaustively up front.

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
  with provenance links back to the document/chunk they came from
- `compliance_controls` — the control set findings are checked against
  (a small custom set initially, per current decision)
- `findings` — risk/compliance claims, linked to their evidence via a
  `finding_evidence` join table (many-to-many with `chunks`)
- `audit_log` — append-only system event log

No `tenant_id` column exists yet (single-tenant MVP, per current
decision) — see docs/SCHEMA.md §0 for how the schema stays extensible to
multi-tenancy without adding unused columns now.

Neo4j (once justified, §7):
- Nodes: `Component`, `DataStore`, `DataFlow`, `TrustBoundary`, `Owner`,
  `ComplianceTag`
- Edges: `SENDS_DATA_TO`, `DEPENDS_ON`, `OWNED_BY`, `TAGGED_WITH`,
  `CROSSES_BOUNDARY`

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
- Minimal eval set + structured logging

**Postponed until justified by real usage:**
- **Neo4j + GraphRAG** — needs a working, trustworthy extraction step from
  docs to graph facts first; adds a second store to keep consistent.
  Build structured SQL retrieval first and see what relationship
  questions it genuinely can't answer.
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
