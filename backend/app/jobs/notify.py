"""E-mail to the owner when a scheduled run has finished."""

import logging
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.mailer import Mailer, SmtpMailer
from app.db.models import AnalysisRun, Schedule

logger = logging.getLogger(__name__)

STATUS_WORDS = {"succeeded": "finished", "failed": "failed", "cancelled": "was cancelled"}


def get_mailer() -> Mailer:
    return SmtpMailer(get_settings())


def run_message(settings: Settings, run: AnalysisRun, schedule: Schedule) -> EmailMessage:
    passed = sum(1 for c in run.checks if c.get("passed"))
    outcome = STATUS_WORDS.get(run.status, run.status)
    message = EmailMessage()
    message["From"] = formataddr(("Portfolio analyses", settings.mail_from))
    message["To"] = settings.notify_to
    message["Subject"] = f"[Portfolio] {schedule.name}: run {outcome}"
    message["Message-ID"] = make_msgid(domain=settings.mail_from.rsplit("@", 1)[-1])
    lines = [
        f"The scheduled run of {schedule.name!r} {outcome}.",
        "",
        f"Run: #{run.id} {run.label}",
        f"Status: {run.message}",
    ]
    if run.checks:
        lines.append(f"Self-checks: {passed} of {len(run.checks)} passed")
    lines += [f"- {error}" for error in run.errors[:10]]
    lines += ["", f"Open it: {settings.site_url.rstrip('/')}/admin/runs/{run.id}", ""]
    message.set_content("\n".join(lines))
    return message


def notify_run_finished(db: Session, run: AnalysisRun) -> None:
    """Never raises: a mail problem must not change the run."""
    if run.schedule_id is None:
        return
    try:
        schedule = db.get(Schedule, run.schedule_id)
        settings = get_settings()
        if schedule is None or not schedule.notify:
            return
        if not (settings.smtp_host and settings.mail_from and settings.notify_to):
            logger.info("Run %s finished; no notification because e-mail is not set up", run.id)
            return
        get_mailer().send(run_message(settings, run, schedule))
    except Exception:
        logger.exception("Could not send the notification for run %s", run.id)
