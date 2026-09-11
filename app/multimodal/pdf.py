"""PDF page rendering via pypdfium2 — a pure pip-installable binding to
PDFium (no system Poppler/Ghostscript binary required), consistent with
CLAUDE.md rule 8 (prefer simple, local solutions with no extra install
steps beyond `uv sync`).

Each page is rendered to a raster image, then treated identically to an
uploaded image by the rest of the multimodal pipeline (OCR + optional
vision captioning) — "PDF-page ingestion" is not a separate code path,
just a source of per-page images.
"""

from PIL import Image


def render_pdf_pages(pdf_bytes: bytes, *, scale: float = 2.0) -> list[Image.Image]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        return [pdf[i].render(scale=scale).to_pil().convert("RGB") for i in range(len(pdf))]
    finally:
        pdf.close()
