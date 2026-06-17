"""Show all retrieved chunks for every kb_faq / general_inquiry case.

Usage (inside Docker):
    docker compose exec -T api python -m scripts.show_chunks
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

_GOLDEN = Path(__file__).parent.parent / "data" / "eval" / "golden_set.jsonl"
_KB_PRIMARY = {"kb_faq", "general_inquiry"}


async def main() -> None:
    from app.services.rag.retriever import get_retriever
    from app.services.rag.reranker import get_reranker

    cases = []
    with _GOLDEN.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            if c.get("category") in _KB_PRIMARY:
                cases.append(c)

    retriever = get_retriever()
    reranker = get_reranker()
    await reranker.rerank("warmup", [{"content": "warmup", "id": "w"}])

    for case in cases:
        print("=" * 72)
        print(f"CASE : {case['case_id']}  |  {case.get('category')}")
        print(f"Q    : {case['user_message']}")
        gt = case.get("ground_truth_answer", "")
        if gt:
            print(f"GT   : {gt[:120]}")

        chunks = await retriever.retrieve(case["user_message"], k=5)
        print(f"CHUNKS RETURNED: {len(chunks)}")

        for i, chunk in enumerate(chunks, 1):
            src = chunk.get("source_id", "?")
            title = chunk.get("title", "")
            content = chunk.get("content", "").replace("\n", " ")
            print(f"  [{i}] {src}  title={title[:50]}")
            print(f"       {content[:280]}")

        print()


if __name__ == "__main__":
    import app.core.logging  # noqa: F401
    asyncio.run(main())
