# ArchLens — Decision Log

Lightweight ADR-style log. Each entry: context, decision, why, and what
would make us revisit it. Newest first.

---

## ADR-006: Cross-encoder reranking via fastembed/ONNX, applied to a bounded top-N candidate pool

**Context:** Phase 4 adds reranking between retrieval and generation
(ADR-004 already decided reranking would come right after hybrid
retrieval, not deferred indefinitely). Needed: a local/free cross-encoder
and a bound on how many candidates it reranks, since cross-encoders score
each (query, passage) pair individually and don't scale to an arbitrary
result-set size the way lexical/vector retrieval does.

**Decision:** Use fastembed's `TextCrossEncoder` with
`Xenova/ms-marco-MiniLM-L-6-v2` (~80MB, ONNX runtime, Apache-2.0),
applied only to the top `rerank_candidate_pool` (default 20) candidates
retrieval returns — configurable, not hardcoded. Implemented as a
standalone module (`app/retrieval/rerank.py`) that only depends on
`RetrievedResult` (app/retrieval/core.py), not on hybrid retrieval or the
generation pipeline specifically, so it stays a drop-in step. Wired into
`app/generation/service.py` only (between retrieval and prompt-building);
`/search` (Phase 2) is unchanged.

**Why:** Same reasoning as the embedding model choice (ADR from Phase 1):
ONNX via fastembed avoids adding torch/GPU-framework dependencies for a
small model that only needs CPU inference, and it's the same library
already a project dependency. Bounding to top-N (not reranking everything
retrieval returns, let alone the whole corpus) keeps latency predictable
regardless of corpus size — verified empirically at ~1-1.5s for 20
candidates on CPU. Verified (not just assumed) to actually improve
ranking quality: on the synthetic dataset, the query "schema validation
for incoming events" has hybrid retrieval rank the wrong chunk (a
document's intro) above the chunk that actually discusses the gap;
reranking corrects this to the right chunk at position 1 — see
`tests/test_rerank.py::test_reranking_corrects_a_real_hybrid_misranking`.

**Why applied to every retrieval mode, not just "hybrid":** The reranker
only reads chunk text and a query string — it has no dependency on how
candidates were retrieved, so gating it to `mode == "hybrid"` would have
been an arbitrary restriction rather than a real constraint.

**Revisit if:** Rerank latency becomes a problem at a larger
`rerank_candidate_pool` or under concurrent load (CPU-only ONNX inference
serializes) — options then are a smaller/faster reranker model, GPU
execution providers (already used for local LLM generation via Ollama on
this machine), or async/batched reranking.

---

## ADR-005: LLM provider is a pluggable abstraction; default is a non-LLM deterministic fallback, not a bundled model

**Context:** Phase 3 needs a "local/free LLM approach; no paid API" for
generation. The candidates were: (a) bundle a model directly via
`llama-cpp-python` or `transformers`+`torch`, (b) call a locally-running
Ollama server, (c) ship a deterministic non-LLM fallback. This dev
environment has no GPU, no Ollama installed, and is running a very new
Python version (3.14) where some ML wheels' compatibility isn't
guaranteed — a large model download/build inside this environment risked
an unverifiable or non-reproducible result.

**Decision:** Define an `LLMProvider` abstraction
(`app/generation/providers.py`) with two implementations:
`TemplateExtractiveProvider` (default — zero-dependency, deterministic,
quotes the top retrieved passage) and `OllamaProvider` (real local LLM
via a locally-running Ollama server, HTTP-only, no bundled weights).
`LLM_PROVIDER=template` ships as the default so the pipeline, its tests,
and its persisted findings are always real and reproducible without
requiring the user to install anything extra first.

**Why:** This is the same pattern the project already uses for
Postgres — an external, independently-installed local service
(docker-compose) rather than a bundled dependency — applied to the LLM.
It keeps CLAUDE.md rule 3 (don't fabricate results) intact: every test
and every persisted `Finding` in this session is honestly labeled
`llm_provider="template-extractive"`, not presented as real-model output
that wasn't actually run. It also keeps rule 8 (prefer simple) —
`llama-cpp-python`/`torch` would add large, compiled, GPU-adjacent
dependencies to the project itself for a capability an already-installed
local service can provide instead.

**Revisit if:** A user wants real generated (non-extractive) answers —
switch `LLM_PROVIDER=ollama` after installing Ollama and pulling a model
(no code change needed, the abstraction already supports it). If bundled
local inference becomes clearly the better default (e.g. Ollama proves
too heavy an ask for typical users), reconsider `llama-cpp-python` with a
small GGUF model as a third provider.

---

## ADR-004: Reranking and bounded agentic reasoning are sequenced last

**Status:** Reranking half of this decision is implemented (Phase 4) —
see ADR-006. Bounded agentic reasoning remains not started.

**Context:** Both improve answer quality but add cost/latency/complexity.

**Decision:** Add reranking immediately after hybrid retrieval is working
(cheap, high value-per-effort). Add the bounded agent loop only after
single-shot retrieve-then-generate demonstrably fails on real multi-hop
questions.

**Why:** Reranking is a small addition with a clear, immediate precision
payoff on top of hybrid retrieval. An agent loop is a much bigger surface
(planning, tool budget, failure modes) that's only worth its complexity
once there's evidence single-shot RAG isn't enough.

**Revisit if:** Early usage shows single-shot answers frequently missing
evidence that requires multiple hops (e.g. "trace this data flow three
services downstream") — that's the trigger to build the agent loop, not a
fixed roadmap date.

---

## ADR-003: Multimodal retrieval postponed behind text retrieval

**Context:** Architecture is often communicated as diagrams, not prose,
so image understanding is genuinely valuable — but it's a distinct
extraction problem (OCR/vision embeddings) from text chunking.

**Decision:** Ship text-only ingestion and retrieval first. Add diagram/
image ingestion as an additional path into the same Postgres/pgvector
schema once text retrieval is solid.

**Why:** Don't let a harder, less-proven extraction problem block a
working core loop. Keeping it in the same schema (rather than a parallel
system) avoids a second retrieval pipeline to maintain later.

**Revisit if:** Early real-world corpora turn out to be diagram-only or
diagram-primary, making text-only retrieval nearly useless in practice —
then multimodal ingestion should move up, not stay last.

---

## ADR-002: Neo4j and GraphRAG postponed; Postgres structured retrieval first

**Context:** Relationship questions ("what's downstream of this data
store," "what crosses this trust boundary") are naturally graph
traversals. Neo4j + GraphRAG is the textbook answer. But it requires a
reliable doc-to-graph extraction step (unsolved, hard) and a second
datastore to keep consistent with Postgres.

**Decision:** Build structured retrieval as SQL over the Postgres schema
first (components, tags, ownership as rows/foreign keys). Only introduce
Neo4j once there's a concrete, recurring class of relationship questions
that SQL joins genuinely can't serve well.

**Why:** Matches the "prefer simple, open-source/local, justify added
complexity" project rule. Two-store consistency and graph-extraction
reliability are real costs that shouldn't be paid speculatively.

**Revisit if:** Structured SQL retrieval is in place and there's a
repeated pattern of multi-hop relationship questions it can't answer
well (not just "graph databases are a better fit in theory").

---

## ADR-001: pgvector on Postgres instead of a standalone vector database

**Context:** Need vector similarity search over chunk embeddings for
hybrid retrieval.

**Decision:** Use the pgvector extension on the same Postgres instance
that holds structured metadata and provenance, rather than a dedicated
vector database (Qdrant, Pinecone, Weaviate, etc.).

**Why:** At ArchLens's expected scale (one org's architecture corpus),
pgvector's ANN search is sufficient, and keeping embeddings in the same
transactional store as the metadata describing them means a chunk and its
embedding can never drift out of sync — no dual-write/sync problem. Also
keeps the deployment footprint to one primary datastore instead of two.

**Revisit if:** Corpus size or query volume grows enough that pgvector's
ANN performance becomes the bottleneck, with evidence (not speculation)
from real usage.
