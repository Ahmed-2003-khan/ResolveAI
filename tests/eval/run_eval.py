"""ResolveAI eval harness — Phase 12.

Runs every case in data/eval/golden_set.jsonl through the full agent graph,
applies deterministic assertions, calls the LLM judge, persists results to
the DB, and writes an HTML report.

Exit code 1 if pass-rate < 85% or any rubric average < 0.75.

Usage (inside the container):
    python tests/eval/run_eval.py
    python tests/eval/run_eval.py --limit 10          # smoke-test: first N cases
    python tests/eval/run_eval.py --no-db             # skip DB persistence
    python tests/eval/run_eval.py --no-judge          # skip LLM judge (faster)
    python tests/eval/run_eval.py --html reports/eval_report.html
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import text

log = structlog.get_logger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent.parent
_GOLDEN_SET = _REPO_ROOT / "data" / "eval" / "golden_set.jsonl"
_DEFAULT_REPORT = _REPO_ROOT / "reports" / "eval_report.html"


def _load_golden_set(path: Path, limit: int | None = None, offset: int = 0) -> list[dict]:
    cases = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    cases = cases[offset:]
    if limit:
        cases = cases[:limit]
    return cases


def _get_git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


# ── Agent runner ──────────────────────────────────────────────────────────────

async def _run_case(case: dict, graph) -> dict:
    """Invoke the agent graph for one eval case.  Returns a raw result dict."""
    conversation_id = f"eval-{case['case_id']}-{uuid.uuid4().hex[:8]}"
    state = {
        "conversation_id": conversation_id,
        "user_id": case.get("user_id", "user-001"),
        "user_message": case["user_message"],
        "user_profile": case.get("user_profile", {}),
        "conversation_history": [],
        "intent": None,
        "cleaned_content": None,
        "pii_map": None,
        "retrieved_chunks": [],
        "tool_plan": [],
        "tool_results": {},
        "draft_response": None,
        "critique_score": None,
        "critique_feedback": None,
        "retry_count": 0,
        "should_escalate": False,
        "final_response": None,
        "total_cost_usd": 0.0,
        "total_latency_ms": 0,
        "audit_trail": [],
    }

    config = {"configurable": {"thread_id": conversation_id}}
    t0 = time.monotonic()
    result = await asyncio.wait_for(graph.ainvoke(state, config), timeout=300.0)
    latency_ms = int((time.monotonic() - t0) * 1000)
    return {**result, "_latency_ms": latency_ms}


# ── DB persistence ────────────────────────────────────────────────────────────

async def _save_to_db(
    run_id: uuid.UUID,
    git_sha: str,
    results: list[dict],
    metrics,
) -> None:
    from app.core.db import async_session_factory
    from app.models.eval_run import EvalResult, EvalRun

    async with async_session_factory() as session:
        run = EvalRun(
            id=run_id,
            git_sha=git_sha,
            run_at=datetime.now(timezone.utc),
            total_cases=metrics.total_cases,
            passed=metrics.passed,
            failed=metrics.failed,
            groundedness=metrics.avg_groundedness,
            helpfulness=metrics.avg_helpfulness,
            policy_score=metrics.avg_policy_score,
            metadata_={
                "pass_rate": metrics.pass_rate,
                "intent_accuracy": metrics.intent_accuracy,
                "tool_accuracy": metrics.tool_accuracy,
                "avg_latency_ms": metrics.avg_latency_ms,
                "by_category": metrics.by_category,
            },
        )
        session.add(run)

        for r in results:
            er = EvalResult(
                run_id=run_id,
                case_id=r.get("case_id"),
                passed=r.get("passed"),
                actual_response=r.get("actual_response", ""),
                expected_response=r.get("ground_truth_answer", ""),
                judge_scores=r.get("judge_scores"),
                metadata_={
                    "category": r.get("category"),
                    "intent_match": r.get("intent_match"),
                    "tools_match": r.get("tools_match"),
                    "latency_ms": r.get("latency_ms"),
                    "failures": r.get("failures", []),
                },
            )
            session.add(er)

        await session.commit()
    log.info("eval_saved_to_db", run_id=str(run_id))


# ── HTML report ───────────────────────────────────────────────────────────────

def _status_badge(passed: bool) -> str:
    if passed:
        return '<span class="badge pass">PASS</span>'
    return '<span class="badge fail">FAIL</span>'


def _score_cell(val: float | None) -> str:
    if val is None:
        return "<td>—</td>"
    colour = "green" if val >= 0.75 else ("orange" if val >= 0.5 else "red")
    return f'<td style="color:{colour};font-weight:600">{val:.2f}</td>'


def _generate_html(results: list[dict], metrics, run_id: str, git_sha: str, report_path: Path) -> None:
    rows_html = []
    for r in results:
        j = r.get("judge_scores") or {}
        failures = r.get("failures", [])
        fail_html = (
            '<ul style="margin:0;padding-left:1rem;font-size:0.8rem;color:#b00">'
            + "".join(f"<li>{f}</li>" for f in failures)
            + "</ul>"
        ) if failures else ""
        rows_html.append(f"""
        <tr>
            <td>{r.get('case_id','')}</td>
            <td>{r.get('category','')}</td>
            <td style="max-width:260px;font-size:0.85rem">{r.get('user_message','')[:120]}</td>
            <td style="max-width:300px;font-size:0.85rem">{(r.get('actual_response') or '')[:180]}</td>
            <td>{_status_badge(r.get('passed', False))}</td>
            {_score_cell(j.get('groundedness'))}
            {_score_cell(j.get('helpfulness'))}
            {_score_cell(j.get('policy_score'))}
            <td style="font-size:0.8rem">{r.get('latency_ms','—')} ms</td>
            <td>{fail_html}</td>
        </tr>""")

    # Category table
    cat_rows = []
    for cat, stats in sorted(metrics.by_category.items()):
        colour = "green" if stats["pass_rate"] >= 0.85 else ("orange" if stats["pass_rate"] >= 0.6 else "red")
        cat_rows.append(f"""
        <tr>
            <td>{cat}</td>
            <td>{stats['total']}</td>
            <td>{stats['passed']}</td>
            <td style="color:{colour};font-weight:600">{stats['pass_rate']:.1%}</td>
        </tr>""")

    overall_colour = "green" if metrics.pass_rate >= 0.85 else "red"
    ground_colour = "green" if metrics.avg_groundedness >= 0.75 else "red"
    helpful_colour = "green" if metrics.avg_helpfulness >= 0.75 else "red"
    policy_colour = "green" if metrics.avg_policy_score >= 0.75 else "red"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ResolveAI Eval Report — {run_id[:8]}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f5f7fa; color: #1a1a2e; }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #fff; padding: 2rem 3rem; }}
  .header h1 {{ margin: 0 0 0.5rem; font-size: 1.8rem; }}
  .header .meta {{ opacity: 0.7; font-size: 0.9rem; }}
  .container {{ max-width: 1400px; margin: 2rem auto; padding: 0 2rem; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .card {{ background: #fff; border-radius: 10px; padding: 1.25rem 1.5rem; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
  .card .label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: .08em; color: #666; margin-bottom: .3rem; }}
  .card .value {{ font-size: 2rem; font-weight: 700; }}
  .section {{ background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,.08); margin-bottom: 2rem; overflow: hidden; }}
  .section-title {{ padding: 1rem 1.5rem; border-bottom: 1px solid #eee; font-size: 1rem; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ background: #f8f9fc; padding: .65rem 1rem; text-align: left; font-weight: 600; color: #555; border-bottom: 2px solid #e5e7eb; white-space: nowrap; }}
  td {{ padding: .6rem 1rem; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
  tr:hover {{ background: #fafbff; }}
  .badge {{ display: inline-block; padding: .2rem .6rem; border-radius: 4px; font-size: .75rem; font-weight: 700; }}
  .badge.pass {{ background: #d1fae5; color: #065f46; }}
  .badge.fail {{ background: #fee2e2; color: #991b1b; }}
  .threshold-banner {{ padding: 1rem 1.5rem; border-radius: 8px; margin-bottom: 1.5rem; font-weight: 600; }}
  .threshold-banner.ok {{ background: #d1fae5; color: #065f46; }}
  .threshold-banner.fail {{ background: #fee2e2; color: #991b1b; }}
</style>
</head>
<body>
<div class="header">
  <h1>ResolveAI Eval Report</h1>
  <div class="meta">Run ID: {run_id} &nbsp;|&nbsp; Git SHA: {git_sha} &nbsp;|&nbsp; {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>
</div>
<div class="container">

  <div class="summary-grid">
    <div class="card">
      <div class="label">Pass Rate</div>
      <div class="value" style="color:{overall_colour}">{metrics.pass_rate:.1%}</div>
    </div>
    <div class="card">
      <div class="label">Cases</div>
      <div class="value">{metrics.total_cases}</div>
    </div>
    <div class="card">
      <div class="label">Passed</div>
      <div class="value" style="color:green">{metrics.passed}</div>
    </div>
    <div class="card">
      <div class="label">Failed</div>
      <div class="value" style="color:{'red' if metrics.failed else 'green'}">{metrics.failed}</div>
    </div>
    <div class="card">
      <div class="label">Groundedness</div>
      <div class="value" style="color:{ground_colour}">{metrics.avg_groundedness:.2f}</div>
    </div>
    <div class="card">
      <div class="label">Helpfulness</div>
      <div class="value" style="color:{helpful_colour}">{metrics.avg_helpfulness:.2f}</div>
    </div>
    <div class="card">
      <div class="label">Policy Score</div>
      <div class="value" style="color:{policy_colour}">{metrics.avg_policy_score:.2f}</div>
    </div>
    <div class="card">
      <div class="label">Avg Latency</div>
      <div class="value">{metrics.avg_latency_ms:.0f} ms</div>
    </div>
    <div class="card">
      <div class="label">Intent Accuracy</div>
      <div class="value">{metrics.intent_accuracy:.1%}</div>
    </div>
    <div class="card">
      <div class="label">Tool Accuracy</div>
      <div class="value">{metrics.tool_accuracy:.1%}</div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Results by Category</div>
    <table>
      <thead><tr><th>Category</th><th>Total</th><th>Passed</th><th>Pass Rate</th></tr></thead>
      <tbody>{''.join(cat_rows)}</tbody>
    </table>
  </div>

  <div class="section">
    <div class="section-title">Per-Case Results ({len(results)} cases)</div>
    <div style="overflow-x:auto">
    <table>
      <thead>
        <tr>
          <th>Case ID</th><th>Category</th><th>User Message</th><th>Response</th>
          <th>Result</th><th>Ground.</th><th>Helpful.</th><th>Policy</th>
          <th>Latency</th><th>Failures</th>
        </tr>
      </thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
    </div>
  </div>
</div>
</body>
</html>"""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")
    log.info("html_report_written", path=str(report_path))


# ── Main ──────────────────────────────────────────────────────────────────────

def _patch_router_for_groq() -> None:
    """Force the LLM router to try Groq before OpenAI for eval runs."""
    import app.services.llm.router as _router_mod
    _router_mod._TIER_PROVIDERS["cheap"] = ["groq", "openai", "ollama"]
    _router_mod._TIER_PROVIDERS["smart"] = ["groq", "openai"]
    # Reset singleton so it picks up the new order
    _router_mod._router = None
    log.info("eval_router_groq_first")


async def main(args: argparse.Namespace) -> int:
    from app.agent.graph import build_graph
    from langgraph.checkpoint.memory import MemorySaver
    from tests.eval.llm_judge import get_judge
    from tests.eval.metrics import check_assertions, compute_aggregate, check_thresholds

    # Note: --groq only affects the judge. Agent always uses OpenAI→Groq→Ollama
    # because llama-3.1-8b-instant is unreliable at function/tool calling.

    # Warm up the reranker so the first real case doesn't eat the timeout
    log.info("eval_warmup_start")
    try:
        from app.services.rag.reranker import get_reranker
        reranker = get_reranker()
        await reranker.rerank("test query", [{"content": "warmup", "id": "warmup"}])
        log.info("eval_warmup_done")
    except Exception as exc:
        log.warning("eval_warmup_failed", error=str(exc))

    log.info("eval_start", golden_set=str(_GOLDEN_SET), limit=args.limit, offset=args.offset)

    cases = _load_golden_set(_GOLDEN_SET, limit=args.limit, offset=args.offset)
    log.info("eval_cases_loaded", count=len(cases))

    graph = build_graph(checkpointer=MemorySaver())
    # Judge uses OpenAI gpt-4o-mini (reliable JSON); Groq llama-3.1-8b unreliable for scoring
    judge = get_judge(use_groq=False) if not args.no_judge else None

    run_id = uuid.uuid4()
    git_sha = _get_git_sha()
    results: list[dict] = []

    for i, case in enumerate(cases, 1):
        case_id = case.get("case_id", f"case_{i}")
        log.info("eval_case_start", case_id=case_id, n=i, total=len(cases))

        actual_response = ""
        actual_intent = "general_inquiry"
        tools_called: list[str] = []
        retrieved_chunks: list[dict] = []
        latency_ms = 0
        run_error = ""

        try:
            raw = await _run_case(case, graph)
            actual_response = raw.get("final_response") or raw.get("draft_response") or ""
            actual_intent = raw.get("intent") or "general_inquiry"
            retrieved_chunks = raw.get("retrieved_chunks") or []
            latency_ms = raw.get("_latency_ms", 0)

            # Extract tool names from tool_results
            tool_results = raw.get("tool_results") or {}
            tools_called = list(tool_results.keys())

        except asyncio.TimeoutError:
            run_error = "timeout after 60s"
            log.warning("eval_case_timeout", case_id=case_id)
        except Exception as exc:
            run_error = str(exc)
            log.warning("eval_case_error", case_id=case_id, error=run_error)

        # Deterministic assertions
        assertion = check_assertions(case, actual_response, actual_intent, tools_called)

        # LLM judge
        judge_scores: dict | None = None
        if judge and actual_response and not run_error:
            scores = await judge.judge(
                case, actual_response, retrieved_chunks,
                tool_results=raw.get("tool_results") or None,
            )
            judge_scores = scores.to_dict()
        elif run_error:
            judge_scores = {"groundedness": 0.0, "helpfulness": 0.0, "policy_score": 0.0, "reasoning": run_error, "error": run_error}

        result = {
            "case_id": case_id,
            "category": case.get("category", ""),
            "user_message": case.get("user_message", ""),
            "actual_response": actual_response,
            "ground_truth_answer": case.get("ground_truth_answer", ""),
            "actual_intent": actual_intent,
            "expected_intent": case.get("expected_intent", ""),
            "expected_tools": case.get("expected_tools", []),
            "tools_called": tools_called,
            "passed": assertion.passed,
            "intent_match": assertion.intent_match,
            "tools_match": assertion.tools_match,
            "must_include_pass": assertion.must_include_pass,
            "must_not_include_pass": assertion.must_not_include_pass,
            "failures": assertion.failures,
            "judge_scores": judge_scores,
            "latency_ms": latency_ms,
            "run_error": run_error,
        }
        results.append(result)

        status = "PASS" if assertion.passed else "FAIL"
        log.info(
            "eval_case_done",
            case_id=case_id,
            status=status,
            intent=actual_intent,
            latency_ms=latency_ms,
            failures=assertion.failures or None,
        )

    metrics = compute_aggregate(results)
    # When judge is skipped, rubric scores are all 0 — only gate on pass_rate
    min_rubric = 0.75 if not args.no_judge else 0.0
    ok, violations = check_thresholds(metrics, min_rubric=min_rubric)

    log.info(
        "eval_summary",
        pass_rate=f"{metrics.pass_rate:.1%}",
        passed=metrics.passed,
        total=metrics.total_cases,
        groundedness=metrics.avg_groundedness,
        helpfulness=metrics.avg_helpfulness,
        policy_score=metrics.avg_policy_score,
        intent_accuracy=f"{metrics.intent_accuracy:.1%}",
        tool_accuracy=f"{metrics.tool_accuracy:.1%}",
        avg_latency_ms=metrics.avg_latency_ms,
    )

    if violations:
        log.error("eval_threshold_violations", violations=violations)

    # Persist to DB
    if not args.no_db:
        try:
            await _save_to_db(run_id, git_sha, results, metrics)
        except Exception as exc:
            log.warning("eval_db_persist_failed", error=str(exc))

    # HTML report
    report_path = Path(args.html) if args.html else _DEFAULT_REPORT
    _generate_html(results, metrics, str(run_id), git_sha, report_path)
    print(f"\nHTML report: {report_path}")

    # Print summary to stdout
    print(f"\n{'='*60}")
    print(f"  ResolveAI Eval Results")
    print(f"{'='*60}")
    print(f"  Cases:         {metrics.total_cases}")
    print(f"  Passed:        {metrics.passed}  ({metrics.pass_rate:.1%})")
    print(f"  Failed:        {metrics.failed}")
    print(f"  Groundedness:  {metrics.avg_groundedness:.3f}")
    print(f"  Helpfulness:   {metrics.avg_helpfulness:.3f}")
    print(f"  Policy Score:  {metrics.avg_policy_score:.3f}")
    print(f"  Intent Acc:    {metrics.intent_accuracy:.1%}")
    print(f"  Tool Acc:      {metrics.tool_accuracy:.1%}")
    print(f"  Avg Latency:   {metrics.avg_latency_ms:.0f} ms")
    print(f"{'='*60}")

    if violations:
        print("\n  THRESHOLD VIOLATIONS:")
        for v in violations:
            print(f"  ✗  {v}")
        print()
        return 1

    print("\n  All thresholds met.\n")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ResolveAI eval harness")
    parser.add_argument("--limit", type=int, default=None, help="Run only first N cases")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N cases (for batching)")
    parser.add_argument("--no-db", action="store_true", help="Skip DB persistence")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge (faster, no rubric scores)")
    parser.add_argument("--groq", action="store_true", help="Force Groq for agent + judge (faster, cheaper)")
    parser.add_argument("--html", type=str, default=None, help="Path for HTML report")
    return parser.parse_args()


if __name__ == "__main__":
    import app.core.logging  # noqa: F401  — configure structlog

    args = _parse_args()
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)
