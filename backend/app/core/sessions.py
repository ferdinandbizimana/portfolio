"""Login sessions: an opaque random token in a cookie, its SHA-256 in the database."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import User, UserSession


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: Session,
    user: User,
    settings: Settings,
    now: datetime,
    ip_address: str | None,
    user_agent: str | None,
) -> str:
    """Create a session and return the token to put in the cookie."""
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            token_hash=_hash_token(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.session_absolute_hours),
            ip_address=ip_address,
            user_agent=(user_agent or "")[:512] or None,
        )
    )
    return token


def resolve_session(
    db: Session, token: str | None, settings: Settings, now: datetime
) -> tuple[UserSession, User] | None:
    """Return the live session and its user, refreshing its idle timer, or None."""
    if not token:
        return None
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == _hash_token(token))
    ).first()
    if row is None:
        return None
    user_session, user = row
    idle_limit = user_session.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    if now >= user_session.expires_at or now >= idle_limit:
        db.delete(user_session)
        db.commit()
        return None
    user_session.last_seen_at = now
    db.commit()
    return user_session, user


def revoke_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == _hash_token(token)))


def revoke_other_sessions(db: Session, user_id: int, keep: UserSession) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user_id, UserSession.id != keep.id))
