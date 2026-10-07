"""Record a correction candidate through the existing project lesson store."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from app.corrections import propose_correction


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{Path(sys.argv[0]).name} correction",
        description="Save an inactive regression proposal; no check or action is executed.",
    )
    parser.add_argument("--project", required=True, help="Stable project ID for the existing lesson store")
    parser.add_argument("--revision", required=True, help="Code revision to which this proposal applies")
    parser.add_argument("--failure", required=True, help="Observed failure")
    parser.add_argument("--correction", required=True, help="Proposed correction")
    parser.add_argument("--check", required=True, help="Proposed regression check, stored as text")
    parser.add_argument("--evidence", required=True, action="append", nargs=2,
                        metavar=("REF", "SHA256"), help="Supplied reference and hash; repeat up to four times")
    parser.add_argument("--session", default="", help="Optional source session ID")
    parser.add_argument("--db", type=Path, help="Operator-selected lesson database; created if absent")
    args = parser.parse_args(argv)
    try:
        report = propose_correction(
            args.project, args.failure, args.correction, args.check, args.revision,
            [{"ref": ref, "sha256": checksum} for ref, checksum in args.evidence],
            args.session, db_path=args.db,
        )
        print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({"error": str(error), "execution_allowed": False}), file=sys.stderr)
        return 2
