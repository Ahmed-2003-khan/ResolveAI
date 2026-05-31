"""Eval metrics utilities — pass-rate, rubric averages, and assertion checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssertionResult:
    passed: bool
    intent_match: bool
    tools_match: bool
    must_include_pass: bool
    must_not_include_pass: bool
    failures: list[str] = field(default_factory=list)


def check_assertions(case: dict[str, Any], final_response: str, actual_intent: str, tools_called: list[str]) -> AssertionResult:
    """Run deterministic assertions against a single eval case result."""
    failures: list[str] = []
    response_lower = final_response.lower()

    # Intent match
    expected_intent = case.get("expected_intent", "")
    intent_match = actual_intent == expected_intent
    if not intent_match:
        failures.append(f"intent: expected '{expected_intent}', got '{actual_intent}'")

    # Tool match — all expected tools must have been called
    expected_tools: list[str] = case.get("expected_tools", [])
    tools_called_set = set(tools_called)
    missing_tools = [t for t in expected_tools if t not in tools_called_set]
    tools_match = len(missing_tools) == 0
    if not tools_match:
        failures.append(f"tools: expected {expected_tools}, missing {missing_tools}")

    # must_include — case-insensitive substring check
    must_include: list[str] = case.get("must_include", [])
    missing_strings: list[str] = [s for s in must_include if s.lower() not in response_lower]
    must_include_pass = len(missing_strings) == 0
    if not must_include_pass:
        failures.append(f"must_include: response missing {missing_strings}")

    # must_not_include — none of these strings should appear
    must_not_include: list[str] = case.get("must_not_include", [])
    found_forbidden: list[str] = [s for s in must_not_include if s.lower() in response_lower]
    must_not_include_pass = len(found_forbidden) == 0
    if not must_not_include_pass:
        failures.append(f"must_not_include: response contains {found_forbidden}")

    passed = intent_match and tools_match and must_include_pass and must_not_include_pass
    return AssertionResult(
        passed=passed,
        intent_match=intent_match,
        tools_match=tools_match,
        must_include_pass=must_include_pass,
        must_not_include_pass=must_not_include_pass,
        failures=failures,
    )


@dataclass
class AggregateMetrics:
    total_cases: int
    passed: int
    failed: int
    pass_rate: float
    avg_groundedness: float
    avg_helpfulness: float
    avg_policy_score: float
    intent_accuracy: float
    tool_accuracy: float
    avg_latency_ms: float
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)


def compute_aggregate(results: list[dict[str, Any]]) -> AggregateMetrics:
    """Compute aggregate metrics from a list of per-case result dicts."""
    if not results:
        return AggregateMetrics(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    total = len(results)
    passed_count = sum(1 for r in results if r.get("passed", False))
    failed_count = total - passed_count

    groundedness_vals = [r["judge_scores"]["groundedness"] for r in results if r.get("judge_scores") and r["judge_scores"].get("groundedness") is not None]
    helpfulness_vals = [r["judge_scores"]["helpfulness"] for r in results if r.get("judge_scores") and r["judge_scores"].get("helpfulness") is not None]
    policy_vals = [r["judge_scores"]["policy_score"] for r in results if r.get("judge_scores") and r["judge_scores"].get("policy_score") is not None]

    intent_accuracy = sum(1 for r in results if r.get("intent_match", False)) / total
    tool_accuracy_vals = [r for r in results if r.get("expected_tools") is not None]
    tool_accuracy = sum(1 for r in tool_accuracy_vals if r.get("tools_match", False)) / max(len(tool_accuracy_vals), 1)

    latencies = [r["latency_ms"] for r in results if r.get("latency_ms") is not None]

    # Per-category breakdown
    by_category: dict[str, dict[str, Any]] = {}
    for r in results:
        cat = r.get("category", "unknown")
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0, "pass_rate": 0.0}
        by_category[cat]["total"] += 1
        if r.get("passed"):
            by_category[cat]["passed"] += 1
    for cat, stats in by_category.items():
        stats["pass_rate"] = round(stats["passed"] / stats["total"], 3) if stats["total"] else 0.0

    return AggregateMetrics(
        total_cases=total,
        passed=passed_count,
        failed=failed_count,
        pass_rate=round(passed_count / total, 3),
        avg_groundedness=round(sum(groundedness_vals) / len(groundedness_vals), 3) if groundedness_vals else 0.0,
        avg_helpfulness=round(sum(helpfulness_vals) / len(helpfulness_vals), 3) if helpfulness_vals else 0.0,
        avg_policy_score=round(sum(policy_vals) / len(policy_vals), 3) if policy_vals else 0.0,
        intent_accuracy=round(intent_accuracy, 3),
        tool_accuracy=round(tool_accuracy, 3),
        avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        by_category=by_category,
    )


def check_thresholds(metrics: AggregateMetrics, min_pass_rate: float = 0.85, min_rubric: float = 0.75) -> tuple[bool, list[str]]:
    """Return (ok, list_of_violations)."""
    violations: list[str] = []
    if metrics.pass_rate < min_pass_rate:
        violations.append(f"pass_rate {metrics.pass_rate:.1%} < threshold {min_pass_rate:.1%}")
    if metrics.avg_groundedness < min_rubric:
        violations.append(f"avg_groundedness {metrics.avg_groundedness:.3f} < {min_rubric}")
    if metrics.avg_helpfulness < min_rubric:
        violations.append(f"avg_helpfulness {metrics.avg_helpfulness:.3f} < {min_rubric}")
    if metrics.avg_policy_score < min_rubric:
        violations.append(f"avg_policy_score {metrics.avg_policy_score:.3f} < {min_rubric}")
    return len(violations) == 0, violations
