# ArchLens — Decision Log

Lightweight ADR-style log. Each entry: context, decision, why, and what
would make us revisit it. Newest first.

---

## ADR-011: Real public evaluation corpus (NIST/Kubernetes/OWASP) + compact IR-metric evaluation suite

**Context:** Phase 8 asked for a small real-world public corpus (from
official sources — AWS, NIST, Kubernetes, Terraform, or OpenAPI/security
docs) alongside the existing synthetic dataset, plus realistic
evaluation cases with ground truth: Recall@5/10, MRR/nDCG, finding
correctness/completeness, citation accuracy, groundedness,
abstention/false-confidence, and a baseline-RAG-vs-ArchLens comparison.

**Decision — corpus sourcing:** Fetched (via WebFetch/WebSearch, not
fabricated) four short excerpts from three sources with unambiguous
public-reuse terms:
- Kubernetes documentation, "Pod Security Standards" — CC BY 4.0.
- NIST Cybersecurity Framework, "Five Functions" — U.S. government work,
  public domain (17 U.S.C. §105).
- OWASP Top 10:2021, A01 (Broken Access Control) and A02 (Cryptographic
  Failures) — CC BY 3.0 Unported.

AWS and Terraform (both on the task's suggested list) were deliberately
excluded: AWS documentation prose is copyrighted by Amazon with no
open-reuse license for verbatim excerpts, and Terraform's MPL-2.0
license covers HashiCorp's *code*, not its documentation *prose* (which
is conventionally all-rights-reserved, publicly viewable but not
licensed for reuse). Reusing either without a clear license would
conflict with engineering guideline 3's spirit (don't present something as
clearly usable when it isn't) even though the task didn't name licensing
explicitly as a rule. Every file under `data/samples/public/` carries
its own URL/license/retrieval-date header, plus a consolidated
`SOURCES.md` ledger — kept deliberately small (4 files, ~1-2KB each),
per the task's "do not use large unnecessary datasets."

**Decision — evaluation suite (`app/evaluation/`, `tests/test_evaluation.py`):**
- `metrics.py`: generic, standard binary-relevance Recall@k, MRR
  (mean reciprocal rank), and nDCG@k — not ArchLens-specific, so the
  same functions could score any ranked-list-vs-ground-truth-set problem.
- `golden.py`: every expected value (which document a query should
  retrieve, what verdict a review question should produce) was verified
  by actually running the system before being written down as "ground
  truth" — never assumed or guessed (engineering guideline 3/4).
- `baseline.py`: "baseline RAG" = lexical-only retrieval
  (`app.retrieval.core.retrieve(mode="lexical")`); "ArchLens" = the
  actual production path (hybrid retrieval + cross-encoder reranking,
  the same two functions `/answer` and `/review` call). Not a
  reimplemented strawman — a real, measured comparison of the same
  system with and without Phases 2/4's hybrid+rerank additions.
  Measured result: baseline Recall@5 = 0.125 vs ArchLens Recall@5 = 1.0
  over the 8 golden retrieval cases (synthetic + public corpus combined)
  — see the test run for the exact numbers at time of writing; this
  number will drift as the corpus grows and should be re-measured, not
  assumed to hold forever.

**Two more real bugs found and fixed while building golden review cases
against the real public corpus** (in addition to ADR-009's three,
extending `app/policy/markers.py`):
1. "cannot" and (already-removed) "never" are too context-dependent as
   generic negation words — OWASP's own definition of access control
   ("users **cannot** act outside their intended permissions") uses
   "cannot" to describe *correct* behavior, not a gap. Removed.
2. A handful of official-doc-style negation-of-permission words
   ("forbidden", "disallowed", "prohibited", "not allowed", "denied")
   were missing — the synthetic corpus's "no documented X" phrasing
   doesn't appear in Kubernetes/OWASP prose at all, so several real
   gap statements (e.g. "HostPath volumes: forbidden") were originally
   invisible to the scanner. Added as generic (not per-topic) English
   negation words.

**Revisit if:** The public corpus needs to grow (keep it small and
recheck each new source's license before adding), or the baseline
comparison should include a stronger baseline (e.g. vector-only, not
just lexical-only) once there's a concrete reason to measure that.

---

## ADR-010: Evidence-granularity fix — sentence-level, not chunk-level, marker scanning

**Context:** ADR-009 documented a known limitation: the policy engine
(`app/policy/engine.py`) scanned whole retrieved chunks (~1000
characters, often 2-3 unrelated bullet points from Phase 1's chunker)
for negation/affirmation markers. A question relevant to only one bullet
in a multi-bullet chunk could still pick up an unrelated bullet's marker
just because it shared the chunk — observed concretely with a
`data-pipeline.md` "Known gaps" chunk covering three unrelated topics,
where a question about only one of them (`event-collector`) produced
CONFLICT instead of the correct FAIL.

**Decision:** Added `_logical_units()` to `app/policy/engine.py`: splits
each retrieved chunk into bullet/sentence-level units — rejoining a
bullet's own wrapped continuation lines first (Phase 1's chunker
preserves the source file's line-wrapping, so a phrase split across a
wrap boundary needs rejoining before further splitting), then splitting
on sentence-ending punctuation. Relevance filtering and marker scanning
now both operate on these units, not on whole chunks. `Citation` objects
are unaffected — they still point at the whole chunk (the actual
retrieval/provenance unit); only the verdict *reasoning* is now scoped
more precisely. No schema change, no retrieval change, no API change —
contained entirely within `app/policy/engine.py`.

**Why not re-chunk instead:** Changing the chunking strategy
(Phase 1/2) to produce smaller, single-topic chunks would ripple into
retrieval scoring, reranking, and every existing citation/provenance
test — a much bigger change for the same fix, and would violate "reuse
existing modules; don't redesign working retrieval unnecessarily."
Fixing the scanning granularity inside the one module that actually had
the problem is the smaller, contained change.

**A second, related bug found while testing this fix against real data:**
a list-header sentence ("The Baseline policy enforces or disallows the
following:") trivially matched both an affirmation word ("enforces")
and a negation word ("disallows") in the same structural sentence,
producing a false CONFLICT on a sentence making no substantive claim at
all. Fixed by excluding colon-terminated lines (list/section headers)
from the unit set — a generic, structural fix, not a per-document patch.

**Verified:** `tests/test_policy.py::test_review_integrates_graph_evidence`
was previously written to deliberately avoid asserting a specific
verdict for the ambiguous case (ADR-009); it now asserts the correct
`FAIL` verdict directly, and a new unit-level regression test
(`test_evaluate_unrelated_bullet_in_same_chunk_does_not_contaminate_verdict`)
pins the fix independent of the database/corpus.

**Revisit if:** A corpus with much longer, more topically-mixed chunks
emerges where sentence-level splitting still isn't fine-grained enough
— at that point, reconsider chunking strategy itself rather than
scanning-granularity tricks.

---

## ADR-009: Phase 7 bounded agent + policy engine — deterministic control flow and rule-based verdicts, not LLM-driven; separate `/review` endpoint; marker-scan bugs found and fixed

**Context:** This phase adds bounded agentic reasoning (app/agent/) and
an Architecture Review / Policy Engine (app/policy/) producing PASS/
FAIL/UNKNOWN/CONFLICT verdicts with severity, confidence, citations, and
recommendations — integrating text, graph, and multimodal evidence.
docs/ARCHITECTURE.md's "Bounded agentic reasoning" section describes an
LLM-driven plan-act-observe loop; building the first real version
surfaced concrete decisions.

**Decisions:**
1. **The agent's step-by-step control flow is deterministic (regex/
   keyword rules), not LLM-planned.** `app/agent/controller.py` always
   searches first, then queries the graph only if the question matches a
   relationship-intent pattern *and* names a known component — a fixed,
   inspectable rule, not a model's judgment call. Rationale: ADR-005 and
   ADR-008 already found the local models practical on this machine
   unreliable for structured, must-follow-exactly instructions (a
   compound vision prompt degenerated into a 200-word repetition loop;
   see ADR-008). The few "planning" decisions this agent needs to make
   are simple enough that a deterministic rule is both more reliable and
   fully testable (`tests/test_agent.py` asserts exact tool sequences,
   which would be impossible to assert reliably against LLM output).
2. **Read-only tool allowlist, enforced structurally, not just by
   convention.** `app/agent/tools.py`'s `TOOL_REGISTRY` contains exactly
   two functions (`search_tool`, `graph_tool`), both pure wrappers over
   already-existing read paths (`app.retrieval.core.retrieve`,
   `app.graph.retrieval`). Neither calls `db.add`/`db.commit` or a Cypher
   write clause — verified by a static-source-inspection test
   (`tests/test_security.py::test_agent_tools_contain_no_write_operations`),
   not just asserted in a docstring. The one write in the whole review
   pipeline (persisting the final `Finding`) happens once, in
   `app/policy/service.py`, strictly after the bounded loop ends.
3. **The policy engine is rule-based (negation/affirmation marker
   scanning over evidence text), not LLM-judged** — same reasoning as
   (1). `app/policy/markers.py` + `app/policy/engine.py` scan retrieved
   text (and short synthetic sentences built from graph facts) for
   plain-English negation ("no documented...", "without...") vs.
   affirmation ("uses...", "is encrypted...") phrasing, matching how the
   existing synthetic sample data's "Known gaps" sections were already
   written. A verdict is CONFLICT when both appear in relevant evidence
   — the contradiction-detection requirement — and UNKNOWN when no
   evidence is relevant enough to judge, rather than guessing.
4. **New endpoint `POST /review`, `/answer` untouched.** Rather than add
   an agent/policy mode flag to the existing `/answer` (Phase 3), this
   phase ships a separate endpoint. This makes backward compatibility
   structural rather than something to carefully verify: `/answer`'s
   code path (`app/generation/service.py`) has zero lines changed, so
   its behavior cannot have regressed. `Finding.verdict`/`Finding.severity`
   (migration `9fbf4e4d16c0`) are nullable additions — existing `/answer`
   findings simply leave them null.
5. **Three real bugs found and fixed during development** (see
   `tests/test_policy.py`'s regression tests for each): (a) the bare
   word "documented" was an affirmation pattern, so "no **documented**
   rate limiting" — a negation — falsely also matched as an affirmation,
   producing CONFLICT for a plain FAIL case; (b) "never" was a negation
   pattern, so "passwords are **never** persisted or logged" — a
   *good* practice — falsely matched as a negation; (c) marker scanning
   ran over *all* retrieved evidence regardless of which document it
   came from, so an unrelated document's negation (found via hybrid
   retrieval's necessarily-broad top-k) contaminated verdicts about
   completely different topics. Fixed by: removing the ambiguous bare
   words, requiring a minimum keyword-overlap *count* (not just a
   fraction — a 5-keyword question sharing one common word like "user"
   was clearing a fractional threshold too easily) between the question
   and each evidence text before scanning it for markers, and a short
   generic-word stopword list (engineering guideline 4: every change here was
   caught by actually running it against real data, not assumed correct).

**Known limitation, stated plainly — Status: fixed in ADR-010** (below
this entry in the log, i.e. done more recently). Left here unedited as
the historical record of what the limitation was and why it existed;
see ADR-010 for the fix. Original text: marker scanning happens at
chunk granularity (whatever the Phase 1 chunker produced, ~1000 chars —
often 2-3 unrelated bullet points together). A question relevant to one
bullet in a multi-bullet chunk can still pick up an unrelated bullet's
marker in the same chunk (observed with a multi-hop graph question
against `data-pipeline.md`'s "Known gaps" section, which discusses three
unrelated gaps in one chunk — see `tests/test_policy.py::test_review_integrates_graph_evidence`,
which deliberately does not assert a specific verdict for this case).
Fixing this would need sentence-level (not chunk-level) evidence
granularity, which is a chunking-strategy change out of scope for this
phase (engineering guideline 2 — implement only the requested phase).

**Revisit if:** A better local LLM becomes reliable enough for
structured plan/judge tasks (re-evaluate deterministic control flow vs.
LLM planning), or sentence-level evidence granularity becomes worth the
chunking-strategy change.

---

## ADR-008: Phase 6 multimodal ingestion — same chunk table (not a parallel one), OCR always on, vision captioning optional and honestly limited

**Context:** docs/ARCHITECTURE.md and ADR-003 already said multimodal
retrieval should "land as an additional ingestion path into the same
pgvector/Postgres schema... not a parallel system" when the time came.
Phase 6 is that milestone: image/PDF-page ingestion, OCR, vision-based
component/relationship extraction, visual evidence provenance, and
multimodal retrieval integrated with existing retrieval.

**Decisions:**
1. **OCR and vision-caption text go into the same `chunks` table as
   prose**, embedded with the same text-embedding model
   (`sentence-transformers/all-MiniLM-L6-v2`, already used for every
   other chunk). Two new columns distinguish them: `modality`
   (`text`/`image_ocr`/`image_caption`) and `bbox` (pixel-region
   provenance for image-derived chunks — the image equivalent of
   `start_offset`/`end_offset`). No separate image-embedding model, no
   joint text-image embedding space, no parallel table. **Why:** a CLIP-
   style joint embedding space was considered and rejected for this
   milestone — it would need its own vector column/dimension and its
   own retrieval code path, exactly the "parallel system" ADR-003 said
   to avoid. Routing image content through OCR into *text* first means
   `/search`, `/answer`, hybrid retrieval, and reranking all work on
   diagram content with **zero code changes** — verified directly: a
   diagram's OCR'd component labels are retrieved by existing hybrid
   search and cited in `/answer` responses without touching
   `app/retrieval/` or `app/generation/` retrieval logic, only adding a
   `modality` filter option.
2. **OCR is local, ONNX-based, and always on** — `rapidocr-onnxruntime`
   (same local/no-API-key pattern as embedding and reranking). No opt-in
   needed; it needs no model choice. Verified against the real diagram
   fixtures (`data/samples/diagrams/`): >95% confidence on every text
   region, correct labels, real pixel bounding boxes.
3. **PDF pages render via `pypdfium2`**, not a system Poppler/Ghostscript
   dependency — a pure pip-installable PDFium binding, so `uv sync`
   remains the only install step (engineering guideline 8). A generated
   single-page PDF and its PNG source produce byte-identical OCR results
   in this milestone's tests.
4. **Vision captioning is optional, off by default** (`VISION_PROVIDER=
   none`), mirroring the Phase 3 `LLM_PROVIDER=template` pattern exactly
   — a diagram is still fully OCR-searchable with zero vision model
   installed. `VISION_PROVIDER=ollama` uses a locally-running Ollama
   server with `moondream` (~1.7GB), the smallest practical local
   vision-capable model — chosen the same way Phase 3's `llama3.2:1b`
   was, for the same tight-RAM-machine reasons (see ADR-005).
5. **Component names come from OCR (reliable); relationship extraction
   from the vision caption is real but empirically weak, and is honestly
   reported as such rather than smoothed over.** Verified directly
   against `moondream`: a compound prompt asking for a description *and*
   a strict `"A -> B"` relationship list reliably produced degenerate
   repetition-loop output (`"...Larger-service - Larger-service -
   Larger-service..."` repeated hundreds of times). A simpler,
   single-ask caption prompt produces coherent, on-topic text instead —
   that's what ships (`app/multimodal/service.py::VISION_PROMPT`) — but
   it rarely contains the strict `A -> B` format
   `app/multimodal/graph.py::parse_vision_relationships` requires, so
   relationship extraction from diagrams will often correctly return
   zero results with this model. That parser also cross-checks every
   parsed relationship against OCR-confirmed component names specifically
   *because* of this observed unreliability — `"Larger-service"` is not
   a real label in the diagram, and the cross-check filters exactly this
   kind of hallucination out (engineering guideline 3: don't pass through
   unverified model claims as fact). Component extraction from OCR labels
   remains reliable regardless, since it's text recognition, not
   generation.
6. **`components.extraction_method` gets a fourth value,
   `'vision_extracted'`** (migration `cc8e51c1a598`), distinct from
   Phase 5's `'rule_based'` (prose regex) even though component *names*
   in this path come from OCR text recognition, not "vision
   understanding" per se — the pipeline as a whole (OCR + vision) is the
   diagram path, so it's labeled distinctly from prose extraction. Graph
   upsert logic (Postgres `components` + Neo4j nodes/edges) is *shared*
   with Phase 5's — `app/graph/service.py`'s upsert helpers were
   promoted from module-private to reusable, rather than duplicated in
   `app/multimodal/graph.py`.

**Revisit if:** A larger/better local vision model becomes practical on
typical hardware (better relationship-extraction reliability), or a real
need emerges for a joint text-image embedding space (e.g. searching by
visual similarity rather than OCR'd/captioned text) — that would be a
genuinely new capability, not something this milestone's design blocks
adding later.

---

## ADR-007: Phase 5 GraphRAG milestone — schema deviations from the original sketch, rule-based (not LLM) extraction, no relationship mirror table

**Context:** ADR-002 postponed Neo4j/GraphRAG until structured Postgres
retrieval existed and a concrete relationship-question need was clear
(Phase 2's structured filters now exist). docs/ARCHITECTURE.md §5 sketched
a graph schema (Nodes: `Component`, `DataStore`, `DataFlow`,
`TrustBoundary`, `Owner`, `ComplianceTag`; Edges: `SENDS_DATA_TO`,
`DEPENDS_ON`, `OWNED_BY`, `TAGGED_WITH`, `CROSSES_BOUNDARY`) before any
extraction existed to populate it. Building the first real milestone
surfaced three places where the sketch needed a concrete decision.

**Decisions:**
1. **Single `:Component` label with a `type` property**, not separate
   `:Component`/`:DataStore` labels. Mirrors how Postgres already models
   it (`components.type`, one table) — two divergent taxonomies (Postgres
   columns vs. Neo4j labels) would need to be kept in sync for no benefit.
2. **No `DataFlow` node.** A data flow is a `SENDS_DATA_TO` relationship
   directly between two `:Component` nodes. The original sketch didn't
   specify what a separate node would hold that the edge itself couldn't;
   inventing structure for it would be speculative, not justified by an
   actual query need.
3. **`TrustBoundary` and `ComplianceTag` are not populated.** The sample
   documents don't state either concept explicitly. Extraction only
   encodes facts actually present in source text (engineering guideline 3 — no
   fabricated facts); the label/edge-type constants stay reserved in
   `app/graph/schema.py` for when real extraction for them exists.
4. **Extraction is rule-based (regex), not LLM-based**, and Postgres
   `components.extraction_method` gets a third value, `'rule_based'`
   (migration `540fcff68f20`), distinct from the `'llm_extracted'` value
   Phase 1 already reserved. A small, fixed set of patterns
   (`app/graph/extraction.py`) tuned against the actual structure of
   `data/samples/*.md` ("## Components" bullet lists, explicit "from A to
   B" / "calls it" / "accepts events ... reach" phrasing) — not a general
   NLP/LLM extractor. Every extracted fact is traceable to a specific
   regex match against specific source text; a document with different
   structure yields fewer (or zero) facts, never guessed ones.
5. **No Postgres mirror table for relationships.** Only `:Component`
   nodes have a Postgres-side row (`components`, via `pg_component_id`);
   `SENDS_DATA_TO`/`DEPENDS_ON`/`OWNED_BY` relationships exist only in
   Neo4j, carrying `pg_document_id`/`pg_chunk_id` properties directly for
   provenance. A relationships table was avoidable scope for this
   milestone — Postgres has no established need to query relationships
   independently of the graph yet.

**Why local Neo4j Community Edition, not a hosted graph DB:** Same
reasoning as every other local component in this stack (Postgres,
Ollama, the embedding/rerank models) — free, no API key, runs via the
same docker-compose pattern already established
(docs/DECISIONS.md ADR-001, ADR-005).

**Known limitation, not hidden:** unlike Postgres (a dedicated
`archlens_test` database), the local Neo4j setup has no separate test
database — Community Edition's default single-database setup. The test
suite (`tests/test_graph.py`) wipes the *entire* local graph before every
test for isolation, which means running it also clears dev graph data.
Acceptable for a local single-developer setup; would need a real
test/dev graph separation (or Neo4j Enterprise's multi-database support)
before this could run in a shared or CI environment safely.

**Revisit if:** Real usage needs `TrustBoundary`/`ComplianceTag` facts,
needs to query relationships from Postgres directly (not just via the
graph), or the rule-based extractor needs to handle document structures
it wasn't tuned against — at that point, LLM-based extraction becomes the
natural next step, using the `'llm_extracted'` value already reserved.

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
It keeps engineering guideline 3 (don't fabricate results) intact: every test
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

**Status:** Resolved — Phase 6 implements image/PDF-page ingestion, OCR,
optional vision captioning, and multimodal retrieval; see ADR-008 for
what shipped and what's still weak (vision-based relationship
extraction).

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

**Status:** Resolved — Phase 5's first GraphRAG milestone implements
Neo4j + a rule-based extraction step; see ADR-007 for what changed and
why, and what's still not done (LLM-based extraction, TrustBoundary/
ComplianceTag, feeding graph results into `/answer`).

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
