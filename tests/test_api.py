"""
HydroGuard-AI — API Test Suite

Run with:
    cd hydroguard_ai
    pytest tests/ -v
    pytest tests/ -v --tb=short -q   # compact output
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Session-scoped test client (DB initialised once)."""
    with TestClient(app) as c:
        yield c


# ============================================================
#  System / health
# ============================================================

class TestSystem:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "running"
        assert "version" in d

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "healthy"
        assert "model_loaded" in d
        assert "timestamp" in d

    def test_model_info(self, client):
        r = client.get("/model/info")
        assert r.status_code == 200
        assert "status" in r.json()

    def test_database_statistics(self, client):
        r = client.get("/database/statistics")
        assert r.status_code == 200
        d = r.json()
        assert "total_records" in d
        assert "total_anomalies" in d


# ============================================================
#  Anomaly retrieval
# ============================================================

class TestAnomalies:
    def test_list_anomalies(self, client):
        r = client.get("/anomalies")
        assert r.status_code == 200
        d = r.json()
        assert "total" in d
        assert "page" in d
        assert "anomalies" in d
        assert isinstance(d["anomalies"], list)

    def test_list_with_filters(self, client):
        r = client.get("/anomalies?city=Islamabad&limit=5")
        assert r.status_code == 200
        assert r.json()["page_size"] <= 5

    def test_not_found(self, client):
        r = client.get("/anomalies/99999999")
        assert r.status_code == 404


# ============================================================
#  Prediction (model may or may not be trained)
# ============================================================

class TestPrediction:
    def test_predict_missing_city(self, client):
        """city is a required field — expect 422."""
        r = client.post("/predict", json={"tmin": 25.0})
        assert r.status_code == 422

    def test_predict_invalid_humidity(self, client):
        """humidity > 100 violates field constraint — expect 422."""
        r = client.post("/predict", json={"city": "Islamabad", "humidity": 150})
        assert r.status_code == 422

    def test_predict_or_graceful_fail(self, client):
        """Either returns 200 (model trained) or 400 (model not trained)."""
        payload = {
            "city": "Islamabad",
            "date": "2024-07-15",
            "month": 7, "day": 15,
            "tmin": 25.5, "tmax": 38.2, "tavg": 31.8,
            "prcp": 45.0, "wspd": 15.5,
            "humidity": 85, "pressure": 1002.5,
            "dew_point": 24.3, "cloud_cover": 90,
        }
        r = client.post("/predict", json=payload)
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            d = r.json()
            assert "anomaly_score" in d
            assert "is_anomaly" in d
            assert "hri_score" in d
            assert "risk_level" in d

    def test_predict_batch_or_graceful_fail(self, client):
        payload = {
            "data": [
                {
                    "city": "Lahore",
                    "date": "2024-08-01",
                    "prcp": 120.0,
                    "humidity": 95,
                    "pressure": 990.0,
                    "cloud_cover": 100,
                }
            ]
        }
        r = client.post("/predict/batch", json=payload)
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            d = r.json()
            assert "total" in d
            assert "predictions" in d


# ============================================================
#  Admin (no valid token → 401)
# ============================================================

class TestAdmin:
    def test_analytics_no_token(self, client):
        r = client.get("/analytics")
        assert r.status_code == 401

    def test_analytics_wrong_token(self, client):
        r = client.get("/analytics", headers={"X-Admin-Token": "wrong"})
        assert r.status_code == 401

    def test_train_no_token(self, client):
        r = client.post("/train", json={})
        assert r.status_code == 401


# ============================================================
#  Risk Map
# ============================================================

class TestRiskMap:
    def test_risk_map_or_graceful_fail(self, client):
        r = client.get("/risk-map")
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            d = r.json()
            assert "entries" in d
            assert "count" in d


# ============================================================
#  Sample payloads for manual / integration use
# ============================================================

SAMPLE_NORMAL = {
    "city": "Islamabad", "date": "2024-06-15", "month": 6, "day": 15,
    "season": "Summer",
    "tmin": 22.0, "tmax": 35.0, "tavg": 28.5,
    "prcp": 2.0, "wspd": 8.0, "humidity": 55,
    "pressure": 1012.0, "dew_point": 18.0, "cloud_cover": 30,
}

SAMPLE_EXTREME = {
    "city": "Islamabad", "date": "2024-07-25", "month": 7, "day": 25,
    "season": "Monsoon",
    "tmin": 25.0, "tmax": 32.0, "tavg": 28.5,
    "prcp": 150.0, "wspd": 25.0, "humidity": 95,
    "pressure": 995.0, "dew_point": 26.0, "cloud_cover": 100,
}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
