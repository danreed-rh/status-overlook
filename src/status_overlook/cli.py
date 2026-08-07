"""CLI entrypoint. Phase 0: version / placeholder only."""

from __future__ import annotations

import argparse
import sys

from status_overlook import __version__
from status_overlook.paths import all_managed_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="status-overlook",
        description="Overlook your Jira and GitHub work status.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="Check CLIs, auth, and config (later phase)")
    sub.add_parser("paths", help="Print managed file locations")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "doctor":
        print("doctor: not implemented yet.")
        return 0
    if args.command == "paths":
        for path in all_managed_paths():
            print(path)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
