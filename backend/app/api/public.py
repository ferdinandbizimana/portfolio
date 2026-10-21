"""Public portfolio: what visitors can read, and the contact form."""

import logging
import smtplib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis import Redis
from sqlalchemy import select

from app.api.deps import DbDep, RedisDep, SettingsDep, client_ip
from app.content import service
from app.content.schemas import ContactIn, PortfolioOut, ProjectOut
from app.core import audit
from app.core.config import Settings, get_settings
from app.core.mailer import Mailer, MailNotConfiguredError, SmtpMailer, contact_message
from app.db.models import Project

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public"])


def get_mailer(settings: Annotated[Settings, Depends(get_settings)]) -> Mailer:
    return SmtpMailer(settings)


MailerDep = Annotated[Mailer, Depends(get_mailer)]


@router.get("/portfolio", response_model=PortfolioOut)
def portfolio(db: DbDep) -> PortfolioOut:
    return PortfolioOut(
        profile=service.profile_out(db, service.get_profile(db)),
        experience=[service.experience_out(e) for e in service.experience_entries(db)],
        skills=[service.skill_group_out(g) for g in service.skill_groups(db)],
        projects=[
            service.project_summary_out(db, p) for p in service.projects(db, published_only=True)
        ],
    )


@router.get("/projects/{slug}", response_model=ProjectOut)
def project(slug: str, db: DbDep) -> ProjectOut:
    found = db.scalar(select(Project).where(Project.slug == slug, Project.published.is_(True)))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found.")
    return service.project_out(db, found)


def _contact_allowed(redis: Redis, ip: str, max_per_hour: int) -> bool:
    key = f"contact:ip:{ip}"
    count = int(redis.incr(key))  # type: ignore[arg-type]
    if count == 1:
        redis.expire(key, 3600)
    return count <= max_per_hour


@router.post("/contact", status_code=status.HTTP_202_ACCEPTED)
def contact(
    body: ContactIn,
    request: Request,
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
    mailer: MailerDep,
) -> dict[str, str]:
    ip = client_ip(request)
    accepted = {"status": "Thank you. Your message has been sent."}
    if body.website:
        # Spam robot: pretend it worked, send nothing.
        audit.record(db, "contact.spam_blocked", ip_address=ip)
        db.commit()
        return accepted
    if not _contact_allowed(redis, ip, settings.contact_max_per_hour):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "You have sent several messages already. Please try again in an hour.",
        )
    try:
        mailer.send(contact_message(settings, body.name, body.email, body.subject, body.message))
    except (MailNotConfiguredError, OSError, smtplib.SMTPException):
        logger.exception("Contact message could not be sent")
        audit.record(db, "contact.failed", ip_address=ip)
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Your message could not be sent right now. Please try again later.",
        ) from None
    audit.record(db, "contact.sent", ip_address=ip, reply_to=body.email)
    db.commit()
    return accepted
