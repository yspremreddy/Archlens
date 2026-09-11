"""Vision-model abstraction for diagram captioning and relationship
extraction. Mirrors app/generation/providers.py's LLMProvider pattern
deliberately — same shape, same reasoning (docs/DECISIONS.md ADR-005):

- `NoOpVisionProvider` (default, `VISION_PROVIDER=none`): returns no
  caption. A diagram is still fully searchable via OCR text
  (app/multimodal/ocr.py) with this provider — only the vision *caption*
  chunk and vision-derived relationship extraction are skipped. Honest
  about not having actually looked at the image (CLAUDE.md rule 3),
  rather than fabricating a description.
- `OllamaVisionProvider` (`VISION_PROVIDER=ollama`): calls a
  locally-running Ollama server with a vision-capable model (default
  `moondream`, ~1.7GB) — free, local, no API key. Separate from the text
  `OllamaProvider` (app/generation/providers.py) because captioning
  needs a vision-capable model, which the text pipeline's `llama3.2:1b`
  is not.
"""

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import Settings, get_settings

NOOP_VISION_PROVIDER_NAME = "noop"
OLLAMA_VISION_PROVIDER_NAME = "ollama-vision"


@dataclass(frozen=True)
class VisionResult:
    caption: str
    provider: str
    model: str


class VisionProviderError(RuntimeError):
    """Raised when a real vision backend fails or is unreachable — never
    silently swallowed into a fabricated caption (CLAUDE.md rule 3)."""


class VisionProvider(ABC):
    @abstractmethod
    def describe(self, image_bytes: bytes, *, prompt: str) -> VisionResult | None: ...


class NoOpVisionProvider(VisionProvider):
    def describe(self, image_bytes: bytes, *, prompt: str) -> VisionResult | None:
        del image_bytes, prompt
        return None


class OllamaVisionProvider(VisionProvider):
    def __init__(self, *, host: str, model: str, timeout_seconds: float):
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    def describe(self, image_bytes: bytes, *, prompt: str) -> VisionResult:
        try:
            resp = httpx.post(
                f"{self._host}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "images": [base64.b64encode(image_bytes).decode("ascii")],
                    "stream": False,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise VisionProviderError(
                f"Ollama vision request failed (host={self._host}, model={self._model}): {exc}"
            ) from exc

        data = resp.json()
        text = data.get("response")
        if not text:
            raise VisionProviderError(f"Ollama returned no 'response' field: {data!r}")
        return VisionResult(
            caption=text.strip(), provider=OLLAMA_VISION_PROVIDER_NAME, model=self._model
        )


def build_vision_provider(settings: Settings) -> VisionProvider:
    if settings.vision_provider == "ollama":
        return OllamaVisionProvider(
            host=settings.ollama_host,
            model=settings.vision_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    return NoOpVisionProvider()


@lru_cache
def get_vision_provider() -> VisionProvider:
    return build_vision_provider(get_settings())
