"""Time-based training/evaluation with simple baselines. No random splits: whole years are held out."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURES, TargetConfig

ARTIFACT, REPORT = "break_risk.joblib", "evaluation.json"


class ClimatologyBaseline:
    """Base rate of the target by 10-day bin of the year (fit on training years only)."""
    def fit(self, df):
        self.global_ = float(df["y"].mean())
        self.rate_ = df.groupby((df["doy"] - 1) // 10)["y"].mean().to_dict()
        return self

    def predict_proba(self, df):
        return ((df["doy"] - 1) // 10).map(self.rate_).fillna(self.global_).to_numpy(dtype=float)


class DryRunBaseline:
    """Base rate conditioned on the current dry-run length (0,1,2,3,4,5+)."""
    def fit(self, df):
        self.global_ = float(df["y"].mean())
        self.rate_ = df.groupby(df["dry_run"].clip(upper=5))["y"].mean().to_dict()
        return self

    def predict_proba(self, df):
        return df["dry_run"].clip(upper=5).map(self.rate_).fillna(self.global_).to_numpy(dtype=float)


def split_years(years, n_val: int, n_test: int, min_train: int = 3):
    ys = sorted(set(int(y) for y in years))
    if len(ys) < n_val + n_test + min_train:
        raise ValueError(f"Need at least {n_val + n_test + min_train} years of data "
                         f"(train>={min_train}, val={n_val}, test={n_test}); have {len(ys)}.")
    return ys[:len(ys) - n_val - n_test], ys[len(ys) - n_val - n_test:len(ys) - n_test], ys[len(ys) - n_test:]


def score(y, p) -> dict:
    y, p = np.asarray(y, float), np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    out = {"n": int(len(y)), "base_rate": float(y.mean()),
           "brier": float(np.mean((p - y) ** 2)),
           "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
           "roc_auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None}
    return out


def _bss(y, p, p_clim) -> float:
    b, bc = np.mean((p - y) ** 2), np.mean((p_clim - y) ** 2)
    return float(1 - b / bc) if bc > 0 else float("nan")


def bootstrap_bss(test: pd.DataFrame, p_model, p_clim, n_boot=500, seed=0):
    """Year-block bootstrap of the Brier skill score vs climatology. None if <3 test years."""
    years = test["year"].to_numpy()
    uniq = np.unique(years)
    if len(uniq) < 3:
        return None
    idx = {y: np.where(years == y)[0] for y in uniq}
    y_all = test["y"].to_numpy(float)
    rng, vals = np.random.default_rng(seed), []
    for _ in range(n_boot):
        pick = np.concatenate([idx[y] for y in rng.choice(uniq, len(uniq), replace=True)])
        vals.append(_bss(y_all[pick], np.asarray(p_model)[pick], np.asarray(p_clim)[pick]))
    lo, hi = np.nanpercentile(vals, [2.5, 97.5])
    return {"low": float(lo), "high": float(hi), "n_years": int(len(uniq)), "method": "year-block bootstrap, 95%"}


def _candidates():
    return {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "random_forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=20, random_state=0, n_jobs=1),
    }


def train_and_evaluate(dataset: pd.DataFrame, cfg: TargetConfig, n_val: int, n_test: int,
                       provenance: dict, out_dir: Path | None = None, n_boot: int = 500) -> dict:
    tr_y, va_y, te_y = split_years(dataset["year"], n_val, n_test)
    tr, va, te = (dataset[dataset["year"].isin(g)] for g in (tr_y, va_y, te_y))
    if tr["y"].nunique() < 2:
        raise ValueError("Training data contains only one class; cannot fit a classifier.")

    # model selection on the validation years (train-only fits)
    val_scores = {}
    for name, m in _candidates().items():
        m.fit(tr[FEATURES], tr["y"])
        val_scores[name] = score(va["y"], m.predict_proba(va[FEATURES])[:, 1])["brier"]
    best = min(val_scores, key=val_scores.get)

    # refit everything on train+val, evaluate once on the untouched test years
    trva = pd.concat([tr, va])
    final = _candidates()[best].fit(trva[FEATURES], trva["y"])
    clim, dryrun = ClimatologyBaseline().fit(trva), DryRunBaseline().fit(trva)
    p_model = final.predict_proba(te[FEATURES])[:, 1]
    p_clim, p_dry = clim.predict_proba(te), dryrun.predict_proba(te)
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": {**asdict(cfg), "definition": "at least dry_len consecutive days with rain < dry_mm "
                   "inside days t+1..t+horizon_days"},
        "intended_use": "historical-pattern-based local dry-spell risk estimate from past rainfall only; "
                        "NOT a forecast-driven prediction and NOT operationally validated",
        "data_provenance": provenance,
        "split_years": {"train": tr_y, "validation": va_y, "test": te_y},
        "validation_brier_by_model": val_scores, "selected_model": best,
        "test": {
            "model": score(te["y"], p_model),
            "baseline_climatology": score(te["y"], p_clim),
            "baseline_dry_run_conditioned": score(te["y"], p_dry),
            "brier_skill_vs_climatology": _bss(te["y"].to_numpy(float), p_model, p_clim),
            "brier_skill_ci": bootstrap_bss(te, p_model, p_clim, n_boot),
        },
        "features": FEATURES,
        "caveats": ["Test-year rows within a year are autocorrelated; effective sample size is smaller than n.",
                    "Skill on reanalysis rainfall does not imply skill against gauge observations."],
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": final, "features": FEATURES, "target_cfg": asdict(cfg), "model_name": best,
                     "trained_at_utc": report["created_at_utc"]}, out_dir / ARTIFACT)
        (out_dir / REPORT).write_text(json.dumps(report, indent=2))
    return report
