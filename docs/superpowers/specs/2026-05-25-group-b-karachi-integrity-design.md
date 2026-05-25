# Group B — Karachi Model Integrity Audit + Retrain Design

## Goal

Determine whether Karachi's reported AUC (0.9303) is inflated by near-duplicate contamination between validation and test splits, then retrain with 9 coastal features using a clean temporal holdout. Two sequential phases: audit first, retrain second.

## Architecture

**Phase 1 — Audit (`scripts/audit_karachi.py`):** Load the current saved model and preprocessor from disk. Create a strict temporal holdout (last 15% of Karachi rows by date). Evaluate on this holdout without touching model weights. Emit `integrity_audit.json` with pass/fail verdict.

**Phase 2 — Retrain (extended `scripts/train_city.py`):** Compute 9 coastal features from raw CSV columns and add them as new columns to the Karachi training DataFrame. Extend `WeatherDataPreprocessorV2.NUMERICAL_V2` with the 9 coastal feature names — the `num_present` filter ensures other cities are unaffected. Retrain with same temporal split logic as the audit so AUC is directly comparable. Deploy via container restart.

---

## Phase 1: Audit Script

### File
`scripts/audit_karachi.py`

### Input
- `backend/data/pakistan_weather_2000_2024.csv` (default; overridable via `--data`)
- `backend/saved_models/city_models/karachi/` — existing model + preprocessor

### Data split
Load all Karachi rows. Sort by date ascending. Use the last **15%** (floor) as the audit holdout (~876 rows for 5,844 total). The remaining 85% is ignored — the model is not retrained. Temporal ordering guarantees no future-to-past contamination.

### Near-duplicate analysis
For each holdout positive (flood event), compute cosine similarity against every training-set positive. A holdout positive is "contaminated" if any training positive has similarity ≥ 0.95. Report `near_duplicate_rate = contaminated_positives / total_holdout_positives`.

### Metrics
| Field | Description |
|---|---|
| `reported_auc` | 0.9303 — read from `training_metrics.json` |
| `clean_holdout_auc` | ROC-AUC on temporal holdout using existing model |
| `clean_holdout_prauc` | PR-AUC on same holdout |
| `auc_drop` | `reported_auc − clean_holdout_auc` |
| `near_duplicate_rate` | Fraction of holdout positives with cosine sim ≥ 0.95 to any training positive |
| `holdout_n` | Number of rows in holdout |
| `holdout_positives` | Number of positive labels in holdout |
| `pass_fail` | `PASS` \| `FAIL_AUC_FLOOR` \| `FAIL_AUC_DROP` \| `FAIL_BOTH` |
| `retrain_recommended` | `true` if either criterion triggered |
| `audited_at` | ISO timestamp |

### Pass/fail criteria
- **FAIL_AUC_FLOOR**: `clean_holdout_auc < 0.70`
- **FAIL_AUC_DROP**: `auc_drop > 0.10` (i.e. clean AUC < 0.83)
- **FAIL_BOTH**: both conditions true
- **PASS**: neither condition true

### Output
`backend/saved_models/city_models/karachi/integrity_audit.json` — written atomically (temp file + rename). Also printed to stdout in human-readable form.

### CLI
```bash
python scripts/audit_karachi.py
python scripts/audit_karachi.py --data backend/data/pakistan_weather_2000_2024.csv
```
Exit code 0 on PASS, exit code 1 on any FAIL — enables CI integration.

---

## Phase 2: Coastal Feature Integration

### Modified files
- `backend/app/ml/preprocessing_v2.py` — extend `NUMERICAL_V2` with 9 coastal feature names
- `scripts/train_city.py` — for Karachi slug, compute coastal features from raw CSV rows before preprocessor fit

### Coastal feature names (added to `NUMERICAL_V2`)
```
sst_anomaly, sea_breeze_instability, cyclone_proximity, cyclone_season,
humidity_persistence, coastal_moisture_flux, urban_drainage_stress,
tidal_proxy, coastal_pressure_grad
```
All 9 are already defined and computed in `backend/app/ml/feature_pipeline.py::_karachi_coastal_features()`. For non-Karachi cities these columns will not be present in the DataFrame; the `num_present` filter silently excludes them. No other city is affected.

### Computation in `train_city.py`
After loading the Karachi CSV slice and **before any train/val/holdout split**, apply `_karachi_coastal_features()` row-by-row to add the 9 columns. This ensures train, validation, and holdout all receive coastal features. The function requires: `tavg`, `tmin`, `tmax`, `humidity`, `pressure`, `wspd`, `prcp`, and the row's month. All are present in the master CSV.

### Input dimension after retrain
35 → **44** (28 numerical + 9 coastal + 5 temporal + 2 categorical one-hot; exact final dim determined by preprocessor fit).

### Training gate
AUC ≥ 0.70 on internal validation split (unchanged from existing gate). `--force` flag overrides.

### `training_metrics.json` additions
```json
{
  "coastal_features": true,
  "coastal_feature_names": ["sst_anomaly", ...],
  "integrity_audit_auc": "<clean_holdout_auc from audit>"
}
```

### Temporal split (matches audit)
Train: first 85% by date. Validation: drawn from train via StratifiedGroupKFold (unchanged). Holdout: last 15% — same slice the audit used, so retrained AUC is directly comparable to audit AUC.

---

## Phase 3: Deploy + Validate

### Deploy
```bash
docker compose restart hydroguard-api
```
Container boots, `CityModelService` lazy-loads new Karachi model (44-dim preprocessor) from disk. TCN rolling buffer re-warms from CSV via `warm_up_tcn_buffers()` on lifespan startup.

### Post-restart validation (in order)
1. **Smoke test**: `./backend/smoke_test.sh http://127.0.0.1:8000` — `/cities/karachi/risk` must return 200 with valid `hri_score`
2. **Calibration audit**: `python scripts/calibration_audit.py --city Karachi` — regenerates `integrity_audit.json` with post-retrain calibration metrics
3. **Group D telemetry**: observe Karachi in the admin MonitoringScreen health grid — epistemic_stability should transition from `warming_up` → `stable` within the first 30-minute window; PSI status should be `ok` at cold start

---

## Testing

### `tests/test_audit_karachi.py`
| Test | What it checks |
|---|---|
| `test_temporal_split_no_future_leakage` | Holdout dates all > train dates |
| `test_near_duplicate_rate_range` | Rate in [0.0, 1.0] |
| `test_pass_fail_auc_floor` | FAIL_AUC_FLOOR when AUC = 0.65 |
| `test_pass_fail_auc_drop` | FAIL_AUC_DROP when AUC = 0.82 |
| `test_pass_when_both_criteria_met` | PASS when AUC = 0.88 |
| `test_output_json_schema` | All required fields present in output |
| `test_exit_code_nonzero_on_fail` | Script exits 1 on FAIL |

### `tests/test_coastal_features.py`
| Test | What it checks |
|---|---|
| `test_coastal_features_computed_for_karachi` | All 9 columns present in Karachi training DataFrame post-computation |
| `test_coastal_features_absent_for_islamabad` | 0 coastal columns in Islamabad DataFrame |
| `test_preprocessor_accepts_44_dim` | `WeatherDataPreprocessorV2` fit on 44-col df produces 44-dim output |
| `test_preprocessor_still_accepts_35_dim` | Non-Karachi cities unaffected (35-dim output unchanged) |

---

## Constraints

- Audit script is **read-only** with respect to the model — it never writes to model files, only to `integrity_audit.json`
- Coastal feature computation uses only columns already in the master CSV — no external APIs
- `NUMERICAL_V2` extension is backward-compatible for all non-Karachi cities due to `num_present` filter
- Hot-swap (`register_model()`) is explicitly excluded — dimension change requires clean restart
- Class imbalance strategy unchanged: class weighting + `max_precision_at_recall_0.7` threshold optimization
