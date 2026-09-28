from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import joblib
import pandas as pd

from .features import FEATURES, MIN_HISTORY_DAYS, TargetConfig, feature_frame
from .train import ARTIFACT, REPORT


class InsufficientHistory(Exception):
    pass


def load_artifact(models_dir: Path):
    path = models_dir / ARTIFACT
    return joblib.load(path) if path.exists() else None


def load_report(models_dir: Path) -> dict | None:
    path = models_dir / REPORT
    return json.loads(path.read_text()) if path.exists() else None


def predict_break_risk(artifact: dict, precip: pd.Series, as_of: date) -> dict:
    """Uses only rainfall on days <= as_of (the series is explicitly truncated). Works fully offline."""
    ts = pd.Timestamp(as_of)
    s = precip[pd.DatetimeIndex(pd.to_datetime(precip.index)) <= ts]
    if len(s) < MIN_HISTORY_DAYS:
        raise InsufficientHistory(f"Need at least {MIN_HISTORY_DAYS} days of history up to {as_of}; have {len(s)}.")
    feats = feature_frame(s, TargetConfig(**{**artifact["target_cfg"]}))
    if ts not in feats.index:
        raise InsufficientHistory(f"No rainfall recorded for {as_of}; latest available is {s.index.max().date()}.")
    row = feats.loc[[ts], FEATURES]
    if row.isna().any(axis=None):
        raise InsufficientHistory("Recent rainfall has gaps; cannot compute features for this date.")
    prob = float(artifact["model"].predict_proba(row)[0, 1])
    cfg = artifact["target_cfg"]
    return {"as_of": as_of.isoformat(), "probability": prob, "model": artifact["model_name"],
            "horizon_days": cfg["horizon_days"],
            "event": f"a run of >= {cfg['dry_len']} consecutive days with rain < {cfg['dry_mm']} mm "
                     f"within the next {cfg['horizon_days']} days",
            "basis": "historical-pattern-based estimate from local past rainfall only (no weather-model forecast)"}
