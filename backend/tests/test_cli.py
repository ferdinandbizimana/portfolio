import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app import cli
from app.core.passwords import verify_password
from app.db.models import User
from app.db.session import get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
def _cli_uses_test_database(engine: Engine, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    monkeypatch.setattr("app.db.session.get_engine", lambda: engine)


def test_create_admin_then_refuse_a_second(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "a long enough password")

    assert cli.main(["create-admin", "--email", "Me@Example.com"]) == 0
    assert cli.main(["create-admin", "--email", "other@example.com"]) == 1

    users = db.scalars(select(User)).all()
    assert [user.email for user in users] == ["me@example.com"]
    assert verify_password(users[0].password_hash, "a long enough password")


def test_create_admin_rejects_short_password(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    assert cli.main(["create-admin", "--email", "me@example.com"]) == 1
    assert db.scalars(select(User)).all() == []


def test_set_password(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "a long enough password")
    cli.main(["create-admin", "--email", "me@example.com"])
    monkeypatch.setenv("ADMIN_PASSWORD", "another long password")

    assert cli.main(["set-password", "--email", "ME@example.com"]) == 0

    db.expire_all()
    user = db.scalars(select(User)).one()
    assert verify_password(user.password_hash, "another long password")
