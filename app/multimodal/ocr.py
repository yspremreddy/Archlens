"""Local OCR via RapidOCR (ONNX runtime) — the same local, open-source,
no-API-key pattern already used for embeddings and reranking elsewhere
in this project (see docs/DECISIONS.md ADR-001/ADR-006). Always on: OCR
needs no model choice/opt-in, unlike vision captioning
(app/multimodal/vision.py), so a diagram is always at least
text-searchable via whatever labels it contains.

Returns text regions with pixel-space bounding boxes — the basis for
`chunks.bbox` (docs/SCHEMA.md, extended by this phase; see
docs/DECISIONS.md ADR-008), so a citation for OCR'd text can point at
the exact region of the image it came from, not just "somewhere in this
diagram."
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class OcrRegion:
    text: str
    confidence: float
    bbox: dict  # {"x0", "y0", "x1", "y1"} in pixel coordinates


@lru_cache
def _get_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def extract_regions(image: Image.Image) -> list[OcrRegion]:
    engine = _get_engine()
    array = np.array(image.convert("RGB"))
    result, _ = engine(array)
    if not result:
        return []

    regions = []
    for box, text, confidence in result:
        if not text.strip():
            continue
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        regions.append(
            OcrRegion(
                text=text,
                confidence=float(confidence),
                bbox={"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)},
            )
        )
    return regions
