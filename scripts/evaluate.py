#!/usr/bin/env python3
"""
HydroGuard-AI -- Per-City Evaluation Report  v2.0
=================================================
Reads saved model artifacts and produces a complete metric report for every
trained city.  Does NOT load TensorFlow or re-run training.

Metric sources
--------------
  AUC / PR-AUC / ECE / Brier
      Loaded from training_metrics.json (TEST split, unbiased).
      Recomputed from test_data.npz / cal_data.npz if the JSON keys are absent.

  Precision / Recall / F1
      Computed from test_data.npz (unbiased TEST split) when present.
      Falls back to cal_data.npz for existing models trained before v3.5.1
      (mildly in-distribution for threshold; the calibrated domain is identical).

  AlertTier thresholds
      Always derived from cal_data.npz via AlertTierClassifier.from_cal_data().

Operational semantics
---------------------
  ADVISORY  recall-priority:  threshold at recall >= 85%  -- in-app notification
  ALERT     precision-priority: threshold at precision >= 65% -- push notification
  Brier     probabilistic quality; lower = better; no threshold involved
  F1        balance metric reported for academic completeness; not the primary
            optimisation target of this architecture

Usage
-----
  python scripts/evaluate.py
  python scripts/evaluate.py --models-dir backend/saved_models/city_models
  python scripts/evaluate.py --city islamabad
  python scripts/evaluate.py --output backend/evaluation_results
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
BACKEND   = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# Stub dotenv so the app imports don't fail outside Docker
import types as _t
_dotenv = _t.ModuleType("dotenv"); _dotenv.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", _dotenv)

import os
os.environ.setdefault("JWT_SECRET_KEY", "evaluate-script-key")

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Formatting helpers ────────────────────────────────────────────────────────

def _f(v, fmt=".4f") -> str:
    if v is None:
        return "N/A"
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return "N/A"


def _banner(title: str, width: int = 100) -> None:
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="HydroGuard-AI per-city evaluation report"
    )
    parser.add_argument(
        "--models-dir", "-m",
        default=str(BACKEND / "saved_models/city_models"),
        help="Directory containing per-city model subdirectories",
    )
    parser.add_argument(
        "--city", "-c",
        default=None,
        help="Evaluate a single city only (e.g. islamabad)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Directory to write evaluation_report.json (default: models-dir parent)",
    )
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    if not models_dir.exists():
        logger.error("models-dir not found: %s", models_dir)
        sys.exit(1)

    from app.ml.evaluation.city_metrics import CityEvaluator

    evaluator = CityEvaluator()

    # Discover city directories
    if args.city:
        candidates = [models_dir / args.city.lower()]
    else:
        candidates = sorted(
            p for p in models_dir.iterdir()
            if p.is_dir() and not p.name.endswith((".tmp", ".bak"))
        )

    reports = []
    for city_dir in candidates:
        if not city_dir.is_dir():
            logger.warning("City directory not found: %s", city_dir)
            continue
        logger.info("Evaluating %s ...", city_dir.name)
        report = evaluator.evaluate(city_dir)
        if report is None:
            logger.warning("[%s] Skipped -- missing artifacts", city_dir.name)
            continue
        reports.append(report)

    if not reports:
        logger.error("No cities could be evaluated.")
        sys.exit(1)

    # ── Print report ──────────────────────────────────────────────────────────
    _banner("HydroGuard-AI v3.5  PER-CITY EVALUATION REPORT")

    # Table 1: probabilistic metrics
    print(f"\n  PROBABILISTIC METRICS  (threshold-free; evaluate calibrated probability quality)")
    print(f"  {'City':<14} {'Split':<6} {'Rows':>6}  {'Pos%':>5}  "
          f"{'AUC':>7}  {'PR-AUC':>7}  {'ECE':>7}  {'Brier':>7}")
    print("  " + "-" * 80)
    for r in reports:
        print(
            f"  {r.city_slug:<14} {r.eval_split:<6} {r.n_rows:>6}  "
            f"{r.positive_rate*100:>4.1f}%  "
            f"{_f(r.auc):>7}  {_f(r.pr_auc):>7}  "
            f"{_f(r.ece):>7}  {_f(r.brier_score):>7}"
        )

    # Table 2: ADVISORY tier
    print(f"\n  ADVISORY TIER  -- recall-priority  (threshold derived at recall >= 85%)")
    print(f"  {'City':<14} {'Adv.Thr':>8}  {'Precision':>10}  {'Recall':>8}  "
          f"{'F1':>8}  {'#Alerts':>8}  {'ThreshSrc'}")
    print("  " + "-" * 88)
    for r in reports:
        adv = r.advisory
        print(
            f"  {r.city_slug:<14} {_f(adv.threshold):>8}  "
            f"{_f(adv.precision):>10}  {_f(adv.recall):>8}  "
            f"{_f(adv.f1):>8}  {adv.n_predicted_positive:>8}  "
            f"{r.threshold_source}"
        )

    # Table 3: ALERT tier
    print(f"\n  ALERT TIER  -- precision-priority  (threshold derived at precision >= 65%)")
    print(f"  F1 is a balance metric reported for academic completeness -- "
          f"not the primary optimisation target.")
    print(f"  {'City':<14} {'Alrt.Thr':>8}  {'Precision':>10}  {'Recall':>8}  "
          f"{'F1':>8}  {'#Alerts':>8}")
    print("  " + "-" * 70)
    for r in reports:
        alrt = r.alert
        print(
            f"  {r.city_slug:<14} {_f(alrt.threshold):>8}  "
            f"{_f(alrt.precision):>10}  {_f(alrt.recall):>8}  "
            f"{_f(alrt.f1):>8}  {alrt.n_predicted_positive:>8}"
        )

    print("\n" + "=" * 100)
    print("\n  KEY:")
    print("  Split      = test  -> metrics from held-out TEST set (unbiased, preferred)")
    print("               cal   -> metrics from CAL set (existing models; same calibrated domain)")
    print("  AUC        = ROC area under curve on calibrated probabilities")
    print("  PR-AUC     = Precision-Recall AUC (more informative for imbalanced classes)")
    print("  ECE        = Expected Calibration Error (calibrator fitted on CAL, measured on TEST)")
    print("  Brier      = Brier Score -- probabilistic quality; lower is better (0 = perfect)")
    print("  Adv.Thr    = advisory threshold (lowest thr achieving recall >= 85%)")
    print("  Alrt.Thr   = alert threshold (highest thr achieving precision >= 65%)")
    print("  ThreshSrc  = derived (from PR curve) | default_* (fallback; see AlertTierClassifier)")
    print("  F1         = balance metric; not used for threshold selection in this architecture\n")

    # ── Serialize JSON report ─────────────────────────────────────────────────
    output_dir = Path(args.output) if args.output else models_dir.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "evaluation_report.json"

    json_payload = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "v3.5.1",
        "models_dir":      str(models_dir),
        "cities":          [r.to_dict() for r in reports],
    }
    report_path.write_text(json.dumps(json_payload, indent=2, default=str))
    logger.info("Evaluation report written -> %s", report_path)


if __name__ == "__main__":
    main()
