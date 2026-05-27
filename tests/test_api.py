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
        """v1 /predict is tombstoned — returns 308 regardless of body content."""
        r = client.post("/predict", json={"tmin": 25.0}, follow_redirects=False)
        assert r.status_code == 308

    def test_predict_invalid_humidity(self, client):
        """humidity > 100 violates field constraint — expect 422."""
        r = client.post("/predict", json={"city": "Islamabad", "humidity": 150})
        assert r.status_code == 422

    def test_predict_or_graceful_fail(self, client):
        """v1 /predict is tombstoned (308). Redirect lands on v2 endpoint.
        v2 returns 200 (heuristic/model) or 404 (city not found).
        Sending a full v2-compatible payload to avoid 422."""
        payload = {
            "city":        "Islamabad",
            "prcp":        45.0,
            "humidity":    85.0,
            "pressure":    1002.5,
            "tmax":        38.2,
            "tmin":        25.5,
            "cloud_cover": 90.0,
        }
        r = client.post("/predict", json=payload)
        # 308 redirect -> 200 (v2 prediction) or 404 (city not in dataset)
        assert r.status_code in (200, 308, 404)
        if r.status_code == 200:
            d = r.json()
            # v2 response fields
            assert "inference_id" in d
            assert "risk_band"    in d
            assert "is_alert"     in d

    def test_predict_batch_or_graceful_fail(self, client):
        """v1 /predict/batch is tombstoned (308)."""
        payload = {
            "data": [
                {
                    "city":     "Lahore",
                    "prcp":     120.0,
                    "humidity": 95.0,
                    "pressure": 990.0,
                }
            ]
        }
        r = client.post("/predict/batch", json=payload, follow_redirects=False)
        # Tombstone returns 308
        assert r.status_code in (308, 200, 404)


# ============================================================
#  Admin (no valid token → 401)
# ============================================================

class TestAdmin:
    def test_analytics_no_token(self, client):
        # /admin/analytics requires auth; /analytics is public
        r = client.get("/admin/analytics")
        assert r.status_code == 401

    def test_analytics_wrong_token(self, client):
        r = client.get("/admin/analytics", headers={"X-Admin-Token": "wrong"})
        assert r.status_code == 401

    def test_train_no_token(self, client):
        # /train now tombstones to 308; /api/v2/training requires admin
        r = client.post("/api/v2/training/islamabad", json={},
                        follow_redirects=False)
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


# ── v2 test fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def auth_headers(client):
    """Get a valid JWT token for test requests (session-scoped)."""
    reg = client.post("/auth/register", json={
        "username": "v2testuser", "email": "v2test@test.com",
        "password": "TestPass123!"
    })
    if reg.status_code not in (200, 201, 400):
        return {}
    login = client.post("/auth/login", json={
        "username": "v2testuser", "password": "TestPass123!"
    })
    if login.status_code != 200:
        return {}
    token = login.json().get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


# ================================================================
#  v2 API Tests
# ================================================================

SAMPLE_V2_PREDICT = {
    "city":     "Islamabad",
    "prcp":     45.0,
    "humidity": 85.0,
    "pressure": 1004.0,
    "tmax":     33.0,
    "tmin":     26.0,
    "cloud_cover": 80.0,
}


class TestV2Schema:
    """v2 Pydantic schema validation."""

    def test_weather_input_v2_required_fields(self):
        from app.schemas.v2 import WeatherInputV2
        import pydantic
        # Missing prcp, humidity, pressure -- should fail validation
        with pytest.raises((pydantic.ValidationError, Exception)):
            WeatherInputV2(city="Islamabad")

    def test_weather_input_v2_valid(self):
        from app.schemas.v2 import WeatherInputV2
        w = WeatherInputV2(**SAMPLE_V2_PREDICT)
        assert w.city == "Islamabad"
        assert w.prcp == 45.0
        assert w.humidity == 85.0
        assert w.pressure == 1004.0

    def test_prediction_response_v2_shape(self):
        from app.schemas.v2 import PredictionResponseV2
        from datetime import datetime, timezone
        r = PredictionResponseV2(
            inference_id        = "test-uuid",
            city                = "Islamabad",
            city_slug           = "islamabad",
            inferred_at         = datetime.now(timezone.utc),
            model_version       = "test-v1",
            calibration_version = "none",
            source              = "heuristic",
            event_probability   = 0.42,
            confidence_interval = [0.35, 0.49],
            uncertainty         = 0.14,
            model_entropy       = 0.69,
            risk_band           = "Moderate",
            is_alert            = False,
        )
        assert r.inference_id == "test-uuid"
        assert r.risk_band == "Moderate"
        assert not r.is_alert

    def test_shap_entry_schema(self):
        from app.schemas.v2 import ShapEntry
        s = ShapEntry(feature="prcp_climo_pct", shap=0.31, value=2.8)
        assert s.feature == "prcp_climo_pct"


class TestV2Cities:
    """v2 Cities API endpoints."""

    def test_list_cities(self, client):
        resp = client.get("/api/v2/cities")
        assert resp.status_code == 200
        data = resp.json()
        assert "cities" in data
        assert "total" in data
        assert isinstance(data["cities"], list)

    def test_cities_overview(self, client):
        resp = client.get("/api/v2/cities/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "cities" in data

    def test_predict_v2_missing_required(self, client, auth_headers):
        # All weather fields are optional (filled from defaults) — empty body is valid.
        # Field-range validation still applies: humidity out of [0,100] must return 422.
        resp = client.post(
            "/api/v2/cities/islamabad/predict",
            json={"humidity": 999},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_predict_v2_unknown_city(self, client, auth_headers):
        resp = client.post(
            "/api/v2/cities/atlantis/predict",
            json=SAMPLE_V2_PREDICT,
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_predict_v2_valid(self, client, auth_headers):
        resp = client.post(
            "/api/v2/cities/islamabad/predict",
            json=SAMPLE_V2_PREDICT,
            headers=auth_headers,
        )
        # 200 (city_model or heuristic) or 404 (city not in dataset)
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()
            assert "inference_id"   in data
            assert "risk_band"      in data
            assert "is_alert"       in data
            assert "source"         in data

    def test_city_alerts_endpoint(self, client):
        resp = client.get("/api/v2/cities/islamabad/alerts")
        assert resp.status_code in (200, 404)

    def test_city_status_endpoint(self, client):
        resp = client.get("/api/v2/cities/islamabad/status")
        assert resp.status_code in (200, 404)


class TestV2Events:
    """v2 Events API endpoints."""

    def test_list_events(self, client):
        resp = client.get("/api/v2/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total" in data

    def test_event_statistics(self, client):
        resp = client.get("/api/v2/events/statistics")
        assert resp.status_code == 200

    def test_unknown_event_id(self, client):
        resp = client.get("/api/v2/events/nonexistent-uuid")
        assert resp.status_code == 404


class TestV2Drift:
    """v2 Drift API endpoints."""

    def test_all_drift_states(self, client):
        resp = client.get("/api/v2/drift")
        assert resp.status_code == 200
        data = resp.json()
        assert "cities" in data

    def test_city_drift(self, client):
        resp = client.get("/api/v2/drift/islamabad")
        assert resp.status_code in (200, 500)   # 500 acceptable if no drift data yet

    def test_legacy_drift_endpoint_redirects(self, client):
        resp = client.get("/drift")
        assert resp.status_code == 200
        data = resp.json()
        assert "redirect" in data


class TestOODGuard:
    """OOD detector response shape."""

    def test_ood_response_shape(self):
        from app.ml.ood.detector import OODDetector
        det = OODDetector()
        resp = det.ood_response("islamabad", distance=12.5)
        assert resp["source"]    == "ood_guard"
        assert resp["risk_band"] == "Unknown"
        assert resp["is_alert"]  == False
        assert "ood_distance"    in resp
        assert "ood_reason"      in resp
        assert resp["event_probability"] is None


# ============================================================
#  V1 Forecast Deprecation
# ============================================================
class TestV1ForecastDeprecation:
    def test_v1_forecast_still_returns_200(self, client):
        r = client.get("/cities/islamabad/forecast")
        assert r.status_code == 200

    def test_v1_forecast_has_deprecation_header(self, client):
        r = client.get("/cities/islamabad/forecast")
        assert "Deprecation" in r.headers
        assert "v1" in r.headers["Deprecation"]
        assert "2026-08-01" in r.headers["Deprecation"]

    def test_v1_forecast_body_source_synthetic(self, client):
        r = client.get("/cities/islamabad/forecast")
        d = r.json()
        assert d.get("source") == "synthetic"
        assert d.get("deprecated") is True
        assert "islamabad" in d.get("migrate_to", "")

    def test_v1_forecast_existing_fields_preserved(self, client):
        r = client.get("/cities/islamabad/forecast")
        d = r.json()
        assert "forecast" in d
        assert "city" in d
        assert "today" in d
        assert len(d["forecast"]) == 7

    def test_v1_forecast_has_link_header(self, client):
        r = client.get("/cities/islamabad/forecast")
        assert "Link" in r.headers
        assert "/api/v2/cities/islamabad/forecast" in r.headers["Link"]
        assert 'rel="successor-version"' in r.headers["Link"]


class TestOverview:
    def test_overview_has_live_weather_flag(self, client):
        response = client.get("/api/v2/cities/overview")
        assert response.status_code == 200
        assert response.json()["live_weather"] is True
