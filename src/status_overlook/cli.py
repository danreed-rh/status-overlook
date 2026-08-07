"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from status_overlook import __version__
from status_overlook.doctor import print_doctor, run_doctor
from status_overlook.paths import all_managed_paths, track_store_path
from status_overlook.reconcile import run_reconcile
from status_overlook.store import load_store


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

    sub.add_parser("doctor", help="Check CLIs and auth")
    sub.add_parser("paths", help="Print managed file locations")

    p_rec = sub.add_parser("reconcile", help="Discover assigned work and update track store")
    p_rec.add_argument("--skip-github", action="store_true")
    p_rec.add_argument("--skip-jira", action="store_true")
    p_rec.add_argument("--dry-run", action="store_true", help="Do not write track_store.json")

    p_show = sub.add_parser("show-store", help="Print track store summary")
    p_show.add_argument("--all", action="store_true", help="Include done items")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "doctor":
        results = run_doctor()
        print_doctor(results)
        return 0 if all(r.ok for r in results) else 1

    if args.command == "paths":
        for path in all_managed_paths():
            print(path)
        print(f"track_store: {track_store_path()}")
        return 0

    if args.command == "reconcile":
        _, _, code = run_reconcile(
            skip_github=args.skip_github,
            skip_jira=args.skip_jira,
            dry_run=args.dry_run,
        )
        return code

    if args.command == "show-store":
        store = load_store()
        if not store.items:
            print(f"Empty store ({track_store_path()})")
            return 0
        print(f"updated_at: {store.updated_at}")
        for item in sorted(store.items.values(), key=lambda i: i.id):
            if item.lifecycle == "done" and not args.all:
                continue
            pin = " pin" if item.pinned else ""
            print(
                f"{item.lifecycle:6}{pin}  {item.id}  [{item.remote_status}]  {item.summary[:80]}"
            )
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
