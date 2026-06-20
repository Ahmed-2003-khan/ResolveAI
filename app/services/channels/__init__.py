from app.services.channels.base import ChannelAdapter
from app.services.channels.email import EmailAdapter
from app.services.channels.web import WebAdapter
from app.services.channels.whatsapp import WhatsAppAdapter

_ADAPTERS: dict[str, ChannelAdapter] = {
    "whatsapp": WhatsAppAdapter(),
    "email": EmailAdapter(),
    "web": WebAdapter(),
}


def get_channel_adapter(channel: str) -> ChannelAdapter:
    try:
        return _ADAPTERS[channel]
    except KeyError:
        raise ValueError(f"Unknown channel: {channel!r}") from None


__all__ = [
    "ChannelAdapter",
    "WhatsAppAdapter",
    "EmailAdapter",
    "WebAdapter",
    "get_channel_adapter",
]
