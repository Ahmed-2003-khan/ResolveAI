"""KB Coverage Audit — Phase 13.

For EVERY case in the golden set, queries the retriever and shows the actual
chunks returned with a relevance verdict. Helps identify where KB content is
missing or wrong before adding new data.

Verdict logic per category:
  kb_faq / general_inquiry  → needs KB: scored by ground-truth token overlap
  order_status / account / refund / txn / ticket / escalate / session_end / abuse / oos
                            → KB is supplementary; scored by topic overlap with user message

Usage (inside Docker):
    # All 100 cases
    docker compose exec -T api python -m scripts.kb_coverage_audit

    # Only FAQ / general_inquiry cases
    docker compose exec -T api python -m scripts.kb_coverage_audit --category kb_faq,general_inquiry

    # Save to file
    docker compose exec -T api python -m scripts.kb_coverage_audit > /app/reports/kb_audit.txt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

_GOLDEN_SET = Path(__file__).parent.parent / "data" / "eval" / "golden_set.jsonl"

# Categories where KB is the PRIMARY source of truth (agent must answer from KB).
_KB_PRIMARY = {"kb_faq", "general_inquiry"}

# For kb_primary cases: if best chunk score < this, it's a real gap.
_FAQ_GAP_THRESHOLD = 0.50

# For tool-based cases: if best chunk score < this, KB is unhelpful (less critical).
_TOOL_GAP_THRESHOLD = 0.30

_STOP = {
    "the", "and", "for", "are", "our", "you", "your", "can", "will",
    "with", "that", "this", "from", "not", "but", "all", "has", "have",
    "is", "in", "of", "to", "a", "an", "or", "it", "at", "by", "be",
    "as", "we", "on", "if", "any", "also", "available", "may", "hai",
    "kya", "mera", "meri", "aap", "main", "hun", "tha", "thi", "hain",
}


def _key_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2 and t not in _STOP}


def _score(reference: str, chunk_content: str) -> float:
    """Fraction of reference key tokens found in chunk_content."""
    ref_tokens = _key_tokens(reference)
    if not ref_tokens:
        return 0.0
    chunk_lower = chunk_content.lower()
    matched = {t for t in ref_tokens if t in chunk_lower}
    return len(matched) / len(ref_tokens)


def _best_score_across_chunks(reference: str, chunks: list[dict]) -> tuple[float, str, str]:
    """Return (best_score, source_id, content_snippet) across all chunks."""
    best_score = 0.0
    best_src = "—"
    best_snippet = ""
    for c in chunks:
        content = c.get("content", "")
        s = _score(reference, content)
        if s > best_score:
            best_score = s
            best_src = c.get("source_id", "?")
            best_snippet = content[:200].replace("\n", " ")
    return best_score, best_src, best_snippet


async def audit(filter_categories: set[str] | None) -> None:
    from app.services.rag.retriever import get_retriever
    from app.services.rag.reranker import get_reranker

    cases: list[dict] = []
    with _GOLDEN_SET.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            if filter_categories is None or c.get("category") in filter_categories:
                cases.append(c)

    if not cases:
        print("No matching cases found.")
        return

    retriever = get_retriever()
    reranker = get_reranker()
    await reranker.rerank("warmup", [{"content": "warmup", "id": "w"}])

    gaps_kb: list[dict] = []      # KB-primary cases with bad coverage
    gaps_tool: list[dict] = []    # Tool cases with no useful KB at all
    ok_cases: list[dict] = []

    print(f"\n{'='*72}")
    print(f"  KB Coverage Audit — {len(cases)} cases")
    print(f"{'='*72}")

    for case in cases:
        case_id    = case["case_id"]
        category   = case.get("category", "")
        question   = case["user_message"]
        ground_truth = case.get("ground_truth_answer", "")
        is_kb_primary = category in _KB_PRIMARY

        chunks = await retriever.retrieve(question, k=5)

        # Reference text: use ground truth for kb_primary, question for tool cases
        reference = ground_truth if is_kb_primary else question
        best_score, best_src, best_snippet = _best_score_across_chunks(reference, chunks)

        threshold = _FAQ_GAP_THRESHOLD if is_kb_primary else _TOOL_GAP_THRESHOLD
        is_gap = best_score < threshold or len(chunks) == 0

        # Classify verdict
        if is_kb_primary and is_gap:
            verdict = "KB-GAP  ❌"
        elif not is_kb_primary and is_gap:
            verdict = "NO-KB   ⚠️ "
        else:
            verdict = "OK      ✅"

        # Print result
        print(f"\n[{verdict}] {case_id:10s}  cat={category:20s}  "
              f"chunks={len(chunks)}  score={best_score:.2f}  best={best_src}")
        print(f"  Q : {question[:90]}")

        if is_kb_primary:
            print(f"  GT: {ground_truth[:90]}")

        # Always show top chunk content for inspection
        if chunks:
            top = chunks[0]
            print(f"  #1 chunk [{top.get('source_id')}]: "
                  f"{top.get('content','')[:150].replace(chr(10),' ')}")
        else:
            print("  #1 chunk: (none returned)")

        # Show all chunk sources briefly
        if len(chunks) > 1:
            srcs = ", ".join(c.get("source_id", "?") for c in chunks)
            print(f"  All sources: {srcs}")

        entry = {
            "case_id": case_id,
            "category": category,
            "question": question,
            "ground_truth": ground_truth,
            "best_score": best_score,
            "best_chunk": best_src,
            "chunks_returned": len(chunks),
            "is_kb_primary": is_kb_primary,
        }
        if is_kb_primary and is_gap:
            gaps_kb.append(entry)
        elif not is_kb_primary and is_gap:
            gaps_tool.append(entry)
        else:
            ok_cases.append(entry)

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(cases)
    print(f"\n\n{'='*72}")
    print(f"  SUMMARY")
    print(f"{'='*72}")
    print(f"  Total cases       : {total}")
    print(f"  OK                : {len(ok_cases)}")
    print(f"  KB-GAP (critical) : {len(gaps_kb)}   ← need new KB entries")
    print(f"  NO-KB (minor)     : {len(gaps_tool)}   ← tool cases, KB not needed")
    print(f"{'='*72}")

    if gaps_kb:
        print(f"\n{'─'*72}")
        print("  KB-GAP cases — need new FAQ/article entries:")
        print(f"{'─'*72}")
        for g in gaps_kb:
            print(f"\n  {g['case_id']:10s}  score={g['best_score']:.2f}  "
                  f"chunks={g['chunks_returned']}  best={g['best_chunk']}")
            print(f"  Q : {g['question']}")
            print(f"  GT: {g['ground_truth']}")

    if gaps_tool:
        print(f"\n{'─'*72}")
        print("  NO-KB cases (tool-based, low priority):")
        print(f"{'─'*72}")
        for g in gaps_tool:
            print(f"  {g['case_id']:10s}  score={g['best_score']:.2f}  "
                  f"Q: {g['question'][:70]}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KB coverage audit — full golden set")
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Comma-separated categories to audit (default: all). "
             "e.g. kb_faq,general_inquiry",
    )
    return parser.parse_args()


if __name__ == "__main__":
    import app.core.logging  # noqa: F401

    args = _parse_args()
    filter_cats = (
        {c.strip() for c in args.category.split(",")}
        if args.category else None
    )
    asyncio.run(audit(filter_cats))
