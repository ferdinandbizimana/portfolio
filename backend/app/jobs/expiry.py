"""Sending the monthly expiry follow-up (scheduler) and the "send now" job."""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import expiry
from app import storage as storage_module
from app.core.config import Settings, get_settings
from app.core.mailer import Mailer
from app.db.models import ExpiryReview
from app.db.session import session_scope
from app.jobs.notify import get_mailer
from app.scheduling import local_time
from app.storage import LocalStorage

logger = logging.getLogger(__name__)


def ready(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.mail_from and settings.expiry_mail_to)


def _deliver(
    db: Session,
    settings: Settings,
    storage: LocalStorage,
    review: ExpiryReview,
    mailer: Mailer,
    now: datetime,
) -> None:
    month = f"{local_time(settings, now):%Y-%m}"
    mailer.send(expiry.monthly_message(settings, storage, review, month))
    review.mailed_month = month
    review.mailed_at = now
    db.commit()


def send_monthly(
    db: Session, settings: Settings, now: datetime, mailer: Mailer, storage: LocalStorage
) -> bool:
    """On the last day of the month: the latest expiry monitoring run, once a month."""
    local_now = local_time(settings, now)
    if not ready(settings) or not expiry.mail_due(settings, local_now):
        return False
    run = expiry.latest_run(db)
    if run is None:
        return False
    review = expiry.ensure_review(db, storage, run)
    db.commit()
    if review.mailed_month == f"{local_now:%Y-%m}":
        return False
    _deliver(db, settings, storage, review, mailer, now)
    return True


def send_now(review_id: int) -> bool:
    """Background job for the admin's "Send the e-mail now" button."""
    settings = get_settings()
    if not ready(settings):
        logger.info("Expiry follow-up not sent: SMTP or EXPIRY_MAIL_TO is not set up")
        return False
    with session_scope() as db:
        review = db.get(ExpiryReview, review_id)
        if review is None:
            return False
        _deliver(
            db, settings, storage_module.get_storage(), review, get_mailer(), datetime.now(UTC)
        )
    return True
