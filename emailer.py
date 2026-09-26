"""
Gmail SMTP sender. Credentials come from environment variables
(GitHub Actions secrets), never from files:

  GMAIL_USER          sending Gmail address
  GMAIL_APP_PASSWORD  16-character app password
  EMAIL_TO            recipient(s), comma-separated
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import settings

log = logging.getLogger(__name__)


def send(subject: str, html: str) -> bool:
    user = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("EMAIL_TO", user or "")
    if not (user and password and to):
        log.warning("Email skipped: GMAIL_USER / GMAIL_APP_PASSWORD / EMAIL_TO not set")
        return False

    recipients = [a.strip() for a in to.split(",") if a.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText("This report is HTML. Open it in a mail client that shows HTML.", "plain"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=ssl.create_default_context()) as s:
        s.login(user, password)
        s.sendmail(user, recipients, msg.as_string())
    log.info("Email sent to %s", ", ".join(recipients))
    return True
