from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import structlog

from app.services.pii.regex_rules import COMPILED

logger = structlog.get_logger(__name__)

PIIMap = dict[str, str]


@dataclass
class RedactionResult:
    redacted_text: str
    pii_map: PIIMap = field(default_factory=dict)


class PIIRedactor:
    def redact(self, text: str) -> RedactionResult:
        """Regex-based PII redaction. Returns redacted text and a reversible pii_map."""
        pii_map: PIIMap = {}
        result = text

        for pii_type, pattern in COMPILED.items():
            count: list[int] = [0]

            def _make_replacer(
                ptype: str, cnt: list[int]
            ) -> Callable[[re.Match[str]], str]:
                def replacer(match: re.Match[str]) -> str:
                    cnt[0] += 1
                    placeholder = f"<{ptype}_{cnt[0]}>"
                    pii_map[placeholder] = match.group(0)
                    return placeholder

                return replacer

            result = pattern.sub(_make_replacer(pii_type, count), result)

        return RedactionResult(redacted_text=result, pii_map=pii_map)

    def restore(self, text: str, pii_map: PIIMap) -> str:
        """Replace placeholder tokens with their original PII values."""
        result = text
        for placeholder, original in pii_map.items():
            result = result.replace(placeholder, original)
        return result

    async def _call_ollama(
        self, prompt: str, base_url: str, model: str
    ) -> str:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json().get("response", "")

    async def redact_with_llm(
        self,
        text: str,
        ollama_base_url: str = "http://localhost:11434",
        model: str = "llama3:8b",
    ) -> RedactionResult:
        """Regex pass followed by an optional Llama-3 pass for spelled-out PII.

        Falls back to regex-only result if Ollama is unavailable.
        """
        regex_result = self.redact(text)

        prompt = (
            "You are a PII redaction assistant. The text below has already had structured PII "
            "(CNICs, phone numbers, IBANs, card numbers, emails) replaced with placeholders. "
            "Find any remaining personally identifiable information that was spelled out in words "
            "(e.g. 'one two three four' as an account number) and replace it with [REDACTED]. "
            "Return ONLY the (possibly modified) text — no explanation.\n\nText:\n"
            + regex_result.redacted_text
        )

        try:
            llm_text = await self._call_ollama(prompt, ollama_base_url, model)
        except Exception as exc:
            logger.warning("pii_llm_pass_skipped", reason=str(exc))
            return regex_result

        return RedactionResult(
            redacted_text=llm_text or regex_result.redacted_text,
            pii_map=regex_result.pii_map,
        )
