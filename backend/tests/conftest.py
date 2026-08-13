import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Use an isolated, in-memory-style sqlite file for tests so they never
# touch a developer's real eaglewatch.db.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_eaglewatch.db")
