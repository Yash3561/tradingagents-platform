"""
Outbound email (password reset, email verification).

SMTP is optional: when SMTP_HOST is unset the link is logged to the backend
log instead of sent — dev/local flows keep working without a mail provider.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def _frontend_base() -> str:
    url = get_settings().frontend_url.strip().rstrip("/")
    return url or "http://localhost:5173"


def _send_smtp(to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if s.smtp_port == 465:
        server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
        server.starttls()
    try:
        if s.smtp_user:
            server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)
    finally:
        server.quit()


async def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email; returns True if handed to SMTP, False if only logged."""
    s = get_settings()
    if not s.smtp_host:
        logger.warning("[mailer] SMTP not configured — email to %s: %s\n%s", to, subject, body)
        return False
    try:
        await asyncio.to_thread(_send_smtp, to, subject, body)
        return True
    except Exception:
        logger.exception("[mailer] failed to send to %s", to)
        return False


async def send_password_reset(to: str, token: str) -> bool:
    link = f"{_frontend_base()}/reset-password?token={token}"
    return await send_email(
        to,
        "Reset your TradingAgents password",
        "Someone requested a password reset for your TradingAgents account.\n\n"
        f"Reset it here (link expires in 30 minutes):\n{link}\n\n"
        "If this wasn't you, you can ignore this email — your password is unchanged.",
    )


async def send_verification(to: str, token: str) -> bool:
    link = f"{_frontend_base()}/verify-email?token={token}"
    return await send_email(
        to,
        "Verify your TradingAgents email",
        "Welcome to TradingAgents!\n\n"
        f"Confirm your email address (link expires in 48 hours):\n{link}\n",
    )
