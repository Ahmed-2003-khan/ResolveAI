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
- Tool results the agent received (live data from CRM — use this to verify facts)
- Retrieved KB context

Score the agent response on EXACTLY these three rubrics. Each score must be a float between 0.0 and 1.0 (two decimal places).

RUBRICS:
1. groundedness (0.0-1.0):
   - 1.0: Every factual claim in the response matches the tool results or KB context exactly.
   - 0.5: Mostly grounded but one claim cannot be verified from the provided data.
   - 0.0: Response contradicts the tool results OR contains hallucinated facts.
   CRITICAL: If tool_results are provided they are the ground truth. Examples of groundedness=0.0:
     - Tool shows order status="pending" but agent says "dispatched" or "delivered"
     - Tool shows account_status="frozen" but agent says account is active or gives a balance
     - Tool shows balance=45000 PKR but agent says a different amount
     - Agent gives a tracking number not present in tool_results
   Do NOT penalise natural language variation (e.g. "shipped" vs "dispatched", "on its way" vs "dispatched").

2. helpfulness (0.0-1.0):
   - 1.0: Fully resolves the customer query with all relevant details. The customer has everything they need.
   - 0.5: Partially helpful — correct direction but missing important details (e.g. no ETA, no refund ID).
   - 0.0: Does not address the customer's actual question, or gives factually wrong information.
   CATEGORY-SPECIFIC guidance:
     - order_status: 1.0 requires mentioning the correct status AND any available ETA or tracking info.
     - account_balance: 1.0 requires mentioning the actual balance (or explaining the account is frozen/closed).
     - recent_transactions: 1.0 requires listing the transactions with amounts; 0.5 if vague summary only.
     - refund_request: 1.0 requires confirming the refund was submitted with a reference; 0.0 if refused when it should succeed.
     - support_ticket: 1.0 requires confirming ticket creation with a ticket ID or reference.
     - kb_faq: 1.0 requires a specific, accurate answer from KB; 0.5 if only general/vague.
     - escalation: 1.0 if agent confirms it is connecting the customer to a human agent.
     - out_of_scope: 1.0 if agent politely declines and explains it only handles customer support queries.
     - session_end: 1.0 if agent responds with a friendly, appropriate goodbye in the customer's language.

3. policy_score (0.0-1.0):
   - 1.0: Professional, empathetic tone. No hallucinated policies. Handles all scenarios correctly.
   - 0.5: Mostly compliant but slightly off-tone or one questionable claim.
   - 0.0: Rude, invents policies, gives harmful advice, or answers an out-of-scope request instead of redirecting.

IMPORTANT RULES:
- Language does NOT matter. Roman Urdu, Urdu script, English — judge by content, not wording.
- "Shipped", "sent", "on its way", "dispatched" all mean the same thing — do not penalise synonyms.
- A frozen-account response explaining the account is frozen IS correct even if it gives no balance.
- An escalation response that confirms connecting to a human agent scores 1.0 on all rubrics.
- A polite out-of-scope refusal that redirects to support scores helpfulness 0.9+.
- A friendly session_end goodbye (any language) scores 1.0 on all rubrics.

Respond with ONLY a JSON object — no markdown, no explanation:
{"groundedness": 0.00, "helpfulness": 0.00, "policy_score": 0.00, "reasoning": "one short sentence"}
"""

_JUDGE_USER = """Customer message: {user_message}

Agent response: {actual_response}

Ground-truth answer (reference only): {ground_truth}

Tool results (live CRM data — primary source of truth for facts):
{tool_results}

Retrieved KB context (first 600 chars):
{context_snippet}

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
    """LLM judge using OpenAI gpt-4o-mini — reliable structured JSON output."""

    def __init__(self, use_groq: bool = False) -> None:
        # use_groq kept for backwards compat but defaults False — Groq llama-3.1-8b
        # returns inconsistent JSON scores; gpt-4o-mini is far more reliable here.
        self._use_groq = use_groq
        self._groq: "GroqProvider | None" = None

    def _get_groq(self):
        if self._groq is None:
            from app.services.llm.groq_provider import GroqProvider
            self._groq = GroqProvider()
        return self._groq

    async def judge(
        self,
        case: dict,
        actual_response: str,
        retrieved_chunks: list[dict] | None = None,
        tool_results: dict | None = None,
    ) -> JudgeScores:
        # Build KB context from all retrieved chunks (up to 600 chars total)
        context_snippet = ""
        if retrieved_chunks:
            parts = [c.get("content", "") for c in retrieved_chunks if c.get("content")]
            context_snippet = " | ".join(parts)[:600]

        # Format tool results as readable JSON for the judge
        tool_results_text = "(no tools were called)"
        if tool_results:
            tool_results_text = json.dumps(tool_results, indent=2, default=str)[:800]

        messages = [
            ChatMessage(role="system", content=_JUDGE_SYSTEM.strip()),
            ChatMessage(
                role="user",
                content=_JUDGE_USER.format(
                    user_message=case.get("user_message", ""),
                    actual_response=actual_response,
                    ground_truth=case.get("ground_truth_answer", ""),
                    tool_results=tool_results_text,
                    context_snippet=context_snippet,
                ).strip(),
            ),
        ]

        try:
            if self._use_groq:
                result = await self._get_groq().chat(messages, model_tier="cheap", max_tokens=200)
            else:
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


def get_judge(use_groq: bool = True) -> LLMJudge:
    global _judge
    if _judge is None:
        _judge = LLMJudge(use_groq=use_groq)
    return _judge
