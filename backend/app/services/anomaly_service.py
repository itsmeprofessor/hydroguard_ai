"""
HydroGuard-AI — Anomaly Detection Service
==========================================
Core ML inference service: Autoencoder + LSTM Hybrid + HRI + Cloudburst rule engine.

Key design decisions:
  - Singleton pattern via module-level `anomaly_service`.
  - Per-city rolling LSTM sequence buffer with warm-up on startup.
  - HRI composite score: anomaly signal × rainfall × regional vulnerability.
  - Cloudburst rule engine runs independently of the neural model.
  - train() splits BEFORE fit — no data leakage.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.core.config import (
    CloudburstConfig,
    ModelConfig,
    DATA_DIR,
    MODELS_DIR,
    HYBRID_WARMUP_CSV,
    HYBRID_WARMUP_ENABLED,
    HYBRID_WARMUP_ROWS_PER_CITY,
)
from ml.models.autoencoder import HybridAnomalyDetector, LSTMAutoencoder, WeatherAutoencoder
from utils.preprocessing import WeatherDataPreprocessor, load_and_prepare_data

logger = logging.getLogger(__name__)

class AnomalyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        prediction_result: Dict[str, Any],
        weather_data: Dict[str, Any],
    ) -> AnomalyRecord:
        date_raw = prediction_result.get("date")
        try:
            parsed_date = (
                datetime.strptime(date_raw, "%Y-%m-%d")
                if isinstance(date_raw, str)
                else date_raw
            )
        except Exception:
            parsed_date = datetime.utcnow()

        cb = prediction_result.get("cloudburst_risk", {})

        record = AnomalyRecord(
            city        = prediction_result.get("city"),
            region      = weather_data.get("region"),
            date        = parsed_date,
            tmin        = weather_data.get("tmin"),
            tmax        = weather_data.get("tmax"),
            tavg        = weather_data.get("tavg"),
            prcp        = weather_data.get("prcp"),
            wspd        = weather_data.get("wspd"),
            humidity    = weather_data.get("humidity"),
            pressure    = weather_data.get("pressure"),
            dew_point   = weather_data.get("dew_point"),
            cloud_cover = weather_data.get("cloud_cover"),
            anomaly_score            = prediction_result.get("anomaly_score"),
            threshold                = prediction_result.get("threshold"),
            is_anomaly               = prediction_result.get("is_anomaly"),
            risk_level               = prediction_result.get("risk_level"),
            hri_score                = prediction_result.get("hri_score"),
            hri_label                = prediction_result.get("hri_label"),
            cloudburst_risk_score    = cb.get("risk_score"),
            cloudburst_risk_category = cb.get("risk_category"),
            is_cloudburst_likely     = cb.get("is_cloudburst_likely", False),
            remarks                  = prediction_result.get("remarks"),
            feature_contributions    = prediction_result.get("feature_contributions"),
            detailed_explanation     = prediction_result.get("detailed_explanation"),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, record_id: int) -> Optional[AnomalyRecord]:
        return self.db.query(AnomalyRecord).filter(AnomalyRecord.id == record_id).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        city: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date:   Optional[datetime] = None,
        is_anomaly_only: bool = True,
    ) -> List[AnomalyRecord]:
        q = self.db.query(AnomalyRecord)
        if is_anomaly_only:
            q = q.filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
        if city:
            q = q.filter(AnomalyRecord.city == city)
        if risk_level:
            q = q.filter(AnomalyRecord.risk_level == risk_level)
        if start_date:
            q = q.filter(AnomalyRecord.date >= start_date)
        if end_date:
            q = q.filter(AnomalyRecord.date <= end_date)
        return q.order_by(AnomalyRecord.date.desc()).offset(skip).limit(limit).all()

    def get_count(
        self,
        city: Optional[str] = None,
        risk_level: Optional[str] = None,
        is_anomaly_only: bool = True,
    ) -> int:
        q = self.db.query(AnomalyRecord)
        if is_anomaly_only:
            q = q.filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
        if city:
            q = q.filter(AnomalyRecord.city == city)
        if risk_level:
            q = q.filter(AnomalyRecord.risk_level == risk_level)
        return q.count()

    def get_statistics(self) -> Dict[str, Any]:
        total     = self.db.query(func.count(AnomalyRecord.id)).scalar()
        anomalies = self.db.query(func.count(AnomalyRecord.id)).filter(
            AnomalyRecord.is_anomaly == True  # noqa: E712
        ).scalar()
        by_city = dict(
            self.db.query(AnomalyRecord.city, func.count(AnomalyRecord.id))
            .filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
            .group_by(AnomalyRecord.city).all()
        )
        by_risk = dict(
            self.db.query(AnomalyRecord.risk_level, func.count(AnomalyRecord.id))
            .filter(AnomalyRecord.is_anomaly == True)  # noqa: E712
            .group_by(AnomalyRecord.risk_level).all()
        )
        cloudburst = self.db.query(func.count(AnomalyRecord.id)).filter(
            AnomalyRecord.is_cloudburst_likely == True  # noqa: E712
        ).scalar()

        return {
            "total_records":    total,
            "total_anomalies":  anomalies,
            "anomaly_rate":     round(anomalies / total * 100, 2) if total else 0.0,
            "by_city":          by_city,
            "by_risk_level":    by_risk,
            "cloudburst_alerts": cloudburst,
        }
# ============================================================
#  Per-city LSTM sequence buffer
# ============================================================

class _CitySequenceBuffer:
    """Thread-safe rolling buffer of feature vectors per city for LSTM windowing."""

    def __init__(self, sequence_length: int):
        self.sequence_length = int(sequence_length)
        self._buf: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.sequence_length)
        )
        self._lock = Lock()

    def push_and_get_sequence(
        self, city: str, x_vec: np.ndarray
    ) -> Optional[np.ndarray]:
        if x_vec.ndim == 2:
            x_vec = x_vec[0]
        city_key = (city or "UNKNOWN").strip() or "UNKNOWN"
        with self._lock:
            self._buf[city_key].append(np.asarray(x_vec, dtype=float))
            if len(self._buf[city_key]) < self.sequence_length:
                return None
            return np.stack(list(self._buf[city_key]), axis=0)

    def seed_city(self, city: str, x_rows: np.ndarray) -> None:
        if x_rows is None or len(x_rows) == 0:
            return
        if x_rows.ndim == 1:
            x_rows = x_rows.reshape(1, -1)
        city_key = (city or "UNKNOWN").strip() or "UNKNOWN"
        with self._lock:
            for i in range(x_rows.shape[0]):
                self._buf[city_key].append(np.asarray(x_rows[i], dtype=float))


# ============================================================
#  HRI calculation
# ============================================================

def compute_hri(
    anomaly_score: float,
    anomaly_threshold: float,
    prcp: float,
    city: str,
    config: ModelConfig,
) -> Dict[str, Any]:
    """
    Compute HydroGuard Risk Index (0–100).

    HRI = 40 × anomaly_component + 35 × rainfall_component + 25 × regional_vulnerability
    """
    ae_norm = min(
        max((anomaly_score - anomaly_threshold) / (anomaly_threshold * 2 + 1e-8), 0.0),
        1.0,
    )

    if prcp >= 100:   rain_norm = 1.00
    elif prcp >= 75:  rain_norm = 0.90
    elif prcp >= 50:  rain_norm = 0.70
    elif prcp >= 30:  rain_norm = 0.45
    elif prcp >= 10:  rain_norm = 0.20
    else:             rain_norm = 0.00

    vul = config.REGIONAL_VULNERABILITY.get(city, config.REGIONAL_VULNERABILITY["DEFAULT"])
    w   = config.HRI_WEIGHTS
    hri_raw = (
        w["anomaly_score"]          * ae_norm
        + w["rainfall_intensity"]   * rain_norm
        + w["regional_vulnerability"] * vul
    )
    hri_score = int(round(min(hri_raw * 100, 100)))

    if hri_score < 25:    label = "Low"
    elif hri_score < 50:  label = "Guarded"
    elif hri_score < 75:  label = "Elevated"
    else:                 label = "Severe"

    return {
        "hri_score": hri_score,
        "hri_label": label,
        "hri_components": {
            "anomaly":                round(ae_norm,   4),
            "rainfall":               round(rain_norm, 4),
            "regional_vulnerability": round(vul,       4),
        },
    }


# ============================================================
#  Main service
# ============================================================

class AnomalyDetectionService:

    def __init__(self):
        self.preprocessor:     Optional[WeatherDataPreprocessor] = None
        self.autoencoder:      Optional[WeatherAutoencoder]      = None
        self.lstm_autoencoder: Optional[LSTMAutoencoder]         = None
        self.hybrid_detector:  Optional[HybridAnomalyDetector]   = None
        self._sequence_buffer: Optional[_CitySequenceBuffer]     = None

        self.is_trained = False
        self.training_metadata: Dict = {}

        self.config            = ModelConfig()
        self.cloudburst_config = CloudburstConfig()

        self._try_load_model()

    # --------------------------------------------------------
    #  Model lifecycle
    # --------------------------------------------------------

    def _try_load_model(self) -> bool:
        model_path        = MODELS_DIR / "autoencoder_model"
        preprocessor_path = MODELS_DIR / "preprocessor.joblib"

        if not (model_path.exists() and preprocessor_path.exists()):
            return False

        try:
            self.preprocessor = WeatherDataPreprocessor.load(preprocessor_path)
            test = np.zeros((1, len(self.preprocessor.numerical_features)))
            self.preprocessor.numerical_imputer.transform(test)

            self.autoencoder = WeatherAutoencoder.load(model_path)

            lstm_path = MODELS_DIR / "lstm_model"
            if lstm_path.exists():
                try:
                    self.lstm_autoencoder = LSTMAutoencoder.load(lstm_path)
                    self.hybrid_detector  = HybridAnomalyDetector(
                        self.autoencoder, self.lstm_autoencoder
                    )
                except Exception as e:
                    logger.warning(f"Failed to load LSTM model: {e}")
                    self.hybrid_detector = HybridAnomalyDetector(self.autoencoder)
            else:
                self.hybrid_detector = HybridAnomalyDetector(self.autoencoder)

            self.is_trained       = True
            self._sequence_buffer = _CitySequenceBuffer(self.config.SEQUENCE_LENGTH)
            logger.info("Existing model loaded successfully.")

            if self.lstm_autoencoder:
                self._warm_hybrid_buffer_after_load()
            return True

        except Exception as e:
            logger.warning(f"Failed to load model: {e}")
            return False

    def train(
        self,
        data_path: str,
        use_lstm: bool = True,
        epochs: Optional[int] = None,
        batch_size: Optional[int] = None,
        save_model: bool = True,
    ) -> Dict[str, Any]:
        epochs     = epochs     or self.config.EPOCHS
        batch_size = batch_size or self.config.BATCH_SIZE

        logger.info(f"Training started — data: {data_path}")
        start_time = datetime.now()

        df = load_and_prepare_data(data_path)

        available_numerical   = [f for f in self.config.NUMERICAL_FEATURES   if f in df.columns]
        available_categorical = [f for f in self.config.CATEGORICAL_FEATURES if f in df.columns]
        available_temporal    = [f for f in self.config.TEMPORAL_FEATURES    if f in df.columns]

        # Split BEFORE fitting — no leakage
        total_rows = len(df)
        train_end  = int(total_rows * (1 - self.config.VALIDATION_SPLIT))
        df_train   = df.iloc[:train_end].copy()
        df_val     = df.iloc[train_end:].copy()

        self.preprocessor = WeatherDataPreprocessor(
            numerical_features   = available_numerical,
            categorical_features = available_categorical,
            temporal_features    = available_temporal,
            sequence_length      = self.config.SEQUENCE_LENGTH,
            feature_weights      = self.config.FEATURE_WEIGHTS,
        )
        X_train, df_train_proc = self.preprocessor.fit_transform(df_train)
        X_val,   _             = self.preprocessor.transform(df_val)
        X_full,  df_full_proc  = self.preprocessor.transform(df)

        input_dim = X_train.shape[1]
        logger.info(f"Feature dim={input_dim} | Train={len(X_train)} | Val={len(X_val)}")

        # Autoencoder
        self.autoencoder = WeatherAutoencoder(
            input_dim     = input_dim,
            encoding_dim  = self.config.ENCODING_DIM,
            hidden_layers = self.config.HIDDEN_LAYERS,
            dropout_rate  = self.config.DROPOUT_RATE,
            learning_rate = self.config.LEARNING_RATE,
        )
        ae_history = self.autoencoder.train(
            X_train                 = X_train,
            X_val                   = X_val,
            epochs                  = epochs,
            batch_size              = batch_size,
            early_stopping_patience = self.config.EARLY_STOPPING_PATIENCE,
            threshold_k             = self.config.THRESHOLD_K,
        )

        # LSTM Autoencoder
        lstm_history = None
        if use_lstm:
            X_sequences, _, _ = self.preprocessor.create_sequences(
                X_full, df_full_proc, group_by="city"
            )
            if len(X_sequences) > 100:
                seq_split = int(len(X_sequences) * (1 - self.config.VALIDATION_SPLIT))
                self.lstm_autoencoder = LSTMAutoencoder(
                    sequence_length = self.config.SEQUENCE_LENGTH,
                    n_features      = input_dim,
                    lstm_units      = self.config.LSTM_UNITS,
                    encoding_dim    = self.config.ENCODING_DIM,
                    dropout_rate    = self.config.DROPOUT_RATE,
                    learning_rate   = self.config.LEARNING_RATE,
                )
                lstm_history = self.lstm_autoencoder.train(
                    X_train                 = X_sequences[:seq_split],
                    X_val                   = X_sequences[seq_split:],
                    epochs                  = epochs // 2,
                    batch_size              = max(batch_size // 2, 16),
                    early_stopping_patience = self.config.EARLY_STOPPING_PATIENCE,
                    threshold_k             = self.config.THRESHOLD_K,
                )
            else:
                logger.warning("Insufficient sequences for LSTM — skipping.")
                use_lstm = False

        # Hybrid detector
        if use_lstm and self.lstm_autoencoder:
            self.hybrid_detector = HybridAnomalyDetector(self.autoencoder, self.lstm_autoencoder)
        else:
            self.hybrid_detector = HybridAnomalyDetector(self.autoencoder)

        self._sequence_buffer = _CitySequenceBuffer(self.config.SEQUENCE_LENGTH)
        if self.lstm_autoencoder:
            self._seed_buffer_from_X_and_df(X_full, df_full_proc)

        if save_model:
            self._save_models()

        training_time         = (datetime.now() - start_time).total_seconds()
        ae_anomalies, ae_scores = self.autoencoder.detect_anomalies(X_full)

        self.training_metadata = {
            "training_time_seconds": training_time,
            "total_samples":         len(df),
            "train_samples":         len(X_train),
            "validation_samples":    len(X_val),
            "input_dim":             input_dim,
            "num_cities":            df["city"].nunique(),
            "cities":                df["city"].unique().tolist(),
            "date_range": {
                "start": str(df["date"].min()),
                "end":   str(df["date"].max()),
            },
            "autoencoder": {
                "final_loss":     float(ae_history["loss"][-1]),
                "final_val_loss": float(ae_history["val_loss"][-1]),
                "threshold":      float(self.autoencoder.threshold),
                "epochs_trained": len(ae_history["loss"]),
            },
            "lstm": None if not lstm_history else {
                "final_loss":     float(lstm_history["loss"][-1]),
                "final_val_loss": float(lstm_history["val_loss"][-1]),
                "epochs_trained": len(lstm_history["loss"]),
            },
            "anomaly_stats": {
                "total_anomalies_detected": int(np.sum(ae_anomalies)),
                "anomaly_percentage":       float(np.mean(ae_anomalies) * 100),
                "mean_score":               float(np.mean(ae_scores)),
                "max_score":                float(np.max(ae_scores)),
            },
        }
        self.is_trained = True
        logger.info(f"Training complete in {training_time:.1f}s.")

        return {
            "status":            "success",
            "message":           "Model trained successfully",
            "training_metadata": self.training_metadata,
            "ae_history":        ae_history,
            "lstm_history":      lstm_history,
        }

    def _save_models(self) -> None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.autoencoder.save(MODELS_DIR / "autoencoder_model")
        if self.lstm_autoencoder:
            self.lstm_autoencoder.save(MODELS_DIR / "lstm_model")
        self.preprocessor.save(MODELS_DIR / "preprocessor.joblib")
        logger.info(f"Models saved → {MODELS_DIR}")

    # --------------------------------------------------------
    #  Sequence buffer warm-up
    # --------------------------------------------------------

    def _resolve_warmup_csv_path(self) -> Optional[Path]:
        if HYBRID_WARMUP_CSV:
            p = Path(HYBRID_WARMUP_CSV)
            if p.is_file():
                return p
            logger.warning(f"HYBRID_WARMUP_CSV not found: {p}")
        csvs = sorted(DATA_DIR.glob("*.csv"))
        return csvs[0] if csvs else None

    def _seed_buffer_from_X_and_df(
        self,
        X: np.ndarray,
        df_processed: pd.DataFrame,
        rows_per_city: Optional[int] = None,
    ) -> None:
        if not HYBRID_WARMUP_ENABLED or self._sequence_buffer is None:
            return
        n   = max(int(rows_per_city or HYBRID_WARMUP_ROWS_PER_CITY), self.config.SEQUENCE_LENGTH)
        dfw = df_processed.reset_index(drop=True)
        dfw["_row"] = np.arange(len(dfw), dtype=int)
        if "city" not in dfw.columns:
            return
        warmed = 0
        for city in dfw["city"].dropna().unique():
            sub  = dfw[dfw["city"] == city]
            sub  = sub.sort_values("date") if "date" in sub.columns else sub.sort_values("_row")
            tail = sub.tail(n)
            if len(tail) == 0:
                continue
            self._sequence_buffer.seed_city(str(city), X[tail["_row"].values.astype(int)])
            warmed += 1
        logger.info(f"Hybrid buffer warmed for {warmed} cities.")

    def _warm_hybrid_buffer_after_load(self) -> None:
        if not HYBRID_WARMUP_ENABLED or not self.lstm_autoencoder:
            return
        path = self._resolve_warmup_csv_path()
        if path is None:
            return
        try:
            df         = load_and_prepare_data(str(path))
            X, df_proc = self.preprocessor.transform(df)
            self._seed_buffer_from_X_and_df(X, df_proc)
        except Exception as e:
            logger.warning(f"Hybrid buffer warmup failed: {e}", exc_info=True)

    # --------------------------------------------------------
    #  Prediction
    # --------------------------------------------------------

    def predict(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction.")

        data = weather_data.copy()

        # Derived features
        if data.get("temp_range") is None:
            tmin, tmax = data.get("tmin"), data.get("tmax")
            if tmin is not None and tmax is not None:
                data["temp_range"] = tmax - tmin
            else:
                data["temp_range"] = self.preprocessor.feature_stats.get(
                    "temp_range", {}
                ).get("mean", 10.0)

        for feat in self.preprocessor.numerical_features:
            if data.get(feat) is None:
                data[feat] = self.preprocessor.feature_stats.get(feat, {}).get("mean", 0.0)

        if data.get("date"):
            try:
                d = (
                    datetime.strptime(str(data["date"]), "%Y-%m-%d")
                    if isinstance(data["date"], str)
                    else data["date"]
                )
                data.setdefault("month",      d.month)
                data.setdefault("day",        d.day)
                data.setdefault("dayofweek",  d.weekday())
                data.setdefault("is_weekend", 1 if d.weekday() >= 5 else 0)
            except Exception:
                pass

        for feat in self.preprocessor.temporal_features:
            data.setdefault(feat, 0)
        for feat in self.preprocessor.categorical_features:
            data.setdefault(feat, "UNKNOWN")

        df   = pd.DataFrame([data])
        X, _ = self.preprocessor.transform(df)

        city = data.get("city", "Unknown")
        prcp = float(data.get("prcp", 0) or 0)

        # Autoencoder point-wise scoring
        ae_is_anomaly, ae_errors = self.autoencoder.detect_anomalies(X)
        ae_error     = float(ae_errors[0])
        anomaly      = bool(ae_is_anomaly[0])
        risk_level   = self.autoencoder.get_risk_level(ae_error)
        final_score  = ae_error
        final_thresh = float(self.autoencoder.threshold)
        score_kind   = "autoencoder_reconstruction_error"

        hybrid_payload: Optional[Dict[str, Any]] = None

        # Hybrid (LSTM) scoring
        if (
            self.lstm_autoencoder is not None
            and self.hybrid_detector is not None
            and self._sequence_buffer is not None
        ):
            try:
                seq = self._sequence_buffer.push_and_get_sequence(city, X)
                if seq is not None:
                    X_seq      = seq.reshape(1, seq.shape[0], seq.shape[1])
                    hybrid_out = self.hybrid_detector.detect_anomalies(X_point=X, X_sequence=X_seq)
                    combined   = float(hybrid_out["combined_score"][0])
                    lstm_score = float(hybrid_out["lstm_score"][0]) if hybrid_out.get("lstm_score") is not None else None
                    ae_norm    = float(hybrid_out["ae_score"][0])   if hybrid_out.get("ae_score")   is not None else None

                    anomaly      = bool(hybrid_out["is_anomaly"][0])
                    risk_level   = self._hybrid_risk_level(combined)
                    final_score  = combined
                    final_thresh = 0.5
                    score_kind   = "hybrid_normalized_combined_score"
                    hybrid_payload = {
                        "enabled":         True,
                        "sequence_length": int(self.config.SEQUENCE_LENGTH),
                        "buffer_ready":    True,
                        "combined_score":  round(combined, 6),
                        "threshold":       0.5,
                        "is_anomaly":      anomaly,
                        "risk_level":      risk_level,
                        "components": {
                            "ae_score_normalized":   None if ae_norm    is None else round(ae_norm, 6),
                            "lstm_score_normalized": None if lstm_score is None else round(lstm_score, 6),
                            "weights": {
                                "ae":   float(getattr(self.hybrid_detector, "weight_ae",   1.0)),
                                "lstm": float(getattr(self.hybrid_detector, "weight_lstm", 0.0)),
                            },
                        },
                    }
                else:
                    hybrid_payload = {
                        "enabled":         True,
                        "sequence_length": int(self.config.SEQUENCE_LENGTH),
                        "buffer_ready":    False,
                        "message":         "Buffer filling — using autoencoder-only scoring.",
                    }
            except Exception as e:
                logger.warning(f"Hybrid scoring failed: {e}")
                hybrid_payload = {"enabled": True, "error": str(e)}

        # HRI
        hri = compute_hri(
            anomaly_score     = ae_error,
            anomaly_threshold = float(self.autoencoder.threshold),
            prcp              = prcp,
            city              = city,
            config            = self.config,
        )

        # Feature importance
        feature_names = (
            self.preprocessor.numerical_features
            + self.preprocessor.temporal_features
            + list(self.preprocessor.ohe_categories.keys())
        )
        feature_importance = self.autoencoder.get_feature_importance(X, feature_names[: X.shape[1]])

        cloudburst_risk = self._assess_cloudburst_risk(data)
        explanation     = self._generate_explanation(data, float(final_score), anomaly, feature_importance, cloudburst_risk)

        return {
            "city":                  city,
            "date":                  data.get("date", str(datetime.now().date())),
            "anomaly_score":         round(float(final_score), 6),
            "threshold":             round(float(final_thresh), 6),
            "is_anomaly":            anomaly,
            "risk_level":            risk_level,
            "hri_score":             hri["hri_score"],
            "hri_label":             hri["hri_label"],
            "hri_components":        hri["hri_components"],
            "cloudburst_risk":       cloudburst_risk,
            "remarks":               explanation["summary"],
            "feature_contributions": feature_importance,
            "detailed_explanation":  explanation,
            "hybrid":                hybrid_payload,
            "ae_details": {
                "reconstruction_error": round(ae_error, 6),
                "threshold":            round(float(self.autoencoder.threshold), 6),
                "is_anomaly":           bool(ae_is_anomaly[0]),
                "severity":             self.autoencoder.get_risk_level(ae_error),
            },
            "score_kind": score_kind,
        }

    def predict_batch(self, weather_data_list: List[Dict]) -> List[Dict]:
        return [self.predict(d) for d in weather_data_list]

    # --------------------------------------------------------
    #  Risk helpers
    # --------------------------------------------------------

    def _hybrid_risk_level(self, combined_score: float) -> str:
        if combined_score <= 0.5:
            return "LOW"
        t = (combined_score - 0.5) / 0.5
        if t <= 1 / 3: return "MEDIUM"
        if t <= 2 / 3: return "HIGH"
        return "CRITICAL"

    def _assess_cloudburst_risk(self, weather_data: Dict) -> Dict[str, Any]:
        cfg         = self.cloudburst_config
        indicators  = {k: False for k in [
            "heavy_precipitation", "very_heavy_precipitation",
            "high_humidity", "very_high_humidity",
            "low_pressure", "very_low_pressure",
            "high_cloud_cover", "monsoon_season",
        ]}
        risk_score  = 0.0
        prcp        = float(weather_data.get("prcp", 0) or 0)
        humidity    = float(weather_data.get("humidity", 50) or 50)
        pressure    = float(weather_data.get("pressure", 1013) or 1013)
        cloud_cover = float(weather_data.get("cloud_cover", 0) or 0)
        month       = int(weather_data.get("month", datetime.now().month) or datetime.now().month)
        city        = weather_data.get("city", "")

        if prcp >= cfg.CLOUDBURST:
            indicators["heavy_precipitation"] = indicators["very_heavy_precipitation"] = True
            risk_score += cfg.WEIGHTS["precipitation"] * 1.0
        elif prcp >= cfg.VERY_HEAVY_RAIN:
            indicators["heavy_precipitation"] = indicators["very_heavy_precipitation"] = True
            risk_score += cfg.WEIGHTS["precipitation"] * 0.9
        elif prcp >= cfg.HEAVY_RAIN:
            indicators["heavy_precipitation"] = True
            risk_score += cfg.WEIGHTS["precipitation"] * 0.7
        elif prcp >= cfg.MODERATE_RAIN:
            risk_score += cfg.WEIGHTS["precipitation"] * 0.4
        elif prcp >= cfg.LIGHT_RAIN:
            risk_score += cfg.WEIGHTS["precipitation"] * 0.2

        if pressure <= cfg.VERY_LOW_PRESSURE:
            indicators["low_pressure"] = indicators["very_low_pressure"] = True
            risk_score += cfg.WEIGHTS["pressure"] * 1.0
        elif pressure <= cfg.LOW_PRESSURE:
            indicators["low_pressure"] = True
            risk_score += cfg.WEIGHTS["pressure"] * 0.7
        elif pressure <= cfg.NORMAL_PRESSURE - 5:
            risk_score += cfg.WEIGHTS["pressure"] * 0.3

        if humidity >= cfg.CRITICAL_HUMIDITY:
            indicators["high_humidity"] = indicators["very_high_humidity"] = True
            risk_score += cfg.WEIGHTS["humidity"] * 1.0
        elif humidity >= cfg.VERY_HIGH_HUMIDITY:
            indicators["high_humidity"] = indicators["very_high_humidity"] = True
            risk_score += cfg.WEIGHTS["humidity"] * 0.8
        elif humidity >= cfg.HIGH_HUMIDITY:
            indicators["high_humidity"] = True
            risk_score += cfg.WEIGHTS["humidity"] * 0.5

        if cloud_cover >= cfg.FULL_OVERCAST:
            indicators["high_cloud_cover"] = True
            risk_score += cfg.WEIGHTS["cloud_cover"] * 1.0
        elif cloud_cover >= cfg.OVERCAST:
            indicators["high_cloud_cover"] = True
            risk_score += cfg.WEIGHTS["cloud_cover"] * 0.7

        if month in cfg.MONSOON_MONTHS:
            indicators["monsoon_season"] = True
            risk_score *= cfg.MONSOON_SENSITIVITY_BOOST
        if city in cfg.FLASH_FLOOD_PRONE_CITIES:
            risk_score *= 1.1

        risk_score    = min(risk_score, 1.0)
        risk_category = (
            "CRITICAL" if risk_score >= 0.70 else
            "HIGH"     if risk_score >= 0.50 else
            "MODERATE" if risk_score >= 0.30 else
            "LOW"
        )
        is_cloudburst_likely = (
            risk_score >= 0.50
            and indicators["heavy_precipitation"]
            and (indicators["high_humidity"] or indicators["low_pressure"])
        )

        return {
            "risk_score":           round(risk_score, 3),
            "risk_category":        risk_category,
            "indicators":           indicators,
            "is_cloudburst_likely": is_cloudburst_likely,
        }

    def _generate_explanation(
        self,
        weather_data: Dict,
        anomaly_score: float,
        is_anomaly: bool,
        feature_importance: Dict[str, float],
        cloudburst_risk: Dict,
    ) -> Dict[str, Any]:
        explanation = {
            "summary": "",
            "anomaly_factors": [],
            "weather_conditions": [],
            "recommendations": [],
        }

        numerical_values = {
            f: weather_data.get(f, 0)
            for f in self.preprocessor.numerical_features
            if f in weather_data
        }
        deviations = self.preprocessor.get_feature_deviation(numerical_values)

        for feature, importance in sorted(feature_importance.items(), key=lambda x: -x[1])[:5]:
            if feature in deviations and deviations[feature]["is_outlier"]:
                d = deviations[feature]
                explanation["anomaly_factors"].append({
                    "feature":      feature,
                    "contribution": round(importance * 100, 1),
                    "value":        d["value"],
                    "expected":     round(d["mean"], 2),
                    "direction":    "high" if d["z_score"] > 0 else "low",
                    "z_score":      round(d["z_score"], 2),
                })

        conditions = []
        prcp     = weather_data.get("prcp", 0)
        humidity = weather_data.get("humidity", 50)
        if prcp > 50:       conditions.append("Extreme precipitation")
        elif prcp > 20:     conditions.append("Heavy rainfall")
        elif prcp > 5:      conditions.append("Moderate rainfall")
        if humidity > 90:   conditions.append("Very high humidity")
        elif humidity < 30: conditions.append("Low humidity")
        explanation["weather_conditions"] = conditions

        if is_anomaly:
            if cloudburst_risk["is_cloudburst_likely"]:
                summary = "⚠️ ALERT: Possible cloudburst/flash flood conditions detected. "
            elif cloudburst_risk["risk_category"] in ("HIGH", "CRITICAL"):
                summary = "⚠️ WARNING: High-risk weather conditions detected. "
            else:
                summary = "Unusual weather pattern detected. "
            factors = explanation["anomaly_factors"]
            if factors:
                top = factors[0]
                summary += (
                    f"Primary anomaly: {top['feature']} is unusually "
                    f"{top['direction']} (Z-score: {top['z_score']})."
                )
            explanation["recommendations"] = (
                [
                    "Monitor weather conditions closely",
                    "Avoid low-lying areas and nullahs",
                    "Prepare for possible flash flooding",
                    "Follow local emergency authority guidelines",
                ]
                if cloudburst_risk["is_cloudburst_likely"]
                else ["Stay informed about weather updates", "Take appropriate precautions"]
            )
        else:
            summary = "Weather conditions are within normal parameters."

        explanation["summary"] = summary
        return explanation

    # --------------------------------------------------------
    #  Statistics / model info
    # --------------------------------------------------------

    def get_anomaly_statistics(
        self,
        data_path: str,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
        city:       Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.is_trained:
            raise ValueError("Model must be trained first.")

        df = load_and_prepare_data(data_path)
        if start_date:
            df = df[df["date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["date"] <= pd.to_datetime(end_date)]
        if city:
            df = df[df["city"] == city]
        if len(df) == 0:
            return {"error": "No data found for given filters."}

        X, _ = self.preprocessor.transform(df)
        is_anomaly, scores = self.autoencoder.detect_anomalies(X)

        anomaly_df = df[is_anomaly].copy()
        anomaly_df["anomaly_score"] = scores[is_anomaly]
        anomaly_df["risk_level"]    = anomaly_df["anomaly_score"].apply(self.autoencoder.get_risk_level)

        return {
            "total_records":      len(df),
            "total_anomalies":    int(np.sum(is_anomaly)),
            "anomaly_percentage": round(float(np.mean(is_anomaly) * 100), 2),
            "mean_anomaly_score": round(float(np.mean(scores)), 6),
            "max_anomaly_score":  round(float(np.max(scores)), 6),
            "risk_distribution":  anomaly_df["risk_level"].value_counts().to_dict() if len(anomaly_df) else {},
            "anomalies_by_city":  anomaly_df.groupby("city").size().to_dict() if "city" in anomaly_df.columns and len(anomaly_df) else {},
            "anomalies_by_month": anomaly_df.groupby("month").size().to_dict() if "month" in anomaly_df.columns and len(anomaly_df) else {},
        }

    def get_model_info(self) -> Dict[str, Any]:
        if not self.is_trained:
            return {"status": "not_trained", "message": "Model not trained yet."}
        return {
            "status":     "trained",
            "model_type": "Hybrid Autoencoder + LSTM" if self.lstm_autoencoder else "Autoencoder",
            "training_metadata": self.training_metadata,
            "autoencoder_config": {
                "input_dim":     self.autoencoder.input_dim,
                "encoding_dim":  self.autoencoder.encoding_dim,
                "hidden_layers": self.autoencoder.hidden_layers,
                "threshold":     self.autoencoder.threshold,
            },
            "lstm_config": {
                "sequence_length": self.lstm_autoencoder.sequence_length,
                "lstm_units":      self.lstm_autoencoder.lstm_units,
                "threshold":       self.lstm_autoencoder.threshold,
            } if self.lstm_autoencoder else None,
            "preprocessor_info": {
                "numerical_features":     self.preprocessor.numerical_features,
                "categorical_features":   self.preprocessor.categorical_features,
                "temporal_features":      self.preprocessor.temporal_features,
                "feature_weights_applied": bool(self.preprocessor.feature_weights),
            },
        }


# Module-level singleton — imported by routers
anomaly_service = AnomalyDetectionService()
