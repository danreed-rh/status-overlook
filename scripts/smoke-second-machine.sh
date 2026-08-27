#!/usr/bin/env bash
# Gate 5 helper for Linux (or macOS). Does not replace a real second-machine pass.
# Does not run init (interactive). Exits non-zero if doctor fails.
set -euo pipefail

echo "== version =="
status-overlook --version

echo "== paths =="
status-overlook paths

echo "== doctor =="
status-overlook doctor

echo "== run --force =="
status-overlook run --force

echo "== show --plain (first 40 lines) =="
status-overlook show --plain | sed -n '1,40p'

echo "Next: status-overlook serve --port 8766"
echo "Then: curl -fsS http://127.0.0.1:8766/ | head"
echo "Scheduler: status-overlook install-scheduler --every 15m"
echo "Linux linger (optional): loginctl enable-linger \"\$USER\""
