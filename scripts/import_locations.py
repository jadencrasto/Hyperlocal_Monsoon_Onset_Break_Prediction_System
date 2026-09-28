"""Import locations from CSV (columns: name,level,state,district,latitude,longitude,coordinate_note).
Existing rows are left untouched. Block/village rows must come from a real source (e.g. LGD / Census /
Survey of India data you have the right to use); this project does not ship fabricated block coordinates.
Usage: python scripts/import_locations.py data/locations_pilot.csv"""
import csv
import sys

from _common import session_factory
from app.models import Location

LEVELS = {"state", "district", "block", "village"}


def main(path: str) -> int:
    _, factory = session_factory()
    added = skipped = 0
    with factory() as session, open(path, newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
                assert row["level"] in LEVELS and 6 <= lat <= 38 and 68 <= lon <= 98
            except (KeyError, ValueError, AssertionError):
                print(f"line {i}: invalid row, skipped: {row}", file=sys.stderr)
                skipped += 1
                continue
            exists = session.query(Location).filter_by(name=row["name"], level=row["level"], state=row["state"],
                                                       district=row.get("district") or None).first()
            if exists:
                skipped += 1
                continue
            session.add(Location(name=row["name"], level=row["level"], state=row["state"],
                                 district=row.get("district") or None, latitude=lat, longitude=lon,
                                 coordinate_note=row.get("coordinate_note") or None))
            added += 1
        session.commit()
    print(f"added={added} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "data/locations_pilot.csv"))
