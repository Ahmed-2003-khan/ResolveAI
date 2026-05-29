"""Abstract base class for all agent tools."""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """Every agent tool must subclass this and fill in the four class attributes."""

    name: str
    description: str
    parameters_schema: dict[str, Any]  # JSON Schema object
    requires_confirmation: bool  # True for write tools

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Run the tool and return a plain dict result."""
        ...
