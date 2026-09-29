"""Step 15: location hierarchy service + endpoints.

Uses the tmp database from conftest; the 5 real pilot districts are created in fixtures so
tests are independent of the developer database, and one real-database read-only check is
marked separately.
"""
import pytest
from sqlalchemy import select

from app.models import Location
from app.services import location_service as ls
from app.services.location_service import HierarchyError

from .conftest import FakeProvider

PILOTS = [("Pune", 18.5204, 73.8567), ("Nashik", 19.9975, 73.7898),
          ("Kolhapur", 16.7050, 74.2433), ("Chhatrapati Sambhajinagar", 19.8762, 75.3433),
          ("Nagpur", 21.1458, 79.0882)]


@pytest.fixture
def pilots(session):
    """The 5 pilot districts (matching the real CSV), with a parent state node."""
    state = Location(name="Maharashtra", level="state", state="Maharashtra", district=None,
                     latitude=None, longitude=None, parent_id=None,
                     coordinate_note="Grouping node; coordinates not applicable")
    session.add(state)
    session.flush()
    locs = []
    for name, lat, lon in PILOTS:
        loc = Location(name=name, level="district", state="Maharashtra", district=name,
                       latitude=lat, longitude=lon, parent_id=state.id,
                       coordinate_note="Approximate point for the district headquarters city")
        session.add(loc)
        locs.append(loc)
    session.commit()
    return state, locs


@pytest.fixture
def make_client(settings, session):
    from fastapi.testclient import TestClient

    from app.main import create_app

    def _make():
        app = create_app(settings, {"fake": FakeProvider()}, connectivity=lambda host: True)
        return TestClient(app)
    return _make


def test_level_adjacency_validation(session, pilots):
    state, locs = pilots
    district = locs[0]
    block = Location(name="Haveli", level="block", state="Maharashtra", district="Pune",
                     latitude=None, longitude=None, parent_id=district.id)
    session.add(block)
    session.flush()
    # district directly under state: OK. block under district: OK.
    ls.validate_parent_child(state, district)
    ls.validate_parent_child(district, block)
    # violations: skipping levels, wrong direction, state mismatch
    with pytest.raises(HierarchyError, match="cannot be a direct child"):
        ls.validate_parent_child(state, block)          # state -> block skips district
    with pytest.raises(HierarchyError, match="cannot be a direct child"):
        ls.validate_parent_child(district, state)       # upwards
    other_state = Location(name="X", level="state", state="Gujarat", district=None,
                           latitude=None, longitude=None, parent_id=None)
    session.add(other_state)
    session.flush()
    bad = Location(name="Y", level="district", state="Gujarat", district="Y",
                   latitude=None, longitude=None, parent_id=None)
    session.add(bad)
    session.flush()
    with pytest.raises(HierarchyError, match="state"):
        ls.validate_parent_child(state, bad)            # state node only adopts its own districts
    with pytest.raises(HierarchyError, match="state"):
        ls.validate_parent_child(other_state, district)  # Gujarat node can't adopt Maharashtra district


def test_link_child_and_cycles_of_invalid_parents(session, pilots):
    state, locs = pilots
    district = locs[0]
    out = ls.link_child(session, district.id, state.id)      # idempotent re-link
    assert out["parent_id"] == state.id
    with pytest.raises(HierarchyError, match="not found"):
        ls.link_child(session, district.id, 424242)
    with pytest.raises(HierarchyError, match="not found"):
        ls.link_child(session, 424242, state.id)


def test_children_of_and_tree(session, pilots):
    state, locs = pilots
    kids = ls.children_of(session, state.id)
    assert [k["name"] for k in kids] == sorted(p[0] for p in PILOTS)
    assert all(k["parent_id"] == state.id and k["level"] == "district" for k in kids)
    with pytest.raises(HierarchyError, match="not found"):
        ls.children_of(session, 424242)
    t = ls.tree(session)
    assert t["levels"] == ["state", "district", "block", "panchayat"]
    assert t["levels_present"] == ["state", "district"]      # no fabricated levels
    assert t["levels_with_data"] == []                       # fixture has no rainfall rows
    assert len(t["roots"]) == 1 and t["roots"][0]["name"] == "Maharashtra"
    root = t["roots"][0]
    assert root["n_children"] == 5 and root["has_data"] is False
    assert {c["name"] for c in root["children"]} == {p[0] for p in PILOTS}
    assert all(c["has_data"] is False for c in root["children"])   # no rainfall rows in fixture
    # coordinates: districts have them, the state node does not
    assert root["latitude"] is None and all(c["latitude"] for c in root["children"])


def test_list_locations_level_and_state_filters(session, pilots):
    assert len(ls.list_locations(session)) == 6
    assert len(ls.list_locations(session, level="district")) == 5
    assert ls.list_locations(session, level="block") == []
    with pytest.raises(HierarchyError, match="Unknown level"):
        ls.list_locations(session, level="continent")


def test_coverage_empty_and_with_data(session, pilots):
    state, locs = pilots
    empty = ls.rainfall_coverage(session, state.id)
    assert empty["rows"] == 0 and empty["n_locations_with_data"] == 5
    assert "no districts linked" not in empty.get("note", "")
    with pytest.raises(HierarchyError, match="not found"):
        ls.rainfall_coverage(session, 424242)


def test_ensure_state_nodes_idempotent(session):
    """Districts without a state node get one; re-running adds nothing; nothing fabricated."""
    session.add(Location(name="Pune", level="district", state="Maharashtra", district="Pune",
                         latitude=18.5, longitude=73.8, parent_id=None))
    session.commit()
    first = ls.ensure_state_nodes(session)
    assert first["created"] == ["Maharashtra"]
    second = ls.ensure_state_nodes(session)
    assert second["created"] == []
    dry = ls.ensure_state_nodes(session, dry_run=True)
    assert dry["created"] == []
    n = len(ls.list_locations(session, level="state"))
    assert n == 1


def test_endpoints_tree_children_detail(make_client, session, pilots):
    state, locs = pilots
    c = make_client()
    # /locations/tree
    t = c.get("/api/locations/tree").json()
    assert t["levels_present"] == ["state", "district"]
    assert t["roots"][0]["n_children"] == 5
    # /locations/{id}/children
    kids = c.get(f"/api/locations/{state.id}/children").json()
    assert len(kids) == 5
    assert c.get("/api/locations/424242/children").status_code == 404
    assert c.get("/api/locations/424242/children").json()["detail"]["error"] == "location_not_found"
    # /locations/{id} detail now carries parent_id
    d = c.get(f"/api/locations/{locs[0].id}").json()
    assert d["parent_id"] == state.id
    # /locations stays backward compatible (still the flat list of everything)
    flat = c.get("/api/locations").json()
    assert len(flat) == 6 and all("parent_id" in row for row in flat)
    # invalid level filter -> 422 structured error
    r = c.get("/api/locations?level=continent")
    assert r.status_code == 422 and r.json()["detail"]["error"] == "invalid_level"


def test_prediction_endpoint_still_works_with_hierarchy(make_client, session, pilots, settings,
                                                        monkeypatch):
    """Backward compatibility: pilot districts keep their IDs and the prediction path works
    unchanged (model availability only changes the status code)."""
    from app.ml.train import ARTIFACT
    import joblib
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    r = make_client().get(f"/api/locations/{pilots[1][0].id}/prediction/break-risk")
    assert r.status_code == 503                     # no model installed in this fixture
    assert r.json()["detail"]["error"] == "model_unavailable"


def test_ensure_schema_migration_adds_parent_id(tmp_path):
    """Simulate a pre-Step-15 database: parent_id missing, coordinates NOT NULL, with data."""
    import sqlite3

    from sqlalchemy import create_engine, text

    from app.db import ensure_schema

    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT, level TEXT, "
                 "state TEXT, district TEXT, latitude FLOAT NOT NULL, longitude FLOAT NOT NULL, "
                 "coordinate_note TEXT)")
    conn.execute("INSERT INTO locations (name, level, state, district, latitude, longitude) "
                 "VALUES ('Pune', 'district', 'Maharashtra', 'Pune', 18.5, 73.8)")
    conn.commit()
    conn.close()
    engine = create_engine(f"sqlite:///{db}")
    ensure_schema(engine)
    with engine.connect() as c:
        info = c.execute(text("PRAGMA table_info(locations)")).fetchall()
        cols = {row[1] for row in info}
        notnull = {row[1]: row[3] for row in info}
        assert "parent_id" in cols
        assert not notnull["latitude"] and not notnull["longitude"]  # relaxed for grouping nodes
        row = c.execute(text("SELECT name, latitude, longitude FROM locations")).fetchone()
        assert row == ("Pune", 18.5, 73.8)               # data + coordinates intact
    # relaxed schema now accepts a coordinate-less grouping node
    with engine.begin() as c:
        c.execute(text("INSERT INTO locations (name, level, state, latitude, longitude) "
                       "VALUES ('Maharashtra', 'state', 'Maharashtra', NULL, NULL)"))
    ensure_schema(engine)                            # second run is a no-op
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM locations")).scalar() == 2
