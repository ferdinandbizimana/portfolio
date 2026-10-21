"""Sending e-mail by SMTP (contact form messages)."""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

from app.core.config import Settings


class MailNotConfiguredError(Exception):
    pass


class Mailer(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, message: EmailMessage) -> None:
        s = self._settings
        if not s.smtp_host or not s.mail_from:
            raise MailNotConfiguredError("SMTP_HOST and MAIL_FROM must be set.")
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if s.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=context)
        else:
            smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
        with smtp:
            if s.smtp_security == "starttls":
                smtp.starttls(context=context)
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(message)


def contact_message(
    settings: Settings, name: str, email: str, subject: str, body: str
) -> EmailMessage:
    """The e-mail sent to the portfolio owner for a contact form submission."""
    if not settings.contact_to_email or not settings.mail_from:
        raise MailNotConfiguredError("CONTACT_TO_EMAIL and MAIL_FROM must be set.")
    message = EmailMessage()
    message["From"] = formataddr(("Portfolio contact form", settings.mail_from))
    message["To"] = settings.contact_to_email
    message["Reply-To"] = formataddr((name, email))
    message["Subject"] = f"[Portfolio] {subject}"
    message["Message-ID"] = make_msgid(domain=settings.mail_from.rsplit("@", 1)[-1])
    message.set_content(
        f"New message from the contact form on your portfolio.\n\n"
        f"Name: {name}\nE-mail: {email}\nSubject: {subject}\n\n{body}\n\n"
        f"Reply to this e-mail to answer {name} directly.\n"
    )
    return message
