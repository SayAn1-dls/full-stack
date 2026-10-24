"""Guards for the Vercel deployment: the serverless bundle must contain everything the API imports."""

from __future__ import annotations

import glob
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG = json.loads((REPO / "vercel.json").read_text())


def expand_braces(pattern: str) -> list[str]:
    match = re.fullmatch(r"\{(.*)\}", pattern)
    return match.group(1).split(",") if match else [pattern]


def bundled_files() -> set[str]:
    included: set[str] = {"api/index.py"}
    for pattern in expand_braces(CONFIG["functions"]["api/index.py"]["includeFiles"]):
        included |= {Path(p).as_posix() for p in glob.glob(pattern, root_dir=REPO, recursive=True)}
    return included


def test_rewrite_sends_api_paths_to_the_python_function():
    assert {"source": "/api/(.*)", "destination": "/api/index"} in CONFIG["rewrites"]
    assert (REPO / "api" / "index.py").exists() and CONFIG["outputDirectory"] == "frontend/dist"


def test_entrypoint_exposes_the_fastapi_app():
    spec = importlib.util.spec_from_file_location("vercel_entry", REPO / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert type(module.app).__name__ == "FastAPI"
    assert "/api/decision" in module.app.openapi()["paths"]


def test_every_module_the_api_imports_is_in_the_serverless_bundle():
    """Import the app the way Vercel does and compare the files it loads with the includeFiles globs."""
    script = (
        "import sys; sys.path.insert(0, 'backend'); import app.main, json; "
        "print(json.dumps([m.__file__ for m in sys.modules.values() if getattr(m, '__file__', None)]))"
    )
    out = subprocess.run([sys.executable, "-c", script], cwd=REPO, capture_output=True, text=True, check=True).stdout
    loaded = {Path(f).resolve().relative_to(REPO).as_posix() for f in json.loads(out.splitlines()[-1])
              if str(Path(f).resolve()).startswith(str(REPO)) and ".venv" not in f and "site-packages" not in f}
    missing = sorted(loaded - bundled_files())
    assert not missing, f"imported but not bundled: {missing}"
    assert "backend/app/wind/analytics.py" in loaded


def test_the_data_snapshot_ships_with_the_function_and_the_heavy_pipeline_does_not():
    files = bundled_files()
    assert any(f.startswith("data/elexon/wind_snapshot.json") for f in files)
    assert not any(f.startswith("backend/app/data/") or f.startswith("data/raw") for f in files)


def test_serverless_requirements_stay_tiny():
    lines = [l.split("==")[0].lower() for l in (REPO / "requirements.txt").read_text().splitlines() if l and not l.startswith("#")]
    assert "fastapi" in lines and not {"pandas", "numpy", "pyarrow"} & set(lines)
