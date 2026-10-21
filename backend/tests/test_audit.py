from fastapi.testclient import TestClient

from app.db.models import User


def test_audit_log_requires_login(client: TestClient) -> None:
    assert client.get("/api/admin/audit").status_code == 401


def test_audit_log_lists_newest_first_and_filters(client: TestClient, admin: User) -> None:
    client.post("/api/auth/login", json={"email": admin.email, "password": "wrong password"})
    client.post(
        "/api/auth/login",
        json={"email": admin.email, "password": "correct horse battery staple"},
    )

    page = client.get("/api/admin/audit").json()
    assert page["total"] == 2
    assert [item["action"] for item in page["items"]] == ["auth.login", "auth.login_failed"]
    assert page["items"][1]["detail"] == {"email": admin.email}

    failed_only = client.get("/api/admin/audit", params={"action": "auth.login_failed"}).json()
    assert failed_only["total"] == 1


def test_audit_log_paginates(client: TestClient, admin: User) -> None:
    for _ in range(3):
        client.post("/api/auth/login", json={"email": admin.email, "password": "wrong"})
    client.post(
        "/api/auth/login",
        json={"email": admin.email, "password": "correct horse battery staple"},
    )
    page = client.get("/api/admin/audit", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 4
    assert len(page["items"]) == 2
