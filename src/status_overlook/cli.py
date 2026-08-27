"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys

from status_overlook import __version__
from status_overlook.digest import build_digest_markdown, is_unread, mark_read, write_digests
from status_overlook.doctor import print_doctor, run_doctor
from status_overlook.init import run_init
from status_overlook.paths import all_managed_paths, digest_md_path, track_store_path
from status_overlook.reconcile import run_reconcile
from status_overlook.run import run_pipeline
from status_overlook.scheduler import install_scheduler, uninstall_scheduler
from status_overlook.serve import run_serve
from status_overlook.store import load_store, save_store
from status_overlook.uninstall import run_uninstall


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

    p_init = sub.add_parser("init", help="Probe CLIs and write config.yaml")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing config")
    p_init.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use probed defaults without prompts",
    )

    p_doc = sub.add_parser("doctor", help="Check CLIs, auth, and config")
    p_doc.add_argument("--skip-github", action="store_true")
    p_doc.add_argument("--skip-jira", action="store_true")

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
    p_run.add_argument(
        "--force",
        action="store_true",
        help="Run even outside configured working hours",
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
    p_show.add_argument(
        "--plain",
        action="store_true",
        help="Print markdown digest (agent/file format) instead of terminal layout",
    )
    p_show.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Include reasons, relative time, full key/url",
    )

    p_mr = sub.add_parser("mark-read", help="Mark items as read (clears ● unread)")
    p_mr.add_argument("ids", nargs="*", help="Item ids (e.g. jira:RHOAIENG-1)")
    p_mr.add_argument("--all", action="store_true", help="Mark every item read")

    p_is = sub.add_parser(
        "install-scheduler",
        help="Install OS user scheduler (macOS LaunchAgent, Linux systemd, Windows Task)",
    )
    p_is.add_argument(
        "--every",
        default="15m",
        help="Interval (e.g. 15m, 900s, 1h). Default 15m",
    )

    p_us = sub.add_parser("uninstall-scheduler", help="Remove OS user scheduler")
    p_us.add_argument("--dry-run", action="store_true")

    p_un = sub.add_parser("uninstall", help="Remove scheduler + app data dirs")
    p_un.add_argument("--dry-run", action="store_true")
    p_un.add_argument("-y", "--yes", action="store_true", help="Do not prompt")

    p_serve = sub.add_parser(
        "serve",
        help="Local personal web UI (localhost only)",
    )
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind address (localhost only)")
    p_serve.add_argument("--port", type=int, default=8765, help="Port (default 8765)")
    p_serve.add_argument(
        "--open",
        action="store_true",
        help="Open the UI in your default browser",
    )
    p_serve.add_argument(
        "--ignore-working-hours",
        action="store_true",
        help="Start and stay up outside configured working hours",
    )

    # Back-compat alias
    p_ss = sub.add_parser("show-store", help=argparse.SUPPRESS)
    p_ss.add_argument("--all", action="store_true")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        return run_init(non_interactive=args.non_interactive, force=args.force)

    if args.command == "doctor":
        results = run_doctor(
            require_gh=not args.skip_github,
            require_acli=not args.skip_jira,
        )
        print_doctor(results)
        from status_overlook.doctor import doctor_ok

        return 0 if doctor_ok(
            results,
            require_gh=not args.skip_github,
            require_acli=not args.skip_jira,
        ) else 1

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
            force=args.force,
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

        md = build_digest_markdown(store)
        if getattr(args, "plain", False):
            if args.since_read or args.section:
                from status_overlook.digest import _format_group_line, _section_groups

                sections = (
                    [
                        ("Actionable", "actionable"),
                        ("Pending", "pending"),
                        ("Blocked", "blocked"),
                        ("Recently done", "done"),
                    ]
                    if not args.section
                    else [(args.section.title(), args.section)]
                )
                lines = ["# Status Overlook", ""]
                for title, action in sections:
                    groups = _section_groups(store, action)
                    if args.since_read:
                        groups = [g for g in groups if g.is_unread()]
                    lines.append(f"## {title}")
                    lines.append("")
                    if not groups:
                        lines.append("_None_")
                    else:
                        for group in groups:
                            lines.append(_format_group_line(group))
                    lines.append("")
                print("\n".join(lines).rstrip())
            else:
                path = digest_md_path()
                if path.is_file():
                    print(path.read_text(encoding="utf-8"), end="")
                else:
                    print(md, end="")
            return 0

        from status_overlook.term_show import format_terminal_digest, use_color

        print(
            format_terminal_digest(
                store,
                color=use_color(),
                verbose=getattr(args, "verbose", False),
                since_read=args.since_read,
                section=args.section,
            ),
            end="",
        )
        return 0

    if args.command == "mark-read":
        store = load_store()
        n = mark_read(store, ids=list(args.ids) or None, all_items=args.all)
        save_store(store)
        write_digests(store)
        print(f"Marked {n} item(s) read")
        return 0

    if args.command == "install-scheduler":
        return install_scheduler(every=args.every)

    if args.command == "uninstall-scheduler":
        return uninstall_scheduler(dry_run=args.dry_run)

    if args.command == "uninstall":
        return run_uninstall(dry_run=args.dry_run, yes=args.yes)

    if args.command == "serve":
        return run_serve(
            host=args.host,
            port=args.port,
            open_browser=args.open,
            ignore_working_hours=args.ignore_working_hours,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
