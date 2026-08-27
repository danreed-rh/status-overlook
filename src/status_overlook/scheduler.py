"""OS schedulers: macOS LaunchAgent, Linux systemd user timer, Windows Task Scheduler."""

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
    SYSTEMD_UNIT,
    WINDOWS_TASK_NAME,
    _is_linux,
    _is_macos,
    _is_windows,
    launch_agent_plist_path,
    launch_agents_dir,
    log_dir,
    systemd_service_path,
    systemd_timer_path,
    systemd_user_dir,
    windows_task_xml_path,
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


def _unix_path_env() -> str:
    """PATH for LaunchAgent / systemd so gh and acli resolve."""
    parts: list[str] = []
    if sys.platform == "darwin":
        parts.extend(["/opt/homebrew/bin", "/usr/local/bin"])
    else:
        parts.append("/usr/local/bin")
    parts.extend(
        [
            str(Path.home() / ".local" / "bin"),
            "/usr/bin",
            "/bin",
        ]
    )
    existing = os.environ.get("PATH", "")
    for p in existing.split(":"):
        if p and p not in parts:
            parts.append(p)
    return _sanitize_unix_path(":".join(parts))


def _sanitize_unix_path(raw: str) -> str:
    out: list[str] = []
    for p in raw.split(":"):
        if not p or any(c in p for c in "\n\r%"):
            continue
        out.append(p)
    return ":".join(out)


def _windows_path_env() -> str:
    parts = [
        str(Path(sys.executable).parent),
        os.environ.get("Path") or os.environ.get("PATH") or "",
    ]
    raw = ";".join(p for p in parts if p)
    out: list[str] = []
    for p in raw.split(";"):
        if not p or any(c in p for c in "\n\r&|<>^%"):
            continue
        out.append(p)
    return ";".join(out)


def _path_env() -> str:
    """PATH for scheduled jobs so gh/acli resolve."""
    if _is_windows():
        return _windows_path_env()
    return _unix_path_env()


def launchd_path_env() -> str:
    """Back-compat alias used by tests."""
    return _path_env()


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
    <string>{_xml_escape(_unix_path_env())}</string>
  </dict>
</dict>
</plist>
"""


def render_systemd_service(*, program: list[str] | None = None) -> str:
    program = program or resolve_program()
    # systemd ExecStart: quote args with spaces
    exec_start = " ".join(_systemd_quote(a) for a in program)
    return f"""[Unit]
Description=Status Overlook sync (reconcile + digests)
Documentation=https://github.com/danreed-rh/status-overlook

[Service]
Type=oneshot
ExecStart={exec_start}
Environment="PATH={_unix_path_env().replace('"', "")}"
"""


def render_systemd_timer(*, every_seconds: int) -> str:
    # Prefer OnUnitActiveSec for repeating interval after each run
    if every_seconds % 3600 == 0 and every_seconds >= 3600:
        active = f"{every_seconds // 3600}h"
    elif every_seconds % 60 == 0:
        active = f"{every_seconds // 60}min"
    else:
        active = f"{every_seconds}s"
    return f"""[Unit]
Description=Status Overlook sync timer
Documentation=https://github.com/danreed-rh/status-overlook

[Timer]
OnBootSec=2min
OnUnitActiveSec={active}
Persistent=true
Unit={SYSTEMD_UNIT}.service

[Install]
WantedBy=timers.target
"""


def render_windows_task_xml(
    *,
    every_seconds: int,
    program: list[str] | None = None,
) -> str:
    """Task Scheduler 2.0 XML (register with schtasks /Create /XML)."""
    program = program or resolve_program()
    exe = program[0]
    args = " ".join(program[1:])
    minutes = max(1, (every_seconds + 59) // 60)
    # PT15M style duration for interval
    if minutes % 60 == 0 and minutes >= 60:
        interval = f"PT{minutes // 60}H"
    else:
        interval = f"PT{minutes}M"
    path_env = _windows_path_env()
    quoted_exe = exe if exe.startswith('"') else f'"{exe}"'
    cmd_args = f'/c set "PATH={path_env}" && {quoted_exe} {args}'.strip()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Status Overlook sync (reconcile + digests)</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>{interval}</Interval>
        <Duration>P365D</Duration>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2020-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>{_xml_escape(cmd_args)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _systemd_quote(arg: str) -> str:
    if re.fullmatch(r"[-A-Za-z0-9_./:@+=]+", arg):
        return arg
    return "'" + arg.replace("'", "'\\''") + "'"


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
    try:
        seconds = parse_every(every)
    except ValueError as exc:
        print(exc)
        return 1
    if seconds < 60:
        print("Refusing intervals under 60s.")
        return 1
    if _is_macos():
        return _install_macos(seconds)
    if _is_linux():
        return _install_linux(seconds)
    if _is_windows():
        return _install_windows(seconds)
    print(f"Unsupported platform for install-scheduler: {sys.platform}")
    return 1


def uninstall_scheduler(*, dry_run: bool = False) -> int:
    if _is_macos():
        return _uninstall_macos(dry_run=dry_run)
    if _is_linux():
        return _uninstall_linux(dry_run=dry_run)
    if _is_windows():
        return _uninstall_windows(dry_run=dry_run)
    if dry_run:
        print(f"Would skip scheduler uninstall on {sys.platform}")
        return 0
    print(f"No scheduler uninstall for platform {sys.platform}")
    return 0


def _install_macos(every_seconds: int) -> int:
    plist = launch_agent_plist_path()
    ensure_private_dir(launch_agents_dir())
    write_private_text(plist, render_plist(every_seconds=every_seconds))
    label = f"{BUNDLE_ID}.sync"
    domain = _gui_domain()
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
    print(f"Installed {label} every {every_seconds}s → {plist}")
    print(f"Logs: {log_dir()}/scheduler.*.log")
    return 0


def _uninstall_macos(*, dry_run: bool) -> int:
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


def _install_linux(every_seconds: int) -> int:
    ensure_private_dir(systemd_user_dir())
    service = systemd_service_path()
    timer = systemd_timer_path()
    write_private_text(service, render_systemd_service())
    write_private_text(timer, render_systemd_timer(every_seconds=every_seconds))
    reload = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
        text=True,
        check=False,
    )
    if reload.returncode != 0:
        print(reload.stderr or reload.stdout or "systemctl daemon-reload failed")
        print(f"Units written to {service} and {timer}; enable manually if needed.")
        return 1
    enable = subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{SYSTEMD_UNIT}.timer"],
        capture_output=True,
        text=True,
        check=False,
    )
    if enable.returncode != 0:
        print(enable.stderr or enable.stdout or "systemctl enable failed")
        print(f"Units written; try: systemctl --user enable --now {SYSTEMD_UNIT}.timer")
        return 1
    print(f"Installed systemd user timer {SYSTEMD_UNIT}.timer every {every_seconds}s")
    print(f"  {timer}")
    print(f"  {service}")
    print(f"Status: systemctl --user status {SYSTEMD_UNIT}.timer")
    print("Note: systemd --user timers run while you are logged in.")
    print('  After logout/reboot, keep them running with: loginctl enable-linger "$USER"')
    return 0


def _uninstall_linux(*, dry_run: bool) -> int:
    service = systemd_service_path()
    timer = systemd_timer_path()
    if dry_run:
        print(f"Would disable {SYSTEMD_UNIT}.timer and remove:")
        print(f"  {timer}")
        print(f"  {service}")
        return 0
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{SYSTEMD_UNIT}.timer"],
        capture_output=True,
        text=True,
        check=False,
    )
    for path in (timer, service):
        if path.is_file():
            path.unlink()
            print(f"Removed {path}")
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
        text=True,
        check=False,
    )
    return 0


def _install_windows(every_seconds: int) -> int:
    xml_path = windows_task_xml_path()
    ensure_private_dir(xml_path.parent)
    # schtasks expects UTF-16 LE XML when using /XML on many Windows builds
    xml = render_windows_task_xml(every_seconds=every_seconds)
    xml_path.write_text(xml, encoding="utf-16")
    # Delete existing then create
    subprocess.run(
        ["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    create = subprocess.run(
        ["schtasks", "/Create", "/TN", WINDOWS_TASK_NAME, "/XML", str(xml_path), "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if create.returncode != 0:
        # Fallback: simple minute schedule without XML
        program = resolve_program()
        tr = subprocess.list2cmdline(program)
        minutes = max(1, (every_seconds + 59) // 60)
        create2 = subprocess.run(
            [
                "schtasks",
                "/Create",
                "/TN",
                WINDOWS_TASK_NAME,
                "/TR",
                tr,
                "/SC",
                "MINUTE",
                "/MO",
                str(minutes),
                "/F",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if create2.returncode != 0:
            print(create.stderr or create.stdout or create2.stderr or "schtasks failed")
            print(f"Task XML saved at {xml_path}; import manually if needed.")
            return 1
    print(f"Installed Windows task {WINDOWS_TASK_NAME} every {every_seconds}s")
    print(f"XML: {xml_path}")
    print("Note: the task uses InteractiveToken — it runs while you are logged in.")
    print("  If it fails to start, set Command to the full path from: where status-overlook")
    return 0


def _uninstall_windows(*, dry_run: bool) -> int:
    xml_path = windows_task_xml_path()
    if dry_run:
        print(f"Would delete task {WINDOWS_TASK_NAME} and remove {xml_path}")
        return 0
    subprocess.run(
        ["schtasks", "/Delete", "/TN", WINDOWS_TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    if xml_path.is_file():
        xml_path.unlink()
        print(f"Removed {xml_path}")
    print(f"Removed task {WINDOWS_TASK_NAME} (if it existed)")
    return 0
