"""LLM-as-judge for the ResolveAI eval harness.

Scores each agent response on three rubrics (0.0–1.0):
  - groundedness   : Is the response factually grounded in the retrieved context / tool results?
  - helpfulness    : Does the response fully address the customer's need?
  - policy_score   : Does the response comply with ResolveAI's stated policies and tone guidelines?
"""

from __future__ import annotations

import json
import re
import structlog

from app.config import get_settings
from app.services.llm.base import ChatMessage
from app.services.llm.router import get_llm_router

log = structlog.get_logger(__name__)

_JUDGE_SYSTEM = """You are an expert evaluator for a Pakistani fintech/e-commerce customer support AI called ResolveAI.

You will receive:
- The original customer message
- The agent's response
- The expected ground-truth answer (for reference)
- Any retrieved KB context (may be empty)

Score the agent response on EXACTLY these three rubrics. Each score must be a float between 0.0 and 1.0 (two decimal places).

RUBRICS:
1. groundedness (0.0-1.0):
   - 1.0: All factual claims in the response are supported by context/tool results or are clearly general knowledge.
   - 0.5: Mostly grounded but contains one unsupported claim.
   - 0.0: Response contains fabricated facts not supported by any context.

2. helpfulness (0.0-1.0):
   - 1.0: Fully resolves the customer query. Actionable, specific, nothing important missing.
   - 0.5: Partially helpful — addresses the query but leaves important details out.
   - 0.0: Does not address the customer's actual question at all.

3. policy_score (0.0-1.0):
   - 1.0: Professional, empathetic tone. Correctly declines out-of-scope requests. No hallucinated policies.
   - 0.5: Mostly compliant but slightly off-tone or one policy mention is questionable.
   - 0.0: Rude, makes up policies, or gives harmful advice.

IMPORTANT RULES:
- Messages in Urdu or Roman Urdu are valid. Judge by content, not language.
- An escalation response (connecting to human agent) is CORRECT for escalation requests — score it 1.0 on all rubrics.
- A polite refusal for out-of-scope queries (weather, jokes) is CORRECT — score helpfulness 0.8+ if it explains the scope.
- Responses for session_end (goodbye) that are friendly are scored 1.0 on all rubrics.

Respond with ONLY a JSON object — no markdown, no explanation:
{"groundedness": 0.00, "helpfulness": 0.00, "policy_score": 0.00, "reasoning": "one short sentence"}
"""

_JUDGE_USER = """Customer message: {user_message}

Agent response: {actual_response}

Ground-truth answer (reference only): {ground_truth}

Retrieved context snippet (first 400 chars): {context_snippet}

Score the agent response:"""


class JudgeScores:
    __slots__ = ("groundedness", "helpfulness", "policy_score", "reasoning", "error")

    def __init__(
        self,
        groundedness: float,
        helpfulness: float,
        policy_score: float,
        reasoning: str = "",
        error: str = "",
    ) -> None:
        self.groundedness = groundedness
        self.helpfulness = helpfulness
        self.policy_score = policy_score
        self.reasoning = reasoning
        self.error = error

    def to_dict(self) -> dict:
        return {
            "groundedness": self.groundedness,
            "helpfulness": self.helpfulness,
            "policy_score": self.policy_score,
            "reasoning": self.reasoning,
            "error": self.error,
        }

    @classmethod
    def error_fallback(cls, msg: str) -> "JudgeScores":
        return cls(0.5, 0.5, 0.5, reasoning="", error=msg)


class LLMJudge:
    """Singleton LLM judge using the LLMRouter (falls back to Groq / Ollama)."""

    async def judge(
        self,
        case: dict,
        actual_response: str,
        retrieved_chunks: list[dict] | None = None,
    ) -> JudgeScores:
        context_snippet = ""
        if retrieved_chunks:
            first_chunk = retrieved_chunks[0] if retrieved_chunks else {}
            context_snippet = str(first_chunk.get("content", ""))[:400]

        messages = [
            ChatMessage(role="system", content=_JUDGE_SYSTEM.strip()),
            ChatMessage(
                role="user",
                content=_JUDGE_USER.format(
                    user_message=case.get("user_message", ""),
                    actual_response=actual_response,
                    ground_truth=case.get("ground_truth_answer", ""),
                    context_snippet=context_snippet,
                ).strip(),
            ),
        ]

        try:
            router = get_llm_router()
            result = await router.chat(messages, model_tier="cheap", max_tokens=200)
            raw = result.content.strip()

            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            data = json.loads(raw)
            return JudgeScores(
                groundedness=float(data.get("groundedness", 0.5)),
                helpfulness=float(data.get("helpfulness", 0.5)),
                policy_score=float(data.get("policy_score", 0.5)),
                reasoning=str(data.get("reasoning", "")),
            )

        except json.JSONDecodeError as exc:
            log.warning("judge_json_parse_error", error=str(exc), raw=raw[:200] if "raw" in dir() else "")
            return JudgeScores.error_fallback(f"json_parse_error: {exc}")

        except Exception as exc:
            log.warning("judge_llm_error", error=str(exc))
            return JudgeScores.error_fallback(f"llm_error: {exc}")


_judge: LLMJudge | None = None


def get_judge() -> LLMJudge:
    global _judge
    if _judge is None:
        _judge = LLMJudge()
    return _judge
