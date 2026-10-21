"""Login, logout, current user and password change."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    NowDep,
    RedisDep,
    SettingsDep,
    client_ip,
)
from app.core import audit
from app.core.audit import AuditAction
from app.core.config import Settings
from app.core.passwords import hash_password, needs_rehash, password_problem, verify_password
from app.core.ratelimit import LoginRateLimiter
from app.core.sessions import create_session, revoke_other_sessions, revoke_session
from app.db.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

WRONG_CREDENTIALS = "The e-mail or password is not correct."


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    email: str
    last_login_at: datetime | None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


def _limiter(redis: RedisDep, settings: Settings) -> LoginRateLimiter:
    return LoginRateLimiter(redis, settings.login_max_failures, settings.login_window_minutes * 60)


def _set_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DbDep,
    redis: RedisDep,
    settings: SettingsDep,
    now: NowDep,
) -> UserOut:
    ip = client_ip(request)
    email = body.email.strip().lower()
    limiter = _limiter(redis, settings)

    if limiter.is_blocked(email, ip):
        audit.record(db, AuditAction.LOGIN_RATE_LIMITED, ip_address=ip, email=email)
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {settings.login_window_minutes} minutes.",
        )

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    # Always run the hash check, even for an unknown e-mail, so timing does not
    # reveal which e-mails exist.
    password_ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not password_ok:
        limiter.record_failure(email, ip)
        audit.record(db, AuditAction.LOGIN_FAILED, ip_address=ip, email=email)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG_CREDENTIALS)

    limiter.reset(email, ip)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    previous_login = user.last_login_at
    user.last_login_at = now
    token = create_session(db, user, settings, now, ip, request.headers.get("user-agent"))
    audit.record(db, AuditAction.LOGIN, user_id=user.id, ip_address=ip)
    db.commit()
    _set_cookie(response, settings, token)
    return UserOut(email=user.email, last_login_at=previous_login)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbDep, settings: SettingsDep) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        revoke_session(db, token)
        audit.record(db, AuditAction.LOGOUT, ip_address=client_ip(request))
        db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(current: CurrentUserDep) -> UserOut:
    return UserOut(email=current.user.email, last_login_at=current.user.last_login_at)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChangeRequest,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    now: NowDep,
) -> None:
    if not verify_password(current.user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The current password is not correct.")
    if problem := password_problem(body.new_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
    current.user.password_hash = hash_password(body.new_password)
    current.user.password_changed_at = now
    revoke_other_sessions(db, current.user.id, keep=current.session)
    audit.record(
        db, AuditAction.PASSWORD_CHANGED, user_id=current.user.id, ip_address=client_ip(request)
    )
    db.commit()
