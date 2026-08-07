"""Platform paths — Mac uses ~/Library; Linux uses XDG."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "status-overlook"
# launchd label / reverse-DNS style id for Mac agents and cache hygiene
BUNDLE_ID = "dev.statusoverlook"


def _home() -> Path:
    return Path.home()


def _is_macos() -> bool:
    return sys.platform == "darwin"


def config_dir() -> Path:
    """Config directory (also holds track store on Mac under Application Support)."""
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / APP_NAME
    if _is_macos():
        return _home() / "Library" / "Application Support" / APP_NAME
    return _home() / ".config" / APP_NAME


def data_dir() -> Path:
    """Persistent data (track store). On Mac, same tree as config under Application Support."""
    if os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ["XDG_DATA_HOME"]) / APP_NAME
    if _is_macos():
        return config_dir()
    return _home() / ".local" / "share" / APP_NAME


def cache_dir() -> Path:
    if os.environ.get("XDG_CACHE_HOME"):
        return Path(os.environ["XDG_CACHE_HOME"]) / APP_NAME
    if _is_macos():
        return _home() / "Library" / "Caches" / APP_NAME
    return _home() / ".cache" / APP_NAME


def log_dir() -> Path:
    if _is_macos() and not os.environ.get("XDG_STATE_HOME"):
        return _home() / "Library" / "Logs" / APP_NAME
    state = os.environ.get("XDG_STATE_HOME")
    if state:
        return Path(state) / APP_NAME / "log"
    return _home() / ".local" / "state" / APP_NAME / "log"


def launch_agents_dir() -> Path:
    """User LaunchAgents (Mac only)."""
    return _home() / "Library" / "LaunchAgents"


def launch_agent_plist_path() -> Path:
    return launch_agents_dir() / f"{BUNDLE_ID}.sync.plist"


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
    # de-dupe while preserving order (Mac config_dir == data_dir)
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


def digest_md_path() -> Path:
    return cache_dir() / "digest.md"


def digest_json_path() -> Path:
    return cache_dir() / "digest.json"


def run_log_path() -> Path:
    return log_dir() / "run.log"
