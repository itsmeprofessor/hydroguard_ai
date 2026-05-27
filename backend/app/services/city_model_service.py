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

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import numpy as np

from app.core.config import DATA_DIR, MODELS_DIR, MCInferenceConfig, HealthCollectorConfig
from app.config.feature_display import display_name as _display_feature_name
from app.ml.models.city_hybrid import CityHybridModel
from app.ml.models.tcn import TCN_SEQ_LEN
SEQUENCE_LENGTH = TCN_SEQ_LEN  # 30 — keep backward-compat name

logger = logging.getLogger(__name__)

# Semaphore is created lazily on first async access (asyncio.Semaphore must
# be created inside a running event loop on Python < 3.10).
_mc_semaphore: Optional[asyncio.Semaphore] = None

# Rolling 100-request MC success rate per city (in-memory, no DB/Redis dependency).
# Key: city slug; Value: deque of bools (True=mc_dropout completed, False=fallback).
_mc_success_window: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

# Per-city timestamp of last MC success rate log to prevent log spam
_mc_last_warn_at: Dict[str, float] = defaultdict(float)

# Per-city ring buffer: True = MC completed within timeout, False = timed out / errored.
_timeout_counter: Dict[str, deque] = defaultdict(
    lambda: deque(maxlen=HealthCollectorConfig.MC_WINDOW_SIZE)
)

# Per-city ring buffer: True = preprocessing succeeded, False = raised exception.
_preprocess_fail_counter: Dict[str, deque] = defaultdict(
    lambda: deque(maxlen=HealthCollectorConfig.MC_WINDOW_SIZE)
)

# Per-city ring buffer of epistemic_uncertainty values from successful MC passes.
_epistemic_buffer: Dict[str, deque] = defaultdict(
    lambda: deque(maxlen=HealthCollectorConfig.EPISTEMIC_BUFFER_SIZE)
)


def get_mc_success_rate(slug: str) -> Optional[float]:
    """Fraction of recent requests that completed MC dropout. None if < 10 obs."""
    w = _mc_success_window[slug]
    return (sum(w) / len(w)) if len(w) >= 10 else None


def get_timeout_rate(slug: str) -> Optional[float]:
    """Fraction of recent MC requests that timed out or errored. None if < 10 obs."""
    w = _timeout_counter[slug]
    if len(w) < 10:
        return None
    return 1.0 - (sum(w) / len(w))


def get_preprocess_fail_rate(slug: str) -> Optional[float]:
    """Fraction of recent predict_v2 calls where preprocessing failed. None if < 10 obs."""
    w = _preprocess_fail_counter[slug]
    return (1.0 - sum(w) / len(w)) if len(w) >= 10 else None


def get_epistemic_buffer_snapshot(slug: str) -> list:
    """Return a copy of the epistemic uncertainty buffer for a city."""
    return list(_epistemic_buffer[slug])


def _classify_prediction_stability(epistemic_uncertainty: float) -> str:
    """Map epistemic uncertainty to a human-readable stability tier."""
    if epistemic_uncertainty > MCInferenceConfig.STABILITY_THRESHOLD_HIGH:
        return "high_uncertainty"
    if epistemic_uncertainty > MCInferenceConfig.STABILITY_THRESHOLD_MODERATE:
        return "moderate_uncertainty"
    return "stable"


def _get_mc_semaphore() -> asyncio.Semaphore:
    """Return (or create) the MC inference semaphore. Thread-safe via GIL."""
    global _mc_semaphore
    if _mc_semaphore is None:
        _mc_semaphore = asyncio.Semaphore(MCInferenceConfig.MAX_CONCURRENT_THREADS)
    return _mc_semaphore


# ──────────────────────────────────────────────────────────
#  Static metadata for KNOWN Pakistani cities.
#  When a new city appears in the CSV that isn't listed here,
#  the system auto-creates an entry using DEFAULT_METADATA.
# ──────────────────────────────────────────────────────────

CITY_METADATA: Dict[str, Dict[str, Any]] = {
    # Enrichment-only: lat/lon/province used when city is discovered from CSV or models.
    # This dict does NOT gate which cities appear — that is driven by the dataset.
    "islamabad": {"name": "Islamabad", "province": "Capital Territory", "pop": "1.1M",  "lat": 33.6844, "lon": 73.0479, "vulnerability": 0.80},
    "lahore":    {"name": "Lahore",    "province": "Punjab",            "pop": "13M",   "lat": 31.5497, "lon": 74.3436, "vulnerability": 0.75},
    "karachi":   {"name": "Karachi",   "province": "Sindh",             "pop": "16M",   "lat": 24.8607, "lon": 67.0011, "vulnerability": 0.85},
    "peshawar":  {"name": "Peshawar",  "province": "KPK",               "pop": "1.9M",  "lat": 34.0151, "lon": 71.5249, "vulnerability": 0.82},
    "quetta":    {"name": "Quetta",    "province": "Balochistan",       "pop": "1.0M",  "lat": 30.1798, "lon": 66.9750, "vulnerability": 0.70},
    "gilgit":    {"name": "Gilgit",    "province": "Gilgit-Baltistan",  "pop": "0.3M",  "lat": 35.9220, "lon": 74.3087, "vulnerability": 0.90},
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

    Skips backup / staging / hidden directories. The training pipeline writes
    new models to ``<slug>.tmp`` and atomically renames the previous version
    to ``<slug>.bak`` (see scripts/train_city.py); these must not show up as
    separate cities in the registry.
    """
    if not CITY_MODELS_DIR.exists():
        return set()
    out: Set[str] = set()
    for p in CITY_MODELS_DIR.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name.startswith(".") or name.endswith((".bak", ".tmp", ".old")):
            continue
        if (p / "autoencoder.keras").exists() or (p / "autoencoder").exists():
            out.add(name)
    return out


# ──────────────────────────────────────────────────────────
#  Per-city sequence buffer (LSTM rolling window)
# ──────────────────────────────────────────────────────────

class _CityBuffer:
    """Thread-safe rolling window buffer per city for TCN next-step input."""

    def __init__(self, seq_len: int = SEQUENCE_LENGTH):
        self._seq_len = seq_len
        self._bufs: Dict[str, deque] = defaultdict(lambda: deque(maxlen=seq_len))
        self._lock = Lock()

    def push_and_get(self, city_slug: str, vec: np.ndarray) -> Optional[np.ndarray]:
        """
        Return the last `seq_len` vectors BEFORE vec, then add vec to the buffer.

        Training:  TCN(X[t-seq_len : t]) → predicts X[t]
        Inference: TCN(sequence)          → error vs x = anomaly signal
        `sequence` must NOT include vec — it is the past context.
        vec is the "next step" target.
        """
        if vec.ndim == 2:
            vec = vec[0]
        with self._lock:
            if len(self._bufs[city_slug]) < self._seq_len:
                # Buffer not full yet — add vec and return None (no prediction)
                self._bufs[city_slug].append(vec.astype(float))
                return None
            # Return CURRENT buffer (past seq_len vectors, NOT including vec)
            seq = np.stack(list(self._bufs[city_slug]))
            # Now slide the window: append vec (drops oldest entry)
            self._bufs[city_slug].append(vec.astype(float))
            return seq

    def seed(self, city_slug: str, rows: np.ndarray) -> None:
        if rows is None or len(rows) == 0:
            return
        with self._lock:
            for r in rows:
                self._bufs[city_slug].append(r.astype(float))

    def fill_count(self, city_slug: str) -> int:
        """Return how many observations are currently buffered for this city."""
        with self._lock:
            return len(self._bufs[city_slug])


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

    # Default alert threshold — overridden per-city by training_metrics.json
    _DEFAULT_ALERT_THRESHOLD = 0.40

    # 5-tier alert ladder keyed to calibrated event_probability
    # Each tier includes the minimum recommended action for civil authorities.
    _ALERT_TIERS: Dict[str, Any] = {
        "clear":      {"min": 0.00, "max": 0.25, "level": 0, "label": "All Clear",
                       "color": "green",  "action": "Normal conditions. No elevated risk indicated."},
        "watch":      {"min": 0.25, "max": 0.40, "level": 1, "label": "Flood Watch",
                       "color": "yellow", "action": "Elevated risk indicated. Stay informed and review your local emergency contacts."},
        "warning":    {"min": 0.40, "max": 0.60, "level": 2, "label": "Flood Warning",
                       "color": "orange", "action": "High risk indicated. Take precautionary measures and monitor official emergency service guidance."},
        "emergency":  {"min": 0.60, "max": 0.80, "level": 3, "label": "Emergency Alert",
                       "color": "red",    "action": "Very high risk indicated. Follow guidance from official emergency authorities (NDMA / Rescue 1122)."},
        "evacuation": {"min": 0.80, "max": 1.01, "level": 4, "label": "Extreme Risk",
                       "color": "purple", "action": "Extreme risk indicated. Follow all instructions from official emergency authorities immediately."},
    }

    @classmethod
    def _compute_alert_tier(cls, p: float, alert_threshold: float) -> Dict[str, Any]:
        """Map calibrated event_probability to a 5-tier alert dict.
        The alert_threshold anchors the Watch→Warning boundary per city.
        """
        # Shift tier boundaries so they track the per-city alert threshold
        tier_boundaries = [
            ("clear",      0.0,                   alert_threshold * 0.625),
            ("watch",      alert_threshold * 0.625, alert_threshold),
            ("warning",    alert_threshold,         alert_threshold * 1.50),
            ("emergency",  alert_threshold * 1.50,  alert_threshold * 2.00),
            ("evacuation", alert_threshold * 2.00,  1.01),
        ]
        for name, lo, hi in tier_boundaries:
            if lo <= p < hi:
                t = cls._ALERT_TIERS[name].copy()
                t["tier"] = name
                return t
        # p >= 1.0 edge case
        t = cls._ALERT_TIERS["evacuation"].copy()
        t["tier"] = "evacuation"
        return t

    def __init__(self):
        self._models:        Dict[str, CityHybridModel] = {}
        self._preprocessors: Dict[str, Any]              = {}   # slug → fitted WeatherDataPreprocessor
        self._locks:         Dict[str, RLock]            = defaultdict(RLock)
        self._registry:      Dict[str, Dict[str, Any]]   = {}
        self._buf = _CityBuffer()
        self._global_lock = Lock()
        self._alert_log:       Dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
        self._fusion_models:   Dict[str, Any]   = {}   # slug -> FusionModel
        self._calibrators:     Dict[str, Any]   = {}   # slug -> IsotonicCalibrator
        self._ood_detectors:   Dict[str, Any]   = {}   # slug -> OODDetector
        self._city_thresholds: Dict[str, float] = {}   # slug -> optimal alert threshold (from metrics)
        self._alert_tiers:     Dict[str, Any]   = {}   # slug -> AlertTierClassifier
        # Initial discovery — also calls _load_city_thresholds()
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
        # Union: a city exists if it has data in the CSV OR a trained model.
        # CITY_METADATA is used only for enrichment (lat/lon/province/etc),
        # never as a source of city slugs — city list is fully dynamic.
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
        # Reload per-city thresholds whenever registry is refreshed
        if hasattr(self, "_city_thresholds"):
            self._load_city_thresholds()
        return registry

    def _load_city_thresholds(self) -> None:
        """Read per-city optimal alert thresholds from training_metrics.json files.
        Falls back to _DEFAULT_ALERT_THRESHOLD when the file is absent or malformed.
        Called once on startup and after each training run.
        """
        import json as _json
        loaded = 0
        for slug in self._registry:
            metrics_path = CITY_MODELS_DIR / slug / "training_metrics.json"
            if metrics_path.exists():
                try:
                    m   = _json.loads(metrics_path.read_text())
                    thr = m.get("optimal_threshold")
                    if isinstance(thr, (int, float)) and 0.01 < float(thr) < 1.0:
                        self._city_thresholds[slug] = float(thr)
                        loaded += 1
                except Exception as exc:
                    logger.debug("[%s] Could not read optimal_threshold: %s", slug, exc)
        logger.info(
            "Per-city alert thresholds loaded: %d/%d cities "
            "(others use default %.2f)",
            loaded, len(self._registry), self._DEFAULT_ALERT_THRESHOLD,
        )

    def _get_alert_threshold(self, slug: str) -> float:
        """Return the calibrated alert threshold for a city (or global default)."""
        return self._city_thresholds.get(slug, self._DEFAULT_ALERT_THRESHOLD)

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
            model = CityHybridModel.load(
                city=_display_name(slug),
                model_dir=self._model_dir(slug),
            )
            # Load v3.3 artifacts (FusionModel, calibrator, OOD detector)
            self._load_v2_artifacts(slug)
            # Warm-start the TCN buffer with historical data so the model
            # produces meaningful sequence scores from the very first request
            # (eliminates the 30-step cold-start blind window).
            self._seed_buffer_from_history(slug)
            return model
        except Exception as exc:
            logger.error("[%s] Failed to load city model: %s", slug, exc)
            return None

    def _seed_buffer_from_history(self, slug: str) -> None:
        """
        Pre-populate _CityBuffer[slug] with the last TCN_SEQ_LEN preprocessed
        rows from the training CSV so the TCN branch is immediately active on
        first request.

        Falls back silently if the CSV or preprocessor is not available.
        """
        from app.ml.models.tcn import TCN_SEQ_LEN
        try:
            preprocessor = self._load_preprocessor(slug)
            if preprocessor is None:
                return

            # Locate the training CSV
            csv_path = DATA_DIR / "pakistan_weather_2000_2024.csv"
            if not csv_path.exists():
                # Try any CSV in data/
                candidates = list(DATA_DIR.glob("*.csv"))
                if not candidates:
                    return
                csv_path = candidates[0]

            df = __import__("pandas").read_csv(csv_path, low_memory=False)
            if "city" in df.columns:
                df_city = df[df["city"].str.strip().str.lower().str.replace(" ", "_")
                             .str.replace("-", "_") == slug].copy()
            else:
                df_city = df.copy()

            if len(df_city) < TCN_SEQ_LEN:
                return

            # Apply the same feature derivation used during training
            import pandas as _pd
            import sys as _sys
            _train_city_mod = _sys.modules.get("train_city")
            if _train_city_mod is None:
                # Inline the necessary transforms
                if "date" in df_city.columns:
                    df_city["date"] = _pd.to_datetime(df_city["date"], errors="coerce")
                    df_city = df_city.sort_values("date")
                if "month" not in df_city.columns and "date" in df_city.columns:
                    df_city["month"] = df_city["date"].dt.month
                if "tavg" in df_city.columns and "dew_point" in df_city.columns:
                    df_city["tdew_spread"] = (df_city["tavg"] - df_city["dew_point"]).clip(0)
                if "humidity" in df_city.columns and "wspd" in df_city.columns:
                    df_city["moisture_flux"] = (df_city["humidity"] / 100.0) * df_city["wspd"].clip(0)

            # Take the last TCN_SEQ_LEN rows and preprocess
            seed_rows = df_city.tail(TCN_SEQ_LEN)
            X_seed, _ = preprocessor.transform(seed_rows)
            self._buf.seed(slug, X_seed)
            logger.info(
                "[%s] TCN buffer warm-started with %d historical rows", slug, len(X_seed)
            )
        except Exception as exc:
            logger.debug("[%s] Buffer warm-start failed (non-fatal): %s", slug, exc)

    def _load_v2_artifacts(self, slug: str) -> None:
        """Load FusionModel, IsotonicCalibrator, OODDetector for a city."""
        model_dir = self._model_dir(slug)

        try:
            from app.ml.models.fusion import FusionModel
            lgbm_path = model_dir / "lgbm_model.pkl"
            if lgbm_path.exists():
                self._fusion_models[slug] = FusionModel.load(lgbm_path)
                logger.info("[%s] FusionModel loaded", slug)
            else:
                logger.warning("[%s] lgbm_model.pkl not found at %s", slug, lgbm_path)
        except Exception as exc:
            logger.warning("[%s] FusionModel load failed: %s", slug, exc)

        try:
            from app.ml.calibration.isotonic import IsotonicCalibrator
            cal_path = model_dir / "calibrator.pkl"
            if cal_path.exists():
                self._calibrators[slug] = IsotonicCalibrator.load(cal_path)
                logger.info("[%s] IsotonicCalibrator loaded", slug)
        except Exception as exc:
            logger.debug("[%s] IsotonicCalibrator load failed: %s", slug, exc)

        try:
            from app.ml.ood.detector import OODDetector
            ood_path = model_dir / "ood_detector.pkl"
            if ood_path.exists():
                self._ood_detectors[slug] = OODDetector.load(ood_path)
                logger.info("[%s] OODDetector loaded", slug)
        except Exception as exc:
            logger.debug("[%s] OODDetector load failed: %s", slug, exc)

        try:
            from app.services.alert_tier import AlertTierClassifier
            cal_data_path = model_dir / "cal_data.npz"
            self._alert_tiers[slug] = AlertTierClassifier.from_cal_data(cal_data_path)
            logger.info("[%s] AlertTierClassifier loaded", slug)
        except Exception as exc:
            logger.debug("[%s] AlertTierClassifier load skipped: %s", slug, exc)

    def _load_preprocessor(self, slug: str) -> Optional[Any]:
        """Load the city-specific fitted preprocessor.

        Tries the v3.2 file (`preprocessor_v2.joblib`) first, then falls back
        to the legacy `preprocessor.joblib` for older models.
        """
        model_dir = self._model_dir(slug)
        v2_path = model_dir / "preprocessor_v2.joblib"
        v1_path = model_dir / "preprocessor.joblib"

        if v2_path.exists():
            try:
                from app.ml.preprocessing_v2 import WeatherDataPreprocessorV2
                return WeatherDataPreprocessorV2.load(v2_path)
            except Exception as exc:
                logger.error("[%s] Failed to load preprocessor_v2: %s", slug, exc)
        if v1_path.exists():
            try:
                import joblib
                return joblib.load(v1_path)
            except Exception as exc:
                logger.error("[%s] Failed to load preprocessor (v1): %s", slug, exc)
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

    def register_model(
        self,
        slug:         str,
        model:        CityHybridModel,
        preprocessor: Any = None,
        fusion_model: Any = None,
        calibrator:   Any = None,
        ood_detector: Any = None,
    ) -> None:
        """Register a freshly trained model + all v3.2 artifacts."""
        with self._locks[slug]:
            self._models[slug] = model
            if preprocessor is not None:
                self._preprocessors[slug] = preprocessor
            if fusion_model is not None:
                self._fusion_models[slug] = fusion_model
            if calibrator is not None:
                self._calibrators[slug] = calibrator
            if ood_detector is not None:
                self._ood_detectors[slug] = ood_detector
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
        logger.debug("[%s] predict() is deprecated in v3.2 -- use predict_v2()", slug)
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
                x_vec = self._preprocess(features, preprocessor, slug=slug)
                sequence = self._buf.push_and_get(slug, x_vec)
                pred = model.predict(x_vec, sequence)
                # `pred` is v3.2-shaped (ae_percentile/tcn_percentile/...). The
                # legacy predict() contract is the v3.1-shaped dict, so bridge
                # the two so existing callers (routes/weather.py, the citizen
                # app, /cities/overview) keep getting risk_level/hri_score/...
                result.update(self._legacy_from_branches(slug, features, pred))
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

    async def predict_v2(
        self,
        city_slug:  str,
        raw_weather: Dict[str, Any],
        request_id:  Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full v2 inference pipeline returning PredictionResponseV2-compatible dict.

        1. OOD check (if OODDetector available)
        2. Feature engineering (FeaturePipelineV2)
        3. Async AE + TCN scoring (asyncio.to_thread)
        4. LightGBM fusion -> P(event)
        5. Isotonic calibration + CI
        6. SHAP explanation
        7. Uncertainty computation (Addition A)
        8. Risk band mapping
        """
        slug = _slug(city_slug)
        model = self.get_model(slug)
        now   = datetime.now(timezone.utc)

        # ---- Feature engineering ----
        try:
            from app.ml.feature_pipeline import build_features, features_to_fusion_dict
            from app.services.rolling_window import get_rolling_window
            from app.services.climatology_store import climatology_store

            ef = await build_features(
                city_slug     = slug,
                raw_weather   = raw_weather,
                rolling_buffer= get_rolling_window(),
                climatology   = climatology_store,
                observed_at   = now,
            )
            feat_dict = ef.to_dict()
        except Exception as exc:
            logger.warning("[%s] FeaturePipeline failed: %s", slug, exc)
            feat_dict = self._v2_feature_defaults(slug, raw_weather)

        # ---- OOD check (v3.3: real features, no zero-fill suppression) ────
        # v3.2 workaround that zeroed all temporal-dynamic features is REMOVED.
        # The OOD detector is now trained on real temporal dynamics computed by
        # _compute_physics_features() in train_city.py, so real inference values
        # have the correct distribution — no Mahalanobis explosion.
        #
        # OOD signal = KEEP flowing through the model (high uncertainty → use as
        # early-warning signal via MC Dropout variance, not as a hard block).
        ood_detector = self._ood_detectors.get(slug)
        ood_detected = False
        ood_distance = 0.0
        if ood_detector is not None:
            try:
                from app.ml.ood.detector import OOD_FEATURES
                ood_vec      = ood_detector.extract_features(feat_dict)
                ood_distance = ood_detector.mahalanobis_distance(ood_vec)
                ood_detected = ood_detector.is_ood(ood_vec)
                if ood_detected:
                    logger.info(
                        "[%s] OOD detected (distance=%.3f) — proceeding with "
                        "elevated uncertainty flag (not blocking inference)",
                        slug, ood_distance,
                    )
            except Exception as exc:
                logger.debug("[%s] OOD check failed: %s", slug, exc)

        # ---- Model not available -- heuristic ----
        if model is None:
            return self._build_degraded_response(slug, raw_weather, now, "heuristic_source")

        # ---- Preprocess ----
        preprocessor = self._preprocessors.get(slug)
        try:
            x_vec = self._preprocess(feat_dict, preprocessor, slug=slug)
            _preprocess_fail_counter[slug].append(True)
        except Exception as exc:
            logger.error("[%s] Preprocess failed: %s", slug, exc)
            _preprocess_fail_counter[slug].append(False)
            return self._build_degraded_response(slug, raw_weather, now, "preprocessing_failed")

        # ---- Rolling window for TCN ----
        sequence = self._buf.push_and_get(slug, x_vec)

        # ---- AE + TCN branch scoring ----
        _branch_t0 = time.perf_counter()

        inference_mode        = "deterministic"
        uncertainty_available = False
        epistemic_uncertainty: Optional[float] = None
        model_uncertainty_score: Optional[float] = None
        prediction_stability: Optional[str] = None
        mc_samples_used       = 1
        degraded_reason: Optional[str] = None
        ae_mc_latency_ms      = 0.0
        ae_result: Dict[str, Any] = {}
        tcn_result: Dict[str, Any] = {}

        if MCInferenceConfig.ENABLED:
            # Immutable snapshot — _CityBuffer is never passed into branch methods
            seq_snapshot = sequence.copy() if sequence is not None else None

            ae_fn, tcn_fn = model.prepare_mc_tasks(
                x_vec, seq_snapshot,
                MCInferenceConfig.DROPOUT_SAMPLES,
                MCInferenceConfig.UNCERTAINTY_MIN,
                MCInferenceConfig.UNCERTAINTY_MAX,
            )
            _gather_t0 = time.perf_counter()
            try:
                async with _get_mc_semaphore():
                    ae_result, tcn_result = await asyncio.wait_for(
                        asyncio.gather(
                            asyncio.to_thread(ae_fn),
                            asyncio.to_thread(tcn_fn),
                        ),
                        timeout=MCInferenceConfig.INFERENCE_TIMEOUT_MS / 1000.0,
                    )
                ae_mc_latency_ms = (time.perf_counter() - _gather_t0) * 1000

                # Deterministic uncertainty merge (documented heuristic weighted blend)
                epistemic_uncertainty = float(np.clip(
                    MCInferenceConfig.AE_UNCERTAINTY_WEIGHT * ae_result["ae_uncertainty"]
                    + MCInferenceConfig.TCN_UNCERTAINTY_WEIGHT * tcn_result["tcn_uncertainty"],
                    MCInferenceConfig.UNCERTAINTY_MIN,
                    MCInferenceConfig.UNCERTAINTY_MAX,
                ))
                model_uncertainty_score = epistemic_uncertainty
                prediction_stability    = _classify_prediction_stability(epistemic_uncertainty)
                inference_mode          = "mc_dropout"
                uncertainty_available   = True
                mc_samples_used         = MCInferenceConfig.DROPOUT_SAMPLES
                _mc_success_window[slug].append(True)
                _timeout_counter[slug].append(True)
                if epistemic_uncertainty is not None:
                    _epistemic_buffer[slug].append(epistemic_uncertainty)

                total_elapsed_ms = (time.perf_counter() - _branch_t0) * 1000
                if total_elapsed_ms > MCInferenceConfig.INFERENCE_TIMEOUT_MS * 0.75:
                    logger.info(
                        "[%s] MC inference approaching timeout budget: %.0fms / %dms",
                        slug, total_elapsed_ms, MCInferenceConfig.INFERENCE_TIMEOUT_MS,
                    )

            except asyncio.TimeoutError:
                logger.info(
                    "[%s] MC inference timeout (>%dms) — falling back to deterministic",
                    slug, MCInferenceConfig.INFERENCE_TIMEOUT_MS,
                )
                degraded_reason = "timeout"
                inference_mode  = "fallback_deterministic"
                _mc_success_window[slug].append(False)
                _timeout_counter[slug].append(False)
            except Exception as exc:
                logger.warning("[%s] MC inference exception — falling back: %s", slug, exc)
                degraded_reason = "exception"
                inference_mode  = "fallback_deterministic"
                _mc_success_window[slug].append(False)
                _timeout_counter[slug].append(False)
        else:
            degraded_reason = "disabled"

        # MC success rate monitoring (in-memory rolling window)
        _win = _mc_success_window[slug]
        if len(_win) >= 10:
            mc_rate = sum(_win) / len(_win)
            _now = time.time()
            if mc_rate < 0.70 and _now - _mc_last_warn_at[slug] > 60:
                logger.error("[%s] MC success rate critically low: %.0f%%", slug, mc_rate * 100)
                _mc_last_warn_at[slug] = _now
            elif mc_rate < 0.90 and _now - _mc_last_warn_at[slug] > 60:
                logger.warning("[%s] MC success rate degraded: %.0f%%", slug, mc_rate * 100)
                _mc_last_warn_at[slug] = _now

        # Point-estimate scores from MC result (or deterministic fallback)
        if ae_result.get("ae_percentile") is not None and tcn_result.get("tcn_percentile") is not None:
            ae_pct  = ae_result.get("ae_percentile", 0.0)
            tcn_pct = tcn_result.get("tcn_percentile", 0.0)
            ae_var  = ae_result.get("ae_variance", 0.5)
            tcn_var = tcn_result.get("tcn_variance", 0.5)
        else:
            # Flag off or MC failed — deterministic fallback
            try:
                raw_scores = await asyncio.to_thread(model.predict, x_vec, sequence)
            except Exception as exc:
                logger.error("[%s] Deterministic branch also failed: %s", slug, exc)
                raw_scores = {
                    "ae_percentile": 0.0, "tcn_percentile": 0.0,
                    "ae_variance": 0.5,   "tcn_variance": 0.5,
                    "ae_error_raw": 0.0,  "tcn_error_raw": 0.0,
                }
            ae_pct  = raw_scores["ae_percentile"]
            tcn_pct = raw_scores["tcn_percentile"]
            ae_var  = raw_scores["ae_variance"]
            tcn_var = raw_scores["tcn_variance"]

        # ---- Fusion (LightGBM) ----
        fusion = self._fusion_models.get(slug)
        p_raw  = (ae_pct * 0.55 + tcn_pct * 0.45)  # fallback if no fusion model
        if fusion is not None and fusion.is_fitted:
            try:
                from app.ml.models.fusion import FUSION_FEATURES
                fusion_input = {f: float(feat_dict.get(f, 0.0) or 0.0) for f in FUSION_FEATURES
                                if f not in ("ae_percentile","tcn_percentile","ae_variance","tcn_variance")}
                fusion_input.update({"ae_percentile": ae_pct, "tcn_percentile": tcn_pct,
                                     "ae_variance": ae_var, "tcn_variance": tcn_var})
                p_raw = await asyncio.to_thread(fusion.predict_scalar, fusion_input)
            except Exception as exc:
                logger.warning("[%s] Fusion model failed: %s", slug, exc)

        # ---- Calibration ----
        calibrator = self._calibrators.get(slug)
        p_calib    = p_raw
        ci_lo, ci_hi = (max(0.0, p_raw - 0.15), min(1.0, p_raw + 0.15))
        uncertainty  = abs(ci_hi - ci_lo)
        model_entropy_val = None

        if calibrator is not None:
            try:
                p_calib = float(calibrator.transform(p_raw))
                ci_lo, ci_hi = calibrator.confidence_interval(p_calib)
                # If bootstrap collapsed to zero-width (common for very low-risk cases),
                # fall back to a variance-based interval so the UI has meaningful bounds.
                if ci_lo == 0.0 and ci_hi == 0.0:
                    half  = float(np.clip(p_calib * (1 - p_calib) * 4 + 0.04, 0.03, 0.20))
                    ci_lo = float(max(0.0, p_calib - half))
                    ci_hi = float(min(1.0, p_calib + half))
                uncertainty  = calibrator.compute_uncertainty(p_calib, ae_var, tcn_var)
                model_entropy_val = calibrator.model_entropy(p_calib)
            except Exception as exc:
                logger.debug("[%s] Calibration failed: %s", slug, exc)

        # ---- SHAP ----
        drivers = None
        if fusion is not None and fusion.is_fitted:
            try:
                shap_dict = await asyncio.to_thread(
                    fusion.shap_values, {**feat_dict,
                                         "ae_percentile": ae_pct, "tcn_percentile": tcn_pct,
                                         "ae_variance": ae_var, "tcn_variance": tcn_var}
                )
                if shap_dict:
                    _branch = {"ae_percentile": ae_pct, "tcn_percentile": tcn_pct,
                                "ae_variance": ae_var, "tcn_variance": tcn_var}
                    drivers = [
                        {"feature": _display_feature_name(k), "shap": v,
                         "value": float(_branch.get(k) if k in _branch else (feat_dict.get(k, 0.0) or 0.0))}
                        for k, v in shap_dict.items()
                    ]
            except Exception as exc:
                logger.warning("[%s] SHAP failed: %s", slug, exc)

        # ---- Risk band ----
        if p_calib < 0.25:   risk_band = "Low"
        elif p_calib < 0.50: risk_band = "Moderate"
        elif p_calib < 0.75: risk_band = "High"
        else:                 risk_band = "Severe"
        # Per-city optimal threshold loaded from training_metrics.json (PR-curve optimized)
        alert_threshold = self._get_alert_threshold(slug)
        is_alert    = p_calib >= alert_threshold
        hri_score   = {"Low": 12, "Moderate": 40, "High": 68, "Severe": 88, "Evac": 95}.get(risk_band, 12)
        alert_tier  = self._compute_alert_tier(p_calib, alert_threshold)

        # Two-tier alert semantics — additive fields, backward compat preserved
        _clf = self._alert_tiers.get(slug)
        if _clf is not None:
            _tier = _clf.classify(p_calib)
            alert_tier_label = _tier.tier
            push_notification = _tier.push_notification
        else:
            alert_tier_label = "ALERT" if is_alert else "NORMAL"
            push_notification = is_alert

        # ---- Alert log (reuse existing mechanism) ----
        if is_alert:
            self._alert_log[slug].append({
                "ts":         now.isoformat(),
                "risk_band":  risk_band,
                "p_event":    round(p_calib, 4),
            })

        return {
            "inference_id":        str(uuid4()),
            "city":                _display_name(slug),
            "city_slug":           slug,
            "inferred_at":         now.isoformat(),
            "model_version":       getattr(model, 'city', slug) + "-v3.2",
            "calibration_version": "isotonic-v1" if calibrator else "none",
            "source":              "city_model",
            "event_probability":   round(p_calib, 4),
            "confidence_interval": [round(ci_lo, 4), round(ci_hi, 4)],
            "uncertainty":         round(uncertainty, 4),
            "model_entropy":       round(model_entropy_val, 4) if model_entropy_val else None,
            "risk_band":           risk_band,
            "hri_score":           hri_score,
            "is_alert":            is_alert,
            "alert_threshold":     round(alert_threshold, 4),
            "alert_tier":          alert_tier,
            "alert_tier_label":    alert_tier_label,
            "push_notification":   push_notification,
            "component_scores":    {
                "ae_percentile":  round(ae_pct,  4),
                "tcn_percentile": round(tcn_pct, 4),
                "p_event_raw":    round(p_raw,   4),
                "ae_variance":    round(ae_var,  4),
                "tcn_variance":   round(tcn_var, 4),
            },
            "drivers":             drivers,
            "weather_inputs":      {
                k: raw_weather.get(k) for k in ["prcp","humidity","pressure","cloud_cover","tmax","tmin","tavg"]
            },
            "climatology_context": {
                "prcp_climo_pct":    round(float(feat_dict.get("prcp_climo_pct", 1.0)), 3),
                "pressure_climo_z":  round(float(feat_dict.get("pressure_climo_z", 0.0)), 3),
                "humidity_climo_pct":round(float(feat_dict.get("humidity_climo_pct", 1.0)), 3),
                "pressure_delta_3h": feat_dict.get("pressure_delta_3h"),
            },
            # Karachi coastal feature signals (null for other cities)
            "coastal_features": {
                k: (round(float(feat_dict[k]), 4) if isinstance(feat_dict.get(k), (int, float)) else None)
                for k in [
                    "sst_anomaly", "sea_breeze_instability", "cyclone_proximity",
                    "humidity_persistence", "coastal_moisture_flux", "urban_drainage_stress",
                    "tidal_proxy", "coastal_pressure_grad", "cyclone_season",
                ]
            } if slug == "karachi" else None,
            # Sequence context — how many observations the TCN has seen since startup
            "sequence_context": {
                "buffer_size":    len(self._buf._bufs.get(slug, [])),
                "required_size":  SEQUENCE_LENGTH,
                "tcn_active":     len(self._buf._bufs.get(slug, [])) >= SEQUENCE_LENGTH,
            },
            # MC Dropout fields — None when flag off or fallback triggered
            "inference_mode":          inference_mode,
            "uncertainty_available":   uncertainty_available,
            "epistemic_uncertainty":   round(epistemic_uncertainty, 4) if epistemic_uncertainty is not None else None,
            "model_uncertainty_score": round(model_uncertainty_score, 4) if model_uncertainty_score is not None else None,
            "prediction_stability":    prediction_stability,
            "mc_samples_requested":    MCInferenceConfig.DROPOUT_SAMPLES if MCInferenceConfig.ENABLED else None,
            "mc_samples_completed":    mc_samples_used if uncertainty_available else None,
            "uncertainty_strategy":    MCInferenceConfig.UNCERTAINTY_STRATEGY if MCInferenceConfig.ENABLED else None,
            "degraded_reason":         degraded_reason,
        }

    # Slugs of cities that the v3.2 fusion model was trained to weight more
    # heavily — must match app.core.config.ModelConfig.FLASH_FLOOD_PRONE_CITIES
    # (which uses display-case names; we keep slugs here to avoid case bugs).
    _FLASH_FLOOD_PRONE_SLUGS = {"islamabad", "rawalpindi", "peshawar", "lahore", "karachi"}

    def _v2_feature_defaults(self, slug: str, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Safe default dict covering every column WeatherDataPreprocessorV2
        was fitted on, for use when only raw weather is available.

        Mirrors (and is the single source of truth for) the fallback feat_dict
        used by `predict_v2()` when the FeaturePipeline is unavailable.
        """
        now      = datetime.now(timezone.utc)
        meta     = self._registry.get(slug, _meta_for(slug))
        vuln     = meta.get("vulnerability") or DEFAULT_METADATA["vulnerability"]
        is_ffp   = 1 if slug in self._FLASH_FLOOD_PRONE_SLUGS else 0

        def _f(key: str, default: float) -> float:
            v = raw.get(key)
            try:
                return float(v) if v is not None else float(default)
            except (TypeError, ValueError):
                return float(default)

        prcp     = _f("prcp",     0.0)
        humidity = _f("humidity", 50.0)
        pressure = _f("pressure", 1013.0)
        cloud    = _f("cloud_cover", 0.0)
        tmax     = _f("tmax", 25.0)
        tmin     = _f("tmin", 20.0)
        tavg     = _f("tavg", (tmax + tmin) / 2.0)
        dew      = _f("dew_point", tavg - 5.0)
        wspd     = _f("wspd", 0.0)
        temp_rng = _f("temp_range", max(tmax - tmin, 0.0))

        month = int(raw.get("month") or now.month)
        season = (
            "Winter" if month in (12, 1, 2) else
            "Spring" if month in (3, 4, 5)  else
            "Summer" if month in (6, 7, 8)  else
            "Autumn"
        )

        return {
            # Raw numerical
            "prcp":        prcp,
            "humidity":    humidity,
            "pressure":    pressure,
            "cloud_cover": cloud,
            "tmin":        tmin,
            "tmax":        tmax,
            "tavg":        tavg,
            "temp_range":  temp_rng,
            "dew_point":   dew,
            "wspd":        wspd,
            # Static derived
            "tdew_spread":   max(tavg - dew, 0.0),
            "moisture_flux": 0.0,
            # Rolling deltas (V2 imputes these to 0.0 anyway, but explicit is safer)
            "pressure_delta_3h":     0.0,
            "pressure_delta_6h":     0.0,
            "humidity_delta_3h":     0.0,
            "rain_rate_1h":          0.0,
            "rain_accumulation_3h":  0.0,
            "rain_accumulation_6h":  0.0,
            "cloud_jump_3h":         0.0,
            # Climatological — neutral defaults.
            # NOTE: `pressure_climo_z` is intentionally omitted. It is in
            # WeatherDataPreprocessorV2.NUMERICAL_V2 but is NOT added by the
            # training pipeline (`_ensure_derived` doesn't add it, and it is
            # not in `_ZERO_IMPUTE_FEATURES`), so the imputer was fit on a
            # 21-column subset that excludes it. Including it here would
            # produce a 22-column transform-time array and break the imputer
            # with a feature-count mismatch.
            "prcp_climo_pct":     1.0,
            "humidity_climo_pct": 1.0,
            # Temporal — `is_monsoon_month` intentionally omitted (same
            # reason as `pressure_climo_z` above: not in the training CSV,
            # so the temporal MinMaxScaler was fit on the other 4 columns).
            "month":             month,
            "day":               int(raw.get("day")       or now.day),
            "dayofweek":         int(raw.get("dayofweek") or now.weekday()),
            "is_weekend":        int(raw.get("is_weekend", int(now.weekday() >= 5))),
            # Categorical
            "city_slug": slug,
            "season":    season,
            # Passthrough features (`vulnerability`, `is_flash_flood_prone`)
            # are deliberately *not* included. They are listed in
            # WeatherDataPreprocessorV2.PASSTHROUGH_V2 but were never present
            # in the training CSV, so providing them at transform time would
            # append 2 extra columns and break the model's input shape.
        }

    def _legacy_from_branches(
        self,
        slug: str,
        features: Dict[str, Any],
        branches: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Translate the v3.2 CityHybridModel output (raw branch percentiles +
        variances) into the v3.1-shaped dict that legacy callers expect:
        ``risk_level``, ``anomaly_score``, ``confidence``, ``is_anomaly``,
        ``ae_score``, ``lstm_score``, ``hri_score``.

        The blend weights (0.55 AE / 0.45 TCN) and the HRI formula
        (0.40 anomaly + 0.35 rainfall + 0.25 vulnerability) match the
        constants documented in CLAUDE.md.
        """
        ae_pct  = float(branches.get("ae_percentile",  0.0) or 0.0)
        tcn_pct = float(branches.get("tcn_percentile", 0.0) or 0.0)
        ae_var  = float(branches.get("ae_variance",    0.5) or 0.5)
        tcn_var = float(branches.get("tcn_variance",   0.5) or 0.5)

        # Combined anomaly score — same weighting as the v3.1 hybrid
        anomaly_score = float(np.clip(0.55 * ae_pct + 0.45 * tcn_pct, 0.0, 1.0))

        # Risk level bands. Match the bands used by predict_v2's risk_band
        # mapping (Low/Moderate/High/Severe), but downcase "Moderate"→"Medium"
        # to keep the legacy enum (the citizen app's riskToScenario maps
        # Low→safe, Medium→warn, High→crit).
        if   anomaly_score < 0.40: risk_level = "Low"
        elif anomaly_score < 0.65: risk_level = "Medium"
        else:                      risk_level = "High"

        # Confidence ≈ 1 − mean variance. Variances live in [0, 0.5]ish,
        # so this lands in [0.5, 1.0].
        confidence = float(np.clip(1.0 - 0.5 * (ae_var + tcn_var), 0.0, 1.0))

        # HRI: weighted blend of anomaly, rainfall, regional vulnerability.
        prcp = float(features.get("prcp") or 0.0)
        rain_norm = float(np.clip(prcp / 50.0, 0.0, 1.0))   # 50 mm/day = 1.0
        meta = self._registry.get(slug, _meta_for(slug))
        vuln = float(meta.get("vulnerability") or DEFAULT_METADATA["vulnerability"])
        hri  = 0.40 * anomaly_score + 0.35 * rain_norm + 0.25 * vuln
        hri_score = int(round(float(np.clip(hri, 0.0, 1.0)) * 100))

        return {
            "risk_level":    risk_level,
            "anomaly_score": round(anomaly_score, 4),
            "confidence":    round(confidence, 4),
            "is_anomaly":    anomaly_score >= 0.40,
            "ae_score":      round(ae_pct,  4),
            "tcn_score":     round(tcn_pct, 4),
            "lstm_score":    round(tcn_pct, 4),  # kept for backward compat — same value as tcn_score
            "hri_score":     hri_score,
        }

    def _preprocess(
        self,
        features: Dict[str, Any],
        preprocessor,
        slug: Optional[str] = None,
    ) -> np.ndarray:
        """Convert raw feature dict → 1D numpy vector matching the model's input_dim."""
        if preprocessor is not None:
            import pandas as pd

            # If this is a V2 preprocessor, every NUMERICAL_V2 column has to
            # be present at transform time (the imputer was fit on the full
            # column set). Pre-populate via the shared helper, then let the
            # caller's keys override.
            try:
                from app.ml.preprocessing_v2 import WeatherDataPreprocessorV2
                if isinstance(preprocessor, WeatherDataPreprocessorV2):
                    resolved_slug = slug or _slug(str(
                        features.get("city_slug") or features.get("city") or ""
                    ))
                    base = self._v2_feature_defaults(resolved_slug, features)
                    # Only allow caller-supplied features to override keys
                    # that already exist in `base`. Anything else (e.g.
                    # `pressure_climo_z`, `is_monsoon_month`,
                    # `vulnerability`, `is_flash_flood_prone`) was not
                    # in the training CSV, so the V2 imputer / scaler /
                    # passthrough handlers would expand the column count
                    # and break shape.
                    for k, v in features.items():
                        if v is not None and k in base:
                            base[k] = v
                    # Inject Karachi coastal features before transform so the
                    # preprocessor sees all 36 numerical columns it was fitted on.
                    # Without this, transform raises ValueError: X has 27 features,
                    # but SimpleImputer is expecting 36.
                    if resolved_slug == "karachi":
                        try:
                            from app.ml.feature_pipeline import _karachi_coastal_features as _kcf
                            now_dt = datetime.now(timezone.utc)
                            coastal = _kcf(
                                raw=base,
                                month=int(base.get("month") or now_dt.month),
                                day=int(base.get("day") or now_dt.day),
                                pressure_delta_3h=float(base.get("pressure_delta_3h") or 0.0),
                                pressure_delta_6h=float(base.get("pressure_delta_6h") or 0.0),
                                humidity_delta_3h=float(base.get("humidity_delta_3h") or 0.0),
                                rain_accumulation_6h=float(base.get("rain_accumulation_6h") or 0.0),
                            )
                            base.update(coastal)
                        except Exception as _kcf_exc:
                            logger.debug("[karachi] Coastal feature injection failed: %s", _kcf_exc)
                    row = pd.DataFrame([base])
                    out = preprocessor.transform(row)
                    x = out[0] if isinstance(out, tuple) else out
                    if x.ndim == 2:
                        x = x[0]
                    return np.asarray(x, dtype=float)
            except ImportError:
                pass  # V2 module not present in this build — fall through to V1

            row_dict = dict(features)

            # Ensure temporal features (month, day, dayofweek, is_weekend) are always
            # present and valid. Without them, MinMaxScaler gets 0 for month (out of
            # the training range 1–12), causing the AE to flag any request as anomalous.
            date_src = row_dict.get("date") or None
            try:
                ts = pd.to_datetime(date_src) if date_src else pd.Timestamp.now()
                row_dict.setdefault("month",     ts.month)
                row_dict.setdefault("day",       ts.day)
                row_dict.setdefault("dayofweek", ts.dayofweek)
                row_dict.setdefault("is_weekend", int(ts.dayofweek >= 5))
            except Exception:
                now = datetime.now(timezone.utc)
                row_dict.setdefault("month",     now.month)
                row_dict.setdefault("day",       now.day)
                row_dict.setdefault("dayofweek", now.weekday())
                row_dict.setdefault("is_weekend", int(now.weekday() >= 5))

            # Inject city/region/season so OHE doesn't default to all-zero "UNKNOWN".
            # OHE unknown category is already safe (all-zero), but an active category
            # matching the city's training data improves reconstruction.
            if hasattr(preprocessor, 'ohe_categories'):
                # City: use the single known city category in this preprocessor
                if "city" not in row_dict and "city" in preprocessor.ohe_categories:
                    cats = preprocessor.ohe_categories["city"]
                    if cats:
                        row_dict.setdefault("city", cats[0])
                # Region: same
                if "region" not in row_dict and "region" in preprocessor.ohe_categories:
                    cats = preprocessor.ohe_categories["region"]
                    if cats:
                        row_dict.setdefault("region", cats[0])
                # Season: derive from current month if not provided
                if "season" not in row_dict and "season" in preprocessor.ohe_categories:
                    m = row_dict.get("month", datetime.now(timezone.utc).month)
                    season = (
                        "Winter" if m in (12, 1, 2) else
                        "Spring" if m in (3, 4, 5)  else
                        "Summer" if m in (6, 7, 8)  else  # includes monsoon
                        "Autumn"
                    )
                    row_dict.setdefault("season", season)

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

    def _build_degraded_response(
        self,
        slug: str,
        raw_weather: Dict[str, Any],
        now: datetime,
        degraded_reason: str,
    ) -> Dict[str, Any]:
        """Return a fully schema-conformant PredictionResponseV2 for any degraded path.

        Covers: untrained-city heuristic, preprocessing failure, and any other
        condition that prevents reaching the fusion pipeline. All callers must
        go through this method — never construct a partial dict inline.
        """
        h         = self._heuristic_predict(slug, raw_weather)
        risk      = h.get("risk_level", "Low")
        band_map  = {"Low": "Low", "Medium": "Moderate", "High": "High"}
        risk_band = band_map.get(risk, "Moderate")
        p_event   = float(h.get("anomaly_score", 0.3))
        alert_threshold = self._get_alert_threshold(slug)
        return {
            "inference_id":        str(uuid4()),
            "city":                _display_name(slug),
            "city_slug":           slug,
            "inferred_at":         now.isoformat(),
            "model_version":       "heuristic",
            "calibration_version": "none",
            "source":              "heuristic",
            "event_probability":   round(p_event, 4),
            "confidence_interval": [
                round(max(0.0, p_event - 0.15), 4),
                round(min(1.0, p_event + 0.15), 4),
            ],
            "uncertainty":         0.30,
            "model_entropy":       None,
            "risk_band":           risk_band,
            "hri_score":           {"Low": 12, "Moderate": 40, "High": 68, "Severe": 88}.get(risk_band, 12),
            "is_alert":            p_event > alert_threshold,
            "alert_threshold":     round(alert_threshold, 4),
            "alert_tier":          self._compute_alert_tier(p_event, alert_threshold),
            "component_scores":    None,
            "drivers":             None,
            "weather_inputs":      {
                k: raw_weather.get(k)
                for k in ["prcp", "humidity", "pressure", "cloud_cover", "tmax", "tmin", "tavg"]
            },
            "climatology_context": None,
            "coastal_features":    None,
            "sequence_context":    None,
            "inference_mode":          "deterministic",
            "uncertainty_available":   False,
            "epistemic_uncertainty":   None,
            "model_uncertainty_score": None,
            "prediction_stability":    None,
            "mc_samples_requested":    None,
            "mc_samples_completed":    None,
            "uncertainty_strategy":    None,
            "degraded_reason":         degraded_reason,
            "inference_runtime_ms":    None,
        }

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

    async def warm_up_tcn_buffers(self) -> None:
        """
        Seed the TCN rolling buffer for every trained city on startup.

        Strategy: fetch live weather for each city, preprocess it through
        the city's own preprocessor, then repeat the vector seq_len times
        to fill the buffer with current-conditions baseline.
        This is far better than a cold start (tcn_percentile=0.0 for 30
        calls) — the model immediately scores against realistic context.
        """
        trained_slugs = [
            s for s in self._registry
            if self._registry[s].get("has_model")
        ]
        if not trained_slugs:
            return

        try:
            from app.services.weather_api import weather_provider
        except Exception:
            logger.warning("TCN warm-up: WeatherAPI unavailable — skipping")
            return

        if weather_provider is None:
            logger.info("TCN warm-up: no weather provider configured — skipping")
            return

        warmed = 0
        for slug in trained_slugs:
            try:
                preprocessor = self._preprocessors.get(slug)
                if preprocessor is None:
                    self.get_model(slug)          # triggers lazy-load which populates preprocessor
                    preprocessor = self._preprocessors.get(slug)
                if preprocessor is None:
                    continue

                snap    = await weather_provider.get_current(slug)
                raw     = snap.to_feature_dict()
                x_vec   = self._preprocess(raw, preprocessor, slug=slug)
                # Seed with seq_len copies of current conditions
                seed_rows = np.tile(x_vec, (SEQUENCE_LENGTH, 1))
                self._buf.seed(slug, seed_rows)
                warmed += 1
                logger.info("[%s] TCN buffer seeded with current weather (%d steps)", slug, SEQUENCE_LENGTH)
            except Exception as exc:
                logger.debug("[%s] TCN warm-up failed: %s", slug, exc)

        logger.info("TCN warm-up complete: %d/%d cities seeded", warmed, len(trained_slugs))


# ──────────────────────────────────────────────────────────
#  Singleton
# ──────────────────────────────────────────────────────────

city_model_service = CityModelService()
