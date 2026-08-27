# Gate 5 helper for Windows PowerShell. Does not replace a real second-machine pass.
# Does not run init (interactive). Stops if doctor fails.
$ErrorActionPreference = "Stop"

Write-Host "== version =="
status-overlook --version

Write-Host "== paths =="
status-overlook paths

Write-Host "== doctor =="
status-overlook doctor

Write-Host "== run --force =="
status-overlook run --force

Write-Host "== show --plain =="
status-overlook show --plain | Select-Object -First 40

Write-Host "Next: status-overlook serve --port 8766"
Write-Host "Open http://127.0.0.1:8766/ (not localhost) in Edge or Chrome"
Write-Host "Scheduler: status-overlook install-scheduler --every 15m"
Write-Host "If the task fails: where status-overlook  — use that full path as Command"
