#!/usr/bin/env python3
"""Fail if a data or office file is tracked (or staged) outside the fake test fixtures.

Protects against committing real RMS exports. Usage:

    python scripts/check_no_data_files.py            # check every tracked file
    python scripts/check_no_data_files.py FILE ...   # check the given files (pre-commit)
"""

import subprocess
import sys
from pathlib import PurePosixPath

BLOCKED_SUFFIXES = {
    ".xlsx", ".xlsm", ".xls", ".xlsb", ".csv", ".tsv", ".parquet",
    ".pkl", ".pickle", ".docx", ".pptx", ".pdf", ".zip",
}  # fmt: skip
ALLOWED_PREFIX = "backend/tests/fixtures/"
BLOCKED_DIRS = {"legacy", "legacy-data", "uploads", "local-data"}


def is_blocked(path: str) -> bool:
    posix = PurePosixPath(path)
    if path.startswith(ALLOWED_PREFIX):
        return False
    if BLOCKED_DIRS.intersection(posix.parts):
        return True
    return posix.suffix.lower() in BLOCKED_SUFFIXES


def tracked_files() -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "--cached"], capture_output=True, text=True, check=True
    ).stdout
    return [line for line in output.splitlines() if line]


def main(argv: list[str]) -> int:
    files = argv or tracked_files()
    blocked = sorted(path for path in files if is_blocked(path))
    if blocked:
        print("Data files must not be committed (only fake fixtures in backend/tests/fixtures/):")
        for path in blocked:
            print(f"  {path}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
