"""Web channel adapter — WebSocket-based chat widget."""

from __future__ import annotations

import structlog
from fastapi import WebSocket

from app.schemas.message import InboundMessage, OutboundMessage
from app.services.channels.base import ChannelAdapter

log = structlog.get_logger(__name__)


class ConnectionManager:
    """In-process registry of active WebSocket connections keyed by session_id."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[session_id] = websocket
        log.info("ws_connected", session_id=session_id)

    def disconnect(self, session_id: str) -> None:
        self._connections.pop(session_id, None)
        log.info("ws_disconnected", session_id=session_id)

    async def send_text(self, session_id: str, text: str) -> None:
        ws = self._connections.get(session_id)
        if ws is not None:
            await ws.send_text(text)
        else:
            log.warning("ws_send_no_connection", session_id=session_id)


# Module-level singleton shared within the FastAPI process
connection_manager = ConnectionManager()


class WebAdapter(ChannelAdapter):
    channel = "web"

    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        # WebSocket connections are authenticated at the transport layer;
        # there is no external webhook signature to verify.
        return True

    async def parse_inbound(self, raw: dict) -> InboundMessage:
        return InboundMessage(
            channel="web",
            channel_msg_id=raw.get("msg_id", ""),
            user_identifier=raw.get("session_id", ""),
            content=raw.get("content", ""),
            raw_payload=raw,
        )

    async def send(self, msg: OutboundMessage) -> str:
        await connection_manager.send_text(msg.to, msg.content)
        return f"ws:{msg.to}"
