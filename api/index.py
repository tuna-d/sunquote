"""Vercel entry point: serves the FastAPI app as a Python function.

Vercel runs the app on a function instance that can be frozen between requests, so two
settings differ from a long-running container (`compose.yaml`): the app opens no client-side
database pool, and it does not migrate at startup (CI runs the migrations on every push to
`main`). The values are defaults: an environment variable set in the Vercel project wins.
"""

import os
import sys
from pathlib import Path

# The package lives in `src/`; do not depend on the host installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SUNQUOTE_MIGRATE_ON_STARTUP", "false")
os.environ.setdefault("SUNQUOTE_DATABASE_CLIENT_POOL", "false")

from sunquote.api.app import app

__all__ = ["app"]
