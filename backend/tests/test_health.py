from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.health import DependencyCheck, get_checks
from app.main import create_app


def ok() -> None:
    return None


def fail() -> None:
    raise ConnectionError("unreachable")


@pytest.fixture
def client_with_checks() -> Iterator[tuple[TestClient, dict[str, DependencyCheck]]]:
    app = create_app()
    checks: dict[str, DependencyCheck] = {}
    app.dependency_overrides[get_checks] = lambda: checks
    with TestClient(app) as client:
        yield client, checks


def test_health_ok_when_all_dependencies_respond(
    client_with_checks: tuple[TestClient, dict[str, DependencyCheck]],
) -> None:
    client, checks = client_with_checks
    checks.update(database=ok, redis=ok)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


def test_health_degraded_names_the_failing_dependency(
    client_with_checks: tuple[TestClient, dict[str, DependencyCheck]],
) -> None:
    client, checks = client_with_checks
    checks.update(database=fail, redis=ok)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"database": "error", "redis": "ok"},
    }
