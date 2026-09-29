"""Train + evaluate the dry-spell risk model from rainfall stored in the local database.
Usage: python scripts/train_model.py [--location-id ID | --all-locations] [--start-year Y] [--end-year Y]
       [--n-val 5] [--n-test 8] [--min-years 16]

Location selection: --location-id trains on exactly that location; --all-locations pools every
location with stored history into one dataset (splits stay year-based, so a calendar year never
crosses splits). With no flag, training proceeds only when exactly one location has stored
history; when several do, the run stops with an error instead of silently pooling them.
--start-year/--end-year (inclusive) restrict the history window for a like-for-like experiment.
"""
import argparse
import sys

import pandas as pd
from sqlalchemy import select

from _common import session_factory
from app.ml.features import TargetConfig, build_dataset
from app.ml.train import required_years, train_and_evaluate
from app.models import DailyRainfall, Location
from app.services.weather_service import WeatherService


def select_history_locations(location_rows, history: dict[int, pd.Series], location_id: int | None,
                             all_locations: bool = False):
    """Resolve which locations with stored history to train on.

    An explicit --location-id pins the choice and must exist and have history. --all-locations
    pools every history-holding location; that is an explicit, logged choice, never a silent
    default. With no flag, a single history-holding location is unambiguous; several are not,
    and pooling them silently is exactly the failure mode this guard exists to prevent.
    Returns (selected_ids, error_message)."""
    known = sorted(loc.id for loc in location_rows)
    with_history = sorted(history)
    if all_locations:
        if not with_history:
            return None, "No stored history found. Run scripts/download_history.py first."
        return with_history, None
    if location_id is not None:
        if location_id not in known:
            return None, f"No location with id={location_id}. Existing location ids: {known}."
        if location_id not in history:
            return None, (f"Location id={location_id} has no usable stored rainfall history. "
                          "Run scripts/download_history.py for it first.")
        return [location_id], None
    if not with_history:
        return None, "No stored history found. Run scripts/download_history.py first."
    if len(with_history) > 1:
        return None, (f"{len(with_history)} locations have stored history (ids {with_history}); training them "
                      "together would silently pool different locations. Choose explicitly with "
                      "--location-id or --all-locations.")
    return with_history, None


def main() -> int:
    ap = argparse.ArgumentParser()
    loc_group = ap.add_mutually_exclusive_group()
    loc_group.add_argument("--location-id", type=int, default=None,
                           help="train on exactly this location id")
    loc_group.add_argument("--all-locations", action="store_true", default=False,
                           help="pool every location with stored history into one dataset "
                                "(year-based splits keep calendar years from crossing splits)")
    ap.add_argument("--start-year", type=int, default=None,
                    help="inclusive first year of history to use (default: all stored history)")
    ap.add_argument("--end-year", type=int, default=None,
                    help="inclusive last year of history to use (default: all stored history)")
    ap.add_argument("--n-val", type=int, default=5)
    ap.add_argument("--n-test", type=int, default=8)
    ap.add_argument("--min-years", type=int, default=None,
                    help="minimum distinct years required (default: the exact split_years() requirement "
                         "for --n-val/--n-test, i.e. n_val + n_test + min_train)")
    a = ap.parse_args()
    if a.start_year is not None and a.end_year is not None and a.start_year > a.end_year:
        ap.error(f"--start-year {a.start_year} is after --end-year {a.end_year}.")
    if a.min_years is not None and a.min_years < required_years(a.n_val, a.n_test):
        ap.error(f"--min-years={a.min_years} is below the {required_years(a.n_val, a.n_test)} distinct years "
                 f"the chronological split needs (n_val={a.n_val}, n_test={a.n_test}, min_train=3).")
    min_years = a.min_years if a.min_years is not None else required_years(a.n_val, a.n_test)
    settings, factory = session_factory()
    svc = WeatherService(factory, {}, settings)
    location_rows, history, kinds_by_loc = [], {}, {}
    with factory() as session:
        location_rows = session.scalars(select(Location)).all()
        for loc in location_rows:
            start = pd.Timestamp(a.start_year, 1, 1).date() if a.start_year is not None else pd.Timestamp(1900, 1, 1).date()
            end = pd.Timestamp(a.end_year, 12, 31).date() if a.end_year is not None else pd.Timestamp.today().date()
            s = svc.history_series(session, loc.id, start, end)
            if s.empty:
                continue
            history[loc.id] = s
            kinds_by_loc[loc.id] = sorted(session.scalars(select(DailyRainfall.kind)
                                             .where(DailyRainfall.location_id == loc.id).distinct()).all())
    chosen, err = select_history_locations(location_rows, history, a.location_id, a.all_locations)
    if err:
        print(err, file=sys.stderr)
        return 2
    # Per-location year coverage: pooled years from other locations must never satisfy one
    # location's split requirement. Each selected location's own usable dataset has to qualify.
    frames, meta = [], []
    for loc in [x for x in location_rows if x.id in chosen]:
        ds = build_dataset(history[loc.id], TargetConfig(), loc.id)
        if ds["year"].nunique() < min_years:
            print(f"Location {loc.id} ({loc.name}) has {ds['year'].nunique()} usable years; the chronological "
                  f"split needs at least {min_years} (n_val={a.n_val}, n_test={a.n_test}, min_train=3). Years held "
                  f"by other locations do not count. Not training.", file=sys.stderr)
            return 2
        frames.append(ds)
        meta.append({"location_id": loc.id, "name": loc.name, "rows": int(len(ds)),
                     "years": int(ds["year"].nunique()), "kinds": kinds_by_loc[loc.id]})
    data = pd.concat(frames, ignore_index=True)
    for m in meta:
        print(f"training location {m['location_id']} ({m['name']}): {m['rows']} usable rows, "
              f"{m['years']} distinct years, kinds={m['kinds']}")
    print(f"dataset: {len(data)} usable rows, {int(data['year'].nunique())} distinct years, "
          f"{data['date'].min().date()} to {data['date'].max().date()}, "
          f"{data['location_id'].nunique()} locations {sorted(int(x) for x in data['location_id'].unique())}")
    rep = train_and_evaluate(data, TargetConfig(), a.n_val, a.n_test,
                             {"kind": "stored_history",
                              "location_selection": {"mode": "explicit_location_id" if a.location_id is not None
                                                     else ("all_locations" if a.all_locations
                                                           else "automatic_single_location"),
                                                     "selected_location_ids": sorted(chosen),
                                                     "available_location_ids_with_history": sorted(history)},
                              "locations": meta, "rows": int(len(data))},
                             settings.models_dir)
    print(f"selected={rep['selected_model']}  test BSS vs climatology={rep['test']['brier_skill_vs_climatology']:.3f}")
    print(f"report: {settings.models_dir / 'evaluation.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
