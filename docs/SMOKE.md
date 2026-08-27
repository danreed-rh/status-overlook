# Second-machine smoke (Gate 5)

Owner Mac is not enough. Run this on a **Linux** desktop or VM and a **Windows** PC (or VM) after a pipx/uv install from git.

## Short version

Install `gh` and `acli` for that OS. Install Status Overlook. `init --non-interactive` (or interactive). `run --force`. `paths`. `show --plain`. `serve --port 8766` without `--open` and fetch `/`. Optionally `install-scheduler`.

## Check

On each OS, all of these succeed:

1. `status-overlook --version` prints a version.
2. `status-overlook paths` shows that OS’s default directories (Linux XDG or `%LOCALAPPDATA%`).
3. `status-overlook run --force` exits 0 after `gh`/`acli` auth (or doctor tells you what is missing).
4. `curl http://127.0.0.1:PORT/` (or a browser) returns HTML titled Status Overlook. Use **127.0.0.1**, not `localhost`, on Windows.
5. `install-scheduler` prints the linger (Linux) or logged-in (Windows) note. The contrib templates contain no `/Users/dareed` or Homebrew-from-a-Mac PATH.

Automated coverage in this repo: `tests/test_contrib_templates.py` and scheduler **render** unit tests. They do not replace a real `schtasks` / `systemctl --user` install.

## Actions — Linux

1. Install Python 3.10+, `gh`, and `acli`. Put `acli` on `PATH`.
2. `gh auth login` and `acli jira auth login --site … --email … --token`.
3. `pipx install git+https://github.com/danreed-rh/status-overlook.git`
4. `status-overlook init` (or `--non-interactive --force` on a throwaway config).
5. `status-overlook doctor`
6. `status-overlook run --force`
7. `status-overlook show --plain | head`
8. `status-overlook serve --port 8766` then `curl -fsS http://127.0.0.1:8766/ | head`
9. `status-overlook install-scheduler --every 15m`
10. `systemctl --user status status-overlook.sync.timer`
11. Optional linger: `loginctl enable-linger "$USER"`

Copy-paste helper: [`scripts/smoke-second-machine.sh`](../scripts/smoke-second-machine.sh) — version, paths, doctor (fails the script), `run --force`, first 40 digest lines. Does **not** run `init`.

## Actions — Windows

1. `winget install GitHub.cli` and install `acli` onto user PATH. Reopen the terminal.
2. `py -3 -m pip install --user pipx` then `py -3 -m pipx ensurepath`. Reopen the terminal.
3. `pipx install git+https://github.com/danreed-rh/status-overlook.git`
4. `status-overlook init` then `doctor` then `run --force` then `paths`
5. `status-overlook serve --port 8766` and open `http://127.0.0.1:8766/` in Edge or Chrome
6. `status-overlook install-scheduler --every 15m`
7. Task Scheduler → `StatusOverlook\Sync`. If it fails, set Command to `where status-overlook`

Copy-paste helper: [`scripts/smoke-second-machine.ps1`](../scripts/smoke-second-machine.ps1)
