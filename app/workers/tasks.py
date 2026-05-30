"""ARQ background tasks — process inbound messages through the agent graph."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select, update

from app.agent.graph import run_with_cache
from app.core.db import async_session_factory
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user_profile import UserProfile
from app.schemas.message import InboundMessage, OutboundMessage
from app.services.channels import get_channel_adapter

log = structlog.get_logger(__name__)


# ── Public task (called by ARQ) ──────────────────────────────────────────────


async def process_inbound_message(ctx: dict, message_data: dict) -> None:
    """End-to-end pipeline: parse → persist inbound → run agent → send reply → persist outbound."""
    try:
        msg = InboundMessage(**message_data)
    except Exception as exc:
        log.error("invalid_message_data", error=str(exc), data=message_data)
        return

    log.info(
        "processing_inbound_message",
        channel=msg.channel,
        user=msg.user_identifier,
        msg_id=msg.channel_msg_id,
    )

    try:
        state = await build_agent_state(msg)
        conversation_id = state["conversation_id"]

        config = {"configurable": {"thread_id": conversation_id}}
        result = await run_with_cache(state, config=config)

        final_response = result.get("final_response") or ""

        await _persist_outbound(conversation_id, final_response, result)

        if final_response:
            adapter = get_channel_adapter(msg.channel)
            out = OutboundMessage(
                channel=msg.channel,
                to=msg.user_identifier,
                content=final_response,
            )
            await adapter.send(out)

        log.info(
            "message_processed",
            conversation_id=conversation_id,
            escalated=result.get("should_escalate", False),
        )

    except Exception as exc:
        log.exception("process_inbound_message_failed", error=str(exc))
        raise


# ── State builder (also used by inline WebSocket handler) ───────────────────


async def build_agent_state(msg: InboundMessage) -> dict[str, Any]:
    """Look up / create DB records and return a populated AgentState dict."""
    async with async_session_factory() as session:
        user = await _get_or_create_user(session, msg)
        conversation = await _get_or_create_conversation(session, user.id, msg.channel)
        history = await _load_history(session, conversation.id)

        # Persist the inbound message
        db_msg = Message(
            conversation_id=conversation.id,
            direction="inbound",
            sender_type="user",
            content=msg.content,
            channel_msg_id=msg.channel_msg_id,
            created_at=datetime.now(timezone.utc),
        )
        session.add(db_msg)

        conversation.last_activity = datetime.now(timezone.utc)
        await session.commit()

        user_profile = {
            "user_id": str(user.id),
            "phone": user.phone,
            "email": user.email,
            "full_name": user.full_name,
            "plan_tier": user.plan_tier or "standard",
            "account_status": user.account_status,
            "language_pref": user.language_pref,
        }

        return {
            "conversation_id": str(conversation.id),
            "user_id": str(user.id),
            "user_message": msg.content,
            "user_profile": user_profile,
            "conversation_history": history,
            # Pipeline outputs — initialised empty
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
            # Telemetry
            "total_cost_usd": 0.0,
            "total_latency_ms": 0,
            "audit_trail": [],
        }


# ── DB helpers ───────────────────────────────────────────────────────────────


async def _get_or_create_user(session, msg: InboundMessage) -> UserProfile:
    """Return an existing user or create a new minimal one."""
    identifier = msg.user_identifier

    if msg.channel == "whatsapp":
        stmt = select(UserProfile).where(UserProfile.phone == identifier)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            user = UserProfile(
                phone=identifier,
                account_status="active",
                language_pref="en",
            )
            session.add(user)
            await session.flush()  # populate id before returning

    elif msg.channel == "email":
        stmt = select(UserProfile).where(UserProfile.email == identifier)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            # phone is NOT NULL; use a synthetic value unique per email
            synthetic_phone = f"email:{identifier[:15]}"
            user = UserProfile(
                phone=synthetic_phone,
                email=identifier,
                account_status="active",
                language_pref="en",
            )
            session.add(user)
            await session.flush()

    else:  # web
        # session_id is stored as a phone-like key
        synthetic_phone = f"web:{identifier[:15]}"
        stmt = select(UserProfile).where(UserProfile.phone == synthetic_phone)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            user = UserProfile(
                phone=synthetic_phone,
                account_status="active",
                language_pref="en",
            )
            session.add(user)
            await session.flush()

    return user


async def _get_or_create_conversation(session, user_id: uuid.UUID, channel: str) -> Conversation:
    """Return the latest active conversation for the user/channel or create one."""
    stmt = (
        select(Conversation)
        .where(
            Conversation.user_id == user_id,
            Conversation.channel == channel,
            Conversation.status == "active",
        )
        .order_by(Conversation.last_activity.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    conv = result.scalar_one_or_none()

    if conv is None:
        conv = Conversation(
            user_id=user_id,
            channel=channel,
            status="active",
            started_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )
        session.add(conv)
        await session.flush()

    return conv


async def _load_history(session, conversation_id: uuid.UUID) -> list[dict]:
    """Return the last 10 messages as OpenAI-style chat history."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    result = await session.execute(stmt)
    messages = result.scalars().all()

    history = []
    for m in reversed(messages):
        role = "user" if m.direction == "inbound" else "assistant"
        history.append({"role": role, "content": m.content})
    return history


async def _persist_outbound(conversation_id: str, content: str, result: dict) -> None:
    """Write the agent's reply and audit trail entries to the database."""
    if not conversation_id:
        return
    conv_uuid = uuid.UUID(conversation_id)
    async with async_session_factory() as session:
        # Always update conversation last_activity
        stmt = select(Conversation).where(Conversation.id == conv_uuid)
        res = await session.execute(stmt)
        conv = res.scalar_one_or_none()
        if conv:
            conv.last_activity = datetime.now(timezone.utc)
            # Explicit goodbye → immediately resolve; human escalation → escalated
            intent = result.get("intent", "")
            if intent == "session_end":
                conv.status = "resolved"
            elif result.get("should_escalate"):
                conv.status = "escalated"

        msg_id: uuid.UUID | None = None
        if content:
            msg = Message(
                conversation_id=conv_uuid,
                direction="outbound",
                sender_type="agent",
                content=content,
                created_at=datetime.now(timezone.utc),
                metadata_={
                    "intent": result.get("intent"),
                    "tools_used": list(result.get("tool_results", {}).keys()),
                    "cost_usd": result.get("total_cost_usd", 0),
                    "latency_ms": result.get("total_latency_ms", 0),
                },
            )
            session.add(msg)
            await session.flush()  # get msg.id before audit rows reference it
            msg_id = msg.id

        # Persist every node's audit entry from the agent state
        for entry in result.get("audit_trail", []):
            raw_output = entry.get("output")
            output_str = (
                raw_output
                if isinstance(raw_output, str) or raw_output is None
                else json.dumps(raw_output, default=str)
            )
            raw_input = entry.get("input")
            input_str = (
                raw_input
                if isinstance(raw_input, str) or raw_input is None
                else json.dumps(raw_input, default=str)
            )
            audit = AuditLog(
                conversation_id=conv_uuid,
                message_id=msg_id,
                node_name=entry.get("node"),
                model_used=entry.get("model"),
                prompt_version=entry.get("prompt_version"),
                input_tokens=entry.get("input_tokens"),
                output_tokens=entry.get("output_tokens"),
                cost_usd=entry.get("cost_usd"),
                latency_ms=entry.get("latency_ms"),
                input_redacted=input_str,
                output=output_str,
                created_at=datetime.now(timezone.utc),
            )
            session.add(audit)

        await session.commit()


# ── Periodic task ─────────────────────────────────────────────────────────────


INACTIVITY_MINUTES = 30


async def auto_resolve_inactive_conversations(ctx: dict) -> None:
    """Mark conversations that have had no activity for INACTIVITY_MINUTES as resolved.

    Runs every 5 minutes via the ARQ cron schedule in arq_settings.py.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=INACTIVITY_MINUTES)
    async with async_session_factory() as session:
        stmt = (
            update(Conversation)
            .where(
                Conversation.status == "active",
                Conversation.last_activity < cutoff,
            )
            .values(status="resolved")
            .returning(Conversation.id)
        )
        result = await session.execute(stmt)
        resolved_ids = result.scalars().all()
        await session.commit()

    if resolved_ids:
        log.info(
            "auto_resolved_inactive_conversations",
            count=len(resolved_ids),
            cutoff_minutes=INACTIVITY_MINUTES,
        )
