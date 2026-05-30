"""Inbound channel endpoints — webhooks for WhatsApp/Email and WebSocket for Web."""

from __future__ import annotations

import json
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from app.agent.graph import run_with_cache
from app.schemas.message import InboundMessage, OutboundMessage
from app.services.channels import get_channel_adapter
from app.services.channels.web import connection_manager

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/messages/inbound", tags=["inbound"])


# ── WhatsApp (Twilio) ────────────────────────────────────────────────────────


@router.post("/whatsapp", response_class=PlainTextResponse)
async def whatsapp_inbound(request: Request) -> Response:
    """Receive Twilio WhatsApp webhook, verify signature, enqueue processing."""
    body = await request.body()
    headers = dict(request.headers)
    headers["_url"] = str(request.url)

    adapter = get_channel_adapter("whatsapp")
    if not adapter.verify_webhook(headers, body):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    # Parse form-encoded body
    form = await request.form()
    raw: dict = dict(form)

    msg = await adapter.parse_inbound(raw)

    await _enqueue(msg)
    log.info("whatsapp_inbound_enqueued", msg_id=msg.channel_msg_id, from_=msg.user_identifier)

    # Twilio expects an empty 200 TwiML response (or valid TwiML)
    return PlainTextResponse("", status_code=200)


# ── Email (AWS SES → SNS) ────────────────────────────────────────────────────


@router.post("/email")
async def email_inbound(request: Request) -> Response:
    """Receive AWS SNS notification from SES, verify, enqueue processing."""
    body = await request.body()
    headers = dict(request.headers)

    adapter = get_channel_adapter("email")
    if not adapter.verify_webhook(headers, body):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        raw: dict = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    msg = await adapter.parse_inbound(raw)

    # Skip empty system messages (e.g. SNS subscription confirmations)
    if msg.content:
        await _enqueue(msg)
        log.info("email_inbound_enqueued", msg_id=msg.channel_msg_id, from_=msg.user_identifier)

    return Response(status_code=204)


# ── Web WebSocket ────────────────────────────────────────────────────────────


@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str) -> None:
    """Persistent WebSocket endpoint for the web chat widget.

    Messages are processed inline (no ARQ queue) so the reply arrives on
    the same connection before the client sees a round-trip delay.
    """
    await connection_manager.connect(session_id, websocket)
    try:
        while True:
            text = await websocket.receive_text()

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {"content": text}

            payload.setdefault("session_id", session_id)
            payload.setdefault("msg_id", str(uuid.uuid4()))

            adapter = get_channel_adapter("web")
            msg = await adapter.parse_inbound(payload)

            log.info("ws_message_received", session_id=session_id, length=len(msg.content))

            result = await _run_agent(msg)
            reply = result.get("final_response") or "I'm sorry, I couldn't process your request."

            await connection_manager.send_text(session_id, reply)

    except WebSocketDisconnect:
        connection_manager.disconnect(session_id)


# ── Shared helpers ───────────────────────────────────────────────────────────


async def _enqueue(msg: InboundMessage) -> None:
    """Push message to the ARQ queue for background processing."""
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        from app.config import get_settings

        settings = get_settings()
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await pool.enqueue_job("process_inbound_message", msg.model_dump(mode="json"))
        await pool.aclose()
    except Exception as exc:
        log.error("enqueue_failed", error=str(exc))
        # Fall back to inline processing so no message is silently dropped
        await _run_agent(msg)


async def _run_agent(msg: InboundMessage) -> dict:
    """Build minimal agent state from an InboundMessage and invoke the graph."""
    from app.workers.tasks import build_agent_state

    state = await build_agent_state(msg)
    config = {"configurable": {"thread_id": state["conversation_id"]}}
    return await run_with_cache(state, config=config)
