"""Publishing: what visitors can and cannot see."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.publishing import build_snapshot
from tests.samples import demo_workbook
from tests.test_engine import start_run, upload

pytestmark = pytest.mark.usefixtures("jobs")


@pytest.fixture
def run(logged_in: TestClient) -> dict[str, Any]:
    data_file = upload(logged_in, demo_workbook(), "confidential-stock-export.xlsx")
    finished = start_run(logged_in, data_file["id"])
    assert finished["status"] == "succeeded"
    return finished


def publish(client: TestClient, run_id: int, **extra: Any) -> dict[str, Any]:
    body = {"title": "Stock by plant, June 2026", "description": "Demo figures.", **extra}
    response = client.post(f"/api/admin/runs/{run_id}/publications", json=body)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def set_visibility(client: TestClient, publication_id: int, visibility: str) -> dict[str, Any]:
    response = client.patch(
        f"/api/admin/publications/{publication_id}", json={"visibility": visibility}
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_summary_level_leaves_out_line_detail_and_checks(
    logged_in: TestClient, run: dict[str, Any]
) -> None:
    preview = logged_in.get(f"/api/admin/runs/{run['id']}/publication-preview").json()

    assert [t["id"] for t in preview["tables"]] == ["by-plant"]
    assert [c["table"] for c in preview["charts"]] == ["by-plant"]
    assert preview["checks"] == []
    assert preview["kpis"] == run["dashboard"]["kpis"]

    detailed = logged_in.get(
        f"/api/admin/runs/{run['id']}/publication-preview",
        params={"detail_level": "detail", "include_checks": True},
    ).json()
    assert [t["id"] for t in detailed["tables"]] == ["by-plant", "lines"]
    assert len(detailed["checks"]) == 3


def test_new_publication_is_private(
    logged_in: TestClient, client: TestClient, run: dict[str, Any]
) -> None:
    publication = publish(logged_in, run["id"])
    logged_in.post("/api/auth/logout")

    assert publication["visibility"] == "private"
    assert client.get("/api/public/dashboards").json() == []
    assert client.get(f"/api/public/dashboards/{publication['slug']}").status_code == 404
    assert client.get(f"/api/public/shared/{publication['secret_token']}").status_code == 404


def test_secret_link_works_but_is_not_listed(logged_in: TestClient, run: dict[str, Any]) -> None:
    publication = set_visibility(logged_in, publish(logged_in, run["id"])["id"], "secret")

    shared = logged_in.get(f"/api/public/shared/{publication['secret_token']}")
    assert shared.status_code == 200
    assert shared.json()["title"] == "Stock by plant, June 2026"
    assert logged_in.get("/api/public/dashboards").json() == []
    assert logged_in.get(f"/api/public/dashboards/{publication['slug']}").status_code == 404
    assert len(publication["secret_token"]) >= 40


def test_public_dashboard_is_listed_and_can_be_unpublished(
    logged_in: TestClient, run: dict[str, Any]
) -> None:
    publication = set_visibility(logged_in, publish(logged_in, run["id"])["id"], "public")
    assert publication["published_at"] is not None

    listed = logged_in.get("/api/public/dashboards").json()
    assert [d["slug"] for d in listed] == [publication["slug"]]
    assert publication["slug"] == "stock-by-plant-june-2026"
    assert logged_in.get(f"/api/public/dashboards/{publication['slug']}").status_code == 200

    set_visibility(logged_in, publication["id"], "private")
    assert logged_in.get(f"/api/public/dashboards/{publication['slug']}").status_code == 404
    assert logged_in.get("/api/public/dashboards").json() == []

    assert logged_in.delete(f"/api/admin/publications/{publication['id']}").status_code == 204
    assert logged_in.get(f"/api/public/shared/{publication['secret_token']}").status_code == 404


def test_public_responses_reveal_nothing_from_the_private_side(
    logged_in: TestClient, run: dict[str, Any]
) -> None:
    publication = set_visibility(
        logged_in,
        publish(logged_in, run["id"], detail_level="detail", include_checks=True)["id"],
        "public",
    )
    response = logged_in.get(f"/api/public/dashboards/{publication['slug']}").json()
    text = json.dumps(response)

    assert set(response) == {"slug", "title", "description", "published_at", "dashboard"}
    assert "confidential-stock-export" not in text
    assert run["inputs"]["stock"]["sha256"] not in text
    assert run["result_hash"] not in text
    assert "run_id" not in text and "data_file_id" not in text
    assert "Excel workbook" not in text  # visitors cannot download it


def test_renewing_the_secret_link_stops_the_old_one(
    logged_in: TestClient, run: dict[str, Any]
) -> None:
    publication = set_visibility(logged_in, publish(logged_in, run["id"])["id"], "secret")
    renewed = logged_in.post(f"/api/admin/publications/{publication['id']}/new-link").json()

    assert renewed["secret_token"] != publication["secret_token"]
    assert logged_in.get(f"/api/public/shared/{publication['secret_token']}").status_code == 404
    assert logged_in.get(f"/api/public/shared/{renewed['secret_token']}").status_code == 200


def test_snapshot_is_frozen_even_when_the_run_is_deleted(
    logged_in: TestClient, run: dict[str, Any]
) -> None:
    publication = set_visibility(logged_in, publish(logged_in, run["id"])["id"], "public")
    assert logged_in.delete(f"/api/admin/runs/{run['id']}").status_code == 204

    still = logged_in.get(f"/api/public/dashboards/{publication['slug']}")
    assert still.status_code == 200
    assert still.json()["dashboard"] == publication["snapshot"]
    assert logged_in.get(f"/api/admin/publications/{publication['id']}").json()["run_id"] is None


def test_only_finished_runs_can_be_published(logged_in: TestClient) -> None:
    rows = [["P1", "M1", None, "1", "not a number"]]
    data_file = upload(logged_in, demo_workbook(rows=rows), "bad.xlsx")
    failed = start_run(logged_in, data_file["id"])
    response = logged_in.post(f"/api/admin/runs/{failed['id']}/publications", json={"title": "x"})
    assert response.status_code == 400


def test_publishing_requires_login(client: TestClient) -> None:
    for method, path in [
        ("get", "/api/admin/publications"),
        ("post", "/api/admin/runs/1/publications"),
        ("get", "/api/admin/runs/1/publication-preview"),
        ("patch", "/api/admin/publications/1"),
        ("delete", "/api/admin/publications/1"),
    ]:
        assert client.request(method, path).status_code == 401, path


def test_slugs_are_unique(logged_in: TestClient, run: dict[str, Any]) -> None:
    first = publish(logged_in, run["id"])
    second = publish(logged_in, run["id"])
    assert (first["slug"], second["slug"]) == (
        "stock-by-plant-june-2026",
        "stock-by-plant-june-2026-2",
    )


def test_capped_table_note_is_reworded_for_visitors() -> None:
    dashboard = {
        "title": "t",
        "tables": [
            {
                "id": "x",
                "title": "x",
                "columns": [],
                "rows": [],
                "level": "summary",
                "note": (
                    "Showing the first 20,000 of 50,000 lines. All lines are in the Excel workbook."
                ),
            }
        ],
    }
    snapshot = build_snapshot(dashboard, "summary", include_checks=False)
    assert snapshot["tables"][0]["note"] == "Showing the first 20,000 of 50,000 lines."
