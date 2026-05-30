"""Unit tests for channel adapters and message schemas."""

from __future__ import annotations

import json

import pytest

from app.schemas.message import InboundMessage, OutboundMessage
from app.services.channels import get_channel_adapter
from app.services.channels.email import EmailAdapter
from app.services.channels.web import WebAdapter
from app.services.channels.whatsapp import WhatsAppAdapter


# ── Schema tests ─────────────────────────────────────────────────────────────


def test_inbound_message_schema():
    msg = InboundMessage(
        channel="whatsapp",
        channel_msg_id="SM123",
        user_identifier="+923001234567",
        content="Hello",
    )
    assert msg.channel == "whatsapp"
    assert msg.user_identifier == "+923001234567"
    assert msg.raw_payload == {}


def test_outbound_message_schema():
    msg = OutboundMessage(
        channel="whatsapp",
        to="+923001234567",
        content="Hi there!",
    )
    assert msg.channel == "whatsapp"
    assert msg.reply_to is None
    assert msg.metadata == {}


def test_inbound_message_invalid_channel():
    with pytest.raises(Exception):
        InboundMessage(
            channel="telegram",  # not in Literal
            channel_msg_id="x",
            user_identifier="y",
            content="z",
        )


# ── Channel registry ──────────────────────────────────────────────────────────


def test_get_channel_adapter_whatsapp():
    adapter = get_channel_adapter("whatsapp")
    assert isinstance(adapter, WhatsAppAdapter)
    assert adapter.channel == "whatsapp"


def test_get_channel_adapter_email():
    adapter = get_channel_adapter("email")
    assert isinstance(adapter, EmailAdapter)
    assert adapter.channel == "email"


def test_get_channel_adapter_web():
    adapter = get_channel_adapter("web")
    assert isinstance(adapter, WebAdapter)
    assert adapter.channel == "web"


def test_get_channel_adapter_unknown():
    with pytest.raises(ValueError, match="Unknown channel"):
        get_channel_adapter("telegram")


# ── WhatsApp adapter ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_whatsapp_parse_inbound():
    adapter = WhatsAppAdapter()
    raw = {
        "From": "whatsapp:+923001234567",
        "To": "whatsapp:+14155238886",
        "Body": "Mera order kahan hai?",
        "MessageSid": "SM_abc123",
        "AccountSid": "ACtest",
    }
    msg = await adapter.parse_inbound(raw)
    assert msg.channel == "whatsapp"
    assert msg.channel_msg_id == "SM_abc123"
    assert msg.user_identifier == "+923001234567"
    assert msg.content == "Mera order kahan hai?"
    assert msg.raw_payload == raw


@pytest.mark.asyncio
async def test_whatsapp_parse_inbound_no_prefix():
    adapter = WhatsAppAdapter()
    raw = {"From": "+923001234567", "Body": "Hi", "MessageSid": "SM1"}
    msg = await adapter.parse_inbound(raw)
    assert msg.user_identifier == "+923001234567"


def test_whatsapp_verify_webhook_no_credentials(monkeypatch):
    """Without credentials configured, verification passes in dev mode."""
    from app.config import Settings

    monkeypatch.setattr(
        "app.services.channels.whatsapp.get_settings",
        lambda: Settings(twilio_auth_token=""),
    )
    adapter = WhatsAppAdapter()
    assert adapter.verify_webhook({}, b"") is True


def test_whatsapp_verify_webhook_missing_signature(monkeypatch):
    """With credentials set but missing header, verification fails."""
    from app.config import Settings

    monkeypatch.setattr(
        "app.services.channels.whatsapp.get_settings",
        lambda: Settings(twilio_auth_token="test_token"),
    )
    adapter = WhatsAppAdapter()
    assert adapter.verify_webhook({"_url": "https://example.com/webhook"}, b"Body=hi") is False


@pytest.mark.asyncio
async def test_whatsapp_send_no_credentials(monkeypatch):
    """Without credentials, send() returns mock-sid gracefully."""
    from app.config import Settings

    monkeypatch.setattr(
        "app.services.channels.whatsapp.get_settings",
        lambda: Settings(twilio_account_sid="", twilio_auth_token=""),
    )
    adapter = WhatsAppAdapter()
    out = OutboundMessage(channel="whatsapp", to="+923001234567", content="Hello")
    sid = await adapter.send(out)
    assert sid == "mock-sid"


# ── Email adapter ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_parse_sns_notification():
    adapter = EmailAdapter()
    ses_payload = {
        "mail": {
            "messageId": "email-id-001",
            "source": "customer@example.com",
            "commonHeaders": {
                "subject": "Need help with my order",
                "from": ["Customer <customer@example.com>"],
            },
        },
        "content": "I need help with order ORD-123",
    }
    raw = {
        "Type": "Notification",
        "MessageId": "sns-id-001",
        "Message": json.dumps(ses_payload),
    }
    msg = await adapter.parse_inbound(raw)
    assert msg.channel == "email"
    assert msg.channel_msg_id == "email-id-001"
    assert msg.user_identifier == "customer@example.com"
    assert "ORD-123" in msg.content


@pytest.mark.asyncio
async def test_email_parse_subscription_confirmation():
    adapter = EmailAdapter()
    raw = {
        "Type": "SubscriptionConfirmation",
        "MessageId": "sub-001",
        "SubscribeURL": "",  # empty URL to skip HTTP call
    }
    msg = await adapter.parse_inbound(raw)
    assert msg.channel == "email"
    assert msg.content == ""  # subscription confirmations have no user content


def test_email_verify_webhook_json_content_type():
    adapter = EmailAdapter()
    headers = {"content-type": "application/json"}
    assert adapter.verify_webhook(headers, b"{}") is True


def test_email_verify_webhook_sns_content_type():
    adapter = EmailAdapter()
    headers = {"content-type": "text/plain; charset=UTF-8; application/x-amz-sns-message-type"}
    assert adapter.verify_webhook(headers, b"{}") is True


@pytest.mark.asyncio
async def test_email_send_no_credentials(monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(
        "app.services.channels.email.get_settings",
        lambda: Settings(aws_access_key_id="", aws_secret_access_key=""),
    )
    adapter = EmailAdapter()
    out = OutboundMessage(channel="email", to="customer@example.com", content="Hello")
    sid = await adapter.send(out)
    assert sid == "mock-ses-id"


# ── Web adapter ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_web_parse_inbound():
    adapter = WebAdapter()
    raw = {
        "session_id": "web-abc123",
        "msg_id": "msg-001",
        "content": "Hi, I need support",
    }
    msg = await adapter.parse_inbound(raw)
    assert msg.channel == "web"
    assert msg.user_identifier == "web-abc123"
    assert msg.channel_msg_id == "msg-001"
    assert msg.content == "Hi, I need support"


def test_web_verify_webhook_always_true():
    adapter = WebAdapter()
    assert adapter.verify_webhook({}, b"") is True
