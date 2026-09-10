"""Local embedding generation via fastembed (ONNX runtime).

Chosen over sentence-transformers/torch for Phase 1 because fastembed has
no torch/CUDA dependency (much smaller, faster install) while running the
same open-source sentence-embedding model class fully locally — no API
key, no network calls at inference time (see docs/SCHEMA.md §8 and
docs/DECISIONS.md). Model weights are downloaded once from Hugging Face
on first use and cached under the user's local fastembed cache directory;
after that, embedding is fully offline.
"""

from functools import lru_cache

from fastembed import TextEmbedding

from app.config import get_settings


@lru_cache
def _get_model() -> TextEmbedding:
    settings = get_settings()
    return TextEmbedding(model_name=settings.embedding_model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    return [vec.tolist() for vec in model.embed(texts)]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
