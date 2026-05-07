"""
SMTP email provider using smtplib (SSL).
Runs blocking I/O in a thread pool to stay async-safe.
"""
import asyncio
import smtplib
from email.mime.text import MIMEText

from app.configs.settings import settings
from app.libs.email.base import BaseEmailClient


class SMTPEmailClient(BaseEmailClient):

    async def send(self, to: str, subject: str, body: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._send_sync, to, subject, body)

    @staticmethod
    def _send_sync(to: str, subject: str, body: str) -> None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to

        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, [to], msg.as_string())
