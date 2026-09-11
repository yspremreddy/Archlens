"""LLM provider abstraction for Phase 3 generation.

Two local/free providers, no paid API, no API key ever required:

- `TemplateExtractiveProvider` (default): zero-dependency, deterministic,
  builds an answer purely by extracting/quoting from the retrieved
  context. Always available — no model download, no external service —
  so the retrieve->generate pipeline works out of the box and tests never
  depend on network access or a multi-GB model. It is explicitly NOT a
  language model; `LLMResult.provider` is always labeled
  "template-extractive" so callers (and engineering guideline 3 — don't
  fabricate results) can tell the difference from real generation.
- `OllamaProvider`: calls a locally-running Ollama server
  (https://ollama.com — free, open-source, runs entirely on the caller's
  machine, no API key). Requires the user to install Ollama and pull a
  model themselves (e.g. `ollama pull llama3.2:1b`); this is a real local
  LLM, chosen over bundling a model via llama-cpp-python/transformers
  because those add heavy compiled/GPU-framework dependencies to the
  project itself, whereas Ollama is an external, independently-installed
  local service — the same pattern this project already uses for
  Postgres (docker-compose, not a pip dependency).

Selected via `Settings.llm_provider` ("template" | "ollama").
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import Settings, get_settings
from app.generation.prompts import extract_first_context_passage

TEMPLATE_PROVIDER_NAME = "template-extractive"
OLLAMA_PROVIDER_NAME = "ollama"

UNKNOWN_ANSWER = "UNKNOWN: insufficient evidence in the retrieved context."


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: str
    model: str


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, *, system_prompt: str, user_prompt: str) -> LLMResult: ...


class LLMProviderError(RuntimeError):
    """Raised when a real LLM backend fails or is unreachable — never
    silently swallowed into a fabricated answer (engineering guideline 3)."""


class TemplateExtractiveProvider(LLMProvider):
    """Deterministic, non-LLM fallback: quotes the single most relevant
    retrieved passage (the caller puts the top-ranked chunk first in the
    context, as [1]) verbatim, or returns the UNKNOWN sentinel if no
    context was given. This guarantees a grounded, citation-backed answer
    is always producible locally with zero setup — at the cost of not
    actually synthesizing across multiple chunks the way a real LLM would.
    """

    def generate(self, *, system_prompt: str, user_prompt: str) -> LLMResult:
        # system_prompt is intentionally unused: this provider does no
        # instruction-following at all, so there is nothing for a system
        # prompt to constrain — it's accepted only to satisfy the
        # LLMProvider interface uniformly across providers.
        del system_prompt
        passage = extract_first_context_passage(user_prompt)
        if passage is None:
            text = UNKNOWN_ANSWER
        else:
            text = f"[1] {passage}"
        return LLMResult(text=text, provider=TEMPLATE_PROVIDER_NAME, model="n/a")


class OllamaProvider(LLMProvider):
    def __init__(self, *, host: str, model: str, timeout_seconds: float):
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    def generate(self, *, system_prompt: str, user_prompt: str) -> LLMResult:
        try:
            resp = httpx.post(
                f"{self._host}/api/generate",
                json={
                    "model": self._model,
                    "system": system_prompt,
                    "prompt": user_prompt,
                    "stream": False,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"Ollama request failed (host={self._host}, model={self._model}): {exc}"
            ) from exc

        data = resp.json()
        text = data.get("response")
        if not text:
            raise LLMProviderError(f"Ollama returned no 'response' field: {data!r}")
        return LLMResult(text=text.strip(), provider=OLLAMA_PROVIDER_NAME, model=self._model)


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "ollama":
        return OllamaProvider(
            host=settings.ollama_host,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    return TemplateExtractiveProvider()


@lru_cache
def get_llm_provider() -> LLMProvider:
    return build_llm_provider(get_settings())
