# HydroGuard-AI — Backend patch (Phase 4 + 5)
# ─────────────────────────────────────────────────────────────────────────────
# Two small additions that do NOT touch your ML code or existing routes.
#
# (A) CORS — allow the Flutter app + HTML dashboard to call the API from any
#     origin (localhost, LAN IP, deployed).
# (B) Two thin alias routes that the HTML dashboard already queries:
#         GET /database/statistics
#         GET /analytics
#     Both compute their payloads directly from the anomalies table via the
#     existing AnomalyRepository — no duplication of ML logic.
#
# File layout suggestion:
#   backend/app/api/routes/analytics_aliases.py   ← new file (this one)
#   backend/app/main.py                           ← add CORS + register router
# ─────────────────────────────────────────────────────────────────────────────

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db.database import get_db
from app.db.repositories.anomaly_repo import AnomalyRepository

router = APIRouter(tags=["Analytics (dashboard aliases)"])


# ── Helper ───────────────────────────────────────────────────────────────────
def _as_dict(rec: Any) -> dict:
    """Normalize a record to a dict whether it's SQLAlchemy, dataclass, or dict."""
    if isinstance(rec, dict):
        return rec
    if hasattr(rec, "__dict__"):
        return {k: v for k, v in rec.__dict__.items() if not k.startswith("_")}
    # Last-resort fallback
    try:
        return dict(rec)
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════════════
# GET /database/statistics
# Used by the HTML dashboard's `loadAnalytics()` for the top metric cards.
# Returns counts only — cheap and always available.
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/database/statistics")
async def database_statistics() -> dict:
    try:
        with get_db() as db:
            repo = AnomalyRepository(db)
            # If your repo exposes a `.count(...)`-style helper, prefer it.
            # Otherwise we materialize then count — fine for demo volumes.
            all_records = repo.list(skip=0, limit=100_000)

        total = len(all_records)
        anomalies = sum(
            1 for r in all_records if _as_dict(r).get("is_anomaly")
        )
        cloudburst = sum(
            1
            for r in all_records
            if (_as_dict(r).get("cloudburst_risk") or {}).get(
                "is_cloudburst_likely"
            )
            or _as_dict(r).get("is_cloudburst_likely")
        )

        return {
            "total_records":     total,
            "total_anomalies":   anomalies,
            "cloudburst_alerts": cloudburst,
            "generated_at":      datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stats failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# GET /analytics
# Used by the HTML dashboard's doughnut + top-cities list.
# Returns the derived aggregates the JS expects.
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/analytics")
async def analytics() -> dict:
    try:
        with get_db() as db:
            repo = AnomalyRepository(db)
            rows = repo.list(skip=0, limit=100_000)

        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        by_risk: Counter = Counter({"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0})
        city_counter: Counter = Counter()
        weekly_anomalies = 0

        for raw in rows:
            r = _as_dict(raw)

            lvl = (r.get("risk_level") or "LOW").upper()
            by_risk[lvl] = by_risk.get(lvl, 0) + 1

            if r.get("is_anomaly"):
                city_counter[r.get("city") or "Unknown"] += 1

                created = r.get("created_at")
                # Parse ISO string OR accept a datetime directly.
                if isinstance(created, str):
                    try:
                        created_dt = datetime.fromisoformat(
                            created.replace("Z", "+00:00")
                        )
                    except ValueError:
                        created_dt = None
                elif isinstance(created, datetime):
                    created_dt = created
                else:
                    created_dt = None

                if created_dt is not None:
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                    if created_dt >= week_ago:
                        weekly_anomalies += 1

        top_cities = [
            {"city": city, "count": count}
            for city, count in city_counter.most_common(8)
        ]

        return {
            "alerts_by_risk_level":      dict(by_risk),
            "top_cities_by_frequency":   top_cities,
            "total_anomalies_this_week": weekly_anomalies,
            "generated_at":              datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"analytics failed: {e}")
