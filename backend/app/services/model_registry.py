"""
HydroGuard-AI — Model Registry
================================
Full-provenance registry for every trained city model.

Each entry records:
  - architecture and hyperparameters
  - training / validation / test date windows
  - dataset SHA256 fingerprint
  - git commit hash (if available)
  - feature schema (names, types, weights)
  - performance metrics
  - calibration parameters
  - promotion timestamp and status

The registry is persisted as:
  backend/saved_models/registry.json

Usage:
    from app.services.model_registry import model_registry

    # Register a newly trained model
    model_registry.register(city_slug, entry)

    # Get latest entry for a city
    entry = model_registry.get_latest(city_slug)

    # Get full history
    history = model_registry.get_history(city_slug)
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from app.core.config import MODELS_DIR

logger = logging.getLogger(__name__)

REGISTRY_PATH = MODELS_DIR / "registry.json"

# ──────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────

def _git_commit() -> str:
    """Return the current HEAD commit hash or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _sha256_file(path: Path) -> str:
    """SHA256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return "unknown"


# ──────────────────────────────────────────────────────────
#  Registry
# ──────────────────────────────────────────────────────────

class ModelRegistry:
    """
    Thread-safe persistent registry of trained city model metadata.
    """

    def __init__(self, registry_path: Path = REGISTRY_PATH):
        self._path   = registry_path
        self._lock   = Lock()
        self._data:  Dict[str, List[Dict[str, Any]]] = {}  # slug → list of entries
        self._load()

    # ── Persistence ───────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info("Model registry loaded: %d city entries", len(self._data))
            except Exception as exc:
                logger.warning("Could not load model registry: %s — starting fresh", exc)
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, default=str)

    # ── Public API ─────────────────────────────────────────

    def register(
        self,
        city_slug: str,
        *,
        architecture:        str,
        input_dim:           int,
        feature_schema:      Dict[str, Any],
        train_date_start:    str,
        train_date_end:      str,
        val_date_start:      str,
        val_date_end:        str,
        dataset_sha256:      str,
        dataset_path:        str,
        n_train:             int,
        n_val:               int,
        ae_val_loss:         float,
        lstm_val_loss:       Optional[float],
        ae_threshold_p99:    float,
        sequence_length:     int,
        epochs_ae:           int,
        epochs_lstm:         Optional[int],
        hyperparameters:     Dict[str, Any],
        metrics:             Optional[Dict[str, Any]] = None,
        calibration_params:  Optional[Dict[str, Any]] = None,
        notes:               str = "",
    ) -> Dict[str, Any]:
        """
        Register a newly trained model in the registry.
        Returns the entry dict.
        """
        entry: Dict[str, Any] = {
            "city_slug":          city_slug,
            "version":            self._next_version(city_slug),
            "promoted_at":        datetime.now(timezone.utc).isoformat(),
            "status":             "active",
            "git_commit":         _git_commit(),
            "architecture":       architecture,
            "input_dim":          input_dim,
            "sequence_length":    sequence_length,
            "feature_schema":     feature_schema,
            "train_date_start":   train_date_start,
            "train_date_end":     train_date_end,
            "val_date_start":     val_date_start,
            "val_date_end":       val_date_end,
            "dataset_sha256":     dataset_sha256,
            "dataset_path":       dataset_path,
            "n_train":            n_train,
            "n_val":              n_val,
            "ae_val_loss":        round(ae_val_loss, 6),
            "lstm_val_loss":      round(lstm_val_loss, 6) if lstm_val_loss is not None else None,
            "ae_threshold_p99":   round(ae_threshold_p99, 6),
            "epochs_ae":          epochs_ae,
            "epochs_lstm":        epochs_lstm,
            "hyperparameters":    hyperparameters,
            "metrics":            metrics or {},
            "calibration_params": calibration_params or {},
            "notes":              notes,
        }

        with self._lock:
            if city_slug not in self._data:
                self._data[city_slug] = []
            # Mark previous entry as archived
            for prev in self._data[city_slug]:
                if prev.get("status") == "active":
                    prev["status"] = "archived"
            self._data[city_slug].append(entry)
            self._save()

        logger.info(
            "[%s] Registry entry v%s — AE val_loss=%.5f | input_dim=%d",
            city_slug, entry["version"], ae_val_loss, input_dim,
        )
        return entry

    def get_latest(self, city_slug: str) -> Optional[Dict[str, Any]]:
        """Return the most recent (active) registry entry for a city."""
        with self._lock:
            entries = self._data.get(city_slug, [])
        for entry in reversed(entries):
            if entry.get("status") == "active":
                return entry
        return entries[-1] if entries else None

    def get_history(self, city_slug: str) -> List[Dict[str, Any]]:
        """Return all registry entries for a city (newest first)."""
        with self._lock:
            return list(reversed(self._data.get(city_slug, [])))

    def list_cities(self) -> List[str]:
        """All city slugs that have at least one registry entry."""
        with self._lock:
            return list(self._data.keys())

    def all_entries(self) -> Dict[str, Dict[str, Any]]:
        """Return latest active entry for every city."""
        result = {}
        for slug in self.list_cities():
            entry = self.get_latest(slug)
            if entry:
                result[slug] = entry
        return result

    def summary(self) -> Dict[str, Any]:
        """High-level registry summary for the /health and admin endpoints."""
        entries = self.all_entries()
        return {
            "total_registered": len(entries),
            "cities":           list(entries.keys()),
            "entries": {
                slug: {
                    "version":    e.get("version"),
                    "promoted_at": e.get("promoted_at"),
                    "architecture": e.get("architecture"),
                    "ae_val_loss": e.get("ae_val_loss"),
                    "n_train":     e.get("n_train"),
                }
                for slug, e in entries.items()
            },
        }

    # ── Internal ──────────────────────────────────────────

    def _next_version(self, city_slug: str) -> int:
        existing = self._data.get(city_slug, [])
        versions = [e.get("version", 0) for e in existing if isinstance(e.get("version"), int)]
        return (max(versions) + 1) if versions else 1


# ── Singleton ─────────────────────────────────────────────
model_registry = ModelRegistry()
