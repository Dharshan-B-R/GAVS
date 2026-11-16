"""Bootstrap a brand-new KiranaAI database from the current SQLAlchemy models.

Run from any working directory with DATABASE_URL configured:
    python backend/scripts/bootstrap_fresh_database.py

This is ONLY for an empty database. Existing installations must use
    cd backend && alembic upgrade head
Do not run this script against an existing or populated database.
"""
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Importing the application registers every model and creates the current
# metadata schema on an empty database (the existing startup initialization).
import main  # noqa: F401, E402

config = Config(str(BACKEND_DIR / "alembic.ini"))
command.stamp(config, "head")
print("Fresh KiranaAI database created from current models and stamped at Alembic head.")
