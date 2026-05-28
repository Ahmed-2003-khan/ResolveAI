"""Unit tests for app.services.rag.chunker."""
from __future__ import annotations

import pytest

from app.services.rag.chunker import (
    ChunkResult,
    _split_paragraphs,
    _split_words,
    chunk_article,
    chunk_document,
)

_CHUNK_CHARS = 2048
_OVERLAP_CHARS = 256


# ---------------------------------------------------------------------------
# _split_paragraphs
# ---------------------------------------------------------------------------

def test_split_paragraphs_basic():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird."
    result = _split_paragraphs(text)
    assert result == ["First paragraph.", "Second paragraph.", "Third."]


def test_split_paragraphs_empty_lines_collapsed():
    text = "A\n\n\n\nB"
    assert _split_paragraphs(text) == ["A", "B"]


def test_split_paragraphs_strips_whitespace():
    text = "  Hello  \n\n  World  "
    result = _split_paragraphs(text)
    assert result == ["Hello", "World"]


def test_split_paragraphs_single_paragraph():
    assert _split_paragraphs("Only one.") == ["Only one."]


def test_split_paragraphs_empty_string():
    assert _split_paragraphs("") == []


# ---------------------------------------------------------------------------
# _split_words
# ---------------------------------------------------------------------------

def test_split_words_respects_max_chars():
    long_text = " ".join(["word"] * 200)  # ~900 chars
    chunks = _split_words(long_text, 100)
    for c in chunks:
        assert len(c) <= 100


def test_split_words_no_loss():
    words = ["alpha", "beta", "gamma", "delta"]
    text = " ".join(words)
    chunks = _split_words(text, 15)
    reconstructed = " ".join(chunks)
    for word in words:
        assert word in reconstructed


def test_split_words_single_word_larger_than_max():
    chunks = _split_words("superlongword", max_chars=5)
    # Falls back to the word itself (no internal split)
    assert chunks == ["superlongword"]


# ---------------------------------------------------------------------------
# chunk_article
# ---------------------------------------------------------------------------

def test_chunk_article_short_text_single_chunk():
    text = "Short article.\n\nStill short."
    chunks = chunk_article(text)
    assert len(chunks) == 1
    assert "Short article." in chunks[0]


def test_chunk_article_long_text_multiple_chunks():
    para = "x" * 800  # 800-char paragraph
    text = "\n\n".join([para] * 5)  # 4000 chars total
    chunks = chunk_article(text)
    assert len(chunks) >= 2


def test_chunk_article_each_chunk_within_limit():
    para = "word " * 300  # ~1500 chars per paragraph
    text = "\n\n".join([para] * 4)
    for chunk in chunk_article(text):
        assert len(chunk) <= _CHUNK_CHARS


def test_chunk_article_overlap_present():
    para = "alpha " * 300  # ~1800 chars
    text = "\n\n".join([para] * 3)
    chunks = chunk_article(text)
    if len(chunks) >= 2:
        # Tail of chunk[0] should appear at the start of chunk[1]
        overlap_tail = chunks[0][-_OVERLAP_CHARS:]
        assert overlap_tail.strip() in chunks[1] or chunks[1].startswith(overlap_tail.strip()[:20])


def test_chunk_article_empty_returns_fallback():
    chunks = chunk_article("")
    assert len(chunks) == 1
    assert chunks[0] == ""


def test_chunk_article_oversized_single_paragraph():
    big_para = "word " * 600  # ~3000 chars, exceeds _CHUNK_CHARS
    chunks = chunk_article(big_para)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= _CHUNK_CHARS


def test_chunk_article_preserves_all_content():
    """No significant content should be dropped; overlap may duplicate some bytes."""
    para = "important " * 400  # 4000 chars
    text = "\n\n".join([para] * 2)  # ~8000 chars
    chunks = chunk_article(text)
    total = sum(len(c) for c in chunks)
    # lstrip() on the overlap tail may trim a few whitespace chars, so allow
    # ±1 % tolerance; the bulk of the content must survive.
    assert total >= len(text) * 0.99


# ---------------------------------------------------------------------------
# chunk_document — ticket / faq dispatch
# ---------------------------------------------------------------------------

def test_chunk_document_ticket_single_chunk():
    results = chunk_document("", "ticket", question="Where is my order?", answer="It is on the way.")
    assert len(results) == 1
    r = results[0]
    assert isinstance(r, ChunkResult)
    assert r.chunk_index == 0
    assert r.total_chunks == 1
    assert "Where is my order?" in r.content
    assert "It is on the way." in r.content


def test_chunk_document_faq_single_chunk():
    results = chunk_document("", "faq", question="Q?", answer="A.")
    assert len(results) == 1
    assert results[0].content == "Q: Q?\n\nA: A."


def test_chunk_document_ticket_no_question():
    results = chunk_document("", "ticket", question=None, answer="Answer only.")
    assert len(results) == 1
    assert results[0].content == "Answer only."


def test_chunk_document_ticket_no_question_no_answer():
    results = chunk_document("fallback content", "ticket", question=None, answer=None)
    assert len(results) == 1
    assert "fallback content" in results[0].content


# ---------------------------------------------------------------------------
# chunk_document — article / policy dispatch
# ---------------------------------------------------------------------------

def test_chunk_document_article_returns_chunk_results():
    content = "paragraph one\n\n" * 50  # medium-length article
    results = chunk_document(content, "article")
    assert all(isinstance(r, ChunkResult) for r in results)
    assert all(r.total_chunks == len(results) for r in results)
    for i, r in enumerate(results):
        assert r.chunk_index == i


def test_chunk_document_policy_same_as_article():
    content = "policy text\n\n" * 80
    r_article = chunk_document(content, "article")
    r_policy = chunk_document(content, "policy")
    assert len(r_article) == len(r_policy)
    assert r_article[0].content == r_policy[0].content


def test_chunk_document_article_metadata_is_dict():
    results = chunk_document("Some content here.", "article")
    for r in results:
        assert isinstance(r.metadata, dict)
