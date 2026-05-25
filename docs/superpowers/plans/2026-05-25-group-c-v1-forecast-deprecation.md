# Group C — V1 Forecast Deprecation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mark `GET /cities/{city}/forecast` responses as synthetic and deprecated so API consumers know to migrate to `GET /api/v2/cities/{city}/forecast` before the 2026-08-01 sunset.

**Architecture:** Add `Response` (FastAPI dependency injection) to `city_forecast()`, set `Deprecation` and `Link` headers on every response, log a WARNING, and append three fields (`source`, `deprecated`, `migrate_to`) to the return dict. The v2 forecast endpoint is untouched.

**Tech Stack:** FastAPI (response header injection via `Response` parameter), pytest.

---

## File Map

| File | Change |
|---|---|
| `backend/app/api/routes/city_predictions.py` | Add `Response` to FastAPI import; update `city_forecast` signature + body |
| `tests/test_api.py` | Add `TestV1ForecastDeprecation` class with 4 assertions |

---

### Task 1: Add deprecation signal to GET /cities/{city}/forecast

**Files:**
- Modify: `backend/app/api/routes/city_predictions.py:31` (FastAPI import line)
- Modify: `backend/app/api/routes/city_predictions.py:322-371` (the `city_forecast` function)
- Test: `tests/test_api.py` (append new test class after existing classes)

---

- [ ] **Step 1: Write the failing test**

Open `tests/test_api.py`. Scroll to the end of the file (after the last test class). Append this class:

```python
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
```

- [ ] **Step 2: Run the tests to confirm they fail**

```
pytest tests/test_api.py::TestV1ForecastDeprecation -v --tb=short
```

Expected: 3 failures — `test_v1_forecast_has_deprecation_header`, `test_v1_forecast_body_source_synthetic` fail (header absent, body fields absent); `test_v1_forecast_still_returns_200` and `test_v1_forecast_existing_fields_preserved` should already pass.

---

- [ ] **Step 3: Add `Response` to the FastAPI import in city_predictions.py**

Open `backend/app/api/routes/city_predictions.py`. Find line 31:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
```

Replace it with:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
```

---

- [ ] **Step 4: Update the `city_forecast` function**

In `backend/app/api/routes/city_predictions.py`, find the `city_forecast` function (starts around line 322). Replace the entire function with:

```python
@router.get("/{city}/forecast", response_model=Dict[str, Any])
async def city_forecast(city: str, request: Request, response: Response):
    """7-day outlook for *city* (deterministic per-day seed for reproducibility).

    DEPRECATED — use GET /api/v2/cities/{city}/forecast for live WeatherAPI forecasts.
    Sunset: 2026-08-01.
    """
    slug = _validate_city(city)
    logger.warning(
        "Deprecated /cities/%s/forecast called from %s", slug, request.client
    )
    response.headers["Deprecation"] = 'version="v1"; sunset="2026-08-01"'
    response.headers["Link"] = (
        f'</api/v2/cities/{slug}/forecast>; rel="successor-version"'
    )

    base = _default_weather(slug)

    today    = datetime.now(timezone.utc).date()
    seed_str = f"{slug}-{today.isoformat()}"
    rng = random.Random(int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % 2**32)

    month       = today.month
    is_monsoon  = 6 <= month <= 9

    days: List[Dict[str, Any]] = []
    for offset in range(7):
        d = today + timedelta(days=offset)
        prcp_base = base["prcp"]
        if is_monsoon:
            prcp_base *= rng.uniform(0.5, 3.5)
        else:
            prcp_base *= rng.uniform(0.1, 1.8)

        features = {
            **base,
            "prcp":     round(max(prcp_base, 0), 1),
            "humidity": round(base["humidity"] + rng.uniform(-10, 10), 1),
            "pressure": round(base["pressure"] + rng.uniform(-8, 5), 1),
        }
        pred = city_model_service.predict(city=_display_name(slug), features=features)

        days.append({
            "date":        d.isoformat(),
            "day_name":    d.strftime("%A"),
            "prcp":        features["prcp"],
            "tmax":        base["tmax"],
            "tmin":        base["tmin"],
            "risk_level":  pred["risk_level"],
            "hri_score":   pred["hri_score"],
            "is_anomaly":  pred["is_anomaly"],
            "scenario":    _risk_to_scenario(pred["risk_level"]),
        })

    meta = city_model_service.get_metadata(slug) or _meta_for(slug)
    return {
        "city":         meta["name"],
        "province":     meta["province"],
        "forecast":     days,
        "today":        today.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source":       "synthetic",
        "deprecated":   True,
        "migrate_to":   f"/api/v2/cities/{slug}/forecast",
    }
```

---

- [ ] **Step 5: Run the full targeted test suite to confirm all 4 new tests pass**

```
pytest tests/test_api.py::TestV1ForecastDeprecation -v --tb=short
```

Expected output:
```
PASSED tests/test_api.py::TestV1ForecastDeprecation::test_v1_forecast_still_returns_200
PASSED tests/test_api.py::TestV1ForecastDeprecation::test_v1_forecast_has_deprecation_header
PASSED tests/test_api.py::TestV1ForecastDeprecation::test_v1_forecast_body_source_synthetic
PASSED tests/test_api.py::TestV1ForecastDeprecation::test_v1_forecast_existing_fields_preserved
4 passed
```

---

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```
pytest tests/test_api.py -v --tb=short
```

Expected: all previously passing tests still pass; 4 new tests pass on top.

---

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/city_predictions.py tests/test_api.py
git commit -m "feat: mark GET /cities/{city}/forecast as synthetic/deprecated (v1 sunset 2026-08-01)"
```
