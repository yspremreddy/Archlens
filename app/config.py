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
