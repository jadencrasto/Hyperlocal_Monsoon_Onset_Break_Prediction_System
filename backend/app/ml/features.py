"""Leakage-safe features and target for a local dry-spell risk model.

Target (precise): y(t) = 1 if, within days t+1 .. t+H, there is a run of at least L consecutive days
with rain < dry_mm (fully inside that window). Default H=7, L=5, dry_mm=2.5.
Features at day t use ONLY rainfall on days <= t (trailing windows). Rows are restricted to the
monsoon season so that t+H stays inside the season.

This model uses local rainfall history only. It is a historical-pattern-based estimate, not a
forecast-driven prediction: it has no access to weather-model forecasts.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FEATURES = ["r1", "sum3", "sum7", "sum14", "sum30", "rainy_frac14", "dry_run", "doy_sin", "doy_cos"]
MIN_HISTORY_DAYS = 30


@dataclass(frozen=True)
class TargetConfig:
    horizon_days: int = 7
    dry_len: int = 5
    dry_mm: float = 2.5
    first_md: tuple[int, int] = (6, 15)
    season_end_md: tuple[int, int] = (9, 30)


def _full_daily(precip: pd.Series) -> pd.Series:
    s = precip.copy()
    s.index = pd.DatetimeIndex(pd.to_datetime(s.index)).normalize()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))


def feature_frame(precip: pd.Series, cfg: TargetConfig = TargetConfig()) -> pd.DataFrame:
    """Features for every day, computed from trailing data only (NaN where history is incomplete)."""
    p = _full_daily(precip)
    df = pd.DataFrame(index=p.index)
    df["r1"] = p
    for k in (3, 7, 14, 30):
        df[f"sum{k}"] = p.rolling(k, min_periods=k).sum()
    rainy = (p >= cfg.dry_mm).astype(float).where(p.notna())
    df["rainy_frac14"] = rainy.rolling(14, min_periods=14).mean()
    run, out = 0, []
    for v in p.to_numpy():
        if np.isnan(v):
            run = 0
            out.append(np.nan)
        else:
            run = run + 1 if v < cfg.dry_mm else 0
            out.append(run)
    df["dry_run"] = out
    ang = 2 * np.pi * df.index.dayofyear.to_numpy() / 365.25
    df["doy_sin"], df["doy_cos"] = np.sin(ang), np.cos(ang)
    return df[FEATURES]


def target_series(precip: pd.Series, cfg: TargetConfig = TargetConfig()) -> pd.Series:
    p = _full_daily(precip)
    H, L = cfg.horizon_days, cfg.dry_len
    dry = (p < cfg.dry_mm).astype(float).where(p.notna())
    l_dry = (dry.rolling(L, min_periods=L).sum() == L).to_numpy() & dry.rolling(L, min_periods=L).sum().notna().to_numpy()
    observed = p.notna().to_numpy()
    n = len(p)
    y = np.full(n, np.nan)
    for t in range(n - H):
        if l_dry[t + L:t + H + 1].any():
            y[t] = 1.0
        elif observed[t + 1:t + H + 1].all():
            y[t] = 0.0
    return pd.Series(y, index=p.index, name="y")


def build_dataset(precip: pd.Series, cfg: TargetConfig = TargetConfig(), location_id: int | None = None) -> pd.DataFrame:
    X, y = feature_frame(precip, cfg), target_series(precip, cfg)
    df = X.join(y)
    idx = df.index
    md = idx.month * 100 + idx.day
    end = pd.to_datetime(pd.DataFrame({"year": idx.year, "month": np.full(len(idx), cfg.season_end_md[0]),
                                       "day": np.full(len(idx), cfg.season_end_md[1])}))
    in_season = (md >= cfg.first_md[0] * 100 + cfg.first_md[1]) & ((idx + pd.Timedelta(days=cfg.horizon_days)) <= end.to_numpy())
    df = df[in_season].dropna()
    df["date"], df["year"], df["doy"] = df.index, df.index.year, df.index.dayofyear
    df["location_id"] = location_id
    df["y"] = df["y"].astype(int)
    return df.reset_index(drop=True)
