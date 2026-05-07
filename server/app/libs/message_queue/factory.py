"""
Message queue factory — creates the configured provider instance.
"""
from app.configs.settings import settings
from app.libs.message_queue.base import BaseMessageQueue


def create_message_queue() -> BaseMessageQueue:
    provider = settings.MESSAGE_QUEUE_PROVIDER
    match provider:
        case "redis_streams":
            from app.db.redis import redis_client
            from app.libs.message_queue.providers.redis_streams import RedisStreamsQueue

            return RedisStreamsQueue(redis_client.client)
        case _:
            raise ValueError(f"Unsupported message queue provider: {provider}")
