"""
Notification service — sends email/webhook alerts for high-scoring jobs.
Uses SMTP for email and/or HTTP POST for webhooks.
"""

import json
import smtplib
import structlog
from email.mime.text import MIMEText
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = structlog.get_logger(__name__)


def send_email_notification(
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
) -> bool:
    """Send an email notification via SMTP."""
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info("email_notification_sent", to=to_addr, subject=subject)
        return True
    except Exception as e:
        logger.error("email_notification_failed", error=str(e))
        return False


def send_webhook_notification(
    webhook_url: str,
    payload: dict,
) -> bool:
    """Send an HTTP POST webhook notification (Discord, Slack, etc.)."""
    try:
        data = json.dumps(payload).encode()
        req = Request(webhook_url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        urlopen(req, timeout=10)
        logger.info("webhook_notification_sent", url=webhook_url[:60])
        return True
    except URLError as e:
        logger.error("webhook_notification_failed", error=str(e))
        return False


def notify_high_score_job(
    job_title: str,
    company: str,
    score: int,
    url: str,
    reasoning: str,
    email_config: Optional[dict] = None,
    webhook_url: Optional[str] = None,
) -> None:
    """
    Send notification for a high-scoring job.
    Called automatically when a job scores above a configurable threshold.

    email_config example:
        {"host": "smtp.gmail.com", "port": 587, "user": "...", "password": "...",
         "from_addr": "...", "to_addr": "..."}
    """
    subject = f"🎯 High-match job: {job_title} @ {company} ({score}/100)"
    body = (
        f"Job: {job_title}\n"
        f"Company: {company}\n"
        f"Match Score: {score}/100\n"
        f"URL: {url}\n\n"
        f"Reasoning: {reasoning}\n"
    )

    if email_config:
        send_email_notification(
            smtp_host=email_config["host"],
            smtp_port=email_config["port"],
            smtp_user=email_config["user"],
            smtp_password=email_config["password"],
            from_addr=email_config["from_addr"],
            to_addr=email_config["to_addr"],
            subject=subject,
            body=body,
        )

    if webhook_url:
        send_webhook_notification(webhook_url, {
            "title": job_title,
            "company": company,
            "score": score,
            "url": url,
            "reasoning": reasoning,
        })
