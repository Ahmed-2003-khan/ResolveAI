from __future__ import annotations

import re
from dataclasses import dataclass, field

# ~512 tokens at 4 chars/token; 64-token overlap
_CHUNK_CHARS = 2048
_OVERLAP_CHARS = 256


@dataclass
class ChunkResult:
    content: str
    chunk_index: int
    total_chunks: int
    metadata: dict = field(default_factory=dict)


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines, dropping empty paragraphs."""
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _split_words(text: str, max_chars: int) -> list[str]:
    """Hard-split oversized paragraph on word boundaries."""
    chunks: list[str] = []
    buf = ""
    for word in text.split():
        if len(buf) + len(word) + 1 <= max_chars:
            buf = f"{buf} {word}".lstrip()
        else:
            if buf:
                chunks.append(buf)
            buf = word
    if buf:
        chunks.append(buf)
    return chunks or [text[:max_chars]]


def chunk_article(content: str) -> list[str]:
    """
    Paragraph-aware sliding window chunker.
    Window = 512 tokens (~2048 chars), overlap = 64 tokens (~256 chars).
    """
    paragraphs = _split_paragraphs(content)
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # Paragraph itself is too large — hard-split it first
        if len(para) > _CHUNK_CHARS:
            for sub in _split_words(para, _CHUNK_CHARS):
                if len(current) + len(sub) + 2 <= _CHUNK_CHARS:
                    current = f"{current}\n\n{sub}".strip()
                else:
                    if current:
                        chunks.append(current)
                        current = current[max(0, len(current) - _OVERLAP_CHARS) :].lstrip()
                    current = sub
            continue

        if len(current) + len(para) + 2 <= _CHUNK_CHARS:
            current = f"{current}\n\n{para}".strip() if current else para
        else:
            if current:
                chunks.append(current)
                current = current[max(0, len(current) - _OVERLAP_CHARS) :].lstrip()
            current = para

    if current:
        chunks.append(current)

    return chunks or [content[:_CHUNK_CHARS]]


def chunk_document(
    content: str,
    source_type: str,
    question: str | None = None,
    answer: str | None = None,
) -> list[ChunkResult]:
    """
    Dispatch chunking by source_type.
    - 'ticket' / 'faq': one chunk per item in Q/A format
    - 'article' / 'policy': sliding-window chunker
    """
    if source_type in ("ticket", "faq"):
        q = (question or "").strip()
        a = (answer or content).strip()
        text = f"Q: {q}\n\nA: {a}" if q else a
        return [ChunkResult(content=text, chunk_index=0, total_chunks=1)]

    raw = chunk_article(content)
    return [ChunkResult(content=c, chunk_index=i, total_chunks=len(raw)) for i, c in enumerate(raw)]
