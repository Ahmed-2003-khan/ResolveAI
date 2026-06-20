"""Unit tests for app.services.pii — regex rules and PIIRedactor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.pii.redactor import PIIRedactor, RedactionResult
from app.services.pii.regex_rules import COMPILED, PATTERNS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def redactor() -> PIIRedactor:
    return PIIRedactor()


# ---------------------------------------------------------------------------
# CNIC
# ---------------------------------------------------------------------------


def test_cnic_dashed_format(redactor: PIIRedactor) -> None:
    result = redactor.redact("My CNIC is 12345-1234567-1")
    assert "<CNIC_1>" in result.redacted_text
    assert "12345-1234567-1" not in result.redacted_text
    assert result.pii_map["<CNIC_1>"] == "12345-1234567-1"


def test_cnic_no_dashes(redactor: PIIRedactor) -> None:
    result = redactor.redact("CNIC number: 1234512345671")
    assert "<CNIC_1>" in result.redacted_text
    assert result.pii_map["<CNIC_1>"] == "1234512345671"


def test_cnic_all_zeros_fake(redactor: PIIRedactor) -> None:
    result = redactor.redact("test user CNIC 00000-0000000-0")
    assert "<CNIC_1>" in result.redacted_text


def test_cnic_multiple_in_text(redactor: PIIRedactor) -> None:
    result = redactor.redact("First: 12345-1234567-1 and second: 98765-7654321-9")
    assert "<CNIC_1>" in result.redacted_text
    assert "<CNIC_2>" in result.redacted_text
    assert len([k for k in result.pii_map if k.startswith("<CNIC_")]) == 2


# ---------------------------------------------------------------------------
# MOBILE
# ---------------------------------------------------------------------------


def test_mobile_zero_prefix(redactor: PIIRedactor) -> None:
    result = redactor.redact("Call me at 03001234567 please")
    assert "<MOBILE_1>" in result.redacted_text
    assert result.pii_map["<MOBILE_1>"] == "03001234567"


def test_mobile_plus92_prefix_in_sentence(redactor: PIIRedactor) -> None:
    result = redactor.redact("my number is +923001234567 thanks")
    assert "<MOBILE_1>" in result.redacted_text
    assert result.pii_map["<MOBILE_1>"] == "+923001234567"


def test_mobile_with_space_separator(redactor: PIIRedactor) -> None:
    result = redactor.redact("reach me at 0300 1234567")
    assert "<MOBILE_1>" in result.redacted_text


def test_mobile_with_dash_separator(redactor: PIIRedactor) -> None:
    result = redactor.redact("phone: 0321-7654321")
    assert "<MOBILE_1>" in result.redacted_text


def test_mobile_different_network_prefix(redactor: PIIRedactor) -> None:
    result = redactor.redact("ufone: 03331234567")
    assert "<MOBILE_1>" in result.redacted_text


# ---------------------------------------------------------------------------
# IBAN
# ---------------------------------------------------------------------------


def test_iban_standard(redactor: PIIRedactor) -> None:
    result = redactor.redact("transfer to PK36SCBL0000001123456702")
    assert "<IBAN_1>" in result.redacted_text
    assert result.pii_map["<IBAN_1>"] == "PK36SCBL0000001123456702"


def test_iban_in_sentence(redactor: PIIRedactor) -> None:
    result = redactor.redact("Please send to IBAN PK36SCBL0000001123456702 today")
    assert "<IBAN_1>" in result.redacted_text
    assert "PK36SCBL0000001123456702" not in result.redacted_text


def test_iban_multiple(redactor: PIIRedactor) -> None:
    result = redactor.redact("from PK36SCBL0000001123456702 to PK00HABB0000000012345678")
    assert "<IBAN_1>" in result.redacted_text
    assert "<IBAN_2>" in result.redacted_text


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------


def test_card_16_digits_no_separator(redactor: PIIRedactor) -> None:
    result = redactor.redact("charge card 4111111111111111 please")
    assert "<CARD_1>" in result.redacted_text


def test_card_with_space_groups(redactor: PIIRedactor) -> None:
    result = redactor.redact("card number 4111 1111 1111 1111 please charge")
    assert "<CARD_1>" in result.redacted_text


def test_card_with_dash_groups(redactor: PIIRedactor) -> None:
    result = redactor.redact("my card is 4111-1111-1111-1111")
    assert "<CARD_1>" in result.redacted_text


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------


def test_email_basic(redactor: PIIRedactor) -> None:
    result = redactor.redact("email me at user@example.com for support")
    assert "<EMAIL_1>" in result.redacted_text
    assert result.pii_map["<EMAIL_1>"] == "user@example.com"


def test_email_with_plus_tag(redactor: PIIRedactor) -> None:
    result = redactor.redact("contact user+tag@domain.co for help")
    assert "<EMAIL_1>" in result.redacted_text


def test_email_subdomain(redactor: PIIRedactor) -> None:
    result = redactor.redact("write to support@mail.resolveai.io")
    assert "<EMAIL_1>" in result.redacted_text


def test_multiple_emails(redactor: PIIRedactor) -> None:
    result = redactor.redact("send to a@x.com and b@y.com")
    assert "<EMAIL_1>" in result.redacted_text
    assert "<EMAIL_2>" in result.redacted_text


# ---------------------------------------------------------------------------
# Multi-type PII
# ---------------------------------------------------------------------------


def test_mixed_cnic_and_mobile(redactor: PIIRedactor) -> None:
    text = "CNIC 12345-1234567-1 and phone 03001234567"
    result = redactor.redact(text)
    assert "<CNIC_1>" in result.redacted_text
    assert "<MOBILE_1>" in result.redacted_text
    assert len(result.pii_map) == 2


def test_mixed_email_and_iban(redactor: PIIRedactor) -> None:
    text = "user@example.com sent IBAN PK36SCBL0000001123456702"
    result = redactor.redact(text)
    assert "<EMAIL_1>" in result.redacted_text
    assert "<IBAN_1>" in result.redacted_text


def test_no_pii_text_unchanged(redactor: PIIRedactor) -> None:
    text = "Hello, how can I help you today?"
    result = redactor.redact(text)
    assert result.redacted_text == text
    assert result.pii_map == {}


def test_urdu_roman_context_with_pii(redactor: PIIRedactor) -> None:
    text = "mera number hai 03001234567 aur CNIC 12345-1234567-1"
    result = redactor.redact(text)
    assert "<MOBILE_1>" in result.redacted_text
    assert "<CNIC_1>" in result.redacted_text


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def test_restore_single_pii(redactor: PIIRedactor) -> None:
    original = "My CNIC is 12345-1234567-1"
    result = redactor.redact(original)
    restored = redactor.restore(result.redacted_text, result.pii_map)
    assert restored == original


def test_restore_multiple_pii(redactor: PIIRedactor) -> None:
    original = "CNIC 12345-1234567-1 and mobile 03001234567"
    result = redactor.redact(original)
    restored = redactor.restore(result.redacted_text, result.pii_map)
    assert restored == original


def test_restore_empty_pii_map(redactor: PIIRedactor) -> None:
    text = "no PII here at all"
    assert redactor.restore(text, {}) == text


def test_restore_preserves_surrounding_text(redactor: PIIRedactor) -> None:
    original = "Please email user@example.com about order #12345"
    result = redactor.redact(original)
    restored = redactor.restore(result.redacted_text, result.pii_map)
    assert "order #12345" in restored
    assert "user@example.com" in restored


# ---------------------------------------------------------------------------
# RedactionResult dataclass
# ---------------------------------------------------------------------------


def test_redaction_result_defaults() -> None:
    r = RedactionResult(redacted_text="hello")
    assert r.pii_map == {}


# ---------------------------------------------------------------------------
# regex_rules exports
# ---------------------------------------------------------------------------


def test_patterns_has_all_required_types() -> None:
    assert set(PATTERNS.keys()) == {"CNIC", "MOBILE", "IBAN", "CARD", "EMAIL"}


def test_compiled_keys_match_patterns() -> None:
    assert set(COMPILED.keys()) == set(PATTERNS.keys())


def test_compiled_values_are_patterns() -> None:
    import re

    for name, pat in COMPILED.items():
        assert isinstance(pat, re.Pattern), f"{name} should be compiled"


# ---------------------------------------------------------------------------
# LLM pass (async) — unit tests with mocks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redact_with_llm_happy_path(redactor: PIIRedactor) -> None:
    mock_response = "The <CNIC_1> was redacted [REDACTED] spelled account"
    with patch.object(redactor, "_call_ollama", new_callable=AsyncMock) as mock_ollama:
        mock_ollama.return_value = mock_response
        result = await redactor.redact_with_llm("CNIC 12345-1234567-1 account one two")

    assert result.redacted_text == mock_response
    assert "<CNIC_1>" in result.pii_map


@pytest.mark.asyncio
async def test_redact_with_llm_falls_back_on_error(redactor: PIIRedactor) -> None:
    with patch.object(redactor, "_call_ollama", side_effect=Exception("connection refused")):
        result = await redactor.redact_with_llm("phone 03001234567")

    assert "<MOBILE_1>" in result.redacted_text
    assert result.pii_map["<MOBILE_1>"] == "03001234567"


@pytest.mark.asyncio
async def test_redact_with_llm_uses_regex_result_when_llm_returns_empty(
    redactor: PIIRedactor,
) -> None:
    with patch.object(redactor, "_call_ollama", new_callable=AsyncMock) as mock_ollama:
        mock_ollama.return_value = ""
        result = await redactor.redact_with_llm("email user@example.com")

    assert "<EMAIL_1>" in result.redacted_text


@pytest.mark.asyncio
async def test_call_ollama_sends_correct_payload(redactor: PIIRedactor) -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "clean text"}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.post.return_value = mock_resp

    with patch("app.services.pii.redactor.httpx.AsyncClient", return_value=mock_client):
        result = await redactor._call_ollama("test prompt", "http://localhost:11434", "llama3:8b")

    assert result == "clean text"
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert "llama3:8b" in str(call_kwargs)
