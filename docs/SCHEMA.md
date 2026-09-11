# ArchLens — Phase 1 Schema (PostgreSQL + pgvector)

This is the detailed, column-level schema for Phase 1 (see
docs/ROADMAP.md). It supersedes the conceptual sketch in
docs/ARCHITECTURE.md §5, which now points here.

**This document is a design spec, not a migration.** No migration files,
ORM models, or application code exist yet — this defines what they will
build, so it can be reviewed before anything is written.

## 0. Conventions used throughout

- **Primary keys:** `uuid`, generated with `gen_random_uuid()` (pgcrypto,
  or `uuid-ossp` — pick one when the extension is actually enabled in
  Phase 1 setup; noted here as a Phase 1 implementation detail, not a
  design fork).
- **Timestamps:** `timestamptz`, always UTC. Every table has `created_at
  timestamptz NOT NULL DEFAULT now()`. Tables whose rows can be mutated
  after creation also have `updated_at timestamptz NOT NULL DEFAULT
  now()`, maintained by the application layer for now — no DB triggers in
  Phase 1, since there's no concurrent-writer scenario yet that needs
  DB-enforced consistency (keep it simple per CLAUDE.md rule 8; revisit if
  multiple writers emerge).
- **Append-only tables** (`audit_log`) have `created_at` only — no
  `updated_at`, no update/delete path in the application.
- **Hashing:** `content_hash` fields are `text` storing a `sha256` hex
  digest (`sha256:<64 hex chars>` prefix convention, so the algorithm is
  self-describing if it ever changes) of the exact bytes/text being
  fingerprinted. Used for dedup detection and for provenance — a claim
  can be checked against the exact byte content it was derived from, not
  just a row id that might later change.
- **Soft multi-tenancy readiness:** per the single-tenant-MVP decision, no
  `tenant_id` column is added to any table now (adding unused columns
  ahead of need contradicts rule 8's "don't build ahead of what's
  requested"). What keeps this extensible instead: every table uses a
  surrogate `uuid` primary key (not a natural key), and no business logic
  or unique constraint anywhere assumes single-tenancy implicitly (e.g.
  no `UNIQUE(name)` that would break the moment two tenants both have a
  component called "auth-service"). Adding `tenant_id` later is a
  straightforward additive migration (new nullable column, backfill,
  then constrain) rather than a redesign. This is recorded as a decision
  to revisit, not deferred silently — see docs/ARCHITECTURE.md §8.
- **Deletes:** nothing in Phase 1 has a hard-delete path from the API.
  Foreign keys use `ON DELETE CASCADE` only where the child row is
  meaningless without the parent (e.g. a chunk without its document), and
  `ON DELETE RESTRICT` where deleting the parent should be blocked while
  evidence still points to it (e.g. a chunk cited by a finding).

## 1. `documents`

The uploaded source artifact and its ingestion status. System of record
for "what was uploaded and what happened to it."

| Column            | Type          | Constraints                                   | Notes |
|--------------------|--------------|------------------------------------------------|-------|
| `id`               | uuid          | PK, default `gen_random_uuid()`                | |
| `source_type`      | text          | NOT NULL, CHECK (`source_type IN ('upload')`)  | Deliberately a single valid value for now (uploaded files are the primary source per current decision). The CHECK constraint is there so adding a new source type later — a connected repo — is a one-line constraint change, not a schema redesign. |
| `original_filename`| text          | NOT NULL                                        | As provided by the uploader; untrusted, never used as a path. |
| `mime_type`        | text          | NULL                                             | Detected, not trusted from the client header alone. |
| `file_size_bytes`  | bigint        | NOT NULL, CHECK (`file_size_bytes >= 0`)        | |
| `storage_path`     | text          | NOT NULL                                        | Where the raw file bytes live (local filesystem path in Phase 1, per "reuse existing local setup" direction — object storage is a later swap, not a schema change). |
| `content_hash`     | text          | NOT NULL                                        | sha256 of the raw uploaded bytes. Not UNIQUE — re-uploading the same file is allowed (e.g. a revised review pass) and produces a new `documents` row; the hash is for integrity/dedup *detection*, not a dedup *constraint*. |
| `status`           | text          | NOT NULL, DEFAULT `'pending'`, CHECK (`status IN ('pending','ingested','failed')`) | |
| `error_message`    | text          | NULL                                             | Populated only when `status = 'failed'`. |
| `uploaded_by`      | text          | NULL                                             | Stub field — no auth system exists yet, so this holds an opaque identifier when one is available and is otherwise null. Not a FK to a `users` table, since none exists in Phase 1. |
| `uploaded_at`      | timestamptz   | NOT NULL, DEFAULT `now()`                       | |
| `ingested_at`      | timestamptz   | NULL                                             | Set when ingestion (chunking+embedding) completes successfully. |
| `created_at`       | timestamptz   | NOT NULL, DEFAULT `now()`                       | |
| `updated_at`       | timestamptz   | NOT NULL, DEFAULT `now()`                       | |

**Indexes:**
- `idx_documents_status` on `(status)` — ingestion worker needs to find
  pending documents efficiently.
- `idx_documents_content_hash` on `(content_hash)` — supports "has this
  exact file been uploaded before" checks without being a uniqueness
  constraint.

## 2. `chunks`

A retrieval-unit slice of a document's text, with its embedding.

| Column         | Type            | Constraints                                    | Notes |
|-----------------|----------------|--------------------------------------------------|-------|
| `id`            | uuid            | PK, default `gen_random_uuid()`                  | |
| `document_id`   | uuid            | NOT NULL, FK → `documents(id)` ON DELETE CASCADE  | A chunk has no meaning without its document. |
| `chunk_index`   | integer         | NOT NULL, CHECK (`chunk_index >= 0`)              | Order within the document. |
| `text`          | text            | NOT NULL, CHECK (`length(text) > 0`)              | |
| `start_offset`  | integer         | NULL                                               | Character offset into the source text, where derivable (plain text/markdown). Null for formats where an offset isn't meaningful (e.g. PDF page-based extraction). |
| `end_offset`    | integer         | NULL                                               | |
| `page_number`   | integer         | NULL                                               | For paginated sources. Null for plain text/markdown; `1` for a standalone image (Phase 6); the actual page index for a multi-page PDF (both text-PDF-as-prose and image/PDF-page ingestion — Phase 6 — populate this the same way). |
| `token_count`   | integer         | NULL                                               | Populated by the chunker; informational, used for chunk-size tuning. |
| `content_hash`  | text            | NOT NULL                                           | sha256 of `text`, exactly as stored. This is the field a `finding`'s evidence citation is ultimately checked against. |
| `embedding`     | vector(384)     | NULL                                               | pgvector column. **Dimension 384 assumes a local, open-source sentence-embedding model (e.g. `all-MiniLM-L6-v2`-class) per CLAUDE.md rule 8 — this is a placeholder assumption, not a confirmed decision, and needs sign-off before the ingestion pipeline is built (tracked in TODO.md).** Nullable because a chunk can exist (from chunking) before embedding runs — ingestion is chunk-then-embed as two steps, not atomic. |
| `modality`      | text            | NOT NULL, DEFAULT `'text'`, CHECK (`modality IN ('text','image_ocr','image_caption')`) | **Added Phase 6** (migration `cc8e51c1a598`). Distinguishes a plain text-document chunk from one derived from an uploaded image/PDF page — OCR'd text (`image_ocr`) or a vision-model caption (`image_caption`). All pre-Phase-6 rows default to `'text'` with no backfill needed. Deliberately a column on the *same* table, not a separate one — see docs/DECISIONS.md ADR-008: a chunk is a chunk regardless of modality, embedded and retrieved identically. |
| `bbox`          | jsonb           | NULL                                               | **Added Phase 6.** Pixel-space bounding box (`{"x0","y0","x1","y1"}`) for an `image_ocr` chunk (the OCR engine's detected text region) or the whole-page box for an `image_caption` chunk. Null for `'text'` chunks, which use `start_offset`/`end_offset` instead — region provenance for images, character-offset provenance for prose, same idea applied to the two different source formats. |
| `created_at`    | timestamptz     | NOT NULL, DEFAULT `now()`                          | |

**Constraints:**
- `UNIQUE(document_id, chunk_index)` — no two chunks of the same document
  can claim the same position.

**Indexes:**
- `idx_chunks_document_id` on `(document_id)` — fetch all chunks for a
  document.
- `idx_chunks_content_hash` on `(content_hash)`.
- `idx_chunks_text_fts` — **added in Phase 2.** A functional GIN index on
  `to_tsvector('english', text)`, backing lexical retrieval
  (`app/retrieval/lexical.py`). A functional index rather than a stored
  `tsvector` column: no extra column to keep in sync, and Postgres uses
  the index automatically as long as queries build the identical
  expression.
- `idx_chunks_embedding_hnsw` — **added in Phase 2.** An HNSW index
  (`vector_cosine_ops`) on `embedding`, backing vector retrieval
  (`app/retrieval/vector.py`). HNSW rather than `ivfflat`: no
  list-count/training step needed, and pgvector 0.8.x (bundled in the
  `pgvector/pgvector:pg16` image) supports it natively. This is the
  index Phase 1 explicitly deferred — see the note below, now resolved.
- `idx_chunks_modality` — **added in Phase 6.** Backs the `modality`
  structured filter (`app/retrieval/filters.py`) — "search only diagram
  text" is a common enough query shape to index directly.

## 3. `components`

Architecture entities extracted from (or manually recorded from)
ingested documents — services, data stores, queues, external systems.
This is the structured-retrieval substrate (ARCHITECTURE.md's
"structured retrieval" and future Neo4j graph nodes both derive from
this table later; Phase 1 only needs the table itself, no extraction
logic yet).

| Column               | Type    | Constraints                                    | Notes |
|-----------------------|--------|--------------------------------------------------|-------|
| `id`                  | uuid    | PK, default `gen_random_uuid()`                  | |
| `name`                | text    | NOT NULL                                          | Not globally unique — see tenancy note in §0; also the same real-world component can legitimately be named the same as something in an unrelated doc. |
| `type`                | text    | NOT NULL, CHECK (`type IN ('service','datastore','queue','external_system','other')`) | Small fixed vocabulary for Phase 1; extend the CHECK list as real data demands rather than open-texting it. |
| `description`         | text    | NULL                                               | |
| `owner`               | text    | NULL                                               | Free text in Phase 1 (no owner/user directory exists). |
| `tags`                | text[]  | NOT NULL, DEFAULT `'{}'`                          | Simple array is sufficient for Phase 1 filtering; not `jsonb`, since tags are just labels, not structured data. |
| `source_document_id`  | uuid    | NULL, FK → `documents(id)` ON DELETE SET NULL      | Provenance: which document this was recorded/extracted from. Nullable because Phase 1 may include manually-entered components with no source document. `SET NULL` rather than `CASCADE`/`RESTRICT`: losing the source document shouldn't destroy or block deletion of a component that's since been corroborated elsewhere — but see the note below, this is worth confirming once extraction actually exists. |
| `source_chunk_id`     | uuid    | NULL, FK → `chunks(id)` ON DELETE SET NULL         | Finer-grained provenance than the document alone, when known. |
| `extraction_method`   | text    | NOT NULL, DEFAULT `'manual'`, CHECK (`extraction_method IN ('manual','llm_extracted','rule_based','vision_extracted')`) | Phase 1 shipped manual entry only, with the column unpopulated. Phase 5 adds `'rule_based'` (migration `540fcff68f20`) — a regex extractor over prose (`app/graph/extraction.py`). Phase 6 adds `'vision_extracted'` (migration `cc8e51c1a598`) — components read from OCR'd diagram labels, relationships (when present) parsed from a vision-model caption (`app/multimodal/graph.py`); distinct from `'rule_based'` since the source is an image, not prose, even though component *names* come from OCR text recognition rather than "vision understanding" per se — see docs/DECISIONS.md ADR-008. |
| `created_at`          | timestamptz | NOT NULL, DEFAULT `now()`                     | |
| `updated_at`          | timestamptz | NOT NULL, DEFAULT `now()`                     | |

**Indexes:**
- `idx_components_type` on `(type)`.
- `idx_components_source_document_id` on `(source_document_id)`.
- GIN index on `tags` (`idx_components_tags`) for tag-filtered lookups.

## 4. `compliance_controls`

The (initially small, custom) set of controls findings can be checked
against.

| Column         | Type        | Constraints                                | Notes |
|-----------------|------------|----------------------------------------------|-------|
| `id`            | uuid        | PK, default `gen_random_uuid()`              | |
| `framework`     | text        | NOT NULL, DEFAULT `'archlens-custom'`        | Single custom framework value for now, per current decision; not a CHECK-constrained enum like `documents.source_type` because framework names are expected to genuinely multiply later (SOC2, HIPAA, etc.) rather than move through one or two known states. |
| `control_code`  | text        | NOT NULL                                      | e.g. `AC-1`. Scoped to be unique within a framework, not globally. |
| `title`         | text        | NOT NULL                                      | |
| `description`   | text        | NULL                                           | |
| `category`      | text        | NULL                                           | Free-text grouping (e.g. "access control", "data retention"); not a FK to a separate categories table — not warranted at this size. |
| `created_at`    | timestamptz | NOT NULL, DEFAULT `now()`                     | |
| `updated_at`    | timestamptz | NOT NULL, DEFAULT `now()`                     | |

**Constraints:**
- `UNIQUE(framework, control_code)`.

**Indexes:**
- Covered by the unique constraint above; no additional index needed at
  Phase 1 scale (a small custom set).

## 5. `findings`

A risk/compliance claim the system has produced, with its evidence.

| Column          | Type        | Constraints                                                     | Notes |
|------------------|------------|--------------------------------------------------------------------|-------|
| `id`             | uuid        | PK, default `gen_random_uuid()`                                    | |
| `title`          | text        | NOT NULL                                                            | Short label. |
| `statement`      | text        | NOT NULL                                                            | The actual claim/finding text. |
| `status`         | text        | NOT NULL, DEFAULT `'open'`, CHECK (`status IN ('open','resolved','dismissed')`) | |
| `confidence`     | numeric(3,2)| NULL, CHECK (`confidence IS NULL OR (confidence >= 0 AND confidence <= 1)`) | Null means "not yet scored," not zero confidence — Phase 1 has no generation step to produce this value yet (that's Phase 3), so this column exists but stays null until then. |
| `control_id`     | uuid        | NULL, FK → `compliance_controls(id)` ON DELETE RESTRICT            | A finding tied to a control shouldn't be able to silently lose that link via an unrelated control deletion. |
| `component_id`   | uuid        | NULL, FK → `components(id)` ON DELETE SET NULL                     | Which component the finding is about, when applicable. |
| `created_by`     | text        | NULL                                                                 | Same stub convention as `documents.uploaded_by`. |
| `verdict`        | text        | NULL, CHECK (`verdict IS NULL OR verdict IN ('PASS','FAIL','UNKNOWN','CONFLICT')`) | **Added Phase 7** (migration `9fbf4e4d16c0`). Set by the policy engine (`app/policy/`, `POST /review`); null for a Phase 3 `/answer` finding, which is a free-text answer, not a policy check. |
| `severity`       | text        | NULL, CHECK (`severity IS NULL OR severity IN ('low','medium','high','critical')`) | **Added Phase 7.** Set alongside `verdict`; null otherwise. |
| `created_at`     | timestamptz | NOT NULL, DEFAULT `now()`                                           | |
| `updated_at`     | timestamptz | NOT NULL, DEFAULT `now()`                                           | |

**Indexes:**
- `idx_findings_status` on `(status)`.
- `idx_findings_control_id` on `(control_id)`.
- `idx_findings_verdict` on `(verdict)` — **added Phase 7.**
- `idx_findings_component_id` on `(component_id)`.

### 5a. `finding_evidence` (join table — part of the findings design)

A finding must cite the exact chunks it's grounded in (CLAUDE.md rule 7).
A finding can cite multiple chunks, and a chunk can support multiple
findings, so this is a genuine many-to-many relationship — modeled as a
join table rather than an array/jsonb column on `findings` so each
citation is independently queryable and referentially enforced (you
cannot cite a chunk that doesn't exist, and — per the RESTRICT below —
cannot delete a chunk out from under an existing citation).

| Column           | Type        | Constraints                                          | Notes |
|-------------------|------------|----------------------------------------------------------|-------|
| `id`              | uuid        | PK, default `gen_random_uuid()`                          | |
| `finding_id`      | uuid        | NOT NULL, FK → `findings(id)` ON DELETE CASCADE           | Evidence rows are meaningless without their finding. |
| `chunk_id`        | uuid        | NOT NULL, FK → `chunks(id)` ON DELETE RESTRICT             | Deleting a chunk that's cited as evidence is blocked — provenance must not be able to silently disappear (CLAUDE.md rule 7). |
| `relevance_note`  | text        | NULL                                                       | Optional free text on why this chunk supports the finding. |
| `created_at`      | timestamptz | NOT NULL, DEFAULT `now()`                                  | |

**Constraints:**
- `UNIQUE(finding_id, chunk_id)` — no duplicate citations of the same
  chunk on the same finding.

**Indexes:**
- `idx_finding_evidence_finding_id` on `(finding_id)`.
- `idx_finding_evidence_chunk_id` on `(chunk_id)`.

## 6. `audit_log`

Append-only record of system events, independent of and in addition to
the provenance already carried by `finding_evidence` — this is "who/what
did something and when," not "what evidence supports this claim."

| Column        | Type        | Constraints                                    | Notes |
|----------------|------------|---------------------------------------------------|-------|
| `id`           | uuid        | PK, default `gen_random_uuid()`                   | |
| `event_type`   | text        | NOT NULL                                           | e.g. `document.uploaded`, `document.ingested`, `document.ingestion_failed`, `finding.created`, `finding.status_changed`. Free text (not a CHECK enum) — new event types are expected to be added routinely as functionality grows, and constraining this table would mean a migration every time. |
| `entity_type`  | text        | NOT NULL                                           | e.g. `document`, `chunk`, `finding`. |
| `entity_id`    | uuid        | NULL                                                | Not a FK — audit rows must survive even if the referenced entity is later deleted; enforcing referential integrity here would defeat the purpose of an audit trail. |
| `actor`        | text        | NULL                                                | Same stub convention as elsewhere; null when the action was system-initiated (e.g. the ingestion worker) rather than user-initiated. |
| `detail`       | jsonb       | NULL                                                | Event-specific structured payload (e.g. `{"filename": "...", "size_bytes": ...}`). `jsonb` here (unlike `components.tags`) because event payloads are genuinely heterogeneous across event types. |
| `created_at`   | timestamptz | NOT NULL, DEFAULT `now()`                          | |

**Indexes:**
- `idx_audit_log_entity` on `(entity_type, entity_id)`.
- `idx_audit_log_event_type` on `(event_type)`.
- `idx_audit_log_created_at` on `(created_at)` — audit queries are
  typically time-ranged.

No update or delete path exists in the application for this table by
design (append-only).

## 7. Entity relationships (summary)

```
documents 1───* chunks
documents 1───* components        (source_document_id, nullable)
chunks    1───* components        (source_chunk_id, nullable)
components 1──* findings          (component_id, nullable)
compliance_controls 1──* findings (control_id, nullable)
findings  *───* chunks            (via finding_evidence)
(audit_log references entities informationally, no FK)
```

## 8. Implementation decisions (resolved during Phase 1 build)

1. **Embedding model / dimension — resolved: `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, via `fastembed`.**
   `fastembed` (Qdrant's ONNX-runtime-based embedding library) was chosen
   over `sentence-transformers`+`torch` because it produces the same
   model class fully locally, with no API key and no network calls at
   inference time, but without torch's much larger install footprint —
   a better fit for CLAUDE.md rule 8 ("prefer simple, open-source/local
   solutions") given Phase 1 has no GPU/training need, only inference.
   Model weights are downloaded once from Hugging Face on first use and
   cached locally (`app/ingestion/embedding.py`); every embedding call
   after that is offline. Confirms the `vector(384)` column type used in
   §2 — verified against `fastembed`'s supported model list (`dim: 384`)
   and by generating real embeddings during implementation.
2. **UUID generation — resolved: PostgreSQL's built-in `gen_random_uuid()`, no extension required.**
   As of PostgreSQL 13, `gen_random_uuid()` is a built-in function, not
   gated behind the `pgcrypto` or `uuid-ossp` extensions — confirmed
   against the `pgvector/pgvector:pg16` image used for local Docker
   Postgres (see docker-compose.yml). This is simpler than enabling an
   extension for no added benefit, so no `CREATE EXTENSION` statement
   for UUIDs appears in the migration (only `CREATE EXTENSION vector`
   does, which pgvector genuinely requires).
3. **`components` provenance FK behavior** (`ON DELETE SET NULL`) — still
   a reasonable default, still worth revisiting once real extraction
   exists. Not exercised yet: Phase 1 ships no extraction logic, so this
   remains a documented open item, not a blocking one.
