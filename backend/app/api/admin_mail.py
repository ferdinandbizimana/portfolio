"""Admin: check that contact form e-mail works."""

import logging
import smtplib

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, DbDep, SettingsDep, client_ip
from app.api.public import MailerDep
from app.core import audit
from app.core.mailer import MailNotConfiguredError, contact_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/mail", tags=["admin"])


class MailStatus(BaseModel):
    configured: bool
    recipient: str
    smtp_host: str


@router.get("", response_model=MailStatus)
def mail_status(_: CurrentUserDep, settings: SettingsDep) -> MailStatus:
    return MailStatus(
        configured=bool(settings.smtp_host and settings.mail_from and settings.contact_to_email),
        recipient=settings.contact_to_email,
        smtp_host=settings.smtp_host,
    )


@router.post("/test", status_code=status.HTTP_204_NO_CONTENT)
def send_test(
    request: Request, current: CurrentUserDep, db: DbDep, settings: SettingsDep, mailer: MailerDep
) -> None:
    try:
        mailer.send(
            contact_message(
                settings,
                "Portfolio test",
                settings.contact_to_email or "nobody@example.com",
                "Test message",
                "This is a test message sent from Settings in your admin area. "
                "If you can read it, the contact form works.",
            )
        )
    except MailNotConfiguredError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    except (OSError, smtplib.SMTPException) as error:
        logger.exception("Test e-mail failed")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"The mail server refused or did not answer: {error}"
        ) from None
    audit.record(db, "contact.test_sent", user_id=current.user.id, ip_address=client_ip(request))
    db.commit()
