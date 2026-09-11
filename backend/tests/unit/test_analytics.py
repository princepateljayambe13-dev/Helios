import pytest
from fastapi.testclient import TestClient
from main import app


def test_system_analytics_endpoint():
    with TestClient(app) as client:
        res = client.get("/api/v1/system/analytics?timeframe=24h")
        assert res.status_code == 200
        data = res.json()
        assert data["timeframe"] == "24h"
        assert "buckets" in data
        assert len(data["buckets"]) == 24
        assert "severities" in data
        assert "peak_hour" in data
        assert "avg_per_hour" in data
        assert "busiest_camera" in data
        assert "day_night" in data
        assert "cameras" in data
        assert "object_types" in data

        # Test live
        res_live = client.get("/api/v1/system/analytics?timeframe=live")
        assert res_live.status_code == 200
        assert len(res_live.json()["buckets"]) == 12

        # Test 7d
        res_7d = client.get("/api/v1/system/analytics?timeframe=7d")
        assert res_7d.status_code == 200
        assert len(res_7d.json()["buckets"]) == 7
