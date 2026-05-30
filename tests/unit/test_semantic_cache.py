"""Unit tests for the semantic cache service (Phase 8).

All database and embedding calls are mocked so these tests run without a live
Postgres instance or OpenAI key.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cache.semantic_cache import SemanticCacheService, get_semantic_cache

# ── Fixtures ──────────────────────────────────────────────────────────────────

_FAKE_EMBEDDING = [0.1] * 1536
_FAKE_RESPONSE = "Your order is on its way!"


def _make_session_mock(row=None) -> AsyncMock:
    """Return an AsyncMock that behaves like an AsyncSession context manager."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    # .execute() returns an object whose .mappings().first() returns `row`
    execute_result = MagicMock()
    execute_result.mappings.return_value.first.return_value = row
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    return session


def _patch_embedder(monkeypatch_or_patch=None):
    """Return a context-manager patch for get_embedder used by the cache module."""
    mock_embedder = AsyncMock()
    mock_embedder.embed_one = AsyncMock(return_value=_FAKE_EMBEDDING)
    return patch(
        "app.services.cache.semantic_cache.get_embedder",
        return_value=mock_embedder,
    )


# ── _normalize ────────────────────────────────────────────────────────────────


def test_normalize_lowercases() -> None:
    svc = SemanticCacheService()
    assert svc._normalize("Hello World") == "hello world"


def test_normalize_strips_edges() -> None:
    svc = SemanticCacheService()
    assert svc._normalize("  hello  ") == "hello"


def test_normalize_collapses_internal_whitespace() -> None:
    svc = SemanticCacheService()
    assert svc._normalize("hello   world") == "hello world"


def test_normalize_nfkc() -> None:
    # Full-width characters should become ASCII equivalents after NFKC.
    svc = SemanticCacheService()
    result = svc._normalize("ｈｅｌｌｏ")  # ｈｅｌｌｏ
    assert result == "hello"


def test_normalize_empty_string() -> None:
    svc = SemanticCacheService()
    assert svc._normalize("   ") == ""


# ── _vec_str ──────────────────────────────────────────────────────────────────


def test_vec_str_format() -> None:
    svc = SemanticCacheService()
    result = svc._vec_str([0.1, 0.2, 0.3])
    assert result == "[0.1,0.2,0.3]"


# ── get() — cache miss ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_none_on_miss() -> None:
    svc = SemanticCacheService()
    session_mock = _make_session_mock(row=None)

    with _patch_embedder():
        with patch(
            "app.services.cache.semantic_cache.async_session_factory",
            return_value=session_mock,
        ):
            result = await svc.get("where is my order?")

    assert result is None


@pytest.mark.asyncio
async def test_get_returns_none_for_empty_query() -> None:
    svc = SemanticCacheService()
    result = await svc.get("   ")
    assert result is None


# ── get() — cache hit ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_cached_response_on_hit() -> None:
    svc = SemanticCacheService()
    fake_row = {"id": "fake-uuid", "response": _FAKE_RESPONSE, "distance": 0.01}
    session_mock = _make_session_mock(row=fake_row)

    with _patch_embedder():
        with patch(
            "app.services.cache.semantic_cache.async_session_factory",
            return_value=session_mock,
        ):
            result = await svc.get("where is my order?")

    assert result == _FAKE_RESPONSE


@pytest.mark.asyncio
async def test_get_increments_hit_count_on_hit() -> None:
    svc = SemanticCacheService()
    fake_row = {"id": "fake-uuid", "response": _FAKE_RESPONSE, "distance": 0.005}
    session_mock = _make_session_mock(row=fake_row)

    with _patch_embedder():
        with patch(
            "app.services.cache.semantic_cache.async_session_factory",
            return_value=session_mock,
        ):
            await svc.get("order status please")

    # Should have called execute twice: SELECT and UPDATE
    assert session_mock.execute.call_count == 2
    # commit called once after the UPDATE
    session_mock.commit.assert_awaited_once()


# ── get() — error resilience ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_none_when_embed_fails() -> None:
    svc = SemanticCacheService()
    mock_embedder = AsyncMock()
    mock_embedder.embed_one = AsyncMock(side_effect=RuntimeError("API down"))

    with patch(
        "app.services.cache.semantic_cache.get_embedder",
        return_value=mock_embedder,
    ):
        result = await svc.get("hello?")

    assert result is None


@pytest.mark.asyncio
async def test_get_returns_none_when_db_fails() -> None:
    svc = SemanticCacheService()
    session_mock = AsyncMock()
    session_mock.__aenter__ = AsyncMock(side_effect=OSError("DB unreachable"))
    session_mock.__aexit__ = AsyncMock(return_value=False)

    with _patch_embedder():
        with patch(
            "app.services.cache.semantic_cache.async_session_factory",
            return_value=session_mock,
        ):
            result = await svc.get("any query")

    assert result is None


# ── set() ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_executes_insert() -> None:
    svc = SemanticCacheService()
    session_mock = _make_session_mock()

    with _patch_embedder():
        with patch(
            "app.services.cache.semantic_cache.async_session_factory",
            return_value=session_mock,
        ):
            await svc.set("where is my order?", _FAKE_RESPONSE)

    session_mock.execute.assert_awaited_once()
    session_mock.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_is_noop_for_empty_query() -> None:
    svc = SemanticCacheService()
    # Should return without touching the DB
    with _patch_embedder():
        with patch(
            "app.services.cache.semantic_cache.async_session_factory"
        ) as mock_factory:
            await svc.set("   ", _FAKE_RESPONSE)
            mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_set_is_noop_for_empty_response() -> None:
    svc = SemanticCacheService()
    with _patch_embedder():
        with patch(
            "app.services.cache.semantic_cache.async_session_factory"
        ) as mock_factory:
            await svc.set("hello", "")
            mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_set_survives_db_error() -> None:
    svc = SemanticCacheService()
    session_mock = AsyncMock()
    session_mock.__aenter__ = AsyncMock(side_effect=OSError("DB unreachable"))
    session_mock.__aexit__ = AsyncMock(return_value=False)

    with _patch_embedder():
        with patch(
            "app.services.cache.semantic_cache.async_session_factory",
            return_value=session_mock,
        ):
            # Must not raise
            await svc.set("hello", _FAKE_RESPONSE)


@pytest.mark.asyncio
async def test_set_survives_embed_error() -> None:
    svc = SemanticCacheService()
    mock_embedder = AsyncMock()
    mock_embedder.embed_one = AsyncMock(side_effect=RuntimeError("API down"))

    with patch(
        "app.services.cache.semantic_cache.get_embedder",
        return_value=mock_embedder,
    ):
        with patch("app.services.cache.semantic_cache.async_session_factory") as mock_factory:
            await svc.set("hello", _FAKE_RESPONSE)
            mock_factory.assert_not_called()


# ── Singleton ─────────────────────────────────────────────────────────────────


def test_get_semantic_cache_returns_singleton() -> None:
    a = get_semantic_cache()
    b = get_semantic_cache()
    assert a is b


# ── run_with_cache integration ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_with_cache_returns_cached_on_hit() -> None:
    """Cache hit should bypass the graph entirely."""
    from app.agent.graph import run_with_cache

    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=_FAKE_RESPONSE)

    # Patch the module-level name in graph.py
    with patch("app.agent.graph.get_semantic_cache", return_value=mock_cache):
        with patch("app.agent.graph.CACHE_HITS") as mock_hits:
            with patch("app.agent.graph.CACHE_MISSES"):
                result = await run_with_cache(
                    {
                        "conversation_id": "conv-test",
                        "user_message": "where is my order?",
                    }
                )
            mock_hits.inc.assert_called_once()

    assert result["final_response"] == _FAKE_RESPONSE
    audit = result["audit_trail"]
    assert any(e.get("cache_hit") is True for e in audit)


@pytest.mark.asyncio
async def test_run_with_cache_invokes_graph_on_miss() -> None:
    """Cache miss should run the full graph and then store the result."""
    from app.agent.graph import run_with_cache

    graph_result = {
        "conversation_id": "conv-test",
        "user_message": "hello",
        "final_response": "Hello! How can I help?",
        "audit_trail": [],
    }

    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()

    mock_graph = AsyncMock()
    mock_graph.ainvoke = AsyncMock(return_value=graph_result)

    with patch("app.agent.graph.get_semantic_cache", return_value=mock_cache):
        with patch("app.agent.graph.get_graph", return_value=mock_graph):
            with patch("app.agent.graph.CACHE_MISSES") as mock_misses:
                with patch("app.agent.graph.CACHE_HITS"):
                    result = await run_with_cache(
                        {"conversation_id": "conv-test", "user_message": "hello"}
                    )
                mock_misses.inc.assert_called_once()

    assert result["final_response"] == "Hello! How can I help?"
    mock_cache.set.assert_awaited_once_with("hello", "Hello! How can I help?")
