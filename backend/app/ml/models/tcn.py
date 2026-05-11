"""
HydroGuard-AI — Multi-Scale Causal Temporal Convolutional Network (TCN) v3.3
==============================================================================
Replaces the LSTM branch (fully removed in v3.2; no LSTM anywhere in codebase).

Architecture (v3.3 upgraded):
  seq_len   = 30  (30-observation rolling window; covers ~1 month of daily data)
  filters   = 128 (wider capacity for multi-scale storm dynamics)
  kernel    = 3
  dilations = [1, 2, 4, 8, 16, 32]
  Effective receptive field = (3-1) * (1+2+4+8+16+32) + 1 = 127 observations

Multi-scale dilation hierarchy:
  d=1  : day-to-day flash-flood precursors
  d=2  : 2-day convective system formation
  d=4  : weekly monsoon buildup
  d=8  : bi-weekly synoptic-scale patterns
  d=16 : monthly seasonal transitions
  d=32 : pre-monsoon onset patterns (~2-month lead)

Per TCN block:
  CausalConv1D(filters, kernel, dilation, padding="causal")
  LayerNormalization
  Activation("gelu")
  Dropout(0.2)  ← kept active at MC-inference for uncertainty estimation
  1×1 Conv1D residual projection (only when input channels != filters)
  Add()

After all blocks:
  GlobalAveragePooling1D
  Dense(input_dim, linear)   ← next-step reconstruction target

Objective: MSE on next-step prediction. Strictly causal. No LSTM. No BiTCN.
No custom Keras layers → standard keras.models.load_model works without custom_objects.

Usage:
    from app.ml.models.tcn import build_tcn_reconstructor, TCN_SEQ_LEN

    model = build_tcn_reconstructor(input_dim=35)
    model.compile(optimizer="adam", loss="mse")
    # Training: X_seq (N, 30, 35) → y_next (N, 35)
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  Architecture constants — upgrade to multi-scale dilations
# ─────────────────────────────────────────────────────────────

TCN_SEQ_LEN   = 30           # rolling window (30 observations ≈ 1 month daily)
TCN_FILTERS   = 128          # wider channel depth for multi-scale patterns
TCN_KERNEL    = 3            # kernel size (standard)
TCN_DILATIONS = [1, 2, 4, 8, 16, 32]  # RF = (3-1)*(1+2+4+8+16+32)+1 = 127
TCN_DROPOUT   = 0.20         # spatial dropout — active during MC inference


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
