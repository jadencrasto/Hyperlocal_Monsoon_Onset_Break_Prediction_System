"""Step 12: independent gauge-based validation of the stored rainfall and dry-spell labels.

Compares the daily rainfall stored by the app (Open-Meteo archive = ERA5-family reanalysis)
against NOAA GHCN-Daily station records (gauge observations - fully independent of ERA5).
No model is loaded, retrained, or modified; the database is only read.

Usage: python scripts/validate_labels.py [--test-years-only]
Stations were chosen as the closest GHCN gauge with modern PRCP coverage (see
docs/STEP12_INDEPENDENT_VALIDATION.md). Nashik has no modern gauge in GHCN; IN012161300
covers 1965-2005, so its overlap with the study window is 2000-2005 only (partial check).
"""
import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from _common import session_factory
from app.ml.features import TargetConfig, target_series
from app.services.weather_service import WeatherService

BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"
# location_id -> (GHCN station id, short note)
STATIONS = {
    1: ("IN012190100", "Pune"),
    2: ("IN012161300", "Nashik (gauge ends 2005: partial)"),
    3: ("IN012131800", "Kolhapur"),
    4: ("IN012041000", "Chhatrapati Sambhajinagar"),
    5: ("IN012141800", "Nagpur"),
}
CACHE = Path("data/raw/external")
TEST_YEARS = set(range(2018, 2026))


def fetch_dly(station_id: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{station_id}.dly"
    if not path.exists():
        r = requests.get(f"{BASE}/all/{station_id}.dly", timeout=120)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def parse_dly(path: Path) -> pd.Series:
    """GHCN .dly -> daily PRCP series in mm. Lines: ID(11) YEAR(4) MONTH(2) ELEM(4),
    then 31 x VALUE(5) MFLAG(1) QFLAG(1) SFLAG(1); PRCP is in tenths of mm; -9999 missing;
    QFLAG != ' ' means the value failed quality control -> dropped."""
    out = {}
    for line in path.read_text().splitlines():
        if line[17:21] != "PRCP":
            continue
        year, month = int(line[11:15]), int(line[15:17])
        for day in range(1, 32):
            off = 21 + (day - 1) * 8
            raw = int(line[off:off + 5])
            qflag = line[off + 6]
            try:
                d = date(year, month, day)
            except ValueError:
                continue
            if raw == -9999 or qflag != " ":
                continue
            out[d] = raw / 10.0
    return pd.Series(out, dtype=float).sort_index()


def season_mask(idx: pd.DatetimeIndex) -> np.ndarray:
    md = idx.month * 100 + idx.day
    return (md >= 615) & (md <= 930)


def compare(era5: pd.Series, gauge: pd.Series, label: str, test_years_only: bool) -> dict:
    def _dt(s: pd.Series) -> pd.Series:
        return pd.Series(s.values, index=pd.DatetimeIndex(pd.to_datetime(s.index)))
    era5, gauge = _dt(era5), _dt(gauge)
    cfg = TargetConfig()
    y_e = target_series(era5, cfg)          # labels recomputed per source: independent pipelines
    y_g = target_series(gauge, cfg)
    df = pd.DataFrame({"rain_e": era5, "rain_g": gauge, "y_e": y_e, "y_g": y_g}).dropna(
        subset=["rain_e", "rain_g"])
    df = df[season_mask(df.index)]
    df["year"] = df.index.year
    if test_years_only:
        df = df[df["year"].isin(TEST_YEARS)]
    both_y = df.dropna(subset=["y_e", "y_g"])
    out = {
        "location": label,
        "gauge_days_total": int(len(gauge)),
        "gauge_first": str(gauge.index.min().date()), "gauge_last": str(gauge.index.max().date()),
        "matched_days": int(len(df)), "matched_years": int(df["year"].nunique()),
        "years": f"{df.index.min().year}-{df.index.max().year}",
        "pearson_r": float(df["rain_e"].corr(df["rain_g"])),
        "spearman_rho": float(df["rain_e"].corr(df["rain_g"], method="spearman")),
        "mae_mm": float((df["rain_e"] - df["rain_g"]).abs().mean()),
        "bias_mm": float((df["rain_g"] - df["rain_e"]).mean()),
        "wet25_e": float((df["rain_e"] >= cfg.dry_mm).mean()),
        "wet25_g": float((df["rain_g"] >= cfg.dry_mm).mean()),
        "wet_agree": float(((df["rain_e"] >= cfg.dry_mm) == (df["rain_g"] >= cfg.dry_mm)).mean()),
    }
    if len(both_y):
        agree = float((both_y["y_e"] == both_y["y_g"]).mean())
        out.update({
            "label_days": int(len(both_y)), "label_agreement": agree,
            "events_e": int(both_y["y_e"].sum()), "events_g": int(both_y["y_g"].sum()),
            "events_both": int(((both_y["y_e"] == 1) & (both_y["y_g"] == 1)).sum()),
            "season_counts_r": float(np.corrcoef(
                both_y.groupby("year")["y_e"].sum(), both_y.groupby("year")["y_g"].sum())[0, 1])
            if both_y["year"].nunique() > 2 else None,
        })
    return out, df, both_y


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-years-only", action="store_true",
                    help="restrict comparisons to the 2018-2025 evaluation years")
    a = ap.parse_args()
    settings, factory = session_factory()
    svc = WeatherService(factory, {}, settings)
    print(f"{'location':28s} {'yrs':9s} {'days':>6s} {'r':>5s} {'rho':>5s} {'MAE':>5s} {'bias':>6s} "
          f"{'wetE':>5s} {'wetG':>5s} {'agru':>5s} {'labAgr':>6s} {'evE':>4s} {'evG':>4s} {'rSsn':>5s}")
    for loc_id, (station, label) in STATIONS.items():
        gauge = parse_dly(fetch_dly(station))
        with factory() as session:
            era5 = svc.history_series(session, loc_id, date(2000, 1, 1), date(2025, 12, 31))
        res, df, both_y = compare(era5, gauge, label, a.test_years_only)
        print(f"{label:28s} {res['years']:9s} {res['matched_days']:6d} "
              f"{res['pearson_r']:5.2f} {res['spearman_rho']:5.2f} {res['mae_mm']:5.1f} {res['bias_mm']:+6.1f} "
              f"{res['wet25_e']:5.2f} {res['wet25_g']:5.2f} {res['wet_agree']:5.2f} "
              f"{res.get('label_agreement', float('nan')):6.2f} "
              f"{res.get('events_e', -1):4d} {res.get('events_g', -1):4d} "
              f"{(res.get('season_counts_r') if res.get('season_counts_r') is not None else float('nan')):5.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
