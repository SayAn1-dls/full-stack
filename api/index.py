"""Vercel entrypoint: exposes the FastAPI app that lives in backend/app (see vercel.json for the rewrite)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import app  # noqa: E402,F401
