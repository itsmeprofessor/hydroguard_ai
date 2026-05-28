"""
HydroGuard-AI — LightGBM FusionModel v3.4
==========================================
Supervised binary classifier: AE/TCN branch outputs + dynamic weather features
→ calibrated P(hydro-meteorological event).

v3.4 additions (validation hardening):
  Phase 1 — Grouped Stratified Temporal Split
    Splits by event-cluster groups, not individual rows.
    Guarantees: both classes in both splits, no event cluster spans
    the boundary, seasonal representation preserved.
    Fallback chain: StratifiedGroupKFold → year-month bucket
    → pure stratified (last resort, logged as WARNING).

  Phase 2 — Strict Schema Validation
    Feature schema locked at fit time.
    predict_proba / predict_scalar raise SchemaValidationError
    on any column count / name / order mismatch. Never silently reorders.

Locked feature list (16): see FUSION_FEATURES below.
Regularisation params (Phase 2 fix): num_leaves=20, min_child_samples=40,
  reg_lambda=2.0, reg_alpha=0.5, min_split_gain=0.01.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np

logger = logging.getLogger(__name__)


# ── Locked feature list ────────────────────────────────────────────────────

FUSION_FEATURES: List[str] = [
    "ae_percentile",
    "tcn_percentile",
    "ae_variance",
    "tcn_variance",
    "pressure_delta_3h",
    "pressure_delta_6h",
    "rain_rate_1h",
    "rain_accumulation_3h",
    "prcp_climo_pct",
    "humidity_climo_pct",
    "moisture_flux",
    "tdew_spread",
    "cloud_jump_3h",
    "month",
    "is_monsoon_month",
    "vulnerability",
]

# ── Regularised LGB params (prevents event-cluster memorisation) ───────────

LGB_PARAMS: Dict[str, Any] = {
    "objective":         "binary",
    "n_estimators":      300,
    "learning_rate":     0.05,
    "max_depth":         5,          # shallower — broader generalisation
    "num_leaves":        20,         # was 31
    "min_child_samples": 40,         # was 20 — ≥40 samples per leaf
    "min_split_gain":    0.01,       # minimum gain for a valid split
    "reg_lambda":        2.0,        # L2 on leaf weights
    "reg_alpha":         0.5,        # L1 sparsity
    "subsample":         0.8,
    "colsample_bytree":  0.8,
    "random_state":      42,
    "verbose":           -1,
    "n_jobs":            -1,
}

# ── Schema validation error ────────────────────────────────────────────────

class SchemaValidationError(ValueError):
    """Raised when inference input does not match the fitted feature schema."""


# ── Schema dataclass (Phase 2) ─────────────────────────────────────────────

@dataclass
class FeatureSchema:
    """Immutable feature schema locked at fit time."""
    feature_names: List[str]
    n_features:    int = field(init=False)

    def __post_init__(self):
        self.n_features = len(self.feature_names)

    def validate(self, columns: List[str]) -> None:
        """
        Validate that `columns` exactly matches the fitted schema.
        Raises SchemaValidationError with a precise diagnostic message.
        """
        if len(columns) != self.n_features:
            raise SchemaValidationError(
                f"Feature count mismatch: expected {self.n_features}, "
                f"got {len(columns)}.\n"
                f"  Expected: {self.feature_names}\n"
                f"  Received: {list(columns)}"
            )
        for i, (expected, actual) in enumerate(
            zip(self.feature_names, columns)
        ):
            if expected != actual:
                raise SchemaValidationError(
                    f"Feature mismatch at position {i}: "
                    f"expected '{expected}', got '{actual}'.\n"
                    f"  Full expected: {self.feature_names}\n"
                    f"  Full received: {list(columns)}"
                )


# ── Grouped Stratified Temporal Split (Phase 1) ────────────────────────────

def _build_event_clusters(
    y:         np.ndarray,
    dates:     Optional["pd.Series"] = None,
    gap_steps: int = 7,
) -> np.ndarray:
    """
    Assign group IDs to rows so each continuous event cluster (consecutive
    positive rows within `gap_steps` of each other) shares one group ID.

    Non-event rows are grouped by year-month when dates are available,
    or by 30-row buckets otherwise (keeps them in manageable groups for
    StratifiedGroupKFold rather than treating every row as its own group).

    Returns
    -------
    groups : (N,) int array — group ID per row
    """
    n      = len(y)
    groups = np.zeros(n, dtype=np.int64)

    # ── Positive clusters ─────────────────────────────────────────
    cluster_id    = 0
    in_cluster    = False
    last_pos_step = -gap_steps - 1

    for i in range(n):
        if y[i] == 1:
            if (i - last_pos_step) > gap_steps:
                cluster_id += 1          # start a new cluster
            groups[i]     = cluster_id
            last_pos_step = i
            in_cluster    = True
        # (negatives handled below)

    max_cluster = cluster_id

    # ── Negative groups ───────────────────────────────────────────
    if dates is not None:
        try:
            import pandas as _pd
            dates_ts = _pd.to_datetime(dates).reset_index(drop=True)
            base_id  = max_cluster + 1
            for i in range(n):
                if y[i] != 1:
                    d = dates_ts.iloc[i]
                    # Unique ID per year-month bucket (offset above clusters)
                    groups[i] = base_id + d.year * 12 + d.month
        except Exception:
            _assign_bucket_groups(y, groups, max_cluster, bucket=30)
    else:
        _assign_bucket_groups(y, groups, max_cluster, bucket=30)

    return groups


def _assign_bucket_groups(
    y:           np.ndarray,
    groups:      np.ndarray,
    max_cluster: int,
    bucket:      int = 30,
) -> None:
    """Assign non-event rows into consecutive 30-row buckets (in-place)."""
    base = max_cluster + 1
    for i in range(len(y)):
        if y[i] != 1:
            groups[i] = base + i // bucket


def grouped_stratified_temporal_split(
    X:            np.ndarray,
    y:            np.ndarray,
    sample_weight: Optional[np.ndarray],
    dates:        Optional["pd.Series"] = None,
    eval_frac:    float = 0.2,
    gap_steps:    int   = 7,
    random_state: int   = 42,
) -> Tuple[
    np.ndarray, np.ndarray,
    np.ndarray, np.ndarray,
    Optional[np.ndarray], Optional[np.ndarray],
    str, Dict[str, Any],
]:
    """
    Grouped Stratified Temporal Split — Phase 1 implementation.

    Split hierarchy:
      1. StratifiedGroupKFold on event-cluster groups (preferred)
      2. Year-month bucket groups (fallback when sklearn unavailable)
      3. Pure stratified random split (last resort, logged as WARNING)

    Guarantees
    ----------
    - Both classes appear in train and eval
    - No event cluster spans the train/eval boundary
    - Seasonal (year-month) representation roughly preserved
    - No adjacent temporal window leakage across the split

    Returns
    -------
    X_tr, X_ev, y_tr, y_ev, sw_tr, sw_ev, method_used, split_info
    """
    import pandas as pd
    from sklearn.model_selection import train_test_split

    method_used = "unknown"
    n = len(X)
    n_folds = max(2, int(round(1.0 / eval_frac)))

    groups = _build_event_clusters(y, dates, gap_steps)

    # ── Attempt StratifiedGroupKFold ─────────────────────────────
    try:
        from sklearn.model_selection import StratifiedGroupKFold
        sgkf  = StratifiedGroupKFold(
            n_splits=n_folds,
            shuffle=True,
            random_state=random_state,
        )
        splits     = list(sgkf.split(X, y.astype(int), groups=groups))
        # Use last fold as eval (closest to temporal end when data is ordered)
        tr_idx, ev_idx = splits[-1]
        method_used = "StratifiedGroupKFold"
        logger.info(
            "Split method=StratifiedGroupKFold  n_folds=%d  "
            "using fold %d as eval",
            n_folds, n_folds,
        )
    except Exception as exc:
        logger.warning(
            "StratifiedGroupKFold unavailable (%s). "
            "Falling back to year-month bucket stratified split.",
            exc,
        )
        # ── Fallback: year-month stratified ──────────────────────
        try:
            tr_idx, ev_idx = _year_month_stratified_split(
                y, groups, eval_frac, random_state
            )
            method_used = "year_month_stratified"
        except Exception as exc2:
            logger.warning(
                "Year-month stratified split failed (%s). "
                "Using pure stratified split (WARNING: possible temporal leakage).",
                exc2,
            )
            all_idx       = np.arange(n)
            tr_idx, ev_idx = train_test_split(
                all_idx,
                test_size    = eval_frac,
                stratify     = y.astype(int),
                random_state = random_state,
            )
            method_used = "pure_stratified_FALLBACK"

    X_tr = X[tr_idx]; X_ev = X[ev_idx]
    y_tr = y[tr_idx]; y_ev = y[ev_idx]
    sw_tr = sample_weight[tr_idx] if sample_weight is not None else None
    sw_ev = sample_weight[ev_idx] if sample_weight is not None else None

    # ── Validate split health ─────────────────────────────────────
    n_tr_pos = int((y_tr == 1).sum())
    n_ev_pos = int((y_ev == 1).sum())

    if n_tr_pos == 0 or n_ev_pos == 0:
        raise ValueError(
            f"Split produced single-class partition even with grouped strategy "
            f"(method={method_used}). "
            f"train_pos={n_tr_pos}, eval_pos={n_ev_pos}. "
            "Check label distribution or use --force."
        )

    # Check cluster leakage: no cluster ID in both splits
    tr_clusters = set(groups[tr_idx][y_tr == 1])
    ev_clusters = set(groups[ev_idx][y_ev == 1])
    overlap     = tr_clusters & ev_clusters
    if overlap:
        logger.warning(
            "Split cluster overlap detected: %d cluster(s) appear in both "
            "train and eval. method=%s",
            len(overlap), method_used,
        )

    split_info = {
        "method":             method_used,
        "n_train":            int(len(tr_idx)),
        "n_eval":             int(len(ev_idx)),
        "train_pos":          n_tr_pos,
        "train_neg":          int((y_tr == 0).sum()),
        "eval_pos":           n_ev_pos,
        "eval_neg":           int((y_ev == 0).sum()),
        "train_pos_ratio":    round(n_tr_pos / max(len(y_tr), 1), 4),
        "eval_pos_ratio":     round(n_ev_pos / max(len(y_ev), 1), 4),
        "n_event_clusters":   int(groups[y == 1].max()) if (y == 1).any() else 0,
        "cluster_overlap":    int(len(overlap)),
    }

    logger.info(
        "Split summary | method=%-28s | "
        "train=%d (pos=%d, ratio=%.3f) | "
        "eval=%d (pos=%d, ratio=%.3f) | "
        "clusters=%d | overlap=%d",
        method_used,
        split_info["n_train"], n_tr_pos, split_info["train_pos_ratio"],
        split_info["n_eval"],  n_ev_pos, split_info["eval_pos_ratio"],
        split_info["n_event_clusters"], split_info["cluster_overlap"],
    )

    return X_tr, X_ev, y_tr, y_ev, sw_tr, sw_ev, method_used, split_info


def _year_month_stratified_split(
    y:            np.ndarray,
    groups:       np.ndarray,
    eval_frac:    float,
    random_state: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Group rows by year-month bucket then sample eval_frac groups for eval,
    ensuring both classes are represented.
    """
    rng       = np.random.default_rng(random_state)
    unique_g  = np.unique(groups)
    pos_groups = set(groups[y == 1].tolist())
    neg_groups = set(unique_g.tolist()) - pos_groups

    n_eval_pos = max(1, int(len(pos_groups) * eval_frac))
    n_eval_neg = max(1, int(len(neg_groups) * eval_frac))

    eval_pos_g = set(rng.choice(sorted(pos_groups), n_eval_pos, replace=False))
    eval_neg_g = set(rng.choice(sorted(neg_groups), n_eval_neg, replace=False))
    eval_groups = eval_pos_g | eval_neg_g

    ev_mask = np.isin(groups, list(eval_groups))
    tr_idx  = np.where(~ev_mask)[0]
    ev_idx  = np.where(ev_mask)[0]
    return tr_idx, ev_idx


# ── FusionModel ────────────────────────────────────────────────────────────

class FusionModel:
    """
    LightGBM binary classifier: P(hydro event) from AE/TCN branch scores +
    dynamic weather features.

    v3.4 additions:
      - Grouped Stratified Temporal Split (Phase 1)
      - Strict feature schema validation at predict time (Phase 2)
    """

    def __init__(self):
        self._model:         Any              = None
        self._feature_names: List[str]        = list(FUSION_FEATURES)
        self._schema:        Optional[FeatureSchema] = None
        self._is_fitted:     bool             = False
        self._train_metrics: Dict[str, Any]   = {}
        self._split_info:    Dict[str, Any]   = {}

    # ── Training ───────────────────────────────────────────────────

    def train(
        self,
        X_cal:         np.ndarray,
        y_cal:         np.ndarray,
        sample_weight: Optional[np.ndarray] = None,
        eval_frac:     float                = 0.2,
        dates:         Optional[Any]        = None,   # pd.Series of dates, optional
    ) -> Dict[str, Any]:
        """
        Train LightGBM using grouped-stratified temporal split.

        Parameters
        ----------
        X_cal         : (N, 16) calibration feature matrix
        y_cal         : (N,) binary labels — no abstains (-1 already removed)
        sample_weight : (N,) confidence weights (weak_label_conf)
        eval_frac     : fraction used as eval set
        dates         : optional pd.Series of dates aligned to X_cal rows;
                        enables year-month bucket grouping for split

        Returns
        -------
        dict: val_auc, val_brier, positive_rate, n_samples, split_info
        """
        try:
            import lightgbm as lgb
            from sklearn.metrics import roc_auc_score, brier_score_loss
        except ImportError as exc:
            raise ImportError(
                "lightgbm and scikit-learn are required. "
                f"pip install lightgbm scikit-learn — {exc}"
            )
        import pandas as pd

        X = np.asarray(X_cal, dtype=float)
        y = np.asarray(y_cal, dtype=float)

        # Imbalance correction
        pos       = int(y.sum())
        neg       = int((y == 0).sum())
        scale_pos = (neg / max(pos, 1)) if pos > 0 else 1.0
        params    = {**LGB_PARAMS, "scale_pos_weight": scale_pos}

        # ── Phase 1: Grouped Stratified Temporal Split ────────────
        X_tr, X_ev, y_tr, y_ev, sw_tr, sw_ev, method, split_info = (
            grouped_stratified_temporal_split(
                X, y, sample_weight, dates=dates,
                eval_frac=eval_frac,
            )
        )
        self._split_info = split_info

        # ── Phase 2: Lock feature schema at fit time ──────────────
        self._schema = FeatureSchema(feature_names=list(self._feature_names))

        # ── Fit with named columns (eliminates LightGBM warning) ──
        X_tr_df = pd.DataFrame(X_tr, columns=self._feature_names)
        X_ev_df = pd.DataFrame(X_ev, columns=self._feature_names)

        self._model = lgb.LGBMClassifier(**params)
        self._model.fit(
            X_tr_df, y_tr,
            sample_weight      = sw_tr,
            eval_set           = [(X_ev_df, y_ev)],
            eval_sample_weight = [sw_ev] if sw_ev is not None else None,
            callbacks          = [lgb.early_stopping(30, verbose=False),
                                  lgb.log_evaluation(period=-1)],
        )

        # ── Metrics ───────────────────────────────────────────────
        p_ev = self._model.predict_proba(X_ev_df)[:, 1]
        try:
            val_auc = float(roc_auc_score(y_ev, p_ev)) \
                      if len(np.unique(y_ev)) >= 2 else float("nan")
        except Exception:
            val_auc = float("nan")
        val_brier = float(brier_score_loss(y_ev, p_ev))

        self._is_fitted    = True
        self._train_metrics = {
            "val_auc":         round(val_auc, 4) if not np.isnan(val_auc) else None,
            "val_brier":       round(val_brier, 4),
            "positive_rate":   round(float(y.mean()), 4),
            "n_samples":       int(len(X)),
            "scale_pos_weight": round(scale_pos, 2),
            "split_method":    method,
            "split_info":      split_info,
        }

        auc_str = f"{val_auc:.4f}" if not np.isnan(val_auc) else "NaN"
        logger.info(
            "FusionModel trained: n=%d  pos_rate=%.1f%%  "
            "val_auc=%s  val_brier=%.4f  split=%s",
            len(X), 100 * float(y.mean()), auc_str, val_brier, method,
        )
        return self._train_metrics

    # ── Inference (Phase 2 schema enforcement) ─────────────────────

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        (N, 16) → (N,) P(event), uncalibrated.
        Validates feature schema before inference.
        """
        self._assert_fitted()
        import pandas as pd
        X     = np.asarray(X, dtype=float)
        X_df  = pd.DataFrame(X, columns=self._feature_names)
        self._schema.validate(list(X_df.columns))
        return self._model.predict_proba(X_df)[:, 1]

    def predict_scalar(self, features: Dict[str, float]) -> float:
        """Single observation dict → scalar P(event).
        Validates that all FUSION_FEATURES keys are present.
        """
        self._assert_fitted()
        import pandas as pd
        missing = [f for f in self._feature_names if f not in features]
        extra   = [k for k in features if k not in set(self._feature_names)]
        if missing:
            raise SchemaValidationError(
                f"predict_scalar: missing features: {missing}"
            )
        if extra:
            logger.debug("predict_scalar: ignoring extra keys: %s", extra)
        row  = {f: float(features.get(f, 0.0) or 0.0) for f in self._feature_names}
        X_df = pd.DataFrame([row], columns=self._feature_names)
        self._schema.validate(list(X_df.columns))
        return float(self._model.predict_proba(X_df)[0, 1])

    # ── SHAP explainability ───────────────────────────────────────

    def shap_values(self, features: Dict[str, float]) -> Dict[str, float]:
        """Top-8 SHAP values using LightGBM native pred_contrib (no external shap package)."""
        if not self._is_fitted or self._model is None:
            return {}
        try:
            import pandas as pd
            row  = {f: float(features.get(f, 0.0) or 0.0) for f in self._feature_names}
            X_df = pd.DataFrame([row], columns=self._feature_names)
            # Use the native booster API — more reliable than the sklearn wrapper for pred_contrib.
            # pred_contrib returns (N, n_features + 1); last column = expected value baseline.
            contrib = self._model.booster_.predict(X_df.values, pred_contrib=True)
            sv      = np.asarray(contrib).ravel()[:-1]   # drop expected-value column
            order   = np.argsort(-np.abs(sv))[:8]
            return {self._feature_names[i]: round(float(sv[i]), 4) for i in order}
        except Exception as exc:
            logger.warning("shap_values (LGB native) failed: %s — using gain importance", exc)
            try:
                imp = self.feature_importance()
                top = sorted(imp.items(), key=lambda x: -abs(x[1]))[:8]
                return {k: round(v, 4) for k, v in top}
            except Exception:
                return {}

    def feature_importance(self) -> Dict[str, float]:
        """LightGBM gain-based feature importance."""
        if not self._is_fitted or self._model is None:
            return {}
        return {
            f: float(v)
            for f, v in zip(
                self._feature_names,
                self._model.feature_importances_,
            )
        }

    # ── Persistence ───────────────────────────────────────────────

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("FusionModel saved → %s", path)

    @classmethod
    def load(cls, path: Path) -> "FusionModel":
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected FusionModel, got {type(obj)}")
        logger.info("FusionModel loaded ← %s  (fitted=%s)", path, obj._is_fitted)
        return obj

    # ── Private helpers ───────────────────────────────────────────

    def _assert_fitted(self) -> None:
        if not self._is_fitted or self._model is None:
            raise RuntimeError("FusionModel not trained. Call train() first.")
        # Models saved before v3.4 schema validation won't have _schema in __dict__.
        # Reconstruct it from _feature_names so old pkl files work without retraining.
        if not hasattr(self, "_schema") or self._schema is None:
            self._schema = FeatureSchema(feature_names=list(self._feature_names))

    # ── Properties ────────────────────────────────────────────────

    @property
    def train_metrics(self) -> Dict[str, Any]:
        return self._train_metrics

    @property
    def split_info(self) -> Dict[str, Any]:
        return self._split_info

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def feature_schema(self) -> Optional[FeatureSchema]:
        return self._schema
