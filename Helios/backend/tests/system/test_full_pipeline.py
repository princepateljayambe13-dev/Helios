import pytest
from fastapi.testclient import TestClient
from main import app

def test_full_api_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/v1/system/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "summary" in data
