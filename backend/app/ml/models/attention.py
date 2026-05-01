"""
HydroGuard-AI — Bahdanau (Additive) Attention
==============================================
Causal attention layer for the LSTM branch of the city-specific hybrid model.
Only attends to past/current time steps → safe for real-time forecasting.

Usage:
    context, weights = BahdanauAttention(units=32)(query, values)
    # query : [batch, hidden_dim]
    # values: [batch, seq_len, hidden_dim]  — LSTM output sequences
    # context: [batch, hidden_dim]           — weighted context vector
    # weights: [batch, seq_len, 1]           — attention distribution
"""

from __future__ import annotations

import tensorflow as tf
from tensorflow import keras


class BahdanauAttention(keras.layers.Layer):
    """Additive (Bahdanau) attention.

    Score: e_t = V · tanh(W·h_t + U·s)
    Weight: a_t = softmax(e_t)
    Context: c = Σ a_t · h_t

    Parameters
    ----------
    units : int
        Dimensionality of the attention space.
    name : str
        Layer name.
    """

    def __init__(self, units: int = 32, name: str = "bahdanau_attention", **kwargs):
        super().__init__(name=name, **kwargs)
        self.units = units
        # Learnable projections
        self._W = keras.layers.Dense(units, use_bias=False, name=f"{name}_W")
        self._U = keras.layers.Dense(units, use_bias=False, name=f"{name}_U")
        self._V = keras.layers.Dense(1,     use_bias=False, name=f"{name}_V")

    def call(
        self,
        query: tf.Tensor,
        values: tf.Tensor,
        mask: tf.Tensor | None = None,
    ) -> tuple[tf.Tensor, tf.Tensor]:
        """Compute context vector and attention weights.

        Parameters
        ----------
        query  : (batch, hidden_dim)   — decoder state / last LSTM output
        values : (batch, seq_len, dim) — encoder sequence (LSTM return_sequences)
        mask   : (batch, seq_len) bool — optional padding mask

        Returns
        -------
        context : (batch, dim)        — attended context
        weights : (batch, seq_len, 1) — attention probabilities
        """
        # Expand query to broadcast over time steps → (batch, 1, hidden_dim)
        query_exp = tf.expand_dims(query, axis=1)

        # Compute additive scores → (batch, seq_len, units)
        score = self._V(
            tf.nn.tanh(self._W(values) + self._U(query_exp))
        )  # (batch, seq_len, 1)

        # Apply mask (set masked positions to large negative so softmax → 0)
        if mask is not None:
            mask_exp = tf.cast(tf.expand_dims(mask, axis=-1), dtype=score.dtype)
            score = score * mask_exp + (1.0 - mask_exp) * (-1e9)

        weights = tf.nn.softmax(score, axis=1)  # (batch, seq_len, 1)

        # Weighted sum over time axis
        context = tf.reduce_sum(weights * values, axis=1)  # (batch, dim)

        return context, weights

    def get_config(self) -> dict:
        base = super().get_config()
        base.update({"units": self.units})
        return base

    @classmethod
    def from_config(cls, config: dict) -> "BahdanauAttention":
        return cls(**config)
