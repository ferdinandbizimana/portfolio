"""Shared FastAPI dependencies: database, Redis, clock, current user."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.sessions import resolve_session
from app.db.models import User, UserSession
from app.db.session import get_session
from app.jobs.queue import get_redis


def get_db() -> Iterator[Session]:
    yield from get_session()


def get_redis_client() -> Redis:
    return get_redis()


def get_now() -> datetime:
    """The current time. Overridden in tests."""
    return datetime.now(UTC)


DbDep = Annotated[Session, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis_client)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
NowDep = Annotated[datetime, Depends(get_now)]


def client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers, so this is the real client behind Caddy.
    return request.client.host if request.client else "unknown"


@dataclass
class CurrentUser:
    user: User
    session: UserSession


def get_current_user(
    request: Request, db: DbDep, settings: SettingsDep, now: NowDep
) -> CurrentUser:
    resolved = resolve_session(db, request.cookies.get(settings.session_cookie_name), settings, now)
    if resolved is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in.")
    user_session, user = resolved
    return CurrentUser(user=user, session=user_session)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
