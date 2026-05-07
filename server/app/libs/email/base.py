"""
Abstract base class for email clients.
"""
from abc import ABC, abstractmethod


class BaseEmailClient(ABC):

    @abstractmethod
    async def send(
        self,
        to: str,
        subject: str,
        body: str,
    ) -> None:
        """Send a plain-text email."""
        ...
