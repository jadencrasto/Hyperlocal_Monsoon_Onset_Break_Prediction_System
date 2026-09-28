import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import Base  # noqa: E402


def session_factory():
    s = get_settings()
    engine = make_engine(s.database_url)
    Base.metadata.create_all(engine)
    return s, make_session_factory(engine)
