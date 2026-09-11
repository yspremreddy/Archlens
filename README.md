# ArchLens

ArchLens is an AI Architecture Risk & Compliance Reviewer. Upload architecture
documents or diagrams, ask a review question, and get a **PASS / FAIL / UNKNOWN
/ CONFLICT** verdict — with severity, confidence, a recommendation, and every
claim traceable back to the exact document, chunk, and content hash it came
from.

Everything runs locally and for free: local embeddings and reranking (ONNX,
no torch), an optional local LLM via [Ollama](https://ollama.com), Postgres +
pgvector, Neo4j Community Edition, and a rule-based (not LLM-judged) policy
engine. No paid APIs are required anywhere in the default configuration.

## Architecture

```
┌─────────────┐      ┌───────────────────────────────────────────────┐
│  Frontend   │ HTTP │  FastAPI (app/)                                │
│  React+TS   │─────▶│                                                │
│  (Vite)     │      │  ingestion → chunking → embedding (fastembed)  │
└─────────────┘      │       │                                        │
                      │       ▼                                       │
                      │  hybrid retrieval (lexical FTS + pgvector)    │
                      │       │  → RRF fusion → cross-encoder rerank  │
                      │       ▼                                       │
                      │  bounded agent (search + graph tools)         │
                      │       │                                       │
                      │       ├─▶ Postgres (pgvector): docs, chunks,  │
                      │       │   findings, evidence, provenance      │
                      │       └─▶ Neo4j: component/relationship graph │
                      │       ▼                                       │
                      │  policy engine (regex-based PASS/FAIL/        │
                      │  UNKNOWN/CONFLICT verdicts, sentence-granular)│
                      │       ▼                                       │
                      │  generation (template extractive, or local    │
                      │  Ollama LLM) — grounded, cited answers        │
                      └───────────────────────────────────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design and
[docs/DECISIONS.md](docs/DECISIONS.md) for the ADR log covering every
non-trivial choice (why hybrid retrieval, why rule-based policy instead of
LLM-judged, why sentence-granular evidence scanning, etc.).

### Backend stack
FastAPI · PostgreSQL 16 + pgvector · Neo4j 5 Community · SQLAlchemy 2.0 +
Alembic · fastembed (local embeddings + cross-encoder reranking, ONNX, no
torch) · rapidocr-onnxruntime + pypdfium2 (diagram/PDF ingestion) · optional
Ollama (local LLM + vision) · OpenTelemetry (optional, off by default).

### Frontend stack
React 18+ · TypeScript · Vite · hand-written responsive CSS (no UI framework)
· Fetch API with `AbortController`-based cancellation · Web Storage
(preferences) · IndexedDB (local result caching, raw browser API) · a
hand-rolled Service Worker (static-asset caching only — API responses are
never cached, so findings are always live) · Vitest + Testing Library ·
Playwright.

No new major frameworks were introduced beyond what was explicitly
requested: no React Router (tab-based view switching instead), no charting
library (the graph view is hand-rolled inline SVG), no IndexedDB wrapper, no
service-worker build plugin.

## Setup

### Prerequisites
- Python 3.11+, [uv](https://docs.astral.sh/uv/)
- Node.js 20+ (tested with Node 24)
- Docker Desktop (for Postgres + Neo4j)

### Backend

```bash
# from the repo root
cp .env.example .env          # local defaults, no real secrets
docker compose up -d          # starts Postgres+pgvector and Neo4j
uv sync                       # installs Python dependencies
uv run alembic upgrade head   # applies the schema
uv run uvicorn app.main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/health` → `{"status":"ok","database":true}`

Optional local LLM (otherwise a deterministic template provider is used —
always available, no download required):

```bash
ollama pull llama3.2:1b
# then in .env: LLM_PROVIDER=ollama
```

### Frontend

```bash
cd frontend
cp .env.example .env          # VITE_API_BASE_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:5173
```

The backend allows CORS from `http://localhost:5173` / `127.0.0.1:5173` only
(see `app/main.py`) — no wildcard origin.

### Optional: tracing

Off by default. To enable, run a local OTLP collector (a free, local [Arize
Phoenix](https://github.com/Arize-ai/phoenix) instance works out of the box)
and set `OTEL_ENABLED=true` in `.env`:

```bash
docker run -p 6006:6006 -p 4317:4317 arizephoenix/phoenix
```

## Demo flow

1. Start the backend and frontend as above.
2. Open `http://localhost:5173` → **Upload** tab → upload
   `data/samples/payment-service.md`.
3. Click **Extract graph relationships** on the upload result.
4. Go to **Review** → ask *"does payment-api have rate limiting on the
   checkout endpoint?"* → verdict, severity, confidence, recommendation, and
   citations render, each traceable to a real chunk hash.
5. Go to **Search** → try hybrid vs. lexical vs. vector modes on the same
   query, or click **Ask** for a generated, grounded answer.
6. Go to **Graph** → query `event-collector` downstream to see extracted
   component relationships as an SVG diagram.
7. Go to **Evaluation** → the last-measured retrieval/finding/latency numbers
   from the backend's own evaluation suite (see below — not recomputed live
   by the dashboard).

## Security

- **Prompt injection**: ingested document content is never concatenated into
  the system prompt; it only ever reaches the LLM as clearly delimited
  untrusted user-prompt context (`app/generation/prompts.py`). Verified with
  a real ingested injection payload in `tests/test_security.py`.
- **Poisoned documents**: a document can claim anything, but every citation
  still resolves to a real, hash-verified Postgres row — a human can always
  audit a PASS/FAIL back to its source.
- **Injection against tool queries**: SQL and Cypher injection attempts are
  passed as bound parameters everywhere (SQLAlchemy, Neo4j driver) — verified
  with real attack-string payloads, not just static review.
- **Read-only agent tools**: `TOOL_REGISTRY` is a closed allowlist of exactly
  two read-only tools; tests assert no write operations appear in their
  source and that running the agent never changes row counts.
- **CORS**: explicit localhost-only allowlist, no wildcard origin.

## Evaluation

Run the evaluation suite yourself (requires the backend's Postgres/Neo4j):

```bash
uv run pytest tests/test_evaluation.py -s
```

Last-measured results (synthetic dataset + a real public corpus — Kubernetes
Pod Security Standards, NIST CSF, OWASP Top 10 A01/A02; see
`data/samples/public/SOURCES.md` for licenses):

| Metric | Value |
|---|---|
| Recall@5 / Recall@10 | 1.00 / 1.00 |
| MRR / nDCG@5 | 1.00 / 1.00 |
| Baseline (lexical-only) Recall@5 vs ArchLens (hybrid+rerank) Recall@5 | 0.125 vs 1.00 |
| Finding correctness / completeness | 1.00 / 1.00 |
| Citation accuracy | 34/34 citations verified against real Postgres rows |
| Groundedness (mean) | 1.00 |
| False-confidence rate (abstention on unanswerable questions) | 0.00 |
| `/review` latency (template provider) | ≈0.15s |
| `/answer` latency (template provider) | ≈1.5s |

These numbers reflect a small, curated golden set (`app/evaluation/golden.py`)
against a small corpus — they demonstrate the pipeline works correctly, not
production-scale performance.

## Running the tests

```bash
# backend — 127 tests, requires Docker services running
uv run pytest -q

# frontend unit/component tests
cd frontend && npm run test

# frontend E2E (starts its own dev server; live-backend.spec.ts
# auto-skips if the FastAPI backend isn't running on :8000)
cd frontend && npx playwright install chromium   # first time only
npm run test:e2e

# production build
cd frontend && npm run build
```

## Known limitations

- Vision-based relationship extraction from diagrams is weak/often produces
  no relationships (OCR-based extraction works well; captioning models tried
  locally were not reliable enough for structured relationship output) — see
  ADR-008.
- No multi-tenancy / auth — single-tenant by design (ADR in
  `docs/DECISIONS.md`).
- Neo4j has no dedicated test database; graph-related tests wipe the graph
  before running, documented as an accepted limitation rather than worked
  around.
- The Evaluation dashboard tab shows the last-measured pytest results, not a
  live recomputation — the frontend has no mechanism to trigger and stream a
  multi-minute pytest run.
- No cloud deployment configuration is included; this is a local-first,
  single-machine portfolio project.
