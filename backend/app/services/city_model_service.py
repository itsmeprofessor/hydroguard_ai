"""
HydroGuard-AI — City Model Service (DYNAMIC DISCOVERY)
=========================================================
Per-city inference registry with automatic city discovery.

Discovery sources (union):
  1. Unique values in the dataset CSV's `city` column
  2. Subdirectories of saved_models/city_models/ that contain an autoencoder/
  3. Hand-curated metadata in CITY_METADATA (lat/lon/province/etc.)

A new city in the CSV → auto-appears in the registry → can be trained →
once trained, all endpoints and frontends pick it up via /cities.

Public surface:
  city_model_service.refresh_registry()   — rescan CSV + disk
  city_model_service.list_cities()        — list of city dicts (with metadata)
  city_model_service.list_slugs()         — set of valid city slugs
  city_model_service.predict(city, ...)   — standardised inference
  CITY_METADATA[slug]                     — static metadata for KNOWN cities
  CITY_REGISTRY                            — back-compat shim (mutated by refresh)
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Dict, List, Optional, Set

import numpy as np

from app.core.config import DATA_DIR, MODELS_DIR
from app.ml.models.city_hybrid import CityHybridModel, SEQUENCE_LENGTH

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
#  Static metadata for KNOWN Pakistani cities.
#  When a new city appears in the CSV that isn't listed here,
#  the system auto-creates an entry using DEFAULT_METADATA.
# ──────────────────────────────────────────────────────────

CITY_METADATA: Dict[str, Dict[str, Any]] = {
    "islamabad":  {"name": "Islamabad",  "province": "Capital Territory", "pop": "1.1M",  "lat": 33.6844, "lon": 73.0479, "vulnerability": 0.80},
    "rawalpindi": {"name": "Rawalpindi", "province": "Punjab",            "pop": "2.1M",  "lat": 33.5651, "lon": 73.0169, "vulnerability": 0.78},
    "lahore":     {"name": "Lahore",     "province": "Punjab",            "pop": "13M",   "lat": 31.5497, "lon": 74.3436, "vulnerability": 0.75},
    "karachi":    {"name": "Karachi",    "province": "Sindh",             "pop": "16M",   "lat": 24.8607, "lon": 67.0011, "vulnerability": 0.85},
    "peshawar":   {"name": "Peshawar",   "province": "KPK",               "pop": "1.9M",  "lat": 34.0151, "lon": 71.5249, "vulnerability": 0.82},
    "quetta":     {"name": "Quetta",     "province": "Balochistan",       "pop": "1.0M",  "lat": 30.1798, "lon": 66.9750, "vulnerability": 0.70},
    "faisalabad": {"name": "Faisalabad", "province": "Punjab",            "pop": "3.2M",  "lat": 31.4504, "lon": 73.1350, "vulnerability": 0.65},
    "multan":     {"name": "Multan",     "province": "Punjab",            "pop": "1.9M",  "lat": 30.1575, "lon": 71.5249, "vulnerability": 0.60},
    "hyderabad":  {"name": "Hyderabad",  "province": "Sindh",             "pop": "1.7M",  "lat": 25.3792, "lon": 68.3683, "vulnerability": 0.72},
    "gilgit":     {"name": "Gilgit",     "province": "Gilgit-Baltistan",  "pop": "0.2M",  "lat": 35.9208, "lon": 74.3086, "vulnerability": 0.90},
    "sialkot":    {"name": "Sialkot",    "province": "Punjab",            "pop": "0.7M",  "lat": 32.4945, "lon": 74.5229, "vulnerability": 0.65},
    "gujranwala": {"name": "Gujranwala", "province": "Punjab",            "pop": "2.0M",  "lat": 32.1877, "lon": 74.1945, "vulnerability": 0.62},
    "murree":     {"name": "Murree",     "province": "Punjab",            "pop": "23K",   "lat": 33.9070, "lon": 73.3943, "vulnerability": 0.88},
    "skardu":     {"name": "Skardu",     "province": "Gilgit-Baltistan",  "pop": "0.2M",  "lat": 35.2999, "lon": 75.6378, "vulnerability": 0.85},
    "mirpur":     {"name": "Mirpur",     "province": "AJK",               "pop": "0.5M",  "lat": 33.1481, "lon": 73.7517, "vulnerability": 0.72},
    "muzaffarabad":{"name":"Muzaffarabad","province":"AJK",               "pop": "0.7M",  "lat": 34.3700, "lon": 73.4711, "vulnerability": 0.85},
}

DEFAULT_METADATA: Dict[str, Any] = {
    "province":      "—",
    "pop":           "—",
    "lat":           None,
    "lon":           None,
    "vulnerability": 0.65,  # mid-range default
}

CITY_MODELS_DIR = MODELS_DIR / "city_models"


# Back-compat shim — kept as a module-level dict, mutated by refresh_registry()
# Existing imports (`from app.services.city_model_service import CITY_REGISTRY`)
# continue to work; the dict's contents are updated dynamically at startup
# and after every training run.
CITY_REGISTRY: Dict[str, Dict[str, Any]] = {}


# ──────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────

def _slug(city: str) -> str:
    """Normalise city name to lowercase underscored slug."""
    return city.strip().lower().replace(" ", "_").replace("-", "_")


def _display_name(slug: str) -> str:
    """Pretty display name for a slug."""
    if slug in CITY_METADATA:
        return CITY_METADATA[slug]["name"]
    if slug in CITY_REGISTRY:
        return CITY_REGISTRY[slug].get("name", slug.title())
    return slug.replace("_", " ").title()


def _meta_for(slug: str) -> Dict[str, Any]:
    """Return metadata for a city, falling back to defaults for unknown cities."""
    if slug in CITY_METADATA:
        return CITY_METADATA[slug]
    return {**DEFAULT_METADATA, "name": slug.replace("_", " ").title()}


def _find_default_csv() -> Optional[Path]:
    """Locate the master training CSV (used for city discovery)."""
    candidates = [
        DATA_DIR / "pakistan_weather_2000_2024.csv",
        DATA_DIR / "weather.csv",
    ]
    # Fall back to whatever first .csv lives in DATA_DIR
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*.csv"):
            candidates.append(f)
    for p in candidates:
        if Path(p).exists():
            return Path(p)
    return None


def _discover_cities_from_csv(csv_path: Optional[Path] = None) -> Set[str]:
    """Read unique city slugs from the master dataset's `city` column.
    Returns empty set if the file is missing or unreadable.
    """
    csv_path = csv_path or _find_default_csv()
    if not csv_path or not csv_path.exists():
        logger.info("No dataset CSV found for city discovery (looked in %s)", DATA_DIR)
        return set()
    try:
        import pandas as pd
        df = pd.read_csv(csv_path, usecols=["city"], low_memory=True)
        slugs = {_slug(c) for c in df["city"].dropna().astype(str).str.strip().unique() if c.strip()}
        logger.info("Discovered %d cities in %s: %s",
                    len(slugs), csv_path.name, sorted(slugs))
        return slugs
    except Exception as exc:
        logger.warning("Could not read cities from CSV %s: %s", csv_path, exc)
        return set()


def _discover_trained_cities() -> Set[str]:
    """Scan saved_models/city_models/ for trained model directories.
    A directory counts as 'trained' if it contains either
    autoencoder.keras (Keras 3 format) or autoencoder/ (legacy SavedModel).
    """
    if not CITY_MODELS_DIR.exists():
        return set()
    out: Set[str] = set()
    for p in CITY_MODELS_DIR.iterdir():
        if not p.is_dir():
            continue
        if (p / "autoencoder.keras").exists() or (p / "autoencoder").exists():
            out.add(p.name)
    return out


# ──────────────────────────────────────────────────────────
#  Per-city sequence buffer (LSTM rolling window)
# ──────────────────────────────────────────────────────────

class _CityBuffer:
    """Thread-safe rolling window buffer per city for LSTM input."""

    def __init__(self, seq_len: int = SEQUENCE_LENGTH):
        self._seq_len = seq_len
        self._bufs: Dict[str, deque] = defaultdict(lambda: deque(maxlen=seq_len))
        self._lock = Lock()

    def push_and_get(self, city_slug: str, vec: np.ndarray) -> Optional[np.ndarray]:
        if vec.ndim == 2:
            vec = vec[0]
        with self._lock:
            self._bufs[city_slug].append(vec.astype(float))
            if len(self._bufs[city_slug]) < self._seq_len:
                return None
            return np.stack(list(self._bufs[city_slug]))

    def seed(self, city_slug: str, rows: np.ndarray) -> None:
        if rows is None or len(rows) == 0:
            return
        with self._lock:
            for r in rows:
                self._bufs[city_slug].append(r.astype(float))


# ──────────────────────────────────────────────────────────
#  City Model Service
# ──────────────────────────────────────────────────────────

class CityModelService:
    """
    Lazy-loading registry of per-city hybrid models with dynamic city discovery.

    The registry is rebuilt from CSV + on-disk models on:
      - service initialisation (startup)
      - call to refresh_registry()  (e.g. after training a new city)
    """

    def __init__(self):
        self._models:        Dict[str, CityHybridModel] = {}
        self._preprocessors: Dict[str, Any]              = {}   # slug → fitted WeatherDataPreprocessor
        self._locks:         Dict[str, RLock]            = defaultdict(RLock)
        self._registry:      Dict[str, Dict[str, Any]]   = {}
        self._buf = _CityBuffer()
        self._global_lock = Lock()
        self._alert_log: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
        # Initial discovery
        self.refresh_registry()

    # ──────────────────────────────────────────────────────
    #  Discovery / registry
    # ──────────────────────────────────────────────────────

    def refresh_registry(self, csv_path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
        """Rebuild the city registry from CSV + on-disk models.
        Mutates the module-level CITY_REGISTRY for back-compat.
        Returns the new registry.
        """
        global CITY_REGISTRY

        csv_cities = _discover_cities_from_csv(csv_path)
        trained    = _discover_trained_cities()
        # Union: a city exists if it has data OR a trained model (metadata is
        # only used for enrichment, not gating).
        all_slugs  = csv_cities | trained

        registry: Dict[str, Dict[str, Any]] = {}
        for slug in all_slugs:
            meta = _meta_for(slug)
            registry[slug] = {
                **meta,
                "slug":      slug,
                "has_data":  slug in csv_cities,
                "has_model": slug in trained,
            }

        with self._global_lock:
            self._registry = registry
            CITY_REGISTRY.clear()
            CITY_REGISTRY.update(registry)

        logger.info(
            "City registry refreshed: %d cities total · %d in CSV · %d trained",
            len(registry), len(csv_cities), len(trained),
        )
        return registry

    def list_cities(self) -> List[Dict[str, Any]]:
        """Return metadata for every discovered city."""
        with self._global_lock:
            return [
                {
                    "slug":       slug,
                    "name":       meta["name"],
                    "province":   meta["province"],
                    "population": meta["pop"],
                    "lat":        meta["lat"],
                    "lon":        meta["lon"],
                    "has_data":   meta.get("has_data", False),
                    "has_model":  meta.get("has_model", False),
                }
                for slug, meta in sorted(self._registry.items())
            ]

    def list_slugs(self) -> Set[str]:
        with self._global_lock:
            return set(self._registry.keys())

    def is_known_city(self, city: str) -> bool:
        return _slug(city) in self.list_slugs()

    def get_metadata(self, city: str) -> Optional[Dict[str, Any]]:
        slug = _slug(city)
        with self._global_lock:
            return self._registry.get(slug)

    # ──────────────────────────────────────────────────────
    #  Model loading
    # ──────────────────────────────────────────────────────

    def _model_dir(self, slug: str) -> Path:
        return CITY_MODELS_DIR / slug

    def _has_saved_model(self, slug: str) -> bool:
        d = self._model_dir(slug)
        return (d / "autoencoder.keras").exists() or (d / "autoencoder").exists()

    def _load_or_none(self, slug: str) -> Optional[CityHybridModel]:
        if not self._has_saved_model(slug):
            return None
        try:
            return CityHybridModel.load(
                city=_display_name(slug),
                model_dir=self._model_dir(slug),
            )
        except Exception as exc:
            logger.error("[%s] Failed to load city model: %s", slug, exc)
            return None

    def _load_preprocessor(self, slug: str) -> Optional[Any]:
        """Load the city-specific fitted preprocessor (joblib)."""
        path = self._model_dir(slug) / "preprocessor.joblib"
        if not path.exists():
            return None
        try:
            import joblib
            return joblib.load(path)
        except Exception as exc:
            logger.error("[%s] Failed to load preprocessor: %s", slug, exc)
            return None

    def get_model(self, city: str) -> Optional[CityHybridModel]:
        slug = _slug(city)
        with self._locks[slug]:
            if slug not in self._models:
                loaded = self._load_or_none(slug)
                if loaded:
                    self._models[slug] = loaded
                    # Also try to load the matching preprocessor
                    pre = self._load_preprocessor(slug)
                    if pre is not None:
                        self._preprocessors[slug] = pre
                        logger.info("[%s] City model + preprocessor loaded into memory", slug)
                    else:
                        logger.warning("[%s] Model loaded but preprocessor missing — "
                                       "predictions may fall back to heuristic", slug)
            return self._models.get(slug)

    def register_model(self, slug: str, model: CityHybridModel,
                       preprocessor: Any = None) -> None:
        """Register a freshly trained model + preprocessor."""
        with self._locks[slug]:
            self._models[slug] = model
            if preprocessor is not None:
                self._preprocessors[slug] = preprocessor
        # Refresh so the new model shows up in /cities
        self.refresh_registry()

    # ──────────────────────────────────────────────────────
    #  Inference
    # ──────────────────────────────────────────────────────

    def predict(
        self,
        city: str,
        features: Dict[str, Any],
        preprocessor: Any = None,
    ) -> Dict[str, Any]:
        """Run inference for one city with standardised output.
        If `preprocessor` is None, the city's saved preprocessor is used.
        """
        slug  = _slug(city)
        model = self.get_model(slug)
        # Use cached preprocessor if not explicitly passed
        if preprocessor is None:
            preprocessor = self._preprocessors.get(slug)

        result: Dict[str, Any] = {
            "city":      _display_name(slug),
            "city_slug": slug,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if model is None:
            result.update(self._heuristic_predict(slug, features))
            result["source"] = "heuristic"
        else:
            try:
                x_vec = self._preprocess(features, preprocessor)
                sequence = self._buf.push_and_get(slug, x_vec)
                pred = model.predict(x_vec, sequence)
                result.update(pred)
                result["source"] = "city_model"
            except Exception as exc:
                logger.error("[%s] Inference error: %s", slug, exc)
                result.update(self._heuristic_predict(slug, features))
                result["source"] = "heuristic_fallback"

        result["inputs"] = {
            k: features.get(k) for k in
            ["prcp", "humidity", "pressure", "tmax", "tmin"]
        }

        if result.get("is_anomaly"):
            self._alert_log[slug].append({
                "ts":         result["timestamp"],
                "risk_level": result["risk_level"],
                "score":      result.get("anomaly_score", 0),
            })

        return result

    def _preprocess(self, features: Dict[str, Any], preprocessor) -> np.ndarray:
        """Convert raw feature dict → 1D numpy vector matching the model's input_dim."""
        if preprocessor is not None:
            import pandas as pd

            # Ensure all temporal features the preprocessor needs are present.
            # If only `date` is provided, derive month/day/dayofweek/is_weekend.
            row_dict = dict(features)
            if "date" in row_dict and row_dict["date"]:
                try:
                    ts = pd.to_datetime(row_dict["date"])
                    row_dict.setdefault("month",     ts.month)
                    row_dict.setdefault("day",       ts.day)
                    row_dict.setdefault("dayofweek", ts.dayofweek)
                    row_dict.setdefault("is_weekend", int(ts.dayofweek >= 5))
                except Exception:
                    pass

            row = pd.DataFrame([row_dict])
            out = preprocessor.transform(row)
            # WeatherDataPreprocessor.transform returns (np.ndarray, pd.DataFrame)
            x = out[0] if isinstance(out, tuple) else out
            if x.ndim == 2:
                x = x[0]
            return np.asarray(x, dtype=float)

        # Fallback (no preprocessor): raw 9-dim vector
        keys = [
            "prcp", "humidity", "pressure", "cloud_cover",
            "dew_point", "wspd", "tmin", "tmax", "tavg",
        ]
        return np.array([float(features.get(k, 0.0)) for k in keys], dtype=float)

    def _heuristic_predict(
        self, slug: str, features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Rule-based risk estimate used when city model not yet trained."""
        prcp     = float(features.get("prcp",     0))
        humidity = float(features.get("humidity", 50))
        pressure = float(features.get("pressure", 1013))

        meta = self._registry.get(slug, _meta_for(slug))
        vuln = meta.get("vulnerability", DEFAULT_METADATA["vulnerability"])

        rain_score  = min(prcp / 120.0, 1.0)
        hum_score   = max((humidity - 60) / 40.0, 0)
        pres_score  = max((1013 - pressure) / 20.0, 0)

        score = 0.50 * rain_score + 0.25 * hum_score + 0.25 * pres_score
        score = float(np.clip(score * (0.7 + 0.3 * vuln), 0, 1))

        if score < 0.40:   risk = "Low"
        elif score < 0.65: risk = "Medium"
        else:              risk = "High"

        return {
            "risk_level":    risk,
            "anomaly_score": round(score, 4),
            "confidence":    0.55,
            "is_anomaly":    score > 0.40,
            "ae_score":      0.0,
            "lstm_score":    0.0,
            "hri_score":     int(round(score * 100)),
        }

    # ──────────────────────────────────────────────────────
    #  Utility queries
    # ──────────────────────────────────────────────────────

    def get_recent_alerts(self, city: str, n: int = 10) -> List[Dict[str, Any]]:
        slug = _slug(city)
        return list(self._alert_log[slug])[-n:]

    def model_status(self) -> Dict[str, Any]:
        with self._global_lock:
            slugs    = list(self._registry.keys())
            trained  = [s for s in slugs if self._registry[s].get("has_model")]
            with_csv = [s for s in slugs if self._registry[s].get("has_data")]
        return {
            "total_cities":     len(slugs),
            "in_dataset":       len(with_csv),
            "trained_cities":   len(trained),
            "untrained":        sorted(set(with_csv) - set(trained)),
            "loaded_in_memory": list(self._models.keys()),
            "no_data":          sorted(set(trained) - set(with_csv)),
        }


# ──────────────────────────────────────────────────────────
#  Singleton
# ──────────────────────────────────────────────────────────

city_model_service = CityModelService()
