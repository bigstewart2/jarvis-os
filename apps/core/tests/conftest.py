from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def cleanup_default_jarvis_db():
    db_path = Path(__file__).resolve().parent.parent / "jarvis.db"
    yield
    if db_path.exists():
        db_path.unlink()
