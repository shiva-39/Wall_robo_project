import os
import tempfile
from config import get_settings
import pytest


def _make_temp_db():
    f = tempfile.NamedTemporaryFile(prefix="test_db_", suffix=".db", delete=False)
    f.close()
    return f.name


@pytest.fixture(scope="function")
def client(tmp_path):
    """Function-scoped TestClient with an isolated temporary SQLite DB.

    This ensures each test runs against a fresh DB and avoids cross-test
    interference. The fixture will set `DB_PATH` in the environment and
    call `init_db()` before yielding the TestClient.
    """
    # Create a temp DB path
    db_path = str(tmp_path / "test_db.sqlite")

    # Ensure settings pick up new DB path
    os.environ["DB_PATH"] = db_path
    try:
        # Clear cached settings so get_settings reads the new env var
        try:
            get_settings.cache_clear()
        except Exception:
            pass

        # Import and initialize the app with fresh DB
        from fastapi.testclient import TestClient
        import robot_control_system as rcs

        rcs.init_db()

        tc = TestClient(rcs.app)
        yield tc
    finally:
        try:
            tc.close()
        except Exception:
            pass
