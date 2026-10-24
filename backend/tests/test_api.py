from datetime import datetime, timezone

from fastapi.testclient import TestClient

from civicloop.api import create_app
from civicloop.storage import InMemoryObjectStorage
from civicloop.jobs import InMemoryJobQueue


class FakeAnalysisAdapter:
    provider = "test"
    model_name = "test-model"

    def analyze(self, payload):
        assert payload["media"]
        return {"category": "mixed_waste", "severity": "high", "confidence": 0.9, "details": {}}


def test_fastapi_auth_incident_media_and_analysis(tmp_path):
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        auth_secret="test-secret-that-is-at-least-32-characters",
        storage=InMemoryObjectStorage(),
        queue=InMemoryJobQueue(),
        analysis_adapter_factory=FakeAnalysisAdapter,
    )
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"name": "Supervisor", "email": "api@example.com", "password": "correct horse battery", "role": "supervisor", "city": "Chandigarh", "pincode": "160017"},
        )
        assert registered.status_code == 201
        token_response = client.post("/api/v1/auth/login", json={"email": "api@example.com", "password": "correct horse battery"})
        assert token_response.status_code == 200
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        incident_response = client.post(
            "/api/v1/incidents",
            headers=headers,
            json={"reporter_type": "resident", "description": "Waste near market", "latitude": 30.7333, "longitude": 76.7794, "occurred_at": datetime.now(timezone.utc).isoformat()},
        )
        assert incident_response.status_code == 201
        incident_id = incident_response.json()["id"]
        media_response = client.post(
            f"/api/v1/incidents/{incident_id}/media",
            headers=headers,
            files={"file": ("before.jpg", b"\xff\xd8\xffimage-bytes", "image/jpeg")},
        )
        assert media_response.status_code == 201
        analysis_response = client.post(f"/api/v1/incidents/{incident_id}/analysis", headers=headers)
        assert analysis_response.status_code == 200
        assert analysis_response.json()["category"] == "mixed_waste"


def test_fastapi_rejects_missing_auth(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'api.db'}", auth_secret="test-secret-that-is-at-least-32-characters", storage=InMemoryObjectStorage(), queue=InMemoryJobQueue())
    with TestClient(app) as client:
        response = client.get("/api/v1/incidents")

    assert response.status_code == 401