"""WhatsApp channel adapter — Twilio sandbox."""

from __future__ import annotations

import asyncio

import structlog

from app.config import get_settings
from app.schemas.message import InboundMessage, OutboundMessage
from app.services.channels.base import ChannelAdapter

log = structlog.get_logger(__name__)


class WhatsAppAdapter(ChannelAdapter):
    channel = "whatsapp"

    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        """Verify the Twilio HMAC-SHA1 request signature."""
        settings = get_settings()
        if not settings.twilio_auth_token:
            log.warning("twilio_auth_token_missing_skipping_verification")
            return True  # allow in dev when no credentials are configured

        twilio_sig = headers.get("x-twilio-signature", "")
        if not twilio_sig:
            return False

        url = headers.get("_url", "")
        if not url:
            log.warning("whatsapp_verify_missing_url")
            return False

        # Parse form body into a plain dict for the validator
        try:
            from urllib.parse import parse_qs, unquote_plus

            params: dict[str, str] = {}
            for pair in body.decode().split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[unquote_plus(k)] = unquote_plus(v)
        except Exception:
            return False

        try:
            from twilio.request_validator import RequestValidator

            validator = RequestValidator(settings.twilio_auth_token)
            return validator.validate(url, params, twilio_sig)
        except Exception as exc:
            log.warning("twilio_validation_error", error=str(exc))
            return False

    async def parse_inbound(self, raw: dict) -> InboundMessage:
        from_ = raw.get("From", "")
        # Twilio prefixes WhatsApp numbers with "whatsapp:"
        user_phone = from_.removeprefix("whatsapp:")
        return InboundMessage(
            channel="whatsapp",
            channel_msg_id=raw.get("MessageSid", ""),
            user_identifier=user_phone,
            content=raw.get("Body", ""),
            raw_payload=raw,
        )

    async def send(self, msg: OutboundMessage) -> str:
        settings = get_settings()
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            log.warning("twilio_credentials_missing_skipping_send", to=msg.to)
            return "mock-sid"

        to = msg.to if msg.to.startswith("whatsapp:") else f"whatsapp:{msg.to}"

        def _send_sync() -> str:
            from twilio.rest import Client

            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            message = client.messages.create(
                from_=settings.twilio_whatsapp_from,
                to=to,
                body=msg.content,
            )
            return message.sid

        sid: str = await asyncio.to_thread(_send_sync)
        log.info("whatsapp_sent", to=msg.to, sid=sid)
        return sid
