"""
HydroGuard-AI — Automated Leakage Audit Framework v1.0
=======================================================
Detects six categories of data leakage in ML training pipelines.

Leakage categories:
  1. Temporal overlap     — train/val date intersection
  2. Anchor leakage       — event window appears in both splits
  3. Sequence overlap     — rolling TCN windows overlap across splits
  4. High-similarity      — PCA-based positive sample duplication
  5. Future feature       — features derived from future observations
  6. Duplicate hashes     — identical feature vectors in both splits

Output:
  LeakageReport dataclass → JSON-serialisable
  Leakage score 0–100 → LOW / MODERATE / HIGH / CRITICAL
  Raises LeakageError if score exceeds abort threshold.

Usage:
    from app.ml.validation.leakage_audit import LeakageAuditor

    auditor = LeakageAuditor()
    report  = auditor.audit(
        X_train=X_tr, X_val=X_ev,
        y_train=y_tr, y_val=y_ev,
        dates_train=df_tr["date"], dates_val=df_ev["date"],
        feature_names=feat_names,
        city_slug="islamabad",
        event_anchors=["2010-07-29", "2020-08-27"],
        seq_len=30,
    )
    report.save("leakage_report_islamabad.json")
    report.print_summary()
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────

SCORE_THRESHOLDS = {
    "LOW":      (0,  25),
    "MODERATE": (25, 50),
    "HIGH":     (50, 75),
    "CRITICAL": (75, 101),
}

ABORT_THRESHOLD = 75    # Fail training if leakage score >= this


class LeakageError(RuntimeError):
    """Raised when leakage score exceeds the abort threshold."""


# ── Per-category finding ──────────────────────────────────────────────────

@dataclass
class LeakageFinding:
    category:    str
    severity:    str        # CLEAN / WARNING / VIOLATION
    score_delta: float      # contribution to total score (0–20 per category)
    details:     Dict[str, Any] = field(default_factory=dict)
    message:     str = ""


# ── Report ────────────────────────────────────────────────────────────────

@dataclass
class LeakageReport:
    city_slug:    str
    audited_at:   str
    total_score:  float
    category:     str            # LOW / MODERATE / HIGH / CRITICAL
    abort:        bool
    findings:     List[LeakageFinding]
    summary:      Dict[str, Any] = field(default_factory=dict)

    # ── I/O ──────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info("LeakageReport saved -> %s", path)

    def print_summary(self) -> None:
        sep = "-" * 60
        print(f"\n{sep}")
        print(f"  LEAKAGE AUDIT -- {self.city_slug.upper()}")
        print(f"  Score : {self.total_score:.1f} / 100  [{self.category}]")
        print(f"  Abort : {self.abort}")
        print(sep)
        for f in self.findings:
            icon = "[OK]" if f.severity == "CLEAN" else ("[!]" if f.severity == "WARNING" else "[X]")
            print(f"  {icon}  [{f.category:<22}]  {f.severity:<10}  +{f.score_delta:.0f}  {f.message}")
        print(sep + "\n")


# ── Auditor ───────────────────────────────────────────────────────────────

class LeakageAuditor:
    """
    Automated leakage detection for HydroGuard-AI training splits.

    Call audit() after splitting data; before fitting any model.
    """

    def audit(
        self,
        X_train:        np.ndarray,
        X_val:          np.ndarray,
        y_train:        np.ndarray,
        y_val:          np.ndarray,
        dates_train:    Optional[Any]       = None,   # pd.Series
        dates_val:      Optional[Any]       = None,   # pd.Series
        feature_names:  Optional[List[str]] = None,
        city_slug:      str                 = "unknown",
        event_anchors:  Optional[List[str]] = None,
        seq_len:        int                 = 30,
        abort_threshold: float              = ABORT_THRESHOLD,
    ) -> LeakageReport:
        """
        Run all six leakage checks and return a consolidated report.

        Parameters
        ----------
        X_train, X_val  : preprocessed feature arrays
        y_train, y_val  : binary labels
        dates_train/val : pd.Series of dates aligned to rows
        feature_names   : list of feature column names
        city_slug       : city identifier for report
        event_anchors   : list of ISO date strings for known extreme events
        seq_len         : TCN rolling window length (for sequence overlap)
        abort_threshold : score above which LeakageError is raised
        """
        findings: List[LeakageFinding] = []

        findings.append(self._check_temporal_overlap(dates_train, dates_val))
        findings.append(self._check_anchor_leakage(dates_train, dates_val,
                                                    y_train, y_val,
                                                    event_anchors))
        findings.append(self._check_sequence_overlap(dates_train, dates_val, seq_len))
        findings.append(self._check_high_similarity(X_train, X_val, y_train, y_val))
        findings.append(self._check_future_features(feature_names or []))
        findings.append(self._check_duplicate_hashes(X_train, X_val, y_train, y_val))

        total_score = float(sum(f.score_delta for f in findings))
        total_score = min(max(total_score, 0.0), 100.0)

        category = "LOW"
        for cat, (lo, hi) in SCORE_THRESHOLDS.items():
            if lo <= total_score < hi:
                category = cat
                break

        abort = total_score >= abort_threshold

        # Date spans
        tr_span = _date_span(dates_train)
        ev_span = _date_span(dates_val)

        summary = {
            "city_slug":      city_slug,
            "train_rows":     int(len(X_train)),
            "val_rows":       int(len(X_val)),
            "train_pos":      int((y_train == 1).sum()),
            "val_pos":        int((y_val   == 1).sum()),
            "train_date_span": tr_span,
            "val_date_span":   ev_span,
            "n_features":     int(X_train.shape[1]),
            "seq_len":        seq_len,
        }

        report = LeakageReport(
            city_slug   = city_slug,
            audited_at  = datetime.now(timezone.utc).isoformat(),
            total_score = round(total_score, 2),
            category    = category,
            abort       = abort,
            findings    = findings,
            summary     = summary,
        )

        report.print_summary()

        if abort:
            raise LeakageError(
                f"[{city_slug}] Leakage score {total_score:.1f} ≥ "
                f"abort threshold {abort_threshold}. "
                "Fix data pipeline before retraining. "
                "Use LeakageAuditor(..., abort_threshold=100) to override."
            )

        return report

    # ── Category 1: Temporal Overlap ──────────────────────────────

    def _check_temporal_overlap(
        self,
        dates_train: Optional[Any],
        dates_val:   Optional[Any],
    ) -> LeakageFinding:
        cat = "temporal_overlap"
        if dates_train is None or dates_val is None:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=5.0,
                message="Dates unavailable — cannot verify temporal separation.",
            )
        try:
            import pandas as pd
            tr = set(pd.to_datetime(dates_train).dt.date.tolist())
            ev = set(pd.to_datetime(dates_val).dt.date.tolist())
            overlap = tr & ev
            if not overlap:
                return LeakageFinding(
                    category=cat, severity="CLEAN", score_delta=0.0,
                    details={"overlap_days": 0},
                    message="Train and val date sets are disjoint.",
                )
            pct = round(100 * len(overlap) / max(len(ev), 1), 1)
            return LeakageFinding(
                category=cat, severity="VIOLATION", score_delta=min(20.0, pct * 2),
                details={"overlap_days": len(overlap), "overlap_pct_of_val": pct,
                         "sample_overlap": sorted([str(d) for d in list(overlap)[:5]])},
                message=f"{len(overlap)} date(s) appear in both splits ({pct}% of val).",
            )
        except Exception as exc:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=5.0,
                message=f"Temporal overlap check failed: {exc}",
            )

    # ── Category 2: Anchor Leakage ────────────────────────────────

    def _check_anchor_leakage(
        self,
        dates_train:   Optional[Any],
        dates_val:     Optional[Any],
        y_train:       np.ndarray,
        y_val:         np.ndarray,
        event_anchors: Optional[List[str]],
    ) -> LeakageFinding:
        cat = "anchor_leakage"
        if not event_anchors:
            return LeakageFinding(
                category=cat, severity="CLEAN", score_delta=0.0,
                message="No event anchors provided — skipped.",
            )
        if dates_train is None or dates_val is None:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=3.0,
                message="Dates unavailable — cannot verify anchor isolation.",
            )
        try:
            import pandas as pd
            tr_dates = pd.to_datetime(dates_train).dt.date
            ev_dates = pd.to_datetime(dates_val).dt.date
            violations = []
            for event_str in event_anchors:
                event_dt = pd.Timestamp(event_str).date()
                # Check if any anchor-window row appears in both splits
                for delta in range(-2, 3):   # PRE_EVENT_WINDOW=2
                    d_check = (pd.Timestamp(event_str) +
                               pd.Timedelta(days=delta)).date()
                    in_tr   = (tr_dates == d_check).any()
                    in_ev   = (ev_dates == d_check).any()
                    if in_tr and in_ev:
                        violations.append({
                            "event": event_str,
                            "date":  str(d_check),
                            "delta": delta,
                        })
            if not violations:
                return LeakageFinding(
                    category=cat, severity="CLEAN", score_delta=0.0,
                    details={"events_checked": len(event_anchors)},
                    message="All event anchor windows are isolated to one split.",
                )
            return LeakageFinding(
                category=cat, severity="VIOLATION",
                score_delta=min(20.0, len(violations) * 4.0),
                details={"violations": violations[:10]},
                message=(f"{len(violations)} anchor-window date(s) appear in "
                         "both train and val."),
            )
        except Exception as exc:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=3.0,
                message=f"Anchor leakage check failed: {exc}",
            )

    # ── Category 3: Sequence Overlap ──────────────────────────────

    def _check_sequence_overlap(
        self,
        dates_train: Optional[Any],
        dates_val:   Optional[Any],
        seq_len:     int,
    ) -> LeakageFinding:
        cat = "sequence_overlap"
        if dates_train is None or dates_val is None:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=2.0,
                message="Dates unavailable — cannot verify sequence window separation.",
            )
        try:
            import pandas as pd
            tr_dates = pd.to_datetime(dates_train).sort_values()
            ev_dates = pd.to_datetime(dates_val).sort_values()
            if tr_dates.empty or ev_dates.empty:
                return LeakageFinding(
                    category=cat, severity="WARNING", score_delta=2.0,
                    message="Empty date series.",
                )
            # The last `seq_len` rows of train form the context for the first
            # rows of val. This is structurally correct (past → future) as long
            # as no val date precedes the training cutoff.
            train_cutoff = tr_dates.max()
            val_start    = ev_dates.min()
            if val_start <= train_cutoff:
                overlap_days = int((train_cutoff - val_start).days)
                return LeakageFinding(
                    category=cat, severity="VIOLATION",
                    score_delta=min(15.0, overlap_days * 2.0),
                    details={"train_max": str(train_cutoff.date()),
                             "val_min":   str(val_start.date()),
                             "overlap_days": overlap_days},
                    message=(f"Val starts {overlap_days} day(s) before train ends — "
                             "sequence windows may span split boundary."),
                )
            gap_days = int((val_start - train_cutoff).days)
            severity = "CLEAN" if gap_days >= 1 else "WARNING"
            return LeakageFinding(
                category=cat, severity=severity, score_delta=0.0,
                details={"train_max": str(train_cutoff.date()),
                         "val_min":   str(val_start.date()),
                         "gap_days":  gap_days},
                message=f"Sequence gap between train end and val start: {gap_days} day(s).",
            )
        except Exception as exc:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=2.0,
                message=f"Sequence overlap check failed: {exc}",
            )

    # ── Category 4: High-Similarity Leakage ───────────────────────

    def _check_high_similarity(
        self,
        X_train: np.ndarray,
        X_val:   np.ndarray,
        y_train: np.ndarray,
        y_val:   np.ndarray,
        n_components: int = 8,
        sim_threshold: float = 0.97,
    ) -> LeakageFinding:
        """
        PCA-based cosine similarity between positive train and val samples.
        High mean cosine similarity indicates possible cluster duplication.
        """
        cat = "high_similarity"
        try:
            from sklearn.decomposition import PCA
            from sklearn.preprocessing import normalize

            pos_tr = X_train[y_train == 1]
            pos_ev = X_val[y_val   == 1]

            if len(pos_tr) < 2 or len(pos_ev) < 2:
                return LeakageFinding(
                    category=cat, severity="CLEAN", score_delta=0.0,
                    message="Too few positive samples for similarity check.",
                )

            # Reduce dimensionality then compute cosine similarity
            n_comp = min(n_components, X_train.shape[1], len(pos_tr), len(pos_ev))
            pca    = PCA(n_components=n_comp, random_state=42)
            all_X  = np.vstack([pos_tr, pos_ev])
            pca.fit(all_X)
            tr_emb = normalize(pca.transform(pos_tr))
            ev_emb = normalize(pca.transform(pos_ev))

            # Max cosine similarity: each val positive vs all train positives
            sim_matrix = tr_emb @ ev_emb.T      # (n_tr_pos, n_ev_pos)
            max_sims   = sim_matrix.max(axis=0) # (n_ev_pos,)
            mean_max   = float(np.mean(max_sims))
            frac_high  = float(np.mean(max_sims >= sim_threshold))

            if frac_high > 0.5:
                delta = min(15.0, frac_high * 20.0)
                return LeakageFinding(
                    category=cat, severity="VIOLATION", score_delta=delta,
                    details={"mean_max_cosine": round(mean_max, 4),
                             "frac_above_threshold": round(frac_high, 4),
                             "threshold": sim_threshold,
                             "n_pca_components": n_comp},
                    message=(f"{frac_high*100:.1f}% of val positives have "
                             f"cosine similarity ≥ {sim_threshold} with a train positive."),
                )
            if frac_high > 0.2:
                return LeakageFinding(
                    category=cat, severity="WARNING", score_delta=5.0,
                    details={"mean_max_cosine": round(mean_max, 4),
                             "frac_above_threshold": round(frac_high, 4)},
                    message=(f"Moderate similarity: {frac_high*100:.1f}% of val "
                             "positives near-duplicate a train positive."),
                )
            return LeakageFinding(
                category=cat, severity="CLEAN", score_delta=0.0,
                details={"mean_max_cosine": round(mean_max, 4)},
                message=f"Positive sample similarity is acceptable (mean={mean_max:.3f}).",
            )
        except Exception as exc:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=2.0,
                message=f"Similarity check failed: {exc}",
            )

    # ── Category 5: Future Feature Leakage ────────────────────────

    def _check_future_features(
        self,
        feature_names: List[str],
    ) -> LeakageFinding:
        """
        Scan feature names for patterns that typically indicate future leakage.
        Flags: centered rolling windows, forward fills, future deltas.
        """
        cat = "future_feature_leakage"
        suspicious_patterns = [
            ("_future",   "explicit future label"),
            ("_next_",    "forward-looking delta"),
            ("_fwd_",     "forward feature"),
            ("_centered", "centered (non-causal) rolling window"),
            ("_lead_",    "lead-time feature using future data"),
        ]
        violations = []
        for feat in feature_names:
            for pattern, reason in suspicious_patterns:
                if pattern in feat.lower():
                    violations.append({"feature": feat, "reason": reason})

        # Physics features audit — all v3.3 features are causal by design
        causal_ok = [
            "pressure_delta", "humidity_delta", "rain_rate", "rain_accumulation",
            "cloud_jump", "pressure_accel", "humidity_accel",
            "pressure_volatility", "humidity_volatility", "prcp_trend",
            "atm_instability", "moisture_flux", "tdew_spread",
        ]
        non_causal_features = [
            f for f in feature_names
            if not any(ok in f for ok in causal_ok)
            and f not in {"prcp", "humidity", "pressure", "cloud_cover",
                          "tmin", "tmax", "tavg", "temp_range", "dew_point",
                          "wspd", "month", "day", "dayofweek", "is_weekend",
                          "is_monsoon_month", "vulnerability", "is_flash_flood_prone",
                          "prcp_climo_pct", "humidity_climo_pct",
                          "ae_percentile", "tcn_percentile", "ae_variance",
                          "tcn_variance", "pressure_delta_3h", "pressure_delta_6h",
                          "rain_rate_1h", "rain_accumulation_3h", "prcp_trend_6d"}
            and not f.startswith("city_slug_")
            and not f.startswith("season_")
        ]

        if violations:
            return LeakageFinding(
                category=cat, severity="VIOLATION",
                score_delta=min(20.0, len(violations) * 10.0),
                details={"violations": violations},
                message=(f"{len(violations)} feature(s) contain future-leakage patterns: "
                         f"{[v['feature'] for v in violations]}"),
            )
        if non_causal_features:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=3.0,
                details={"unrecognised_features": non_causal_features[:10]},
                message=(f"{len(non_causal_features)} unrecognised feature(s) — "
                         "verify they are causal."),
            )
        return LeakageFinding(
            category=cat, severity="CLEAN", score_delta=0.0,
            details={"n_features_checked": len(feature_names)},
            message="All features pass causal pattern check.",
        )

    # ── Category 6: Duplicate Hashes ──────────────────────────────

    def _check_duplicate_hashes(
        self,
        X_train: np.ndarray,
        X_val:   np.ndarray,
        y_train: np.ndarray,
        y_val:   np.ndarray,
    ) -> LeakageFinding:
        """Hash each row; flag rows that appear in both splits."""
        cat = "duplicate_hashes"
        try:
            def _hash_rows(X: np.ndarray) -> List[str]:
                return [
                    hashlib.md5(row.astype(np.float32).tobytes()).hexdigest()
                    for row in X
                ]

            tr_hashes = set(_hash_rows(X_train))
            ev_hashes = _hash_rows(X_val)
            dup_count = sum(1 for h in ev_hashes if h in tr_hashes)
            dup_frac  = dup_count / max(len(ev_hashes), 1)

            if dup_frac > 0.10:
                return LeakageFinding(
                    category=cat, severity="VIOLATION",
                    score_delta=min(15.0, dup_frac * 30.0),
                    details={"n_duplicates": dup_count,
                             "dup_fraction": round(dup_frac, 4)},
                    message=(f"{dup_count} val rows ({dup_frac*100:.1f}%) are "
                             "exact duplicates of train rows."),
                )
            if dup_frac > 0.02:
                return LeakageFinding(
                    category=cat, severity="WARNING", score_delta=4.0,
                    details={"n_duplicates": dup_count,
                             "dup_fraction": round(dup_frac, 4)},
                    message=f"{dup_count} near-duplicate rows detected ({dup_frac*100:.1f}%).",
                )
            return LeakageFinding(
                category=cat, severity="CLEAN", score_delta=0.0,
                details={"n_duplicates": dup_count},
                message=f"No significant duplicate sequences ({dup_count} minor matches).",
            )
        except Exception as exc:
            return LeakageFinding(
                category=cat, severity="WARNING", score_delta=2.0,
                message=f"Hash check failed: {exc}",
            )


# ── Utility ───────────────────────────────────────────────────────────────

def _date_span(dates: Optional[Any]) -> Optional[str]:
    if dates is None:
        return None
    try:
        import pandas as pd
        ts = pd.to_datetime(dates)
        return f"{ts.min().date()} to {ts.max().date()}"
    except Exception:
        return None
