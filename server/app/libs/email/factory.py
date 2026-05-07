"""
Email client factory.
"""
from app.libs.email.base import BaseEmailClient


def create_email_client() -> BaseEmailClient:
    from app.libs.email.providers.smtp import SMTPEmailClient
    return SMTPEmailClient()
