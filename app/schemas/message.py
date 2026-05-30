from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    channel: Literal["whatsapp", "email", "web"]
    channel_msg_id: str
    user_identifier: str  # phone | email | web session id
    content: str
    received_at: datetime = Field(default_factory=datetime.utcnow)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OutboundMessage(BaseModel):
    channel: Literal["whatsapp", "email", "web"]
    to: str
    content: str
    reply_to: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
