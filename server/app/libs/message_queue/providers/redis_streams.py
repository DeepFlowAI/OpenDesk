"""
Redis Streams implementation of BaseMessageQueue.

Supports consumer groups for cluster-safe message distribution: when multiple
service instances join the same group, each message is delivered to exactly one
consumer.  Unacknowledged messages are automatically re-claimed after a timeout.
"""
import asyncio
import json
import logging
import os
import socket
from typing import Any

import redis.asyncio as aioredis

from app.libs.message_queue.base import BaseMessageQueue, MessageHandler

logger = logging.getLogger(__name__)

_DEFAULT_BLOCK_MS = 2000
_DEFAULT_BATCH_SIZE = 10
_CLAIM_MIN_IDLE_MS = 30_000


def _default_consumer_name() -> str:
    """Generate a unique consumer name from hostname and PID."""
    return f"{socket.gethostname()}-{os.getpid()}"


class RedisStreamsQueue(BaseMessageQueue):
    """Redis Streams backed message queue with consumer group semantics."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._subscriptions: list[dict[str, Any]] = []
        self._tasks: list[asyncio.Task] = []
        self._running = False

    # -- publish ---------------------------------------------------------------

    async def publish(self, stream: str, data: dict[str, Any]) -> str:
        payload = {"data": json.dumps(data, ensure_ascii=False)}
        message_id: bytes | str = await self._redis.xadd(stream, payload)
        mid = message_id if isinstance(message_id, str) else message_id.decode()
        logger.debug("Published to %s: %s", stream, mid)
        return mid

    # -- subscribe / consume ---------------------------------------------------

    async def subscribe(
        self,
        stream: str,
        group: str,
        consumer: str,
        handler: MessageHandler,
    ) -> None:
        await self.ensure_group(stream, group)
        self._subscriptions.append(
            {"stream": stream, "group": group, "consumer": consumer, "handler": handler}
        )
        logger.info("Subscribed: stream=%s group=%s consumer=%s", stream, group, consumer)

    async def start_consuming(self) -> None:
        if self._running:
            return
        self._running = True
        for sub in self._subscriptions:
            task = asyncio.create_task(self._consume_loop(sub))
            self._tasks.append(task)
        logger.info("Started %d consumer tasks", len(self._tasks))

    async def stop_consuming(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("All consumer tasks stopped")

    # -- group management ------------------------------------------------------

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("Created consumer group: stream=%s group=%s", stream, group)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                pass  # group already exists
            else:
                raise

    # -- lifecycle -------------------------------------------------------------

    async def close(self) -> None:
        await self.stop_consuming()

    # -- internal --------------------------------------------------------------

    async def _consume_loop(self, sub: dict[str, Any]) -> None:
        stream = sub["stream"]
        group = sub["group"]
        consumer = sub["consumer"]
        handler: MessageHandler = sub["handler"]

        while self._running:
            try:
                # Read new messages assigned to this consumer
                results = await self._redis.xreadgroup(
                    group,
                    consumer,
                    {stream: ">"},
                    count=_DEFAULT_BATCH_SIZE,
                    block=_DEFAULT_BLOCK_MS,
                )
                if results:
                    for _stream_name, messages in results:
                        for msg_id, fields in messages:
                            mid = msg_id if isinstance(msg_id, str) else msg_id.decode()
                            await self._process_message(stream, group, mid, fields, handler)

                # Periodically claim stale pending messages from other consumers
                await self._claim_pending(stream, group, consumer, handler)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in consume loop for stream=%s", stream)
                await asyncio.sleep(1)

    async def _process_message(
        self,
        stream: str,
        group: str,
        msg_id: str,
        fields: dict,
        handler: MessageHandler,
    ) -> None:
        try:
            raw = fields.get("data") or fields.get(b"data", b"{}") 
            if isinstance(raw, bytes):
                raw = raw.decode()
            payload = json.loads(raw)
            await handler(msg_id, payload)
            await self._redis.xack(stream, group, msg_id)
        except Exception:
            logger.exception("Handler error for message %s on stream %s", msg_id, stream)

    async def _claim_pending(
        self,
        stream: str,
        group: str,
        consumer: str,
        handler: MessageHandler,
    ) -> None:
        """Claim messages that have been pending for too long (idle consumers)."""
        try:
            claimed = await self._redis.xautoclaim(
                stream, group, consumer, min_idle_time=_CLAIM_MIN_IDLE_MS, start_id="0", count=5
            )
            # xautoclaim returns (next_start_id, [(id, fields), ...], deleted_ids)
            if claimed and len(claimed) > 1:
                for msg_id, fields in claimed[1]:
                    if fields:
                        mid = msg_id if isinstance(msg_id, str) else msg_id.decode()
                        await self._process_message(stream, group, mid, fields, handler)
        except Exception:
            pass  # autoclaim is best-effort
