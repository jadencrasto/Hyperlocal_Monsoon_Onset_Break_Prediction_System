"""Train + evaluate the dry-spell risk model from rainfall stored in the local database.
Usage: python scripts/train_model.py [--n-val 5] [--n-test 8] [--min-years 15]"""
import argparse
import sys

import pandas as pd
from sqlalchemy import select

from _common import session_factory
from app.ml.features import TargetConfig, build_dataset
from app.ml.train import train_and_evaluate
from app.models import DailyRainfall, Location
from app.services.weather_service import WeatherService


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-val", type=int, default=5)
    ap.add_argument("--n-test", type=int, default=8)
    ap.add_argument("--min-years", type=int, default=15)
    a = ap.parse_args()
    settings, factory = session_factory()
    svc = WeatherService(factory, {}, settings)
    frames, meta = [], []
    with factory() as session:
        for loc in session.scalars(select(Location)).all():
            s = svc.history_series(session, loc.id, pd.Timestamp(1900, 1, 1).date(), pd.Timestamp.today().date())
            if s.empty:
                continue
            ds = build_dataset(s, TargetConfig(), loc.id)
            if ds["year"].nunique() >= a.min_years:
                frames.append(ds)
                kinds = session.scalars(select(DailyRainfall.kind).where(DailyRainfall.location_id == loc.id).distinct()).all()
                meta.append({"location_id": loc.id, "name": loc.name, "years": int(ds["year"].nunique()), "kinds": sorted(kinds)})
    if not frames:
        print("No location has enough stored history. Run scripts/download_history.py first.", file=sys.stderr)
        return 2
    data = pd.concat(frames, ignore_index=True)
    rep = train_and_evaluate(data, TargetConfig(), a.n_val, a.n_test,
                             {"kind": "stored_history", "locations": meta, "rows": int(len(data))}, settings.models_dir)
    print(f"selected={rep['selected_model']}  test BSS vs climatology={rep['test']['brier_skill_vs_climatology']:.3f}")
    print(f"report: {settings.models_dir / 'evaluation.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
