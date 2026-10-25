"""Outgoing email: password reset and sign-in links.

With SMTP_HOST set, mail goes through that server (any provider: Brevo, Mailgun, SES,
Gmail with an app password...). Without it nothing is sent: the message is kept in
OUTBOX (tests read it) and, on a local machine, the API returns the link so it can be
clicked on screen (Settings.show_dev_links).
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger(__name__)
OUTBOX: list[EmailMessage] = []  # last messages, for tests and local development
_OUTBOX_MAX = 50


def send(to: str, subject: str, text: str) -> bool:
    """Send one plain-text email. Returns True when it left through SMTP."""
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.mail_from or s.support_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    OUTBOX.append(msg)
    del OUTBOX[:-_OUTBOX_MAX]
    if not s.email_enabled:
        log.info("email not configured (SMTP_HOST empty): not sending '%s'", subject)
        return False
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        log.exception("could not send email '%s'", subject)
        return False
