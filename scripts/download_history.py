"""Download daily rainfall history for one or all locations, year by year (resumable: already-stored
years with >=95% coverage are skipped; failures are logged and the run continues).
Usage: python scripts/download_history.py --start-year 2000 --end-year 2024 [--location-id 1]"""
import argparse
import sys
import time
from datetime import date

from sqlalchemy import func, select

from _common import session_factory
from app.models import DailyRainfall, Location
from app.providers.registry import build_providers
from app.services.weather_service import WeatherService


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="open_meteo")
    ap.add_argument("--start-year", type=int, required=True)
    ap.add_argument("--end-year", type=int, required=True)
    ap.add_argument("--location-id", type=int)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between requests (be polite to the API)")
    a = ap.parse_args()
    settings, factory = session_factory()
    svc = WeatherService(factory, build_providers(settings), settings)
    failures = 0
    with factory() as session:
        q = select(Location) if a.location_id is None else select(Location).where(Location.id == a.location_id)
        for loc in session.scalars(q).all():
            for year in range(a.start_year, a.end_year + 1):
                start, end = date(year, 1, 1), min(date(year, 12, 31), date.today())
                have = session.scalar(select(func.count()).select_from(DailyRainfall).where(
                    DailyRainfall.location_id == loc.id, DailyRainfall.provider == a.provider,
                    DailyRainfall.date.between(start, end)))
                if have >= 0.95 * ((end - start).days + 1):
                    continue
                res = svc.refresh_history(session, loc, a.provider, start, end, "online")
                print(f"{loc.name} {year}: {res.status} {res.n_records} {res.message or ''}")
                failures += res.status != "ok"
                time.sleep(a.pause)
    print(f"finished with {failures} failed request(s); re-run to retry only the missing years")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
