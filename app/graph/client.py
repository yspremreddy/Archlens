"""Neo4j driver singleton.

Neo4j is an independently-running local Docker service (docker-compose.yml,
Community Edition — free, no license), not a bundled dependency — the
same pattern this project already uses for Postgres and Ollama (see
docs/DECISIONS.md ADR-005). The driver here only knows how to connect to
it; schema and query logic live in app/graph/schema.py and
app/graph/retrieval.py.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from neo4j import Driver, GraphDatabase, Session

from app.config import get_settings


@lru_cache
def get_driver() -> Driver:
    settings = get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


@contextmanager
def get_graph_session() -> Iterator[Session]:
    with get_driver().session() as session:
        yield session
