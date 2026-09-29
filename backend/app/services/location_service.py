"""Location hierarchy service: State -> District -> Block -> Panchayat (village cluster).

Rules of the data model (see docs/STEP15_LOCATION_SERVICE.md):
  * districts are the analysis points: they carry coordinates and (today) the rainfall data;
  * state/block/panchayat rows are grouping/navigation nodes: parent_id set, coordinates null;
  * block/panchayat data is NOT invented - the service exposes schema + endpoints ready for
    authoritative data (e.g. LGDirectory 2021), and API consumers see which levels are empty;
  * every function here takes a Session and returns plain dicts, so the API routes stay thin
    and Steps 16-18 can reuse this module without going through HTTP.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import DailyRainfall, Location

LEVELS = ("state", "district", "block", "panchayat")
LEVEL_ORDER = {lv: i for i, lv in enumerate(LEVELS)}
VALID_LEVELS = set(LEVELS)


class HierarchyError(ValueError):
    """Invalid hierarchy operation (bad level, bad parent/child relation)."""


def _out(l: Location, n_children: int | None = None) -> dict:
    d = {"id": l.id, "name": l.name, "level": l.level, "parent_id": l.parent_id,
         "state": l.state, "district": l.district,
         "latitude": l.latitude, "longitude": l.longitude, "coordinate_note": l.coordinate_note}
    if n_children is not None:
        d["n_children"] = n_children
    return d


def validate_parent_child(parent: Location, child: Location) -> None:
    """A child's level must be exactly one step below its parent's, and the state must agree:
    a state node adopts districts whose `state` equals the state node's `name`; deeper nodes
    must share their parent's `state`."""
    if parent.level not in LEVEL_ORDER or child.level not in LEVEL_ORDER:
        raise HierarchyError(f"Unknown level '{parent.level}' or '{child.level}'; "
                             f"valid levels: {sorted(VALID_LEVELS)}")
    if LEVEL_ORDER[child.level] != LEVEL_ORDER[parent.level] + 1:
        raise HierarchyError(
            f"A '{child.level}' cannot be a direct child of a '{parent.level}' "
            f"(hierarchy is {' -> '.join(LEVELS)}).")
    expected_state = parent.name if parent.level == "state" else parent.state
    if (child.state or "") != (expected_state or ""):
        raise HierarchyError(f"Parent state '{expected_state}' does not match child state '{child.state}'.")


def get_location(session: Session, location_id: int) -> Location | None:
    return session.get(Location, location_id)


def list_locations(session: Session, level: str | None = None, state: str | None = None) -> list[dict]:
    q = select(Location).order_by(Location.state, Location.name)
    if level:
        if level not in VALID_LEVELS:
            raise HierarchyError(f"Unknown level '{level}'; valid levels: {sorted(VALID_LEVELS)}")
        q = q.where(Location.level == level)
    if state:
        q = q.where(Location.state == state)
    return [_out(l) for l in session.scalars(q)]


def children_of(session: Session, location_id: int) -> list[dict]:
    parent = get_location(session, location_id)
    if parent is None:
        raise HierarchyError(f"Location {location_id} not found")
    kids = session.scalars(select(Location).where(Location.parent_id == location_id)
                           .order_by(Location.name)).all()
    return [_out(k) for k in kids]


def tree(session: Session) -> dict:
    """Full hierarchy in one query set: states on top, then their children per node."""
    all_locs = session.scalars(select(Location).order_by(Location.name)).all()
    counts: dict[int, int] = {}
    rainfall_locs = set(session.scalars(
        select(DailyRainfall.location_id).where(DailyRainfall.precip_mm.isnot(None)).distinct()))
    kids_by_parent: dict[int | None, list[Location]] = {}
    for l in all_locs:
        kids_by_parent.setdefault(l.parent_id, []).append(l)
    for l in all_locs:
        if l.parent_id is not None:
            counts[l.parent_id] = counts.get(l.parent_id, 0) + 1

    def node(l: Location) -> dict:
        d = _out(l, counts.get(l.id, 0))
        d["has_data"] = l.id in rainfall_locs
        if d["n_children"]:
            d["children"] = [node(k) for k in sorted(kids_by_parent.get(l.id, []), key=lambda x: x.name)]
        return d

    roots = [node(l) for l in sorted(kids_by_parent.get(None, []), key=lambda x: x.name)]
    levels_present = sorted({l.level for l in all_locs}, key=lambda lv: LEVEL_ORDER.get(lv, 99))
    return {"levels": list(LEVELS), "levels_present": levels_present,
            "levels_with_data": sorted({str(i) for i in rainfall_locs}) and
                                 sorted({l.level for l in all_locs if l.id in rainfall_locs},
                                        key=lambda lv: LEVEL_ORDER.get(lv, 99)),
            "roots": roots}


def ensure_state_nodes(session: Session, dry_run: bool = False) -> dict:
    """Create state grouping nodes for states that have districts but no state row.

    Idempotent: existing state nodes are left untouched. This adds ONLY the grouping rows we
    can derive from data already present (state name); it does NOT fabricate any level.",
    """
    states = session.execute(select(Location.state).where(Location.level == "district")
                             .distinct()).scalars().all()
    existing = set(session.scalars(select(Location.name).where(Location.level == "state")))
    created = []
    for st in sorted(s for s in states if s and s not in existing):
        if not dry_run:
            session.add(Location(name=st, level="state", state=st, district=None,
                                 latitude=None, longitude=None, parent_id=None,
                                 coordinate_note="Grouping node; coordinates not applicable"))
        created.append(st)
    if created and not dry_run:
        session.commit()
    return {"created": created, "existing": sorted(existing & set(states)), "dry_run": dry_run}


def link_child(session: Session, child_id: int, parent_id: int) -> dict:
    """Attach an existing location under a parent, validating level adjacency and state."""
    child, parent = get_location(session, child_id), get_location(session, parent_id)
    if child is None:
        raise HierarchyError(f"Location {child_id} not found")
    if parent is None:
        raise HierarchyError(f"Location {parent_id} not found")
    validate_parent_child(parent, child)
    if child.parent_id == parent_id:
        return _out(child)
    child.parent_id = parent_id
    session.commit()
    return _out(child)


def count_descendants(session: Session, location_id: int) -> int:
    """Number of descendants (all levels below) of a location."""
    total, frontier = 0, [location_id]
    while frontier:
        rows = session.execute(select(Location.id).where(Location.parent_id.in_(frontier))).scalars().all()
        total += len(rows)
        frontier = rows
    return total


def rainfall_coverage(session: Session, location_id: int) -> dict:
    """Rainfall data availability for a node (district) or its descendant districts."""
    loc = get_location(session, location_id)
    if loc is None:
        raise HierarchyError(f"Location {location_id} not found")
    if loc.level == "district":
        ids = [location_id]
    else:  # grouping node: aggregate over district leaves strictly below it
        ids, frontier = [], [location_id]
        while frontier:
            rows = session.execute(select(Location.id, Location.level).where(
                Location.parent_id.in_(frontier))).all()
            frontier = [rid for rid, lv in rows]
            ids.extend(rid for rid, lv in rows if lv == "district")
    if not ids:
        return {"location_id": location_id, "level": loc.level, "n_locations_with_data": 0,
                "rows": 0, "first_date": None, "last_date": None,
                "note": "no districts linked below this node yet"}
    rows = session.execute(
        select(func.count(), func.min(DailyRainfall.date), func.max(DailyRainfall.date))
        .where(DailyRainfall.location_id.in_(ids))).one()
    return {"location_id": location_id, "level": loc.level, "n_locations_with_data": len(ids),
            "rows": int(rows[0] or 0), "first_date": rows[1], "last_date": rows[2]}
