# Success checks (internal)

## Phase 0

- [x] Package installs in a venv; `status-overlook --version` and `paths` work
- [x] Managed paths documented; uninstall in Phase 4

## Phase 3–4

- [ ] Digests match mental model (Gate 3)
- [x] `state_changed_at` stable on no-op runs (unit-covered fingerprint)
- [x] Scheduler + uninstall leave no orphan files (Gate 4 — verify on machine)
- [ ] Public docs describe product only (Phase 5 cleanup)
