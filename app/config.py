from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment variables / .env.

    No defaults here are real secrets — see CLAUDE.md rule 5. Local-dev
    Postgres credentials in .env.example are placeholders for a
    Docker-only local database, not anything deployed.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_db: str = "archlens"
    postgres_user: str = "archlens"
    postgres_password: str = "archlens_dev_password"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    database_url: str | None = None

    storage_dir: str = "./data/storage"

    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # LLM provider for Phase 3 generation — "template" (default, zero
    # dependency, deterministic extractive fallback) or "ollama" (real
    # local LLM inference via a locally-running Ollama server). Both are
    # local/free, no API key, no paid API — see app/generation/providers.py.
    llm_provider: str = "template"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    ollama_timeout_seconds: float = 60.0

    groundedness_min_score: float = 0.3

    # Phase 4 reranking — local cross-encoder (ONNX via fastembed, same
    # approach as embedding_model_name above: no torch, no API key).
    # Applied after hybrid retrieval and before generation, and only to
    # the top rerank_candidate_pool candidates (see app/retrieval/rerank.py).
    rerank_enabled: bool = True
    rerank_model_name: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    rerank_candidate_pool: int = 20

    # Phase 5 — Neo4j (Community Edition, local via Docker, free, no
    # license). Graph nodes/edges store Postgres ids as properties so
    # every graph fact can be traced back to its source document/chunk —
    # see app/graph/.
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "archlens_dev_password"
    graph_max_hops: int = 4

    # Phase 6 — multimodal ingestion. OCR (rapidocr-onnxruntime — ONNX,
    # same local/no-API-key pattern as embedding/reranking) always runs;
    # it needs no model choice. Vision captioning/relationship extraction
    # is optional and off by default ("none" — a diagram is still fully
    # OCR-searchable with no vision model at all), matching the
    # LLM_PROVIDER=template default-safe pattern from Phase 3. Set to
    # "ollama" to use a real local vision-capable model (default
    # `moondream`, ~1.7GB) via the same locally-running Ollama server the
    # text LLM provider uses. See app/multimodal/vision.py.
    vision_provider: str = "none"
    vision_model: str = "moondream"

    # Phase 7 — bounded agentic reasoning (app/agent/) and the policy
    # engine (app/policy/). Hard caps: the agent never takes more than
    # agent_max_steps tool calls, and stops (returning best evidence so
    # far) once agent_time_budget_seconds has elapsed — never an
    # open-ended loop, per docs/ARCHITECTURE.md "Bounded agentic
    # reasoning".
    agent_max_steps: int = 4
    agent_time_budget_seconds: float = 20.0
    policy_min_relevance_overlap: float = 0.05

    # Phase 9 — OpenTelemetry tracing. Off by default (zero behavior
    # change, zero new required infra); when enabled, spans export via
    # OTLP to a locally-run, free Arize Phoenix instance (or any other
    # local OTLP collector) — no paid observability SaaS, per CLAUDE.md
    # rule 8. See app/tracing.py.
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "archlens-api"

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
