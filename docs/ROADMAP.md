# ArchLens — Roadmap

Phased by capability, not by date. Each phase should be independently
useful and independently testable — don't start a phase until the
previous one's evidence/provenance and tests are solid, per CLAUDE.md
("implement only the requested phase").

## Phase 0 — Project foundation (current)
- [x] CLAUDE.md project rules
- [x] docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/ROADMAP.md, TODO.md
- [ ] Confirm open questions in ARCHITECTURE.md §8 (tenancy model,
      target compliance frameworks, primary artifact source)

No code, no dependencies, no infrastructure in this phase.

## Phase 1 — Core data model + ingestion (text only)
- Postgres schema: `documents`, `chunks`, `components`,
  `compliance_controls`, `findings`, `audit_log`
- pgvector extension enabled; embeddings stored alongside chunks
- Text ingestion pipeline: markdown / plain text / PDF-text → chunk →
  embed, with content hashing and provenance fields populated
- FastAPI skeleton: ingestion endpoint(s), health check, auth stub
- Tests: ingestion round-trip (doc in → chunks + embeddings + provenance
  out), schema constraints

## Phase 2 — Retrieval (hybrid + structured)
- Lexical/full-text search over chunks
- Vector similarity search over chunks (pgvector)
- Hybrid merge (e.g. reciprocal rank fusion) of the two
- Structured retrieval: metadata-filtered queries (component, tag,
  framework, owner, date)
- Query endpoint returning ranked, cited results (no generation yet)
- Tests: retrieval precision/recall against a small hand-built golden set

## Phase 3 — Single-shot RAG answers
- LLM call that takes retrieved+reranked chunks and produces a cited
  answer/finding, with strict separation of system instructions from
  retrieved (untrusted) content
- Findings persisted with full provenance (chunk ids, scores)
- Minimal eval harness: groundedness check (does the answer's claim
  actually follow from its cited chunks)
- Structured logging of each pipeline stage

## Phase 4 — Reranking
- Cross-encoder (or equivalent) rerank step between hybrid retrieval and
  generation
- Eval harness extended to measure precision-at-k before/after reranking

## Phase 5 — Graph layer (Neo4j + GraphRAG)
- Build after text retrieval is stable.
- Extract architecture components, dependencies, data flows, ownership, and trust boundaries.
- Add Neo4j schema and Postgres ↔ Neo4j provenance strategy.
- Implement graph-aware retrieval for multi-hop relationship questions.
- Compare SQL/structured retrieval vs GraphRAG on the evaluation set.

## Phase 6 — Multimodal retrieval
- Add architecture diagram/image ingestion.
- Extract visual components and relationships using OCR/vision models.
- Store visual evidence with provenance.
- Add multimodal retrieval to the same evidence pipeline.
- Evaluate text-only vs multimodal retrieval.

## Phase 7 — Bounded agentic reasoning
- Add a controlled investigation loop for queries requiring multiple retrieval steps.
- Use a strict tool allowlist and step/time budget.
- Preserve evidence and provenance through every step.
- Return best-supported evidence or UNKNOWN when the investigation cannot establish an answer.

## Portfolio target
The completed portfolio version should include:
- Hybrid retrieval
- Structured retrieval
- Reranking
- GraphRAG
- Multimodal retrieval
- Bounded agentic reasoning
- Evidence/provenance
- Citation support
- Confidence and abstention
- Security controls
- Evaluation and observability