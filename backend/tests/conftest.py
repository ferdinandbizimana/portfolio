"""Shared test fixtures.

Database tests need PostgreSQL. Set TEST_DATABASE_URL, for example:

    docker run -d -p 55432:5432 -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
        -e POSTGRES_DB=test postgres:16-alpine
    TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test uv run pytest

The schema is created by running the Alembic migrations, so migrations are
tested too. Tables are emptied between tests.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fakeredis import FakeStrictRedis
from fastapi.testclient import TestClient
from rq import Queue
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api import deps, public, uploads
from app.core.config import Settings, get_settings
from app.core.passwords import hash_password
from app.db import session as db_session
from app.db.base import Base
from app.db.models import User
from app.main import create_app
from app.storage import LocalStorage, get_storage

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"


class Clock:
    """A controllable clock for session expiry tests."""

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("TEST_DATABASE_URL is not set (see tests/conftest.py).")
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    config = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(config, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def redis() -> FakeStrictRedis:
    return FakeStrictRedis()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        cookie_secure=False,
        cors_origins="http://testserver",
        smtp_host="smtp.example.com",
        mail_from="portfolio@example.com",
        contact_to_email="owner@example.com",
        contact_max_per_hour=3,
    )


class FakeMailer:
    """Collects messages instead of sending them. Set `fail` to simulate a broken server."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = False

    def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise ConnectionRefusedError("mail server down")
        self.sent.append(message)


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


@pytest.fixture
def client(
    db: Session,
    redis: FakeStrictRedis,
    clock: Clock,
    settings: Settings,
    mailer: FakeMailer,
    storage: LocalStorage,
) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[deps.get_db] = lambda: db
    app.dependency_overrides[deps.get_redis_client] = lambda: redis
    app.dependency_overrides[deps.get_now] = lambda: clock.now
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[public.get_mailer] = lambda: mailer
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[uploads.get_job_queue] = lambda: Queue(
        "test", connection=redis, is_async=False
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def jobs(engine: Engine, storage: LocalStorage, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Background jobs run immediately, on the test database and test storage."""
    db_session.get_engine.cache_clear()
    db_session.get_sessionmaker.cache_clear()
    monkeypatch.setattr(db_session, "get_engine", lambda: engine)
    monkeypatch.setattr("app.storage.get_storage", lambda: storage)
    yield
    db_session.get_sessionmaker.cache_clear()


@pytest.fixture
def admin(db: Session) -> User:
    user = User(email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASSWORD))
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def logged_in(client: TestClient, admin: User) -> TestClient:
    response = client.post(
        "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client
