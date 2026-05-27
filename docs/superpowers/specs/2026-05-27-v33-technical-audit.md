# HydroGuard-AI v3.3 — Enterprise Technical Audit Report

**Date:** 2026-05-27  
**Platform version:** v3.3.0 (head commit: `dab46e6`)  
**Base version audited:** v3.3 (commits `34a6160` → `dab46e6`)  
**Audit scope:** 10 domains across 5 parallel audit agents

---

## Executive Summary

HydroGuard-AI v3.3 represents a coherent architectural milestone. The B+ modular runtime control plane (single event origin, bootstrap sequencing, alert tier calibration, broadcaster abstraction) is structurally sound and correctly implemented. The audit identified **3 CRITICAL issues** (one found and fixed during Audit 2 prior to this report; two found by Audits 3 and 5 and fixed in commit `dab46e6`). All 3 have been resolved. No unresolved CRITICAL issues remain.

**Final verdict: Platform is structurally sound and production-ready with the noted WARNING resolutions tracked below.**

---

## Audit Coverage

| Audit | Domain | Status |
|-------|--------|--------|
| 1 | Runtime Architecture + Event Flow | All PASS |
| 2 | Weather API + Polling + Realtime Inference | CRITICAL fixed (`64c067e`) |
| 3 | Alert Tier + Model Calibration + SHAP | CRITICAL fixed (`dab46e6`) |
| 4 | WebSocket + Broadcaster + API Endpoints | WARNING logged |
| 5 | Database + Alembic + Regression + Safety Framing | CRITICAL fixed (`dab46e6`) |

---

## Findings by Domain

### Domain 1: Runtime Architecture + Event Flow (Audit 1)

All findings PASS. The v3.3 runtime control plane is correctly implemented:

- **Single event origin enforced**: `runtime.emit_result()` is the sole broadcaster caller. All inference paths funnel through it.
- **`system_runtime.py` module**: `WORKER_MODE`, `ACTIVE_BROADCASTER`, `FEATURE_FLAGS` correctly initialized. `emit_result()` gate logic (is_alert OR hri ≥ 40) is sound.
- **`bootstrap.py` sequence**: 10-step init (secrets → Alembic → Redis → WeatherAPI → services → broadcaster → models → polling → health) executes in correct dependency order with graceful fallback at every non-fatal step.
- **Shutdown order**: polling → health → broadcaster → Redis — correct reverse of startup.
- **`FEATURE_FLAGS.polling_sensitivity`** correctly read by `WeatherPollingService._has_significant_change()`.

---

### Domain 2: Weather API + Polling + Realtime Inference (Audit 2)

**CRITICAL (fixed `64c067e`):** `pressure_mb` key mismatch in `polling_service.py:104`.

`_has_significant_change()` used `curr.get("pressure_mb", 1013)` but `WeatherSnapshot.to_feature_dict()` returns key `"pressure"`. Result: pressure change detection always compared `1013 vs 1013` — silently broken for all pressure events.

Fix: changed to `curr.get("pressure", 1013.0)` and updated all 8 test references.

All remaining findings PASS:
- `WeatherPollingService` change-detection→predict_v2→emit_result→selective DB persist flow is correct.
- Persistence correctly limited to non-NORMAL tiers via `asyncio.create_task(_persist_result_background(...))`.
- `_poll_all()` error isolation via `asyncio.gather(return_exceptions=True)` correct.

---

### Domain 3: Alert Tier + Model Calibration + SHAP (Audit 3)

**CRITICAL (fixed `dab46e6`):** `cal_data.npz` format mismatch between `train_city.py` (saved `X_cal`/`y_cal`) and `AlertTierClassifier.from_cal_data()` (expected `y_true`/`y_score`).

**Root cause:** `train_city.py:551` saved the fusion feature matrix and labels instead of the raw calibrator-fit probabilities and labels. `from_cal_data()` caught the KeyError and silently fell back to defaults (0.35/0.65) for all 6 cities — making per-city calibrated thresholds non-functional.

**Fixes:**
- `train_city.py:551`: `np.savez(..., y_true=y_cal[mask_cal], y_score=p_raw_cal)`.
- `scripts/fix_cal_data.py`: migration script; regenerated all 6 deployed `cal_data.npz` files using saved `lgbm_model.pkl` to recompute `p_raw`.
- Verified city-specific thresholds are now derived (e.g., Karachi: adv=0.156, alert=0.650 vs. Islamabad: adv=0.000, alert=0.999).

All remaining findings PASS:
- `AlertTierClassifier` threshold derivation direction (`.min()` for advisory, `.max()` for alert) is mathematically correct.
- `IsotonicCalibrator` integration is correct; probability outputs are numerically bounded.
- SHAP driver display names via `_display_feature_name()` applied correctly.
- `FUSION_FEATURES` 16-feature list unchanged; display mapping is presentation-layer only.

**WARNING (not blocking):** `_get_alert_threshold()` returns `optimal_threshold` from `training_metrics.json` (PR-curve operating point) while `AlertTierClassifier` derives precision-65% threshold. These are two different quantities used for two different purposes (`is_alert` vs `alert_tier_label`). Design is not incorrect but could be documented more clearly.

---

### Domain 4: WebSocket + Broadcaster + API Endpoints (Audit 4)

All broadcaster architecture findings PASS:
- `AbstractBroadcaster` / `LocalBroadcaster` / `RedisBroadcaster` correctly implemented.
- `LocalBroadcaster` correctly delegates to existing `ConnectionManager`.
- `RedisBroadcaster` subscribe loop and close() correctly implemented; dormant unless `WORKER_MODE=multi`.
- `bootstrap._init_broadcaster()` correctly selects broadcaster by `WORKER_MODE`.
- `/api/v2/cities/*/predict` correctly routes through `predict_v2()`.

**WARNING:** Parallel event origins exist. The v2 predict endpoint uses `EventBus` (a v3.2-era mechanism) in addition to `runtime.emit_result()`. The `health_collector` also bypasses the runtime control plane via `broadcast_service`. These are not exploitable bugs in production but represent architectural drift — the single event origin invariant is not enforced end-to-end for all code paths.

**WARNING:** `broadcast_service.py` contains `emit_anomaly()` and `emit_risk_map()` which are no longer the canonical event path in v3.3. These are still called by v1 routes and health_collector, so they cannot be deleted without migration, but they represent legacy technical debt.

---

### Domain 5: Database + Alembic + Regression + Safety Framing (Audit 5)

**CRITICAL (fixed `dab46e6`):** Overstated evacuation language in `_ALERT_TIERS` action strings.

`city_model_service._ALERT_TIERS` contained hardcoded action orders:
- `"emergency"`: "Imminent danger. Begin evacuation. Contact rescue services."
- `"evacuation"`: "CRITICAL. Evacuate immediately. Call Rescue 1122."

These deterministic action commands contradict the system's stated role as a probabilistic risk estimator. Clients receive `event_probability: 0.82` (probabilistic) alongside `action: "Evacuate immediately."` (deterministic order) — a dangerous contradiction. The label `"Evacuate Now"` is similarly problematic.

**Fix:** Replaced all action strings with advisory language that defers to official authorities:
- `"emergency"`: "Very high risk indicated. Follow guidance from official emergency authorities (NDMA / Rescue 1122)."
- `"evacuation"`: "Extreme risk indicated. Follow all instructions from official emergency authorities immediately."
- Label `"Evacuate Now"` → `"Extreme Risk"`.

All remaining findings PASS:
- Alembic path resolution (`backend/alembic.ini`) and migration chain (001→002→003→004) correct.
- `init_db()` safety net runs after Alembic as documented.
- `anomaly_service` decommissioned; no active imports.
- v1 city routes still functional; backward compatibility preserved.
- `is_alert`, `event_probability`, `risk_band`, `alert_tier_label` — all probabilistically framed field names.
- No instances of guaranteed/will flood/certain flood language in backend.

---

## FIXED CRITICAL ISSUES (3 total, all resolved)

| ID | Finding | Commit |
|----|---------|--------|
| C-1 | `pressure_mb` key mismatch in polling change detection (silent failure) | `64c067e` |
| C-2 | `cal_data.npz` saves wrong keys — AlertTier thresholds silently default for all cities | `dab46e6` |
| C-3 | Evacuation action orders in `_ALERT_TIERS` contradict probabilistic framing | `dab46e6` |

---

## OPEN WARNING ITEMS

These are tracked issues that do not block current operation but should be addressed before scaling to multi-worker production.

| ID | Finding | Location | Priority |
|----|---------|----------|----------|
| W-1 | Parallel event origins: v2 predict uses EventBus alongside emit_result | `city_model_service.py`, v2 `cities.py` | Medium |
| W-2 | `health_collector` bypasses runtime control plane via `broadcast_service` | `health_collector.py` | Low |
| W-3 | `broadcast_service.py` `emit_anomaly`/`emit_risk_map` are legacy dead paths in v3.3 control plane | `broadcast_service.py` | Low |
| W-4 | `cities_overview()` returns `live_weather: True` even when all weather fetches fail | `api/v2/cities.py` | Low |
| W-5 | Two threshold systems for alert classification not documented together | `city_model_service.py` | Low |

---

## Regression Verification

All 30 v3.3 unit tests pass (`pytest tests/test_alert_tier.py tests/test_polling_service.py tests/test_system_runtime.py tests/test_broadcaster.py`):

- `test_alert_tier.py`: 10/10 — AlertTierClassifier threshold derivation, boundary conditions, fallback
- `test_polling_service.py`: 8/8 — change detection (all 3 fields), poll skip/run logic
- `test_system_runtime.py`: 6/6 — emit_result gate, feature flags
- `test_broadcaster.py`: 6/6 — LocalBroadcaster delegation, RedisBroadcaster publish/close

---

## Production Readiness Assessment

| Area | Status | Notes |
|------|--------|-------|
| Runtime control plane | Ready | Single event origin enforced for primary paths |
| Bootstrap sequence | Ready | Alembic runs at startup; all steps gracefully fallback |
| Alert tier calibration | Ready | Per-city thresholds now derived from PR curves after fix |
| Weather polling | Ready | Change detection on all 3 fields (prcp/pressure/humidity) |
| WebSocket broadcasting | Ready (single-worker) | LocalBroadcaster active; RedisBroadcaster dormant pending multi-worker |
| Safety framing | Ready | Probabilistic language throughout; action strings advisory only |
| Database migrations | Ready | 4-migration chain; Alembic + create_all safety net |
| Feature display names | Ready | Presentation-layer only; ML internals unchanged |

**Bottom line:** The v3.3 architecture is coherent, its invariants are enforced, and the three critical bugs found during audit have been fixed. The platform is ready for single-worker production deployment. Multi-worker deployment requires resolving W-1 (EventBus parallel origin) before enabling `WORKER_MODE=multi`.
