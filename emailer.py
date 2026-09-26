"""
Gmail SMTP sender. Credentials come from environment variables
(GitHub Actions secrets), never from files:

  GMAIL_USER          sending Gmail address
  GMAIL_APP_PASSWORD  16-character app password
  EMAIL_TO            recipient(s), comma-separated

Body = inline-styled summary (renders in Gmail). The full report is attached,
because Gmail strips <style> blocks and CSS variables the report relies on.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import settings

log = logging.getLogger(__name__)


def send(subject: str, body_html: str, report_html: str | None = None, report_name: str = "report.html") -> bool:
    user = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("EMAIL_TO", user or "")
    if not (user and password and to):
        log.warning("Email skipped: GMAIL_USER / GMAIL_APP_PASSWORD / EMAIL_TO not set")
        return False

    recipients = [a.strip() for a in to.split(",") if a.strip()]
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)

    body = MIMEMultipart("alternative")
    body.attach(MIMEText("Crypto Supertrend report. Open the attached HTML file in a browser.", "plain"))
    body.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(body)

    if report_html:
        part = MIMEApplication(report_html.encode("utf-8"), _subtype="html")
        part.add_header("Content-Disposition", "attachment", filename=report_name)
        msg.attach(part)

    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, context=ssl.create_default_context()) as s:
        s.login(user, password)
        s.sendmail(user, recipients, msg.as_string())
    log.info("Email sent to %s", ", ".join(recipients))
    return True
