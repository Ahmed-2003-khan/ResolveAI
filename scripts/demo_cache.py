"""
Semantic Cache Demo
====================
Ek real example ko teen baar agent se guzarta hai:

  Call 1 — Bilkul nayi query   → CACHE MISS  → full agent pipeline chalta hai
  Call 2 — Exactly same query  → CACHE HIT   → fori jawab, agent band
  Call 3 — Similar query (alag words, same meaning) → CACHE HIT (semantic match)

Usage:
    python scripts/demo_cache.py
"""

import asyncio
import textwrap
import time

from app.agent.graph import run_with_cache

# ── Helpers ──────────────────────────────────────────────────────────────────


def _divider(char="-", width=62):
    print(char * width)


def _header(title: str):
    print()
    _divider("=")
    print(f"  {title}")
    _divider("=")


def _section(title: str):
    print()
    _divider()
    print(f"  {title}")
    _divider()


def _print_result(result: dict, elapsed_sec: float):
    audit = result.get("audit_trail") or []

    # Cache hit ya miss?
    cache_node = next((e for e in audit if e.get("node") == "semantic_cache"), None)
    if cache_node and cache_node.get("cache_hit"):
        status_tag = "[HIT]  Cache se jawab aaya — agent nahi chala"
    else:
        status_tag = "[MISS] Cache mein kuch nahi — full pipeline chala"

    print(f"\n  Status          : {status_tag}")
    print(f"  Wall-clock time : {elapsed_sec:.2f}s")
    print(f"  Total latency   : {result.get('total_latency_ms', 0)} ms  (LLM time only)")
    print(f"  Total cost      : ${result.get('total_cost_usd', 0.0):.6f}")

    print()
    _divider()
    print("  FINAL RESPONSE:")
    _divider()
    response = result.get("final_response") or "(koi jawab nahi mila)"
    for line in textwrap.wrap(response, width=58):
        print(f"  {line}")

    if not (cache_node and cache_node.get("cache_hit")):
        print()
        _divider()
        print("  NODE-BY-NODE AUDIT TRAIL:")
        _divider()
        for entry in audit:
            node = entry.get("node", "?")
            lat = entry.get("latency_ms", 0)
            cost = entry.get("cost_usd")
            cost_str = f"  ${cost:.6f}" if cost is not None else "          "

            note = ""
            if node == "classify_intent":
                note = f"→ intent = '{entry.get('output')}'"
            elif node == "redact_pii":
                note = f"→ {entry.get('pii_tokens_found', 0)} PII token(s) redact kiye"
            elif node == "retrieve":
                note = f"→ {entry.get('chunks_returned', 0)} chunk(s) mile"
            elif node == "plan_tools":
                tools = entry.get("output", [])
                note = f"→ tools = {tools if tools else '(koi tool nahi)'}"
            elif node == "execute_tools":
                note = f"→ {entry.get('tools_executed', [])}"
            elif node == "compose_response":
                note = f"→ {'(dobara koshish)' if entry.get('is_retry') else '(pehli koshish)'}"
            elif node == "critique":
                note = f"→ score = {entry.get('score')}  |  {entry.get('feedback', '')}"
            elif node == "send_reply":
                note = "→ response finalize hua"

            print(f"  [{node:20s}] {lat:5d} ms{cost_str}   {note}")


def _make_state(message: str, conv_id: str) -> dict:
    return {
        "conversation_id": conv_id,
        "user_id": "user-001",
        "user_message": message,
        "user_profile": {"plan_tier": "standard", "language_pref": "roman_ur"},
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


# ── Main ─────────────────────────────────────────────────────────────────────


async def main():
    _header("ResolveAI — Semantic Cache Live Demo")

    # ── Call 1: Bilkul nayi query ─────────────────────────────────────────
    msg_original = "mera order ORD-001 kahan hai? 3 din ho gaye hain"

    _section("CALL 1 of 3 — Nayi query (pehli baar — cache empty hai)")
    print(f'\n  Message: "{msg_original}"')
    print("\n  Cache mein kuch nahi hai abhi — full pipeline chalega...\n")

    t0 = time.perf_counter()
    result1 = await run_with_cache(_make_state(msg_original, "conv-demo-001"))
    elapsed1 = time.perf_counter() - t0

    _print_result(result1, elapsed1)

    # ── Call 2: Exactly same query ────────────────────────────────────────
    _section("CALL 2 of 3 — Exactly same query (cache warm hai)")
    print(f'\n  Message: "{msg_original}"')
    print("\n  Cache mein same message store ho gaya tha — seedha jawab milega...\n")

    t0 = time.perf_counter()
    result2 = await run_with_cache(_make_state(msg_original, "conv-demo-002"))
    elapsed2 = time.perf_counter() - t0

    _print_result(result2, elapsed2)

    # ── Call 3: Similar lekin alag wording ────────────────────────────────
    msg_similar = "yaar mujhe batao ORD-001 ka kya hua? deliver hua ya nahi?"

    _section("CALL 3 of 3 — Similar sawaal, alag alfaaz (semantic match test)")
    print(f'\n  Message: "{msg_similar}"')
    print("\n  Alag words hain lekin meaning same hai — cache hit hona chahiye...\n")

    t0 = time.perf_counter()
    result3 = await run_with_cache(_make_state(msg_similar, "conv-demo-003"))
    elapsed3 = time.perf_counter() - t0

    _print_result(result3, elapsed3)

    # ── Summary ───────────────────────────────────────────────────────────
    _header("SUMMARY — Teeno calls ka moazna")

    print(f"""
  {'Call':<8} {'Message (mukhtasar)':<42} {'Time':>7}  {'Cost':>10}
  {'-'*8} {'-'*42} {'-'*7}  {'-'*10}
  {'#1':<8} {'Nayi query (full pipeline)':<42} {elapsed1:>6.2f}s  ${result1.get('total_cost_usd', 0):.6f}
  {'#2':<8} {'Same query  (CACHE HIT)':<42} {elapsed2:>6.2f}s  ${result2.get('total_cost_usd', 0):.6f}
  {'#3':<8} {'Similar query (CACHE HIT)':<42} {elapsed3:>6.2f}s  ${result3.get('total_cost_usd', 0):.6f}
    """)

    speedup = elapsed1 / elapsed2 if elapsed2 > 0 else 0
    saved = result1.get("total_cost_usd", 0) - result2.get("total_cost_usd", 0)
    print(f"  Cache ne Call #2 ko {speedup:.1f}x tez kiya  |  ${saved:.6f} bachaye")

    # DB se verify karo ke row actually store hua
    from sqlalchemy import text

    from app.core.db import async_session_factory

    async with async_session_factory() as session:
        row = (
            (
                await session.execute(
                    text("SELECT query_normalized, hit_count FROM semantic_cache LIMIT 5")
                )
            )
            .mappings()
            .all()
        )

    print()
    _divider()
    print("  DATABASE — semantic_cache table ki rows:")
    _divider()
    for r in row:
        q = r["query_normalized"][:52]
        print(f"  hits={r['hit_count']}  \"{q}...\"")

    print()
    _divider("=")
    print()


if __name__ == "__main__":
    asyncio.run(main())
