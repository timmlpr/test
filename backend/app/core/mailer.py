"""Swappable mail transport. Without SMTP config, mails land in an in-memory dev outbox."""
from __future__ import annotations

import logging
import smtplib
from collections import deque
from email.message import EmailMessage

from app.settings import get_settings

log = logging.getLogger("tracelow.mail")
OUTBOX: deque = deque(maxlen=100)


def send_mail(to: str, subject: str, text: str) -> None:
    s = get_settings()
    if not s.smtp_host:
        OUTBOX.append({"to": to, "subject": subject, "text": text})
        log.info("dev-outbox: mail queued (subject=%s)", subject)  # no recipient in logs
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(text)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
