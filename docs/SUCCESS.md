# Success checks (internal)

## Phase 0–4

- [x] Package installs in a venv; `status-overlook --version` and `paths` work
- [x] Managed paths documented; uninstall removes app data
- [x] `state_changed_at` stable on no-op runs (unit-covered fingerprint)
- [x] Mac LaunchAgent install/uninstall

## Phase 5

- [x] `pipx` / `uv tool install` documented (git URL)
- [x] Linux systemd user timer + Windows Task Scheduler (CLI + `contrib/` templates)
- [x] Windows path defaults under `%LOCALAPPDATA%`
- [x] Product README: capabilities / out-of-scope / always-out-of-scope
- [x] Optional Cursor skill: `skills/status-overlook/SKILL.md`
- [ ] Human Gate 5: second-machine smoke — skipped by owner

## Phase 6

- [x] `status-overlook serve` localhost UI (stdlib `http.server`)
- [x] Actionable / All active / Everything (+ pending/blocked/done); source filters; auto-refresh; mark-read
- [x] Same store/digest as CLI; agents still use files
- [x] Unit tests for UI digest payload + assets
