"""Consistent online SQLite backup; caller supplies a protected destination."""
import argparse
import os
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("destination", type=Path)
parser.add_argument("--source", type=Path,
                    default=Path(os.getenv("MG_STATE_PATH", ".runtime/state.sqlite")))
args = parser.parse_args()
if args.destination.exists() or not args.source.is_file():
    raise SystemExit("Refusing overwrite or missing source.")
args.destination.parent.mkdir(parents=True, exist_ok=True)
with sqlite3.connect(f"file:{args.source.as_posix()}?mode=ro", uri=True) as source:
    with sqlite3.connect(args.destination) as destination:
        source.backup(destination)
        assert destination.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("Consistent state backup created; encrypt and restrict access before exporting.")
