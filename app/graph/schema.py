"""Phase 5 graph schema — the first GraphRAG milestone.

Adapts the schema sketched in docs/ARCHITECTURE.md §5
(Nodes: Component, DataStore, DataFlow, TrustBoundary, Owner, ComplianceTag;
Edges: SENDS_DATA_TO, DEPENDS_ON, OWNED_BY, TAGGED_WITH, CROSSES_BOUNDARY)
to what this milestone actually needs and can populate from the existing
sample data. Documented deviations (see docs/DECISIONS.md ADR-007):

- A single `:Component` label with a `type` property (matching Postgres
  `components.type`: service/datastore/queue/external_system/other)
  instead of separate `:Component`/`:DataStore` labels — mirrors how
  Postgres already models it (one table, a type column) and avoids two
  divergent taxonomies to keep in sync.
- No `DataFlow` node — a data flow is represented directly as a
  `SENDS_DATA_TO` relationship between two `:Component` nodes, since the
  original sketch didn't specify what a separate DataFlow node would
  hold that the edge itself couldn't.
- `TrustBoundary` and `ComplianceTag` are not populated by this
  milestone's extractor — the sample data doesn't state either concept
  explicitly, and inventing values would fabricate facts not actually in
  the source documents (engineering guideline 3). The label/edge-type constants
  are reserved below for when real extraction for them exists.

Every node and relationship this milestone creates carries provenance
properties pointing back to Postgres: `pg_document_id`, `pg_chunk_id`
(the chunk whose text the fact was extracted from) — the same
evidence/provenance model already used by `finding_evidence`
(docs/SCHEMA.md §5a). `:Component` nodes additionally carry
`pg_component_id`, the id of their mirrored row in Postgres `components`.
"""

from app.graph.client import get_graph_session

COMPONENT_LABEL = "Component"
OWNER_LABEL = "Owner"

REL_SENDS_DATA_TO = "SENDS_DATA_TO"
REL_DEPENDS_ON = "DEPENDS_ON"
REL_OWNED_BY = "OWNED_BY"

# Reserved for future extraction — not populated by this milestone (see
# module docstring).
REL_CROSSES_BOUNDARY = "CROSSES_BOUNDARY"
REL_TAGGED_WITH = "TAGGED_WITH"
TRUST_BOUNDARY_LABEL = "TrustBoundary"
COMPLIANCE_TAG_LABEL = "ComplianceTag"


def ensure_graph_schema() -> None:
    """Idempotent — safe to call before every extraction run."""
    with get_graph_session() as session:
        session.run(
            "CREATE CONSTRAINT component_pg_id IF NOT EXISTS "
            "FOR (c:Component) REQUIRE c.pg_component_id IS UNIQUE"
        )
        session.run(
            "CREATE CONSTRAINT owner_name IF NOT EXISTS "
            "FOR (o:Owner) REQUIRE o.name IS UNIQUE"
        )
        session.run("CREATE INDEX component_name IF NOT EXISTS FOR (c:Component) ON (c.name)")
