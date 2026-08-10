"""Remove scheduler + managed app data directories."""

from __future__ import annotations

import shutil

from status_overlook.paths import all_managed_paths, launch_agent_plist_path
from status_overlook.scheduler import uninstall_scheduler


def run_uninstall(*, dry_run: bool = False, yes: bool = False) -> int:
    paths = all_managed_paths()
    print("Managed paths:")
    for p in paths:
        exists = "exists" if p.exists() else "missing"
        print(f"  {p}  ({exists})")

    if dry_run:
        print("Dry run — nothing removed.")
        return 0

    if not yes:
        reply = input("Remove scheduler + all Status Overlook data above? [y/N]: ").strip()
        if reply.casefold() not in {"y", "yes"}:
            print("Aborted.")
            return 0

    uninstall_scheduler(dry_run=False)

    # Remove dirs (config_dir == data_dir on Mac)
    removed: list[str] = []
    for p in paths:
        if p == launch_agent_plist_path():
            continue
        if not p.exists():
            continue
        if p.is_dir():
            shutil.rmtree(p)
            removed.append(str(p))
        elif p.is_file():
            p.unlink()
            removed.append(str(p))

    if removed:
        print("Removed:")
        for r in removed:
            print(f"  {r}")
    else:
        print("Nothing left to remove.")
    # Note: pipx/uv tool uninstall is separate
    print("Tool binary not removed — use pipx uninstall status-overlook (or your install method).")
    return 0
