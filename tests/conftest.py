import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os

os.environ.setdefault("DISABLE_SCANNER", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_radar.db")
os.environ.setdefault("APP_PASSWORD", "")
os.environ.setdefault("OPENAI_API_KEY", "")

import pytest
from app.db import Base, engine


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        from app.main import _invalidate_live_cache
        _invalidate_live_cache()
    except Exception:
        pass
    yield
    try:
        from app.main import _invalidate_live_cache
        _invalidate_live_cache()
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus):
    p = Path("test_radar.db")
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
