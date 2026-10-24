from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `app` importable without installing

from app.data.clean_demand import (  # noqa: E402
    PipelineConfig,
    load_expected_hashes,
    run_pipeline,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"


def require_raw_files() -> dict[str, str]:
    """The real-data suite needs all 18 raw files. A missing file is a failure, not a skip."""
    expected = load_expected_hashes()
    missing = [name for name in expected if not (RAW_DIR / name).exists()]
    if missing:
        pytest.fail(
            f"raw file(s) missing from {RAW_DIR}: {missing}. "
            "Run `cd backend && python -m app.data.fetch_raw_data` first.",
            pytrace=False,
        )
    return expected


def raw_hashes() -> dict[str, str]:
    return {name: sha256_file(RAW_DIR / name) for name in load_expected_hashes()}


def _run(tmp_dir: Path) -> SimpleNamespace:
    require_raw_files()
    before = raw_hashes()
    config = PipelineConfig(
        raw_dir=RAW_DIR, interim_dir=tmp_dir / "interim", processed_dir=tmp_dir / "processed",
        expected_hashes=load_expected_hashes(), reference_checks="on",
    )
    manifest = run_pipeline(config)
    after = raw_hashes()
    return SimpleNamespace(
        manifest=manifest, processed=tmp_dir / "processed", interim=tmp_dir / "interim",
        df=pd.read_parquet(tmp_dir / "processed" / "demand_clean.parquet"),
        hashes_before=before, hashes_after=after,
    )


@pytest.fixture(scope="session")
def real_run(tmp_path_factory) -> SimpleNamespace:
    """One full pipeline run over the real files, shared by the whole real-data suite."""
    return _run(tmp_path_factory.mktemp("real_run_1"))


@pytest.fixture(scope="session")
def real_run_again(tmp_path_factory) -> SimpleNamespace:
    return _run(tmp_path_factory.mktemp("real_run_2"))
