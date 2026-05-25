"""
HydroGuard-AI — Runtime Health Snapshot Schemas
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel


class CityHealthSnapshot(BaseModel):
    city_slug: str

    # Domain 1 — Inference health
    mc_success_rate:      Optional[float]   # None if < 10 observations
    timeout_rate:         Optional[float]   # None if < 10 observations
    preprocess_fail_rate: Optional[float]   # None if < 10 observations
    inference_health:     str               # "ok" | "degraded" | "critical" | "unknown"

    # Domain 2 — Drift
    psi_max:              Optional[float]   # highest PSI across monitored features
    psi_status:           str               # "ok" | "warn" | "critical" | "unknown"
    top_drifted_feature:  Optional[str]     # feature name with highest PSI

    # Domain 3 — Epistemic stability
    epistemic_mean:       Optional[float]   # mean of epistemic buffer
    epistemic_std:        Optional[float]   # std dev of epistemic buffer
    epistemic_drift:      Optional[float]   # |current_mean - warmup_mean| / warmup_std
    epistemic_stability:  str               # "warming_up" | "stable" | "drifting" | "anomalous"
    baseline_ready:       bool


class SystemHealthSnapshot(BaseModel):
    snapshot_at:        datetime
    cities:             Dict[str, CityHealthSnapshot]
    global_status:      str   # "ok" | "degraded" | "critical" | "unknown"
    active_city_count:  int
