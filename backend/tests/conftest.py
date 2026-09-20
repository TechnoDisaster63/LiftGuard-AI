"""Pytest fixtures: isolate runtime state before importing the app."""
import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

_tmp = tempfile.mkdtemp(prefix="liftguard-test-")
os.environ["LIFTGUARD_USER_DB"] = str(Path(_tmp) / "users.db")
os.environ["LIFTGUARD_ARDUINO_ENABLED"] = "false"
os.environ["LIFTGUARD_VOICE_ENABLED"] = "false"
