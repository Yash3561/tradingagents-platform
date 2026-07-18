"""
Outbound email (password reset, email verification, trade alerts).

Provider order:
1. Brevo HTTPS API when BREVO_API_KEY is set — REQUIRED on Render: Render
   blocks outbound SMTP ports (25/465/587) on all plans, so smtplib gets
   "[Errno 101] Network is unreachable" no matter the credentials
   (discovered live 2026-07-18). Sender address (SMTP_FROM) must be a
   Brevo-verified sender.
2. Plain SMTP when SMTP_HOST is set — works locally / on hosts that allow
   SMTP egress.
3. Neither set: the message is logged at WARNING — dev flows keep working
   without a mail provider.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def _send_brevo(to: str, subject: str, body: str) -> None:
    import requests
    s = get_settings()
    r = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": s.brevo_api_key, "content-type": "application/json"},
        json={
            "sender": {"name": "TradingAgents", "email": s.smtp_from or s.smtp_user},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        },
        timeout=15,
    )
    if r.status_code >= 400:
        # Surface Brevo's error body — raise_for_status loses it, and it names
        # the actual problem (unverified sender, suspended account, bad recipient)
        raise RuntimeError(f"brevo {r.status_code}: {r.text[:500]}")
    logger.info("[mailer] brevo accepted email to %s: %s", to, r.text[:200])


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
    """Send an email; returns True if handed to a provider, False if only logged."""
    s = get_settings()
    if getattr(s, "brevo_api_key", ""):
        try:
            await asyncio.to_thread(_send_brevo, to, subject, body)
            return True
        except Exception:
            logger.exception("[mailer] brevo send failed to %s", to)
            return False
    if not s.smtp_host:
        logger.warning("[mailer] no provider configured — email to %s: %s\n%s", to, subject, body)
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
