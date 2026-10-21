from fastapi.testclient import TestClient

from tests.conftest import FakeMailer

MESSAGE = {
    "name": "Amina Uwase",
    "email": "amina@example.org",
    "subject": "Collaboration",
    "message": "Hello, I would like to discuss a supply chain project.",
}


def test_contact_sends_an_email_to_the_owner(client: TestClient, mailer: FakeMailer) -> None:
    response = client.post("/api/public/contact", json=MESSAGE)

    assert response.status_code == 202
    [sent] = mailer.sent
    assert sent["To"] == "owner@example.com"
    assert sent["Reply-To"] == "Amina Uwase <amina@example.org>"
    assert sent["Subject"] == "[Portfolio] Collaboration"
    assert "discuss a supply chain project" in sent.get_content()


def test_contact_honeypot_pretends_success_but_sends_nothing(
    client: TestClient, mailer: FakeMailer
) -> None:
    response = client.post("/api/public/contact", json={**MESSAGE, "website": "http://spam"})
    assert response.status_code == 202
    assert mailer.sent == []


def test_contact_is_rate_limited(client: TestClient, mailer: FakeMailer) -> None:
    for _ in range(3):
        assert client.post("/api/public/contact", json=MESSAGE).status_code == 202
    assert client.post("/api/public/contact", json=MESSAGE).status_code == 429
    assert len(mailer.sent) == 3


def test_contact_validates_input(client: TestClient) -> None:
    assert client.post("/api/public/contact", json={**MESSAGE, "email": "nope"}).status_code == 422
    assert client.post("/api/public/contact", json={**MESSAGE, "message": "hi"}).status_code == 422


def test_contact_reports_a_mail_server_failure(client: TestClient, mailer: FakeMailer) -> None:
    mailer.fail = True
    response = client.post("/api/public/contact", json=MESSAGE)
    assert response.status_code == 503
    assert "could not be sent" in response.json()["detail"]


def test_admin_can_send_a_test_email(logged_in: TestClient, mailer: FakeMailer) -> None:
    status = logged_in.get("/api/admin/mail").json()
    assert status == {
        "configured": True,
        "recipient": "owner@example.com",
        "smtp_host": "smtp.example.com",
    }
    assert logged_in.post("/api/admin/mail/test").status_code == 204
    assert mailer.sent[0]["Subject"] == "[Portfolio] Test message"
