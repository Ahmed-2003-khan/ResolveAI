"""Email channel adapter — AWS SES inbound via SNS + SES outbound."""

from __future__ import annotations

import asyncio
import json

import structlog

from app.config import get_settings
from app.schemas.message import InboundMessage, OutboundMessage
from app.services.channels.base import ChannelAdapter

log = structlog.get_logger(__name__)


class EmailAdapter(ChannelAdapter):
    channel = "email"

    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        """Basic SNS authenticity check.

        A full implementation would fetch the SigningCertURL, verify the RSA
        signature, and confirm the certificate CN.  For the portfolio sandbox,
        we accept any well-formed SNS notification that carries the expected
        content-type header.  Set EMAIL_WEBHOOK_SECRET in .env to enable a
        shared-secret check instead.
        """
        settings = get_settings()
        secret = getattr(settings, "email_webhook_secret", "")
        if secret:
            provided = headers.get("x-webhook-secret", "")
            return provided == secret

        # Accept if SNS content-type present (dev / sandbox mode)
        content_type = headers.get("content-type", "")
        return "sns" in content_type.lower() or "json" in content_type.lower()

    async def parse_inbound(self, raw: dict) -> InboundMessage:
        """Parse an SNS-wrapped SES email notification.

        SNS wraps the SES notification as a JSON string in ``raw["Message"]``.
        """
        sns_type = raw.get("Type", "")

        if sns_type == "SubscriptionConfirmation":
            # Auto-confirm SNS subscription
            subscribe_url = raw.get("SubscribeURL", "")
            if subscribe_url:
                try:
                    import httpx

                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.get(subscribe_url)
                    log.info("sns_subscription_confirmed")
                except Exception as exc:
                    log.warning("sns_subscription_confirm_failed", error=str(exc))
            return InboundMessage(
                channel="email",
                channel_msg_id=raw.get("MessageId", ""),
                user_identifier="sns-subscription@system",
                content="",
                raw_payload=raw,
            )

        # Parse the nested SES notification
        try:
            ses_data: dict = json.loads(raw.get("Message", "{}"))
        except (json.JSONDecodeError, TypeError):
            ses_data = {}

        mail = ses_data.get("mail", {})
        source = mail.get("source", "") or mail.get("commonHeaders", {}).get("from", [""])[0]
        subject = mail.get("commonHeaders", {}).get("subject", "(no subject)")
        body_text = ses_data.get("content", subject)

        return InboundMessage(
            channel="email",
            channel_msg_id=mail.get("messageId", raw.get("MessageId", "")),
            user_identifier=source,
            content=body_text,
            raw_payload=raw,
        )

    async def send(self, msg: OutboundMessage) -> str:
        settings = get_settings()
        if not settings.aws_access_key_id or not settings.aws_secret_access_key:
            log.warning("aws_credentials_missing_skipping_send", to=msg.to)
            return "mock-ses-id"

        def _send_sync() -> str:
            import boto3

            client = boto3.client(
                "ses",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
            response = client.send_email(
                Source=settings.ses_from_email,
                Destination={"ToAddresses": [msg.to]},
                Message={
                    "Subject": {"Data": "Re: Your support request"},
                    "Body": {"Text": {"Data": msg.content}},
                },
            )
            return response["MessageId"]

        message_id: str = await asyncio.to_thread(_send_sync)
        log.info("email_sent", to=msg.to, message_id=message_id)
        return message_id
