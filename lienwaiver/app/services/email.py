"""Outgoing email with three backends: console (dev), smtp (M365 SMTP AUTH), graph (M365 Graph API)."""
from __future__ import annotations

import base64
import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage

import httpx

from ..config import settings

log = logging.getLogger("lienwaiver.email")


@dataclass
class Attachment:
    filename: str
    content: bytes
    mime: str = "application/pdf"


@dataclass
class Mail:
    to: list[str]
    subject: str
    body: str
    attachments: list[Attachment] = field(default_factory=list)


class ConsoleBackend:
    sent: list[Mail] = []

    def send(self, mail: Mail) -> None:
        ConsoleBackend.sent.append(mail)
        names = ", ".join(a.filename for a in mail.attachments) or "none"
        log.info("EMAIL to=%s subject=%r attachments=%s\n%s", mail.to, mail.subject, names, mail.body)


class SmtpBackend:
    def send(self, mail: Mail) -> None:
        msg = EmailMessage()
        msg["From"] = f"{settings.email_from_name} <{settings.email_from}>"
        msg["To"] = ", ".join(mail.to)
        msg["Subject"] = mail.subject
        msg.set_content(mail.body)
        for a in mail.attachments:
            maintype, _, subtype = a.mime.partition("/")
            msg.add_attachment(a.content, maintype=maintype, subtype=subtype, filename=a.filename)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


class GraphBackend:
    """Sends as settings.email_from using client credentials (application permission Mail.Send)."""

    def _token(self) -> str:
        url = f"https://login.microsoftonline.com/{settings.graph_tenant_id}/oauth2/v2.0/token"
        data = {
            "client_id": settings.graph_client_id,
            "client_secret": settings.graph_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        r = httpx.post(url, data=data, timeout=30)
        r.raise_for_status()
        return r.json()["access_token"]

    def send(self, mail: Mail) -> None:
        payload = {
            "message": {
                "subject": mail.subject,
                "body": {"contentType": "Text", "content": mail.body},
                "toRecipients": [{"emailAddress": {"address": t}} for t in mail.to],
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": a.filename,
                        "contentType": a.mime,
                        "contentBytes": base64.b64encode(a.content).decode(),
                    }
                    for a in mail.attachments
                ],
            },
            "saveToSentItems": True,
        }
        url = f"https://graph.microsoft.com/v1.0/users/{settings.email_from}/sendMail"
        r = httpx.post(url, json=payload, headers={"Authorization": f"Bearer {self._token()}"}, timeout=60)
        r.raise_for_status()


def get_backend():
    return {"smtp": SmtpBackend, "graph": GraphBackend}.get(settings.email_backend, ConsoleBackend)()


def send_mail(mail: Mail) -> None:
    mail.to = [t for t in mail.to if t]
    if not mail.to:
        log.warning("No recipient for %r, not sent", mail.subject)
        return
    get_backend().send(mail)
