"""
Abstract base class for message queue implementations.

Provides a pluggable interface for publish/subscribe messaging with consumer
group support. Current implementation: Redis Streams. Future: RabbitMQ, Kafka.
"""
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

MessageHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]
"""Async callback signature: (message_id, payload) -> None"""


class BaseMessageQueue(ABC):
    """Abstract message queue with consumer group semantics for cluster-safe consumption."""

    @abstractmethod
    async def publish(self, stream: str, data: dict[str, Any]) -> str:
        """Publish a message to a stream. Returns the message ID assigned by the broker."""
        ...

    @abstractmethod
    async def subscribe(
        self,
        stream: str,
        group: str,
        consumer: str,
        handler: MessageHandler,
    ) -> None:
        """Register a handler for messages on *stream* within *group*.

        *consumer* should be unique per process (e.g. hostname-pid).
        The handler is invoked for each new message; the implementation MUST
        auto-acknowledge after the handler returns without error.
        """
        ...

    @abstractmethod
    async def start_consuming(self) -> None:
        """Start background tasks that poll subscribed streams."""
        ...

    @abstractmethod
    async def stop_consuming(self) -> None:
        """Gracefully stop all background consumption tasks."""
        ...

    @abstractmethod
    async def ensure_group(self, stream: str, group: str) -> None:
        """Create the consumer group if it does not exist yet."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release any resources held by the queue client."""
        ...
