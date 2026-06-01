import base64

from fastapi.testclient import TestClient

from app.api import app
from app.core.config import settings


def test_health_requires_auth_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    client = TestClient(app)
    assert client.get("/health").status_code == 401

    token = base64.b64encode(
        f"{settings.admin_username}:{settings.admin_password}".encode()
    ).decode()
    response = client.get(
        "/health",
        headers={"Authorization": f"Basic {token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_wrong_password_rejected(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    client = TestClient(app)
    token = base64.b64encode(b"nurikw3:wrong-password").decode()
    assert (
        client.get("/health", headers={"Authorization": f"Basic {token}"}).status_code
        == 401
    )
