"""
HydroGuard-AI — City-Specific Hybrid Anomaly Model
===================================================
Architecture per city:
  Autoencoder  : Dense [64 → 32 → 16 → latent-8 → 16 → 32 → 64 → output]
  LSTM+Attn    : LSTM(64, return_sequences=True) → BahdanauAttention(32)
                 → LSTM(32) → Dense(16) → Dense(1, sigmoid)
  Hybrid score : 0.55 × ae_score + 0.45 × lstm_score   (both normalised 0-1)

Standardised output format (always returned by .predict()):
  {
    "risk_level":    "Low" | "Medium" | "High",
    "anomaly_score": float  0-1,
    "confidence":    float  0-1,
    "is_anomaly":    bool,
    "ae_score":      float  (reconstruction error, normalised),
    "lstm_score":    float  (sequential anomaly probability),
    "hri_score":     int    0-100,
  }

No BiLSTM — strictly causal (forward LSTM only).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import tensorflow as tf
from tensorflow import keras

from app.ml.models.attention import BahdanauAttention

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
#  Hyper-parameters
# ──────────────────────────────────────────────────────────

AE_ENCODER_DIMS  = [64, 32, 16]
AE_LATENT_DIM    = 8
LSTM_UNITS_1     = 64
LSTM_UNITS_2     = 32
ATTN_UNITS       = 32
DROPOUT_RATE     = 0.20
AE_WEIGHT        = 0.55
LSTM_WEIGHT      = 0.45
SEQUENCE_LENGTH  = 7          # rolling window fed to the LSTM branch


# ──────────────────────────────────────────────────────────
#  Autoencoder
# ──────────────────────────────────────────────────────────

def _build_autoencoder(input_dim: int) -> keras.Model:
    """Dense autoencoder: encoder → latent → decoder."""
    inp = keras.Input(shape=(input_dim,), name="ae_input")
    x = inp
    for i, units in enumerate(AE_ENCODER_DIMS):
        x = keras.layers.Dense(units, activation="relu",
                                name=f"ae_enc_{i}")(x)
        x = keras.layers.Dropout(DROPOUT_RATE, name=f"ae_enc_drop_{i}")(x)

    latent = keras.layers.Dense(AE_LATENT_DIM, activation="relu",
                                 name="ae_latent")(x)

    x = latent
    for i, units in enumerate(reversed(AE_ENCODER_DIMS)):
        x = keras.layers.Dense(units, activation="relu",
                                name=f"ae_dec_{i}")(x)
        x = keras.layers.Dropout(DROPOUT_RATE, name=f"ae_dec_drop_{i}")(x)

    out = keras.layers.Dense(input_dim, activation="linear",
                              name="ae_output")(x)
    return keras.Model(inp, out, name="autoencoder")


# ──────────────────────────────────────────────────────────
#  LSTM + Attention anomaly detector
# ──────────────────────────────────────────────────────────

def _build_lstm_attention(input_dim: int) -> keras.Model:
    """LSTM(64, return_seq) → Attention → LSTM(32) → Dense → anomaly prob."""
    inp = keras.Input(shape=(SEQUENCE_LENGTH, input_dim), name="lstm_input")

    # First LSTM — return full sequence for attention
    lstm1_out = keras.layers.LSTM(
        LSTM_UNITS_1, return_sequences=True,
        dropout=DROPOUT_RATE, recurrent_dropout=0.1,
        name="lstm_1",
    )(inp)                                          # (batch, seq_len, 64)

    # Last hidden state used as attention query
    query = lstm1_out[:, -1, :]                     # (batch, 64)

    # Bahdanau attention over the LSTM sequence
    attn_layer = BahdanauAttention(units=ATTN_UNITS, name="attention")
    context, _ = attn_layer(query, lstm1_out)       # context: (batch, 64)

    # Concatenate context + last state → feed to second LSTM step
    combined = keras.layers.Concatenate(name="concat_ctx")([context, query])
    # Reshape to (batch, 1, 128) for second LSTM
    combined = keras.layers.Reshape((1, LSTM_UNITS_1 * 2), name="reshape")(combined)

    lstm2_out = keras.layers.LSTM(
        LSTM_UNITS_2, return_sequences=False,
        dropout=DROPOUT_RATE,
        name="lstm_2",
    )(combined)                                     # (batch, 32)

    x = keras.layers.Dense(16, activation="relu",  name="dense_mid")(lstm2_out)
    x = keras.layers.Dropout(DROPOUT_RATE, name="dense_drop")(x)
    out = keras.layers.Dense(1, activation="sigmoid", name="anomaly_prob")(x)

    return keras.Model(inp, out, name="lstm_attention_model")


# ──────────────────────────────────────────────────────────
#  Hybrid model wrapper
# ──────────────────────────────────────────────────────────

class CityHybridModel:
    """
    Manages the Autoencoder + LSTM+Attention pair for one city.

    Training
    --------
    model = CityHybridModel("islamabad", input_dim=18)
    model.build()
    ae_history, lstm_history = model.train(X_train, X_val, epochs=150)
    model.save(Path("saved_models/city_models/islamabad"))

    Inference
    ---------
    result = model.predict(feature_vector, city_buffer)
    # result: standardised dict (see module docstring)
    """

    RISK_THRESHOLDS = {
        "Low":    (0.00, 0.40),
        "Medium": (0.40, 0.65),
        "High":   (0.65, 1.01),
    }

    def __init__(self, city: str, input_dim: int):
        self.city = city.strip().title()
        self.input_dim = input_dim
        self._ae:    Optional[keras.Model] = None
        self._lstm:  Optional[keras.Model] = None
        # Percentile stats from training set (for score normalisation)
        self._ae_p99:   float = 1.0
        self._ae_mean:  float = 0.0
        self._ae_std:   float = 1.0

    # ──────────────────────────────────────────────────────
    #  Build
    # ──────────────────────────────────────────────────────

    def build(self) -> "CityHybridModel":
        self._ae   = _build_autoencoder(self.input_dim)
        self._lstm = _build_lstm_attention(self.input_dim)
        logger.info("[%s] Models built — AE params: %d, LSTM params: %d",
                    self.city,
                    self._ae.count_params(),
                    self._lstm.count_params())
        return self

    # ──────────────────────────────────────────────────────
    #  Training
    # ──────────────────────────────────────────────────────

    def train(
        self,
        X_train: np.ndarray,
        X_val:   np.ndarray,
        epochs:     int = 150,
        batch_size: int = 64,
        patience:   int = 15,
        ae_lr:      float = 1e-3,
        lstm_lr:    float = 5e-4,
    ) -> Tuple[Any, Any]:
        """Train AE first (reconstruction), then LSTM+Attention (anomaly labelling).

        Parameters
        ----------
        X_train : (N, input_dim)  — normalised feature matrix (normal-only records)
        X_val   : (M, input_dim)  — validation split
        Returns (ae_history, lstm_history)
        """
        if self._ae is None or self._lstm is None:
            self.build()

        # ── Phase 1: Autoencoder ──────────────────────────
        self._ae.compile(
            optimizer=keras.optimizers.Adam(ae_lr),
            loss="mse",
        )
        cb_ae = [
            keras.callbacks.EarlyStopping(monitor="val_loss", patience=patience,
                                          restore_best_weights=True),
            keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5,
                                               patience=patience // 2, min_lr=1e-6),
        ]
        ae_hist = self._ae.fit(
            X_train, X_train,
            validation_data=(X_val, X_val),
            epochs=epochs, batch_size=batch_size,
            callbacks=cb_ae, verbose=0,
        )
        logger.info("[%s] AE training done — best val_loss=%.5f",
                    self.city, min(ae_hist.history["val_loss"]))

        # Calibrate AE score distribution
        rec_errors = self._compute_ae_errors(X_train)
        self._ae_mean = float(np.mean(rec_errors))
        self._ae_std  = float(np.std(rec_errors))
        self._ae_p99  = float(np.percentile(rec_errors, 99))

        # ── Phase 2: LSTM + Attention ─────────────────────
        n_seq = len(X_train) - SEQUENCE_LENGTH
        if n_seq < 100:
            logger.warning("[%s] Not enough sequences (%d) for LSTM — skipped",
                           self.city, n_seq)
            return ae_hist, None

        X_seq, y_seq = self._make_sequences(X_train)
        X_val_seq, y_val_seq = self._make_sequences(X_val)

        self._lstm.compile(
            optimizer=keras.optimizers.Adam(lstm_lr),
            loss="binary_crossentropy",
            metrics=["accuracy"],
        )
        cb_lstm = [
            keras.callbacks.EarlyStopping(monitor="val_loss", patience=patience,
                                          restore_best_weights=True),
            keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5,
                                               patience=patience // 2, min_lr=1e-6),
        ]
        lstm_hist = self._lstm.fit(
            X_seq, y_seq,
            validation_data=(X_val_seq, y_val_seq),
            epochs=epochs, batch_size=batch_size,
            callbacks=cb_lstm, verbose=0,
        )
        logger.info("[%s] LSTM training done — best val_loss=%.5f",
                    self.city, min(lstm_hist.history["val_loss"]))

        return ae_hist, lstm_hist

    # ──────────────────────────────────────────────────────
    #  Inference
    # ──────────────────────────────────────────────────────

    def predict(
        self,
        x: np.ndarray,
        sequence: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """Standardised prediction.

        Parameters
        ----------
        x        : (input_dim,) — current feature vector (preprocessed)
        sequence : (SEQUENCE_LENGTH, input_dim) — rolling window for LSTM,
                   or None to use AE-only scoring

        Returns
        -------
        dict with keys: risk_level, anomaly_score, confidence,
                        is_anomaly, ae_score, lstm_score, hri_score
        """
        if self._ae is None:
            raise RuntimeError(f"Model for {self.city} not built/loaded.")

        x2d = x.reshape(1, -1)

        # ── AE score ──────────────────────────────────────
        rec   = self._ae(x2d, training=False).numpy()
        ae_err = float(np.mean((x2d - rec) ** 2))
        ae_norm = min(ae_err / max(self._ae_p99, 1e-9), 1.0)

        # ── LSTM score ────────────────────────────────────
        lstm_score = 0.0
        if self._lstm is not None and sequence is not None:
            seq3d = sequence.reshape(1, SEQUENCE_LENGTH, self.input_dim)
            lstm_score = float(
                self._lstm(seq3d, training=False).numpy()[0, 0]
            )

        # ── Hybrid score ──────────────────────────────────
        weight_ae   = AE_WEIGHT if sequence is not None else 1.0
        weight_lstm = LSTM_WEIGHT if sequence is not None else 0.0
        hybrid = weight_ae * ae_norm + weight_lstm * lstm_score
        hybrid = float(np.clip(hybrid, 0.0, 1.0))

        # ── Risk level ────────────────────────────────────
        risk_level = "Low"
        for label, (lo, hi) in self.RISK_THRESHOLDS.items():
            if lo <= hybrid < hi:
                risk_level = label
                break

        # ── Confidence ───────────────────────────────────
        # Distance from boundary — further from 0.5 → higher confidence
        confidence = float(min(abs(hybrid - 0.5) * 2.0, 1.0))

        # ── HRI (0-100) ───────────────────────────────────
        hri_score = int(round(hybrid * 100))

        return {
            "risk_level":    risk_level,
            "anomaly_score": round(hybrid, 4),
            "confidence":    round(confidence, 4),
            "is_anomaly":    hybrid > 0.40,
            "ae_score":      round(ae_norm, 4),
            "lstm_score":    round(lstm_score, 4),
            "hri_score":     hri_score,
        }

    # ──────────────────────────────────────────────────────
    #  Save / Load
    # ──────────────────────────────────────────────────────

    # File names — Keras 3 requires explicit .keras extension
    AE_FILENAME   = "autoencoder.keras"
    LSTM_FILENAME = "lstm_attention.keras"
    CALIB_FILENAME = "ae_calibration.npy"

    def save(self, model_dir: Path) -> None:
        """Save AE, LSTM, and calibration stats to *model_dir*."""
        model_dir = Path(model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)
        self._ae.save(model_dir / self.AE_FILENAME)
        if self._lstm is not None:
            self._lstm.save(model_dir / self.LSTM_FILENAME)
        np.save(model_dir / self.CALIB_FILENAME,
                np.array([self._ae_mean, self._ae_std, self._ae_p99]))
        logger.info("[%s] Model saved → %s", self.city, model_dir)

    @classmethod
    def load(cls, city: str, model_dir: Path) -> "CityHybridModel":
        """Load a previously saved city model.
        Tolerates legacy SavedModel directory format if present.
        """
        model_dir = Path(model_dir)
        custom_objects = {"BahdanauAttention": BahdanauAttention}

        ae_path = model_dir / cls.AE_FILENAME
        if not ae_path.exists():
            # Back-compat: try legacy SavedModel directory layout
            legacy = model_dir / "autoencoder"
            if legacy.exists():
                ae_path = legacy
            else:
                raise FileNotFoundError(f"No AE model found in {model_dir}")

        ae = keras.models.load_model(ae_path, custom_objects=custom_objects)
        input_dim = ae.input_shape[-1]

        instance = cls(city=city, input_dim=input_dim)
        instance._ae = ae

        lstm_path = model_dir / cls.LSTM_FILENAME
        if not lstm_path.exists():
            legacy_lstm = model_dir / "lstm_attention"
            if legacy_lstm.exists():
                lstm_path = legacy_lstm
        if lstm_path.exists():
            instance._lstm = keras.models.load_model(
                lstm_path, custom_objects=custom_objects
            )

        calib_path = model_dir / cls.CALIB_FILENAME
        if calib_path.exists():
            arr = np.load(calib_path)
            instance._ae_mean, instance._ae_std, instance._ae_p99 = (
                float(arr[0]), float(arr[1]), float(arr[2])
            )

        logger.info("[%s] Model loaded from %s", city, model_dir)
        return instance

    # ──────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────

    def _compute_ae_errors(self, X: np.ndarray) -> np.ndarray:
        rec = self._ae.predict(X, batch_size=256, verbose=0)
        return np.mean((X - rec) ** 2, axis=1)

    def _make_sequences(
        self, X: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Create overlapping windows (X_seq, y_seq).
        y = 0 for all (training set is normal-only).
        During fine-tuning with labelled anomalies, pass a y array directly.
        """
        n = len(X) - SEQUENCE_LENGTH
        X_seq = np.stack([X[i : i + SEQUENCE_LENGTH] for i in range(n)])
        y_seq = np.zeros(n, dtype=np.float32)
        return X_seq, y_seq

    @property
    def ae_threshold(self) -> float:
        """Reconstruction error threshold (99th percentile on training set)."""
        return self._ae_p99

    @property
    def is_built(self) -> bool:
        return self._ae is not None
