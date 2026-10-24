"""Snapshot loading, including the gzip form used by the deployment."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from app.wind.dataset import DEFAULT_SNAPSHOT, SnapshotError, load_dataset, parse_snapshot

REAL = Path(DEFAULT_SNAPSHOT)


def test_a_gzipped_snapshot_loads_to_the_same_dataset_and_hash(tmp_path):
    text = REAL.read_text()
    (tmp_path / "wind_snapshot.json.gz").write_bytes(gzip.compress(text.encode(), compresslevel=9, mtime=0))
    from_gz = load_dataset(str(tmp_path / "wind_snapshot.json"))      # no .json beside it: falls back to .gz
    original = parse_snapshot(text)
    assert from_gz.sha256 == original.sha256 == hashlib.sha256(REAL.read_bytes()).hexdigest()
    assert from_gz.actual == original.actual and from_gz.publications == original.publications


def test_plain_json_wins_when_both_exist(tmp_path):
    (tmp_path / "wind_snapshot.json").write_text(REAL.read_text())
    (tmp_path / "wind_snapshot.json.gz").write_bytes(gzip.compress(b"not a snapshot"))
    assert load_dataset(str(tmp_path / "wind_snapshot.json")).sha256 == parse_snapshot(REAL.read_text()).sha256


def test_a_missing_snapshot_is_a_clear_error(tmp_path):
    with pytest.raises(SnapshotError, match="run `python -m app.wind.ingest`"):
        load_dataset(str(tmp_path / "nothing.json"))


@pytest.mark.parametrize("broken", ['{"meta":{}}', '{"meta":{},"actuals":{"first":"2026-01-01T00:00:00Z","step_minutes":30,"values":[]},"forecasts":[]}'])
def test_a_snapshot_without_data_is_rejected(broken):
    with pytest.raises((SnapshotError, KeyError)):
        parse_snapshot(broken)


def test_unordered_publications_are_rejected():
    import json

    snap = json.loads(REAL.read_text())
    snap["forecasts"] = list(reversed(snap["forecasts"]))
    with pytest.raises(SnapshotError, match="ascending"):
        parse_snapshot(json.dumps(snap))
