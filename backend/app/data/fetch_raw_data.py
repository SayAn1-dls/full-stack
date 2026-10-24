"""Install the 18 audited raw files into data/raw/, verifying SHA-256 before anything is written.

    python -m app.data.fetch_raw_data

Source: the Kaggle bundle "Electricity Consumption UK 2009-2024" (albertovidalrod, ODbL 1.0), the only place
that still serves the audited bytes for 2019-2024 -- NESO re-published those years on 2025-04-08 and the
current official files have different hashes (see docs/DATA_CLEANING_REPORT.md). Files 2009-2018 are
byte-identical to NESO's current downloads.

Existing files that already verify are left alone; existing files that do not verify are never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from app.data.clean_demand import REPO_ROOT, load_expected_hashes, sha256_file

KAGGLE_BUNDLE_URL = "https://www.kaggle.com/api/v1/datasets/download/albertovidalrod/electricity-consumption-uk-20092022"


def fetch(raw_dir: Path, url: str = KAGGLE_BUNDLE_URL) -> int:
    expected = load_expected_hashes()
    raw_dir.mkdir(parents=True, exist_ok=True)
    todo = []
    for name, sha in expected.items():
        target = raw_dir / name
        if not target.exists():
            todo.append(name)
        elif sha256_file(target) != sha:
            print(f"REFUSING to overwrite {target}: present but SHA-256 differs from the audited file", file=sys.stderr)
            return 1
    if not todo:
        print(f"all {len(expected)} raw files already present and verified in {raw_dir}")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "bundle.zip"
        print(f"downloading {url} ...")
        with urllib.request.urlopen(url, timeout=300) as response, open(archive, "wb") as out:
            shutil.copyfileobj(response, out)
        extracted = Path(tmp) / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            members = {Path(i.filename).name: i for i in bundle.infolist() if not i.is_dir()}
            for name in todo:
                if name not in members:
                    print(f"bundle does not contain {name}", file=sys.stderr)
                    return 1
                data = bundle.read(members[name])  # read by member, never extractall: no path traversal
                if hashlib.sha256(data).hexdigest() != expected[name]:
                    print(f"bundle copy of {name} does not match the audited SHA-256", file=sys.stderr)
                    return 1
                (extracted / name).write_bytes(data)
        for name in todo:
            target = raw_dir / name
            shutil.copyfile(extracted / name, target)
            target.chmod(0o444)
            print(f"installed {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install hash-verified NESO raw files into data/raw/.")
    parser.add_argument("--raw-dir", type=Path, default=REPO_ROOT / "data" / "raw")
    args = parser.parse_args(argv)
    return fetch(args.raw_dir)


if __name__ == "__main__":
    sys.exit(main())
