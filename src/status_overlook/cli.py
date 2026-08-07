"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from status_overlook import __version__
from status_overlook.digest import build_digest_markdown, is_unread, mark_read, write_digests
from status_overlook.doctor import print_doctor, run_doctor
from status_overlook.paths import all_managed_paths, digest_md_path, track_store_path
from status_overlook.reconcile import run_reconcile
from status_overlook.run import run_pipeline
from status_overlook.store import load_store, save_store


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

    p_run = sub.add_parser("run", help="Reconcile, enrich, classify, and write digests")
    p_run.add_argument("--skip-github", action="store_true")
    p_run.add_argument("--skip-jira", action="store_true")
    p_run.add_argument(
        "--skip-reconcile",
        action="store_true",
        help="Enrich existing store only",
    )

    p_show = sub.add_parser("show", help="Show digest (or store with --store)")
    p_show.add_argument("--store", action="store_true", help="Raw track store view")
    p_show.add_argument("--all", action="store_true", help="Include done items (store mode)")
    p_show.add_argument(
        "--since-read",
        action="store_true",
        help="Only items changed since last mark-read",
    )
    p_show.add_argument(
        "--section",
        choices=("actionable", "blocked", "pending", "done"),
        help="Filter digest section",
    )

    p_mr = sub.add_parser("mark-read", help="Mark items as read (clears ● unread)")
    p_mr.add_argument("ids", nargs="*", help="Item ids (e.g. jira:RHOAIENG-1)")
    p_mr.add_argument("--all", action="store_true", help="Mark every item read")

    # Back-compat alias
    p_ss = sub.add_parser("show-store", help=argparse.SUPPRESS)
    p_ss.add_argument("--all", action="store_true")

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
        print(f"digest: {digest_md_path()}")
        return 0

    if args.command == "reconcile":
        _, _, code = run_reconcile(
            skip_github=args.skip_github,
            skip_jira=args.skip_jira,
            dry_run=args.dry_run,
        )
        return code

    if args.command == "run":
        return run_pipeline(
            skip_github=args.skip_github,
            skip_jira=args.skip_jira,
            skip_reconcile=args.skip_reconcile,
        )

    if args.command in ("show", "show-store"):
        store = load_store()
        if not store.items:
            print(f"Empty store ({track_store_path()})")
            return 0
        use_store = args.command == "show-store" or getattr(args, "store", False)
        if use_store:
            print(f"updated_at: {store.updated_at}")
            for item in sorted(store.items.values(), key=lambda i: i.id):
                if item.lifecycle == "done" and not args.all:
                    continue
                pin = " pin" if item.pinned else ""
                unread = " ●" if is_unread(item) else ""
                action = item.action or "-"
                print(
                    f"{item.lifecycle:6} {action:10}{unread}{pin}  {item.id}  "
                    f"[{item.remote_status}]  {item.summary[:70]}"
                )
            return 0

        # Digest mode
        md = build_digest_markdown(store)
        if args.since_read or args.section:
            # Filter via JSON-ish rebuild
            from status_overlook.digest import _section_items, _format_line

            sections = (
                [("Actionable", "actionable"), ("Blocked", "blocked"), ("Pending", "pending"), ("Recently done", "done")]
                if not args.section
                else [(args.section.title(), args.section)]
            )
            lines = ["# Status Overlook", ""]
            for title, action in sections:
                items = _section_items(store, action)
                if args.since_read:
                    items = [i for i in items if is_unread(i)]
                lines.append(f"## {title}")
                lines.append("")
                if not items:
                    lines.append("_None_")
                else:
                    for item in items:
                        lines.append(_format_line(item))
                lines.append("")
            print("\n".join(lines).rstrip())
        else:
            path = digest_md_path()
            if path.is_file():
                print(path.read_text(encoding="utf-8"), end="")
            else:
                print(md, end="")
        return 0

    if args.command == "mark-read":
        store = load_store()
        n = mark_read(store, ids=list(args.ids) or None, all_items=args.all)
        save_store(store)
        write_digests(store)
        print(f"Marked {n} item(s) read")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
