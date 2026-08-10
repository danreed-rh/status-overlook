"""Mac LaunchAgent scheduler install/uninstall."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from status_overlook.fsutil import ensure_private_dir, write_private_text
from status_overlook.paths import (
    BUNDLE_ID,
    _is_macos,
    launch_agent_plist_path,
    launch_agents_dir,
    log_dir,
)


def parse_every(spec: str) -> int:
    """Parse interval like 15m / 900s / 1h into seconds."""
    s = (spec or "").strip().casefold()
    m = re.fullmatch(r"(\d+)\s*([smh]?)", s)
    if not m:
        raise ValueError(f"invalid interval: {spec!r} (use e.g. 15m, 900s, 1h)")
    n = int(m.group(1))
    unit = m.group(2) or "m"
    if unit == "s":
        return n
    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 3600
    raise ValueError(f"invalid interval unit in {spec!r}")


def resolve_program() -> list[str]:
    """Prefer installed console script; fall back to python -m."""
    which = shutil.which("status-overlook")
    if which:
        return [which, "run"]
    return [sys.executable, "-m", "status_overlook", "run"]


def launchd_path_env() -> str:
    parts = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    existing = os.environ.get("PATH", "")
    for p in existing.split(":"):
        if p and p not in parts:
            parts.append(p)
    return ":".join(parts)


def render_plist(*, every_seconds: int, program: list[str] | None = None) -> str:
    program = program or resolve_program()
    ensure_private_dir(log_dir())
    stdout = log_dir() / "scheduler.stdout.log"
    stderr = log_dir() / "scheduler.stderr.log"
    args_xml = "\n".join(f"    <string>{_xml_escape(a)}</string>" for a in program)
    label = f"{BUNDLE_ID}.sync"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
{args_xml}
  </array>
  <key>StartInterval</key>
  <integer>{every_seconds}</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{_xml_escape(str(stdout))}</string>
  <key>StandardErrorPath</key>
  <string>{_xml_escape(str(stderr))}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>{_xml_escape(launchd_path_env())}</string>
  </dict>
</dict>
</plist>
"""


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _gui_domain() -> str:
    return f"gui/{os.getuid()}"


def install_scheduler(*, every: str = "15m") -> int:
    if not _is_macos():
        print("install-scheduler is Mac-only in Phase 4 (Linux/Windows in Phase 5).")
        return 1
    seconds = parse_every(every)
    if seconds < 60:
        print("Refusing intervals under 60s.")
        return 1
    plist = launch_agent_plist_path()
    ensure_private_dir(launch_agents_dir())
    write_private_text(plist, render_plist(every_seconds=seconds))
    label = f"{BUNDLE_ID}.sync"
    domain = _gui_domain()
    # Unload if already loaded
    subprocess.run(
        ["launchctl", "bootout", domain, str(plist)],
        capture_output=True,
        text=True,
        check=False,
    )
    boot = subprocess.run(
        ["launchctl", "bootstrap", domain, str(plist)],
        capture_output=True,
        text=True,
        check=False,
    )
    if boot.returncode != 0:
        # Older macOS fallback
        load = subprocess.run(
            ["launchctl", "load", "-w", str(plist)],
            capture_output=True,
            text=True,
            check=False,
        )
        if load.returncode != 0:
            print(boot.stderr or boot.stdout or load.stderr or "launchctl failed")
            print(f"Plist written to {plist}; load manually if needed.")
            return 1
    print(f"Installed {label} every {seconds}s → {plist}")
    print(f"Logs: {log_dir()}/scheduler.*.log")
    return 0


def uninstall_scheduler(*, dry_run: bool = False) -> int:
    if not _is_macos():
        print("uninstall-scheduler is Mac-only in Phase 4.")
        return 1
    plist = launch_agent_plist_path()
    domain = _gui_domain()
    if dry_run:
        print(f"Would bootout {domain} and remove {plist}")
        return 0
    if plist.is_file():
        subprocess.run(
            ["launchctl", "bootout", domain, str(plist)],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["launchctl", "unload", "-w", str(plist)],
            capture_output=True,
            text=True,
            check=False,
        )
        plist.unlink(missing_ok=True)
        print(f"Removed {plist}")
    else:
        print(f"No plist at {plist}")
    return 0
