"""Webhook client factory."""
from app.configs.settings import settings
from app.libs.webhook.base import BaseWebhookClient


def create_webhook_client() -> BaseWebhookClient:
    """Create the configured webhook delivery provider."""
    match settings.WEBHOOK_PROVIDER:
        case "http":
            from app.libs.webhook.providers.http import HttpWebhookClient

            return HttpWebhookClient()
        case provider:
            raise ValueError(f"Unsupported webhook provider: {provider}")
