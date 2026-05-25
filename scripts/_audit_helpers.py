"""
Pure helper functions for audit_karachi.py.
No I/O, no model loading — importable by tests without any backend deps.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


def temporal_split(
    df: pd.DataFrame,
    holdout_frac: float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Sort df by 'date' column (ascending) and split the last holdout_frac rows
    as the holdout.  Returns (train_df, holdout_df).
    n_holdout = floor(len(df) * holdout_frac)
    """
    df = df.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date").reset_index(drop=True)
    n = len(df)
    n_holdout = int(n * holdout_frac)
    n_train = n - n_holdout
    return df.iloc[:n_train].copy(), df.iloc[n_train:].copy()


def near_duplicate_rate(
    X_train_pos: np.ndarray,
    X_holdout_pos: np.ndarray,
    threshold: float = 0.95,
) -> float:
    """
    Fraction of holdout positives with cosine similarity >= threshold to any
    training positive.  Returns 0.0 when either set is empty.
    """
    if len(X_holdout_pos) == 0 or len(X_train_pos) == 0:
        return 0.0

    def _unit(M: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(M, axis=1, keepdims=True)
        return M / np.where(norms == 0, 1.0, norms)

    A = _unit(X_holdout_pos.astype(float))   # (n_holdout_pos, d)
    B = _unit(X_train_pos.astype(float))     # (n_train_pos, d)
    sim = A @ B.T                             # (n_holdout_pos, n_train_pos)
    contaminated = int((sim.max(axis=1) >= threshold).sum())
    return contaminated / len(X_holdout_pos)


def classify_pass_fail(
    reported_auc: float,
    clean_auc: float,
    auc_floor: float = 0.70,
    max_drop: float = 0.10,
) -> Tuple[str, bool]:
    """
    Return (verdict, retrain_recommended).

    FAIL_AUC_FLOOR  : clean_auc < auc_floor
    FAIL_AUC_DROP   : (reported_auc - clean_auc) > max_drop
    FAIL_BOTH       : both conditions true
    PASS            : neither condition true
    """
    floor_fail = clean_auc < auc_floor
    drop_fail  = (reported_auc - clean_auc) > max_drop
    if floor_fail and drop_fail:
        return "FAIL_BOTH", True
    if floor_fail:
        return "FAIL_AUC_FLOOR", True
    if drop_fail:
        return "FAIL_AUC_DROP", True
    return "PASS", False
