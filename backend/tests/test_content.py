from typing import Any

import pytest
from fastapi.testclient import TestClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64

EXPERIENCE = {
    "role": "Inventory analyst",
    "organisation": "Example Supplies",
    "location": "Kigali",
    "start_month": "2021-03",
    "end_month": "2023-06",
    "description_md": "Ran **monthly** stock reconciliations.",
}

PROJECT = {
    "slug": "stock-reconciliation",
    "title": "Year-end stock reconciliation",
    "summary": "Physical count compared with system stock.",
    "body_md": "## Approach\n\nLine-by-line comparison.",
    "tags": ["SAP MM", "EWM"],
    "published": True,
    "featured": True,
}


def upload(client: TestClient, data: bytes, name: str) -> dict[str, Any]:
    response = client.post("/api/admin/files", files={"file": (name, data)})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/admin/content/profile"),
        ("put", "/api/admin/content/profile"),
        ("post", "/api/admin/content/experience"),
        ("post", "/api/admin/content/skills"),
        ("get", "/api/admin/content/projects"),
        ("post", "/api/admin/files"),
        ("get", "/api/admin/mail"),
    ],
)
def test_admin_content_endpoints_require_login(client: TestClient, method: str, path: str) -> None:
    assert client.request(method, path).status_code == 401


def test_profile_starts_with_defaults_and_can_be_edited(logged_in: TestClient) -> None:
    profile = logged_in.get("/api/admin/content/profile").json()
    assert profile["full_name"] == "Ferdinand Bizimana"

    photo = upload(logged_in, PNG, "me.png")
    cv = upload(logged_in, PDF, "CV Ferdinand.pdf")
    response = logged_in.put(
        "/api/admin/content/profile",
        json={
            "full_name": "Ferdinand Bizimana",
            "headline": "Supply chain and SAP analytics",
            "location": "Kigali, Rwanda",
            "summary_md": "I turn SAP exports into decisions.",
            "about_md": "Longer story.",
            "linkedin_url": "https://www.linkedin.com/in/example",
            "github_url": "",
            "photo_file_id": photo["id"],
            "cv_file_id": cv["id"],
        },
    )
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["photo"]["url"] == f"/api/public/files/{photo['id']}/me.png"
    assert saved["cv"]["filename"] == "CV Ferdinand.pdf"

    public = logged_in.get("/api/public/portfolio").json()["profile"]
    assert public["headline"] == "Supply chain and SAP analytics"
    assert public["cv"]["content_type"] == "application/pdf"


def test_profile_rejects_bad_links_and_unknown_files(logged_in: TestClient) -> None:
    base = {"full_name": "F B"}
    bad_link = logged_in.put(
        "/api/admin/content/profile", json={**base, "linkedin_url": "javascript:alert(1)"}
    )
    unknown_file = logged_in.put("/api/admin/content/profile", json={**base, "cv_file_id": 999})
    assert bad_link.status_code == 422
    assert unknown_file.status_code == 400


def test_experience_crud_and_order(logged_in: TestClient) -> None:
    first = logged_in.post("/api/admin/content/experience", json=EXPERIENCE).json()
    second = logged_in.post(
        "/api/admin/content/experience",
        json={
            **EXPERIENCE,
            "role": "Supply chain officer",
            "start_month": "2023-07",
            "end_month": None,
        },
    ).json()

    roles = [e["role"] for e in logged_in.get("/api/public/portfolio").json()["experience"]]
    assert roles == ["Inventory analyst", "Supply chain officer"]

    assert (
        logged_in.post(
            "/api/admin/content/experience/reorder", json={"ids": [second["id"], first["id"]]}
        ).status_code
        == 204
    )
    roles = [e["role"] for e in logged_in.get("/api/public/portfolio").json()["experience"]]
    assert roles == ["Supply chain officer", "Inventory analyst"]

    updated = logged_in.put(
        f"/api/admin/content/experience/{first['id']}", json={**EXPERIENCE, "location": "Huye"}
    )
    assert updated.json()["location"] == "Huye"
    assert logged_in.delete(f"/api/admin/content/experience/{first['id']}").status_code == 204
    assert len(logged_in.get("/api/admin/content/experience").json()) == 1


def test_experience_validates_months(logged_in: TestClient) -> None:
    bad_month = logged_in.post(
        "/api/admin/content/experience", json={**EXPERIENCE, "start_month": "2021-13"}
    )
    end_before_start = logged_in.post(
        "/api/admin/content/experience", json={**EXPERIENCE, "end_month": "2020-01"}
    )
    assert bad_month.status_code == 422
    assert end_before_start.status_code == 422


def test_reorder_refuses_a_stale_list(logged_in: TestClient) -> None:
    entry = logged_in.post("/api/admin/content/experience", json=EXPERIENCE).json()
    response = logged_in.post(
        "/api/admin/content/experience/reorder", json={"ids": [entry["id"], 12345]}
    )
    assert response.status_code == 400


def test_skill_groups(logged_in: TestClient) -> None:
    group = logged_in.post(
        "/api/admin/content/skills", json={"name": "SAP", "items": [" MM ", "EWM", "FI"]}
    ).json()
    assert group["items"] == ["MM", "EWM", "FI"]
    logged_in.put(
        f"/api/admin/content/skills/{group['id']}", json={"name": "SAP S/4HANA", "items": ["MM"]}
    )
    skills = logged_in.get("/api/public/portfolio").json()["skills"]
    assert skills == [{"id": group["id"], "name": "SAP S/4HANA", "items": ["MM"]}]
    assert logged_in.delete(f"/api/admin/content/skills/{group['id']}").status_code == 204


def test_only_published_projects_are_public(logged_in: TestClient) -> None:
    cover = upload(logged_in, PNG, "cover.png")
    logged_in.post("/api/admin/content/projects", json={**PROJECT, "cover_file_id": cover["id"]})
    draft = logged_in.post(
        "/api/admin/content/projects",
        json={**PROJECT, "slug": "draft-case", "title": "Draft", "published": False},
    ).json()

    public_list = logged_in.get("/api/public/portfolio").json()["projects"]
    assert [p["slug"] for p in public_list] == ["stock-reconciliation"]
    assert public_list[0]["cover"]["filename"] == "cover.png"

    detail = logged_in.get("/api/public/projects/stock-reconciliation").json()
    assert detail["body_md"].startswith("## Approach")
    assert logged_in.get("/api/public/projects/draft-case").status_code == 404
    assert len(logged_in.get("/api/admin/content/projects").json()) == 2

    logged_in.put(
        f"/api/admin/content/projects/{draft['id']}",
        json={**PROJECT, "slug": "draft-case", "published": True},
    )
    assert logged_in.get("/api/public/projects/draft-case").status_code == 200


def test_project_slug_rules(logged_in: TestClient) -> None:
    logged_in.post("/api/admin/content/projects", json=PROJECT)
    duplicate = logged_in.post("/api/admin/content/projects", json=PROJECT)
    bad_slug = logged_in.post("/api/admin/content/projects", json={**PROJECT, "slug": "Bad Slug!"})
    assert duplicate.status_code == 409
    assert bad_slug.status_code == 422


def test_file_upload_checks_content_not_name(logged_in: TestClient) -> None:
    fake_png = logged_in.post(
        "/api/admin/files", files={"file": ("innocent.png", b"<script>alert(1)</script>")}
    )
    assert fake_png.status_code == 415


def test_file_upload_size_limit(logged_in: TestClient) -> None:
    too_big = PNG + b"\x00" * (10 * 1024 * 1024)
    response = logged_in.post("/api/admin/files", files={"file": ("big.png", too_big)})
    assert response.status_code == 413


def test_public_file_download(client: TestClient, logged_in: TestClient) -> None:
    cv = upload(logged_in, PDF, "../../etc/CV.pdf")
    assert cv["filename"] == "CV.pdf"  # path parts removed

    response = client.get(cv["url"])
    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment")
    assert client.get("/api/public/files/999/x.pdf").status_code == 404


def test_file_in_use_cannot_be_deleted(logged_in: TestClient) -> None:
    photo = upload(logged_in, PNG, "me.png")
    logged_in.put(
        "/api/admin/content/profile", json={"full_name": "F B", "photo_file_id": photo["id"]}
    )
    assert logged_in.delete(f"/api/admin/files/{photo['id']}").status_code == 409

    logged_in.put("/api/admin/content/profile", json={"full_name": "F B"})
    assert logged_in.delete(f"/api/admin/files/{photo['id']}").status_code == 204
    assert logged_in.get(photo["url"]).status_code == 404


def test_content_changes_are_in_the_audit_log(logged_in: TestClient) -> None:
    logged_in.post("/api/admin/content/projects", json=PROJECT)
    actions = [e["action"] for e in logged_in.get("/api/admin/audit").json()["items"]]
    assert actions[0] == "content.project_created"
