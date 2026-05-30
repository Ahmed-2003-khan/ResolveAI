"""Send test messages via WebSocket so metrics appear in the API process.

Run from project root (outside container):
    pip install websockets
    python scripts/send_test_messages.py
"""

import asyncio
import json
import uuid

try:
    import websockets
except ImportError:
    print("websockets not installed. Running: pip install websockets")
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets"], check=True)
    import websockets

MESSAGES = [
    "mera order ORD-001 kahan hai?",
    "ORD-002 ka status batao",
    "mujhe refund chahiye",
    "account balance kitna hai?",
    "tumhari return policy kya hai?",
    "delivery charges kitne hain?",
    "app open nahi ho rahi",
    "COD available hai kya?",
    "main manager se baat karna chahta hun",
    "payment fail ho rahi hai website pe",
]

WS_URL = "ws://localhost:8000/ws/chat/{session_id}"


async def send_one(msg: str, idx: int) -> None:
    session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    url = WS_URL.format(session_id=session_id)
    try:
        async with websockets.connect(url) as ws:
            await ws.send(msg)
            reply = await asyncio.wait_for(ws.recv(), timeout=60)
            try:
                data = json.loads(reply)
                response_text = data.get("content", str(reply))[:60]
            except Exception:
                response_text = str(reply)[:60]
            print(f"  OK [{idx:02d}] {msg[:35]:35s} -> {response_text}...")
    except Exception as exc:
        print(f"  !! [{idx:02d}] {msg[:35]:35s} -> ERROR: {exc}")


async def main() -> None:
    print("\n" + "="*60)
    print("  Sending test messages via WebSocket")
    print("  (API process metrics -> visible in Grafana)")
    print("="*60)

    for i, msg in enumerate(MESSAGES, 1):
        await send_one(msg, i)

    print("\n" + "="*60)
    print("  Done! Now check Grafana:")
    print("  http://localhost:3001/d/resolveai-v1")
    print("  (Set time range to 'Last 15 minutes')")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
