from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def ensure_schema(engine: Engine) -> None:
    """Idempotent additive migration for existing SQLite databases.

    Step 15 added Location.parent_id and made latitude/longitude nullable (grouping nodes
    carry no coordinates). SQLite cannot alter column constraints, so relaxing NOT NULL is
    done as add-temp-column -> copy -> drop -> rename (needs SQLite >= 3.35 for DROP COLUMN).
    Every step is a no-op when already applied."""
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(locations)")).fetchall()
        cols = {row[1] for row in rows}
        notnull = {row[1]: row[3] for row in rows}
        if cols and "parent_id" not in cols:
            conn.execute(text("ALTER TABLE locations ADD COLUMN parent_id INTEGER "
                              "REFERENCES locations(id) ON DELETE SET NULL"))
        for c in ("latitude", "longitude"):  # old deployments: allow NULL coordinates
            if c in cols and notnull.get(c):
                tmp = f"{c}_step15_tmp"
                conn.execute(text(f"ALTER TABLE locations ADD COLUMN {tmp} FLOAT"))
                conn.execute(text(f"UPDATE locations SET {tmp} = {c}"))
                conn.execute(text(f"ALTER TABLE locations DROP COLUMN {c}"))
                conn.execute(text(f"ALTER TABLE locations RENAME COLUMN {tmp} TO {c}"))
        conn.commit()


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            if ":memory:" not in url:
                cur.execute("PRAGMA journal_mode=WAL")  # safer concurrent reads during writes
            cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)
