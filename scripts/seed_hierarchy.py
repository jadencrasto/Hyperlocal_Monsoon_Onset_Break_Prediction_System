"""Step 15: create state grouping nodes for the location hierarchy.

Idempotent and additive: only rows we can derive from data already present (a state name
shared by existing districts). Never creates block/panchayat rows - those need authoritative
data. Dry-run by default; pass --commit to write.

Usage: python scripts/seed_hierarchy.py [--commit]
"""
import argparse
import sys

from _common import session_factory
from app.services.location_service import ensure_state_nodes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="actually write; default is a dry run")
    a = ap.parse_args()
    settings, factory = session_factory()
    with factory() as session:
        res = ensure_state_nodes(session, dry_run=not a.commit)
        tag = "created" if a.commit else "would create"
        print(f"{tag} state nodes: {res['created'] or 'none'}")
        print(f"states already having nodes: {res['existing'] or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
