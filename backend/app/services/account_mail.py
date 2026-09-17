"""Transactional account transport. Never uses connected application mailboxes."""
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit
from fastapi import HTTPException

# Test-only memory sink, never logged or enabled in production.
test_messages: dict[str, str] = {}


def configured(settings):
    url = urlsplit(settings.JOBPILOT_ACCOUNT_APP_URL)
    local = settings.ENVIRONMENT != "production" and url.hostname in {"localhost", "127.0.0.1"}
    if (url.scheme != "https" and not (local and url.scheme == "http")) or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise HTTPException(503, "Account email requires a trusted application URL")
    transport = settings.JOBPILOT_ACCOUNT_MAIL_TRANSPORT
    if transport == "test":
        from app.api.routes.e2e import _require_e2e_test_mode
        _require_e2e_test_mode(settings)
    elif transport != "smtp" or not settings.JOBPILOT_ACCOUNT_SMTP_HOST or not settings.JOBPILOT_ACCOUNT_MAIL_FROM:
        raise HTTPException(503, "Account email delivery is unavailable")


def send(settings, email, purpose, token=None):
    configured(settings)
    text = "An account request was received. If you did not request this, ignore this email.\n"
    if token:
        path = "verify-email" if purpose == "verify" else "reset-password"
        # Fragment never reaches web/access logs; the browser posts the token.
        text += f"Continue: {settings.JOBPILOT_ACCOUNT_APP_URL.rstrip('/')}/{path}#token={token}\n"
    else:
        text += "No account action is available for this request. You may sign in or contact your administrator."
    if settings.JOBPILOT_ACCOUNT_MAIL_TRANSPORT == "test":
        test_messages[email] = text
        return
    try:
        message = EmailMessage()
        message["From"] = settings.JOBPILOT_ACCOUNT_MAIL_FROM
        message["To"] = email
        message["Subject"] = "JobPilot account request"
        message.set_content(text)
        with smtplib.SMTP_SSL(settings.JOBPILOT_ACCOUNT_SMTP_HOST, settings.JOBPILOT_ACCOUNT_SMTP_PORT,
                              timeout=10, context=ssl.create_default_context()) as smtp:
            if settings.JOBPILOT_ACCOUNT_SMTP_USER:
                smtp.login(settings.JOBPILOT_ACCOUNT_SMTP_USER, settings.JOBPILOT_ACCOUNT_SMTP_PASSWORD)
            if smtp.send_message(message):
                raise RuntimeError("recipient_not_accepted")
    except Exception:
        raise HTTPException(503, "Account email was not confirmed accepted; try again later") from None
