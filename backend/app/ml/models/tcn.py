"""
HydroGuard-AI — Causal Temporal Convolutional Network (TCN)
=============================================================
Replaces the LSTM + BahdanauAttention branch in CityHybridModel.

Architecture (locked spec from Phase 2/3):
  seq_len   = 24  (24 hourly observations)
  filters   = 64
  kernel    = 3
  dilations = [1, 2, 4, 8]
  Effective receptive field = (3-1) * (1+2+4+8) + 1 = 31 timesteps

Per TCN block:
  CausalConv1D(filters, kernel, dilation, padding="causal")
  LayerNormalization
  Activation("gelu")
  Dropout(0.2)
  1×1 Conv1D residual projection (only if input channels != filters)
  Add()

After all blocks:
  GlobalAveragePooling1D
  Dense(input_dim, linear)   ← next-step reconstruction target

Objective: MSE on next-step prediction.
Strictly causal (no BiTCN, no future leakage).
No custom Keras layers → standard keras.models.load_model works without custom_objects.

Usage:
    from app.ml.models.tcn import build_tcn_reconstructor, TCN_SEQ_LEN

    model = build_tcn_reconstructor(input_dim=28)
    model.compile(optimizer="adam", loss="mse")
    # Training: X_seq (N, 24, 28) → y_next (N, 28)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  Locked architecture constants
# ─────────────────────────────────────────────────────────────

TCN_SEQ_LEN  = 24          # rolling window length (hourly)
TCN_FILTERS  = 64          # convolutional filters per block
TCN_KERNEL   = 3           # kernel size
TCN_DILATIONS = [1, 2, 4, 8]  # dilation rates → RF = (3-1)*(1+2+4+8)+1 = 31
TCN_DROPOUT  = 0.20        # dropout rate (train-time only)


# ─────────────────────────────────────────────────────────────
#  Builder
# ─────────────────────────────────────────────────────────────

def build_tcn_reconstructor(input_dim: int) -> "keras.Model":
    """
    Build a causal TCN next-step reconstructor.

    Parameters
    ----------
    input_dim : int
        Number of features per time step (output of WeatherDataPreprocessorV2).

    Returns
    -------
    keras.Model
        Input shape:  (batch, TCN_SEQ_LEN, input_dim)
        Output shape: (batch, input_dim)   ← predicted next feature vector
    """
    from tensorflow import keras

    inp = keras.Input(shape=(TCN_SEQ_LEN, input_dim), name="tcn_input")
    x   = inp

    for i, dilation in enumerate(TCN_DILATIONS):
        residual = x

        # Causal dilated convolution
        x = keras.layers.Conv1D(
            filters      = TCN_FILTERS,
            kernel_size  = TCN_KERNEL,
            dilation_rate= dilation,
            padding      = "causal",
            use_bias     = True,
            name         = f"tcn_conv_d{dilation}",
        )(x)

        # Normalise + activate
        x = keras.layers.LayerNormalization(name=f"tcn_ln_d{dilation}")(x)
        x = keras.layers.Activation("gelu",    name=f"tcn_gelu_d{dilation}")(x)
        x = keras.layers.Dropout(TCN_DROPOUT,  name=f"tcn_drop_d{dilation}")(x)

        # Residual projection: 1×1 conv if channel count differs
        res_channels = residual.shape[-1]
        if res_channels != TCN_FILTERS:
            residual = keras.layers.Conv1D(
                filters    = TCN_FILTERS,
                kernel_size= 1,
                padding    = "same",
                name       = f"tcn_res_proj_d{dilation}",
            )(residual)

        x = keras.layers.Add(name=f"tcn_add_d{dilation}")([x, residual])

    # Aggregate temporal dimension
    x = keras.layers.GlobalAveragePooling1D(name="tcn_gap")(x)

    # Project to input_dim (next-step reconstruction)
    out = keras.layers.Dense(
        input_dim,
        activation = "linear",
        name       = "tcn_out",
    )(x)

    model = keras.Model(inp, out, name="tcn_reconstructor")

    logger.info(
        "CausalTCN built — input_dim=%d  seq_len=%d  dilations=%s  params=%d",
        input_dim, TCN_SEQ_LEN, TCN_DILATIONS, model.count_params(),
    )
    return model


# ─────────────────────────────────────────────────────────────
#  Sequence builder helper (shared with training pipeline)
# ─────────────────────────────────────────────────────────────

def make_sequences(
    X: np.ndarray,
    seq_len: int = TCN_SEQ_LEN,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Create (input_sequence, target_next_step) pairs for TCN training.

    Input:  X[i : i+seq_len]   shape (seq_len, input_dim)
    Target: X[i+seq_len]        shape (input_dim,)

    Valid next-step prediction objective — no synthetic labels.

    Parameters
    ----------
    X : (N, input_dim) array of preprocessed feature vectors, time-ordered.
    seq_len : int — rolling window length.

    Returns
    -------
    X_seq  : (N - seq_len, seq_len, input_dim)
    y_next : (N - seq_len, input_dim)
    """
    n = len(X) - seq_len
    if n <= 0:
        empty_seq  = np.empty((0, seq_len, X.shape[-1]), dtype=X.dtype)
        empty_next = np.empty((0, X.shape[-1]),          dtype=X.dtype)
        return empty_seq, empty_next

    X_seq  = np.stack([X[i : i + seq_len] for i in range(n)])
    y_next = np.stack([X[i + seq_len]     for i in range(n)])
    return X_seq, y_next


# ─────────────────────────────────────────────────────────────
#  Receptive field diagnostic
# ─────────────────────────────────────────────────────────────

def receptive_field(
    kernel: int = TCN_KERNEL,
    dilations: list[int] = TCN_DILATIONS,
) -> int:
    """Return the effective receptive field in time steps."""
    return (kernel - 1) * sum(dilations) + 1
