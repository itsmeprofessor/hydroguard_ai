"""
HydroGuard-AI -- City-Specific Hybrid Anomaly Model v3.2
==========================================================
Architecture per city:
  AE branch  : Dense [64->32->16->latent-8->16->32->64->out], Dropout 0.20
                Trained on FAIR-WEATHER rows only (weak_label == 0).
                Score: ECDFScaler(ae_error) -> ae_percentile in [0,1]

  TCN branch : CausalTCN (dilations [1,2,4,8], seq_len=24, kernel=3, filters=64)
                Trained as next-step MSE reconstructor on full training set.
                Score: ECDFScaler(tcn_error) -> tcn_percentile in [0,1]

  Hybrid     : Raw branch outputs fed to FusionModel (LightGBM) -> P(event)
               Calibrated by IsotonicCalibrator -> event_probability

  AE/TCN variance: sigmoid(z-score of error vs training distribution)
                   Used for model_entropy and uncertainty computation.

No BahdanauAttention -- removed in v3.2 (replaced by TCN).
Strictly causal. No BiLSTM.

Output from predict():
  {
    ae_percentile:  float [0,1]  -- ECDF rank of AE reconstruction error
    tcn_percentile: float [0,1]  -- ECDF rank of TCN reconstruction error
    ae_variance:    float [0,1]  -- model uncertainty on AE branch
    tcn_variance:   float [0,1]  -- model uncertainty on TCN branch
    ae_error_raw:   float        -- raw MSE (for debugging)
    tcn_error_raw:  float        -- raw MSE (for debugging)
  }
  FusionModel + IsotonicCalibrator (in CityModelService) add:
    event_probability, confidence_interval, uncertainty, model_entropy,
    risk_band, is_alert, drivers
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import tensorflow as tf
from tensorflow import keras

from app.ml.models.tcn import build_tcn_reconstructor, make_sequences, TCN_SEQ_LEN
from app.ml.calibration.ecdf import ECDFScaler

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
#  Autoencoder hyper-parameters (unchanged from v3.1)
# ----------------------------------------------------------------
AE_ENCODER_DIMS = [64, 32, 16]
AE_LATENT_DIM   = 8
DROPOUT_RATE     = 0.20

# Sequence length now driven by TCN (24 hourly steps)
SEQUENCE_LENGTH  = TCN_SEQ_LEN   # 24


# ----------------------------------------------------------------
#  Autoencoder builder (unchanged)
# ----------------------------------------------------------------

def _build_autoencoder(input_dim: int) -> keras.Model:
    """Dense AE: encoder -> latent-8 -> decoder."""
    inp = keras.Input(shape=(input_dim,), name="ae_input")
    x   = inp
    for i, units in enumerate(AE_ENCODER_DIMS):
        x = keras.layers.Dense(units, activation="relu",  name=f"ae_enc_{i}")(x)
        x = keras.layers.Dropout(DROPOUT_RATE,            name=f"ae_enc_drop_{i}")(x)
    latent = keras.layers.Dense(AE_LATENT_DIM, activation="relu", name="ae_latent")(x)
    x      = latent
    for i, units in enumerate(reversed(AE_ENCODER_DIMS)):
        x = keras.layers.Dense(units, activation="relu",  name=f"ae_dec_{i}")(x)
        x = keras.layers.Dropout(DROPOUT_RATE,            name=f"ae_dec_drop_{i}")(x)
    out = keras.layers.Dense(input_dim, activation="linear", name="ae_output")(x)
    return keras.Model(inp, out, name="autoencoder")


# ----------------------------------------------------------------
#  CityHybridModel
# ----------------------------------------------------------------

class CityHybridModel:
    """
    Manages the AE + TCN pair for one city.

    Training
    --------
    model = CityHybridModel("islamabad", input_dim=28)
    model.build()
    ae_hist, tcn_hist = model.train(X_train, X_val, weak_labels=y_train)
    model.save(Path("saved_models/city_models/islamabad"))

    Inference
    ---------
    raw = model.predict(feature_vector, sequence)
    # raw: {ae_percentile, tcn_percentile, ae_variance, tcn_variance, ae_error_raw, tcn_error_raw}
    # FusionModel + calibrator in CityModelService convert these to event_probability.
    """

    AE_FILENAME    = "autoencoder.keras"
    TCN_FILENAME   = "tcn_reconstructor.keras"
    AE_ECDF_FILE   = "ae_ecdf.pkl"
    TCN_ECDF_FILE  = "tcn_ecdf.pkl"

    def __init__(self, city: str, input_dim: int, seq_len: int = SEQUENCE_LENGTH):
        self.city      = city.strip().title()
        self.input_dim = input_dim
        self.seq_len   = seq_len

        self._ae:  Optional[keras.Model] = None
        self._tcn: Optional[keras.Model] = None

        self._ae_ecdf:  ECDFScaler = ECDFScaler()
        self._tcn_ecdf: ECDFScaler = ECDFScaler()

        # Training distribution stats for variance calculation
        self._ae_error_mu:   float = 0.0
        self._ae_error_std:  float = 1.0
        self._tcn_error_mu:  float = 0.0
        self._tcn_error_std: float = 1.0

    # --------------------------------------------------------
    #  Build
    # --------------------------------------------------------

    def build(self) -> "CityHybridModel":
        self._ae  = _build_autoencoder(self.input_dim)
        self._tcn = build_tcn_reconstructor(self.input_dim)
        logger.info(
            "[%s] Models built -- AE params: %d, TCN params: %d",
            self.city,
            self._ae.count_params(),
            self._tcn.count_params(),
        )
        return self

    # --------------------------------------------------------
    #  Training
    # --------------------------------------------------------

    def train(
        self,
        X_train:      np.ndarray,
        X_val:        np.ndarray,
        weak_labels:  Optional[np.ndarray] = None,  # 0=normal, 1=event, -1=abstain
        epochs:       int   = 150,
        batch_size:   int   = 64,
        patience:     int   = 15,
        ae_lr:        float = 1e-3,
        tcn_lr:       float = 5e-4,
    ) -> Tuple[Any, Any]:
        """
        Phase 1: AE trained on FAIR-WEATHER rows only (weak_label == 0).
                 If no labels provided, falls back to full X_train.
        Phase 2: TCN trained on full X_train (next-step MSE).

        Parameters
        ----------
        X_train      : (N, input_dim) normalised feature matrix, time-ordered.
        X_val        : (M, input_dim) validation split (chronologically after train).
        weak_labels  : (N,) array of {-1, 0, 1}; 0 = fair-weather row for AE.
        """
        if self._ae is None or self._tcn is None:
            self.build()

        # ---- Phase 1: Autoencoder on fair-weather rows ----
        if weak_labels is not None and len(weak_labels) == len(X_train):
            X_normal = X_train[weak_labels == 0]
            if len(X_normal) < 50:
                logger.warning(
                    "[%s] Only %d fair-weather rows -- using full X_train for AE.",
                    self.city, len(X_normal),
                )
                X_normal = X_train
        else:
            X_normal = X_train

        logger.info("[%s] AE training on %d fair-weather rows", self.city, len(X_normal))
        self._ae.compile(optimizer=keras.optimizers.Adam(ae_lr), loss="mse")
        cb_ae = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=patience, restore_best_weights=True
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=patience // 2, min_lr=1e-6
            ),
        ]
        ae_hist = self._ae.fit(
            X_normal, X_normal,
            validation_data=(X_val, X_val),
            epochs=epochs, batch_size=batch_size,
            callbacks=cb_ae, verbose=0,
        )
        logger.info("[%s] AE done -- best val_loss=%.5f", self.city,
                    min(ae_hist.history["val_loss"]))

        # Calibrate AE ECDF on training errors
        ae_errs = self._compute_ae_errors(X_train)
        self._ae_ecdf.fit(ae_errs)
        self._ae_error_mu  = float(np.mean(ae_errs))
        self._ae_error_std = max(float(np.std(ae_errs)), 1e-9)

        # ---- Phase 2: TCN next-step reconstruction ----
        X_seq_train, y_seq_train = make_sequences(X_train, self.seq_len)
        X_seq_val,   y_seq_val   = make_sequences(X_val,   self.seq_len)

        if len(X_seq_train) < 100:
            logger.warning(
                "[%s] Not enough sequences (%d) for TCN -- skipped.",
                self.city, len(X_seq_train),
            )
            return ae_hist, None

        if len(X_seq_val) == 0:
            logger.warning("[%s] Val set too small for TCN sequences -- skipped.", self.city)
            return ae_hist, None

        self._tcn.compile(optimizer=keras.optimizers.Adam(tcn_lr), loss="mse")
        cb_tcn = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=patience, restore_best_weights=True
            ),
            keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=patience // 2, min_lr=1e-6
            ),
        ]
        tcn_hist = self._tcn.fit(
            X_seq_train, y_seq_train,
            validation_data=(X_seq_val, y_seq_val),
            epochs=epochs, batch_size=batch_size,
            callbacks=cb_tcn, verbose=0,
        )
        logger.info("[%s] TCN done -- best val_loss=%.5f", self.city,
                    min(tcn_hist.history["val_loss"]))

        # Calibrate TCN ECDF
        tcn_errs = self._compute_tcn_errors(X_seq_train, y_seq_train)
        self._tcn_ecdf.fit(tcn_errs)
        self._tcn_error_mu  = float(np.mean(tcn_errs))
        self._tcn_error_std = max(float(np.std(tcn_errs)), 1e-9)

        return ae_hist, tcn_hist

    # --------------------------------------------------------
    #  Inference
    # --------------------------------------------------------

    def predict(
        self,
        x:        np.ndarray,          # (input_dim,) current feature vector
        sequence: Optional[np.ndarray] = None,  # (seq_len, input_dim) rolling window
    ) -> Dict[str, Any]:
        """
        Branch-level inference.  Returns raw percentile scores and variance
        estimates.  The FusionModel + IsotonicCalibrator in CityModelService
        produce the final event_probability and risk_band.

        Parameters
        ----------
        x        : (input_dim,) preprocessed feature vector for current step
        sequence : (seq_len, input_dim) past seq_len vectors (NOT including x)
                   -- same as v3.1 convention; x is the "next step" target.
                   None -> TCN branch scores 0.0 (AE-only mode).
        """
        if self._ae is None:
            raise RuntimeError(f"Model for {self.city} not built/loaded.")

        x2d = x.reshape(1, -1)

        # ---- AE branch ----
        rec      = self._ae(x2d, training=False).numpy()
        ae_error = float(np.mean((x2d - rec) ** 2))
        ae_pct   = self._ae_ecdf.transform_scalar(ae_error)

        # AE variance: sigmoid of z-score relative to training distribution
        ae_z        = (ae_error - self._ae_error_mu) / max(self._ae_error_std, 1e-9)
        ae_variance = float(1.0 / (1.0 + np.exp(-ae_z)))

        # ---- TCN branch ----
        tcn_pct      = 0.0
        tcn_error    = 0.0
        tcn_variance = 0.0

        if self._tcn is not None and sequence is not None:
            seq3d    = sequence.reshape(1, self.seq_len, self.input_dim)
            pred     = self._tcn(seq3d, training=False).numpy()
            tcn_error = float(np.mean((pred - x2d) ** 2))
            tcn_pct   = self._tcn_ecdf.transform_scalar(tcn_error)
            tcn_z     = (tcn_error - self._tcn_error_mu) / max(self._tcn_error_std, 1e-9)
            tcn_variance = float(1.0 / (1.0 + np.exp(-tcn_z)))

        return {
            "ae_percentile":  round(float(np.clip(ae_pct,  0.0, 1.0)), 4),
            "tcn_percentile": round(float(np.clip(tcn_pct, 0.0, 1.0)), 4),
            "ae_variance":    round(ae_variance,    4),
            "tcn_variance":   round(tcn_variance,   4),
            "ae_error_raw":   round(ae_error,  6),
            "tcn_error_raw":  round(tcn_error, 6),
        }

    # --------------------------------------------------------
    #  Save / Load
    # --------------------------------------------------------

    def save(self, model_dir: Path) -> None:
        model_dir = Path(model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)

        self._ae.save(model_dir / self.AE_FILENAME)
        if self._tcn is not None:
            self._tcn.save(model_dir / self.TCN_FILENAME)

        self._ae_ecdf.save(model_dir / self.AE_ECDF_FILE)
        self._tcn_ecdf.save(model_dir / self.TCN_ECDF_FILE)

        # Legacy calibration file for backward compat reads
        import numpy as _np
        _np.save(
            model_dir / "ae_calibration.npy",
            _np.array([
                self._ae_error_mu,  self._ae_error_std, self._ae_ecdf.training_p99,
                self._tcn_error_mu, self._tcn_error_std, self._tcn_ecdf.training_p99,
            ]),
        )
        logger.info("[%s] Model saved -> %s", self.city, model_dir)

    @classmethod
    def load(cls, city: str, model_dir: Path) -> "CityHybridModel":
        model_dir = Path(model_dir)

        # Load AE
        ae_path = model_dir / cls.AE_FILENAME
        if not ae_path.exists():
            ae_path = model_dir / "autoencoder"   # legacy SavedModel dir
            if not ae_path.exists():
                raise FileNotFoundError(f"No AE model in {model_dir}")
        ae        = keras.models.load_model(ae_path)
        input_dim = ae.input_shape[-1]

        instance     = cls(city=city, input_dim=input_dim)
        instance._ae = ae

        # Load TCN (optional -- may be AE-only)
        tcn_path = model_dir / cls.TCN_FILENAME
        if not tcn_path.exists():
            tcn_path = model_dir / "lstm_attention.keras"   # v3.1 legacy name
        if tcn_path.exists():
            instance._tcn = keras.models.load_model(tcn_path)

        # Load ECDF scalers (preferred) or legacy calibration array
        ae_ecdf_path  = model_dir / cls.AE_ECDF_FILE
        tcn_ecdf_path = model_dir / cls.TCN_ECDF_FILE
        if ae_ecdf_path.exists():
            instance._ae_ecdf = ECDFScaler.load(ae_ecdf_path)
        if tcn_ecdf_path.exists():
            instance._tcn_ecdf = ECDFScaler.load(tcn_ecdf_path)

        # Legacy fallback: read ae_calibration.npy for mu/std
        calib_path = model_dir / "ae_calibration.npy"
        if calib_path.exists():
            arr = np.load(calib_path)
            if len(arr) >= 2:
                instance._ae_error_mu,  instance._ae_error_std  = float(arr[0]), float(arr[1])
            if len(arr) >= 5:
                instance._tcn_error_mu, instance._tcn_error_std = float(arr[3]), float(arr[4])

        logger.info("[%s] Model loaded from %s", city, model_dir)
        return instance

    # --------------------------------------------------------
    #  Helpers
    # --------------------------------------------------------

    def _compute_ae_errors(self, X: np.ndarray) -> np.ndarray:
        rec = self._ae.predict(X, batch_size=256, verbose=0)
        return np.mean((X - rec) ** 2, axis=1)

    def _compute_tcn_errors(
        self, X_seq: np.ndarray, y_next: np.ndarray
    ) -> np.ndarray:
        pred = self._tcn.predict(X_seq, batch_size=256, verbose=0)
        return np.mean((pred - y_next) ** 2, axis=1)

    # --------------------------------------------------------
    #  Properties
    # --------------------------------------------------------

    @property
    def ae_threshold(self) -> float:
        """p99 training AE error (for backward compat)."""
        return self._ae_ecdf.training_p99

    @property
    def is_built(self) -> bool:
        return self._ae is not None
