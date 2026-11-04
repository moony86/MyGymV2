"""Keep pytest collection away from the live database and migration startup."""
import os
from pathlib import Path
import sys
import tempfile

_test_safety_root = tempfile.TemporaryDirectory(prefix='mygym-pytest-safe-')
os.environ['DB_PATH'] = str(Path(_test_safety_root.name) / 'isolated.sqlite3')
os.environ.setdefault('MYGYM_AUTH_ENABLED', '0')
os.environ['PYTEST_CURRENT_TEST'] = 'isolated-test-collection'
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def pytest_sessionfinish(session, exitstatus):
    _test_safety_root.cleanup()
