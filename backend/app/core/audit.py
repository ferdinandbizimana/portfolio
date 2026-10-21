"""Audit log: a record of important actions."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEvent

logger = logging.getLogger("audit")


class AuditAction:
    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGIN_RATE_LIMITED = "auth.login_rate_limited"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGED = "auth.password_changed"  # noqa: S105 (an action name)


def record(
    session: Session,
    action: str,
    *,
    user_id: int | None = None,
    ip_address: str | None = None,
    **detail: Any,
) -> AuditEvent:
    """Add an audit event to the session. The caller commits."""
    event = AuditEvent(action=action, user_id=user_id, ip_address=ip_address, detail=detail)
    session.add(event)
    logger.info("%s user=%s ip=%s %s", action, user_id, ip_address, detail)
    return event
