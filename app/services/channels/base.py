from abc import ABC, abstractmethod

from app.schemas.message import InboundMessage, OutboundMessage


class ChannelAdapter(ABC):
    channel: str

    @abstractmethod
    async def parse_inbound(self, raw: dict) -> InboundMessage: ...

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> str:
        """Deliver message via the channel.  Returns provider message ID."""
        ...

    @abstractmethod
    def verify_webhook(self, headers: dict, body: bytes) -> bool:
        """Return True if the inbound request is authentic.

        Implementations may expect a synthetic ``_url`` key in the headers dict
        so validators that need the full request URL (e.g. Twilio) can read it
        from ``headers["_url"]``.
        """
        ...
