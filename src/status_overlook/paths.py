"""Platform paths — macOS ~/Library; Linux XDG; Windows LOCALAPPDATA."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "status-overlook"
# launchd label / reverse-DNS style id for Mac agents and cache hygiene
BUNDLE_ID = "dev.statusoverlook"
# systemd unit basename (Linux user units)
SYSTEMD_UNIT = "status-overlook.sync"
# Windows Task Scheduler folder\name
WINDOWS_TASK_NAME = r"StatusOverlook\Sync"


def _home() -> Path:
    return Path.home()


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def config_dir() -> Path:
    """Config directory (also holds track store on Mac under Application Support)."""
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / APP_NAME
    if _is_macos():
        return _home() / "Library" / "Application Support" / APP_NAME
    if _is_windows():
        local = os.environ.get("LOCALAPPDATA") or str(_home() / "AppData" / "Local")
        return Path(local) / APP_NAME
    return _home() / ".config" / APP_NAME


def data_dir() -> Path:
    """Persistent data (track store). On Mac/Windows, same tree as config by default."""
    if os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ["XDG_DATA_HOME"]) / APP_NAME
    if _is_macos() or _is_windows():
        return config_dir()
    return _home() / ".local" / "share" / APP_NAME


def cache_dir() -> Path:
    if os.environ.get("XDG_CACHE_HOME"):
        return Path(os.environ["XDG_CACHE_HOME"]) / APP_NAME
    if _is_macos():
        return _home() / "Library" / "Caches" / APP_NAME
    if _is_windows():
        return config_dir() / "Cache"
    return _home() / ".cache" / APP_NAME


def log_dir() -> Path:
    if _is_macos() and not os.environ.get("XDG_STATE_HOME"):
        return _home() / "Library" / "Logs" / APP_NAME
    if _is_windows():
        return config_dir() / "Logs"
    state = os.environ.get("XDG_STATE_HOME")
    if state:
        return Path(state) / APP_NAME / "log"
    return _home() / ".local" / "state" / APP_NAME / "log"


def launch_agents_dir() -> Path:
    """User LaunchAgents (Mac only)."""
    return _home() / "Library" / "LaunchAgents"


def launch_agent_plist_path() -> Path:
    return launch_agents_dir() / f"{BUNDLE_ID}.sync.plist"


def systemd_user_dir() -> Path:
    """User systemd unit directory (Linux)."""
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "systemd" / "user"
    return _home() / ".config" / "systemd" / "user"


def systemd_service_path() -> Path:
    return systemd_user_dir() / f"{SYSTEMD_UNIT}.service"


def systemd_timer_path() -> Path:
    return systemd_user_dir() / f"{SYSTEMD_UNIT}.timer"


def windows_task_xml_path() -> Path:
    """Optional on-disk copy of the scheduled task XML (Windows)."""
    return data_dir() / "scheduler" / "StatusOverlook.Sync.xml"


def all_managed_paths() -> list[Path]:
    """Locations uninstall may remove (files/dirs created by this app)."""
    paths = [
        config_dir(),
        data_dir(),
        cache_dir(),
        log_dir(),
    ]
    if _is_macos():
        paths.append(launch_agent_plist_path())
    if _is_linux():
        paths.extend([systemd_service_path(), systemd_timer_path()])
    if _is_windows():
        paths.append(windows_task_xml_path())
    # de-dupe while preserving order (Mac/Win config_dir == data_dir)
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def config_path() -> Path:
    return config_dir() / "config.yaml"


def track_store_path() -> Path:
    return data_dir() / "track_store.json"


def team_members_path() -> Path:
    return data_dir() / "team_members.json"


def team_queue_path() -> Path:
    return data_dir() / "team_queue.json"


def digest_md_path() -> Path:
    return cache_dir() / "digest.md"


def digest_json_path() -> Path:
    return cache_dir() / "digest.json"


def run_log_path() -> Path:
    return log_dir() / "run.log"
