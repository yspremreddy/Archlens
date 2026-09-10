"""Text chunking for Phase 1 (plain text / markdown only).

Chunking strategy: pack paragraphs (split on blank lines) greedily into
chunks up to `max_chars`, respecting paragraph boundaries where possible.
A single paragraph longer than `max_chars` is hard-split. This is the
simplest strategy that preserves readable chunk boundaries; more
sophisticated (sentence-aware, token-aware) chunking can replace it later
if evaluation shows it matters (per CLAUDE.md rule 8 — simple first).

`token_count` is a whitespace word-count approximation, not a real
tokenizer count — it's stored as informational metadata only (see
docs/SCHEMA.md `chunks.token_count`), not used for any correctness-
critical decision here.
"""

from dataclasses import dataclass

DEFAULT_MAX_CHARS = 1000


@dataclass(frozen=True)
class ChunkSpan:
    index: int
    text: str
    start_offset: int
    end_offset: int
    token_count: int


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[ChunkSpan]:
    if not text.strip():
        return []

    paragraphs = _split_paragraphs_with_offsets(text)

    spans: list[ChunkSpan] = []
    current_parts: list[str] = []
    current_start: int | None = None
    current_end: int | None = None

    def flush() -> None:
        if not current_parts:
            return
        chunk_str = "\n\n".join(current_parts).strip()
        if not chunk_str:
            return
        spans.append(
            ChunkSpan(
                index=len(spans),
                text=chunk_str,
                start_offset=current_start,
                end_offset=current_end,
                token_count=len(chunk_str.split()),
            )
        )

    for para_text, para_start, para_end in paragraphs:
        if len(para_text) > max_chars:
            flush()
            current_parts, current_start, current_end = [], None, None
            for sub_start in range(0, len(para_text), max_chars):
                sub_text = para_text[sub_start : sub_start + max_chars]
                spans.append(
                    ChunkSpan(
                        index=len(spans),
                        text=sub_text.strip(),
                        start_offset=para_start + sub_start,
                        end_offset=para_start + sub_start + len(sub_text),
                        token_count=len(sub_text.split()),
                    )
                )
            continue

        prospective_len = sum(len(p) for p in current_parts) + len(para_text)
        if current_parts and prospective_len > max_chars:
            flush()
            current_parts, current_start, current_end = [], None, None

        if current_start is None:
            current_start = para_start
        current_end = para_end
        current_parts.append(para_text)

    flush()
    return [s for s in spans if s.text]


def _split_paragraphs_with_offsets(text: str) -> list[tuple[str, int, int]]:
    paragraphs: list[tuple[str, int, int]] = []
    start = 0
    n = len(text)
    while start < n:
        sep = text.find("\n\n", start)
        end = sep if sep != -1 else n
        para = text[start:end]
        stripped = para.strip()
        if stripped:
            offset = start + para.find(stripped)
            paragraphs.append((stripped, offset, offset + len(stripped)))
        start = end + 2 if sep != -1 else n
    return paragraphs
