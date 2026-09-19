"""Daily digest delivery adapter. Disabled by default.

Mirrors the account email transport: only explicitly configured transports may
send, and the test sink requires end-to-end test mode. Digest delivery never
reuses connected application mailboxes.
"""
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import HTTPException

# Test-only memory sink, never logged or enabled in production.
test_messages: dict[str, str] = {}


def transport(settings) -> str:
    return settings.JOBPILOT_DIGEST_MAIL_TRANSPORT


def configured(settings) -> bool:
    value = transport(settings)
    if value == "test":
        from app.api.routes.e2e import _require_e2e_test_mode
        _require_e2e_test_mode(settings)
        return True
    if value == "disabled":
        raise HTTPException(503, "Digest email delivery is disabled; previews are in-app only.")
    if value != "smtp" or not settings.JOBPILOT_DIGEST_SMTP_HOST or not settings.JOBPILOT_DIGEST_MAIL_FROM:
        raise HTTPException(503, "Digest email delivery is unavailable; configure SMTP to enable it.")
    return True


def send(settings, email, subject, text) -> str:
    configured(settings)
    if transport(settings) == "test":
        test_messages[email] = f"{subject}\n\n{text}"
        return "test"
    try:
        message = EmailMessage()
        message["From"] = settings.JOBPILOT_DIGEST_MAIL_FROM
        message["To"] = email
        message["Subject"] = subject
        message.set_content(text)
        with smtplib.SMTP_SSL(settings.JOBPILOT_DIGEST_SMTP_HOST, settings.JOBPILOT_DIGEST_SMTP_PORT,
                              timeout=10, context=ssl.create_default_context()) as smtp:
            if settings.JOBPILOT_DIGEST_SMTP_USER:
                smtp.login(settings.JOBPILOT_DIGEST_SMTP_USER, settings.JOBPILOT_DIGEST_SMTP_PASSWORD)
            if smtp.send_message(message):
                raise RuntimeError("recipient_not_accepted")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Digest email was not confirmed accepted; try again later") from None
    return "smtp"