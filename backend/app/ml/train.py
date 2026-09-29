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


def required_years(n_val: int = 5, n_test: int = 8, min_train: int = 3) -> int:
    """Minimum number of distinct years split_years() needs for this chronological split."""
    return n_val + n_test + min_train


def split_years(years, n_val: int, n_test: int, min_train: int = 3):
    if n_val < 1 or n_test < 1 or min_train < 1:
        raise ValueError(f"n_val, n_test and min_train must each be >= 1 "
                         f"(got n_val={n_val}, n_test={n_test}, min_train={min_train}).")
    ys = sorted(set(int(y) for y in years))
    required = required_years(n_val, n_test, min_train)
    if len(ys) < required:
        raise ValueError(f"Need at least {required} years of data "
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


def _num(x) -> float | None:
    """JSON-safe float: undefined values become None so the report never holds NaN/Infinity."""
    if x is None:
        return None
    x = float(x)
    return x if np.isfinite(x) else None


def per_year_metrics(test: pd.DataFrame, p_model, p_clim) -> list[dict]:
    """Per-test-year metrics from the SAME predictions and baselines as the aggregate evaluation.
    roc_auc is None (JSON null) for single-class years; BSS vs climatology is None when the
    climatology baseline has zero variance in that year (skill undefined)."""
    years, y = test["year"].to_numpy(), test["y"].to_numpy(float)
    p_model, p_clim = np.asarray(p_model, float), np.asarray(p_clim, float)
    out = []
    for year in sorted(set(int(v) for v in years)):
        m = years == year
        s = score(y[m], p_model[m])
        out.append({"year": year, "n": s["n"],
                    "positives": int(y[m].sum()), "negatives": int((y[m] == 0).sum()),
                    "observed_rate": _num(s["base_rate"]), "brier": _num(s["brier"]),
                    "log_loss": _num(s["log_loss"]), "roc_auc": _num(s["roc_auc"]),
                    "brier_skill_vs_climatology": _num(_bss(y[m], p_model[m], p_clim[m]))})
    return out


def calibration_diagnostics(y, p, n_bins: int = 10) -> dict:
    """Read-only reliability diagnostics for the existing test probabilities: no refitting, no
    adjustment. Fixed-width bins [low, high) with the last bin including 1.0; empty bins keep
    count 0 and null statistics. Diagnostic only - inclusion does not imply calibration."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    if not np.isfinite(p).all():
        raise ValueError("Calibration diagnostics need finite probabilities.")
    if ((p < 0) | (p > 1)).any():
        raise ValueError(f"Probabilities must lie in [0, 1]; got [{p.min():.6f}, {p.max():.6f}].")
    edges = np.round(np.arange(n_bins + 1) / n_bins, 10)
    reliability = []
    for b in range(n_bins):
        low, high = float(edges[b]), float(edges[b + 1])
        m = (p >= low) & (p <= high) if b == n_bins - 1 else (p >= low) & (p < high)
        n = int(m.sum())
        reliability.append({"low": low, "high": high, "n": n,
                            "mean_predicted": _num(p[m].mean()) if n else None,
                            "observed_rate": _num(y[m].mean()) if n else None,
                            "diff": _num(p[m].mean() - y[m].mean()) if n else None})
    return {"mean_predicted": _num(p.mean()), "observed_rate": _num(y.mean()),
            "mean_diff": _num(p.mean() - y.mean()),
            "binning": {"n_bins": int(n_bins), "bin_width": 1.0 / n_bins,
                        "interval_convention": "[low, high)", "last_bin_includes_upper": True},
            "reliability": reliability,
            "note": "diagnostic only; few years and clustered days make this unreliable evidence"}


def by_location_metrics(test: pd.DataFrame, p_model, p_clim, p_dry=None) -> list[dict]:
    """Per-location test metrics on the pooled evaluation, using the SAME predictions as the
    aggregate block (no refitting). p_dry optionally carries the dry-run heuristic's
    probabilities so the model-vs-heuristic comparison is computed per location too."""
    locs = test["location_id"].to_numpy()
    y = test["y"].to_numpy(float)
    p_model, p_clim = np.asarray(p_model, float), np.asarray(p_clim, float)
    p_dry = np.asarray(p_dry, float) if p_dry is not None else None
    out = []
    for loc in sorted(set(int(v) for v in locs)):
        m = locs == loc
        s = score(y[m], p_model[m])
        p_clim_m, y_m, p_m = p_clim[m], y[m], p_model[m]
        b = float(np.mean((p_m - y_m) ** 2))
        b_dry = float(np.mean((p_dry[m] - y_m) ** 2)) if p_dry is not None else None
        out.append({"location_id": loc, "n": s["n"], "positives": int(y[m].sum()),
                    "negatives": int((y[m] == 0).sum()),
                    "observed_rate": _num(s["base_rate"]),
                    "brier": _num(s["brier"]), "log_loss": _num(s["log_loss"]),
                    "roc_auc": _num(s["roc_auc"]),
                    "brier_vs_climatology": _num(b - float(np.mean((p_clim_m - y_m) ** 2)),
                                                 ) if p_clim_m.size else None,
                    "brier_vs_dry_run_baseline": _num(b - b_dry) if b_dry is not None else None,
                    "brier_skill_vs_climatology": _num(_bss(y_m, p_m, p_clim_m))})
    return out


def _split_block(part: pd.DataFrame, years) -> dict:
    """Per-split summary: rows, year range and which locations are represented."""
    locs = sorted(int(x) for x in part["location_id"].unique()) if "location_id" in part.columns else None
    return {"n_rows": int(len(part)), "n_years": len(years),
            "year_min": int(min(years)), "year_max": int(max(years)),
            "n_locations": len(locs) if locs is not None else None, "location_ids": locs}


def bootstrap_bss(test: pd.DataFrame, p_model, p_clim, n_boot=500, seed=0):
    """Year-block bootstrap of the Brier skill score vs climatology. None if <3 test years.
    Resamples whole years (never single days) and returns percentile bounds plus the actual
    settings used, so reports are reproducible."""
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
    return {"low": float(lo), "high": float(hi), "n_years": int(len(uniq)), "method": "year-block bootstrap, 95%",
            "resampling_unit": "year", "n_resamples": int(n_boot), "seed": int(seed),
            "confidence_level": 0.95, "interval_method": "percentile"}


def _candidates():
    return {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
        "random_forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=20, random_state=0, n_jobs=1),
    }


def train_and_evaluate(dataset: pd.DataFrame, cfg: TargetConfig, n_val: int, n_test: int,
                       provenance: dict, out_dir: Path | None = None, n_boot: int = 500, seed: int = 0) -> dict:
    tr_y, va_y, te_y = split_years(dataset["year"], n_val, n_test)
    tr, va, te = (dataset[dataset["year"].isin(g)] for g in (tr_y, va_y, te_y))
    if tr.empty or va.empty or te.empty:
        raise ValueError(f"Empty chronological split: train rows={len(tr)}, validation rows={len(va)}, "
                         f"test rows={len(te)} (years train={tr_y}, validation={va_y}, test={te_y}).")
    if te["year"].nunique() < 3:
        raise ValueError(f"Year-block bootstrap of the Brier skill score needs >= 3 distinct test years; "
                         f"got {te['year'].nunique()}: {sorted(int(y) for y in te['year'].unique())}. "
                         f"No confidence interval is fabricated below that.")
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
        "dataset": {
            "n_rows": int(len(dataset)),
            "first_date": str(pd.Timestamp(dataset["date"].min()).date()) if "date" in dataset.columns else None,
            "last_date": str(pd.Timestamp(dataset["date"].max()).date()) if "date" in dataset.columns else None,
            "n_years": int(dataset["year"].nunique()),
            "n_locations": int(dataset["location_id"].nunique()) if "location_id" in dataset.columns else None,
            "location_ids": sorted(int(x) for x in dataset["location_id"].unique()) if "location_id" in dataset.columns else None,
        },
        "splits": {name: _split_block(part, yrs) for name, part, yrs
                   in (("train", tr, tr_y), ("validation", va, va_y), ("test", te, te_y))},
        "model_class": type(final).__name__,
        "validation_brier_by_model": val_scores, "selected_model": best,
        "test": {
            "model": score(te["y"], p_model),
            "baseline_climatology": score(te["y"], p_clim),
            "baseline_dry_run_conditioned": score(te["y"], p_dry),
            "brier_skill_vs_climatology": _bss(te["y"].to_numpy(float), p_model, p_clim),
            "brier_skill_ci": bootstrap_bss(te, p_model, p_clim, n_boot=n_boot, seed=seed),
            "per_year": per_year_metrics(te, p_model, p_clim),
            "calibration": calibration_diagnostics(te["y"].to_numpy(float), p_model),
            "by_location": by_location_metrics(te, p_model, p_clim, p_dry),
        },
        "features": FEATURES,
        "caveats": ["Test-year rows within a year are autocorrelated; effective sample size is smaller than n.",
                    "Skill on reanalysis rainfall does not imply skill against gauge observations.",
                    "Per-year and calibration blocks are small-sample diagnostics, not evidence of stable "
                    "skill or of a calibrated model."],
    }
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": final, "features": FEATURES, "target_cfg": asdict(cfg), "model_name": best,
                     "trained_at_utc": report["created_at_utc"]}, out_dir / ARTIFACT)
        (out_dir / REPORT).write_text(json.dumps(report, indent=2))
    return report
