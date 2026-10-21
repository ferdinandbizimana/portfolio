from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AuditEvent, User, UserSession
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, Clock


def login(client: TestClient, email: str = ADMIN_EMAIL, password: str = ADMIN_PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/auth/login", json={"email": email, "password": password})


def actions(db: Session) -> list[str]:
    return list(db.scalars(select(AuditEvent.action).order_by(AuditEvent.id)))


def test_login_sets_a_secure_session_cookie_and_logs_the_event(
    client: TestClient, admin: User, db: Session
) -> None:
    response = login(client)

    assert response.status_code == 200
    assert response.json()["email"] == ADMIN_EMAIL
    cookie = response.headers["set-cookie"]
    assert "session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert actions(db) == ["auth.login"]
    stored = db.scalars(select(UserSession)).one()
    assert stored.token_hash not in cookie  # only the hash is stored, never the token


def test_login_is_case_insensitive_on_email(client: TestClient, admin: User) -> None:
    assert login(client, email="  Admin@Example.COM ").status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_answer(
    client: TestClient, admin: User, db: Session
) -> None:
    wrong_password = login(client, password="not the password")
    unknown_email = login(client, email="someone@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert "set-cookie" not in wrong_password.headers
    assert actions(db) == ["auth.login_failed", "auth.login_failed"]


def test_me_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_the_logged_in_user(logged_in: TestClient) -> None:
    response = logged_in.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == ADMIN_EMAIL


def test_logout_ends_the_session(logged_in: TestClient, db: Session) -> None:
    assert logged_in.post("/api/auth/logout").status_code == 204
    assert logged_in.get("/api/auth/me").status_code == 401
    assert db.scalars(select(UserSession)).all() == []
    assert actions(db)[-1] == "auth.logout"


def test_session_expires_after_idle_time(
    logged_in: TestClient, clock: Clock, settings: Settings
) -> None:
    clock.advance(minutes=settings.session_idle_minutes - 1)
    assert logged_in.get("/api/auth/me").status_code == 200  # activity resets idle timer
    clock.advance(minutes=settings.session_idle_minutes - 1)
    assert logged_in.get("/api/auth/me").status_code == 200
    clock.advance(minutes=settings.session_idle_minutes + 1)
    assert logged_in.get("/api/auth/me").status_code == 401


def test_session_expires_after_absolute_lifetime_even_when_active(
    logged_in: TestClient, clock: Clock, settings: Settings
) -> None:
    step = settings.session_idle_minutes // 2
    elapsed = 0
    while elapsed + step < settings.session_absolute_hours * 60:
        clock.advance(minutes=step)
        elapsed += step
        assert logged_in.get("/api/auth/me").status_code == 200
    clock.advance(minutes=step)
    assert logged_in.get("/api/auth/me").status_code == 401


def test_repeated_failures_are_rate_limited(
    client: TestClient, admin: User, settings: Settings, db: Session
) -> None:
    for _ in range(settings.login_max_failures):
        assert login(client, password="wrong").status_code == 401

    blocked = login(client)  # even the right password is refused while blocked

    assert blocked.status_code == 429
    assert actions(db)[-1] == "auth.login_rate_limited"


def test_successful_login_resets_the_failure_count(
    client: TestClient, admin: User, settings: Settings
) -> None:
    for _ in range(settings.login_max_failures - 1):
        login(client, password="wrong")
    assert login(client).status_code == 200
    for _ in range(settings.login_max_failures - 1):
        login(client, password="wrong")
    assert login(client).status_code == 200


def test_change_password(logged_in: TestClient, db: Session) -> None:
    new_password = "a brand new long password"
    response = logged_in.post(
        "/api/auth/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": new_password},
    )
    assert response.status_code == 204
    assert actions(db)[-1] == "auth.password_changed"

    logged_in.post("/api/auth/logout")
    assert login(logged_in).status_code == 401
    assert login(logged_in, password=new_password).status_code == 200


def test_change_password_rejects_wrong_current_and_short_new(logged_in: TestClient) -> None:
    wrong_current = logged_in.post(
        "/api/auth/password",
        json={"current_password": "nope", "new_password": "a brand new long password"},
    )
    too_short = logged_in.post(
        "/api/auth/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "short"},
    )
    assert wrong_current.status_code == 400
    assert too_short.status_code == 400
    assert "at least 12" in too_short.json()["detail"]


def test_change_password_signs_out_other_sessions(
    client: TestClient, admin: User, db: Session
) -> None:
    login(client)
    other_device_token = client.cookies["session"]
    login(client)  # this device
    client.post(
        "/api/auth/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "a brand new long password"},
    )
    assert client.get("/api/auth/me").status_code == 200
    client.cookies.set("session", other_device_token)
    assert client.get("/api/auth/me").status_code == 401


def test_state_changing_request_from_another_site_is_refused(
    client: TestClient, admin: User
) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
