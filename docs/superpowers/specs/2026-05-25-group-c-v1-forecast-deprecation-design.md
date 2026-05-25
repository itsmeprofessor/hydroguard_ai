# Group C — V1 Forecast Deprecation Design

## Goal

Mark `GET /cities/{city}/forecast` responses as synthetic and deprecated so API consumers know
to migrate to `GET /api/v2/cities/{city}/forecast` before the 2026-08-01 sunset date.

## Context

`/predict` and `/train` are already tombstoned (HTTP 308 redirect + `Deprecation` headers).
The remaining v1 surface that lacks a deprecation signal is `GET /cities/{city}/forecast`.
That endpoint generates a deterministic synthetic forecast (seeded RNG + static baselines)
rather than real WeatherAPI data. The v2 equivalent uses live WeatherAPI forecasts.

---

## Architecture

**Soft deprecation** — the endpoint continues to return HTTP 200 and the full forecast payload.
Three deprecation signals are added on top:

| Layer | Signal |
|---|---|
| HTTP headers | `Deprecation: version="v1"; sunset="2026-08-01"` + `Link: rel="successor-version"` |
| Response body | `"source": "synthetic"`, `"deprecated": true`, `"migrate_to": "/api/v2/cities/{slug}/forecast"` |
| Server log | `logger.warning(...)` on every call (mirrors `/predict` tombstone pattern) |

No schema changes to the v2 forecast endpoint. No other v1 endpoints require changes.

---

## Implementation

### Modified file

`backend/app/api/routes/city_predictions.py` — `city_forecast()` function (line 322).

**Changes:**

1. Add `request: Request` and `response: Response` to the function signature (FastAPI
   dependency injection — both are already used elsewhere in the file).
2. Log at WARNING level: `"Deprecated /cities/%s/forecast called from %s", slug, request.client`
3. Set response headers before returning:
   ```
   response.headers["Deprecation"] = 'version="v1"; sunset="2026-08-01"'
   response.headers["Link"] = f'</api/v2/cities/{slug}/forecast>; rel="successor-version"'
   ```
4. Append three fields to the existing return dict:
   ```python
   "source":     "synthetic",
   "deprecated": True,
   "migrate_to": f"/api/v2/cities/{slug}/forecast",
   ```

No other functions in this file are changed.

### Required imports

`Request` and `Response` are already imported in `city_predictions.py` (check; add if missing).

---

## Testing

### Existing test update

`tests/test_api.py` — find or add a test for `GET /cities/islamabad/forecast` and assert:

```python
assert resp.status_code == 200
assert "Deprecation" in resp.headers
assert "v1" in resp.headers["Deprecation"]
assert resp.json()["source"] == "synthetic"
assert resp.json()["deprecated"] is True
assert "islamabad" in resp.json()["migrate_to"]
```

### What is NOT tested

- v2 forecast endpoint — unchanged, no new assertions needed
- Other v1 endpoints — already covered by existing tombstone tests

---

## Constraints

- HTTP status remains 200 — non-breaking for existing consumers
- All existing body fields (`city`, `province`, `forecast`, `today`, `generated_at`) are preserved
- The three new fields are additive — no consumer can break from receiving extra JSON keys
- v2 `GET /api/v2/cities/{city}/forecast` is untouched
- Sunset date 2026-08-01 matches the existing tombstoned endpoints for consistency
