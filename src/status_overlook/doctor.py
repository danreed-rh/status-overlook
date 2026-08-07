"""CLI presence and auth checks with actionable login hints."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    hint: str = ""


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def check_gh() -> CheckResult:
    if not shutil.which("gh"):
        return CheckResult(
            name="gh",
            ok=False,
            detail="not found on PATH",
            hint="Install GitHub CLI: https://cli.github.com/ — e.g. brew install gh",
        )
    auth = _run(["gh", "auth", "status"])
    if auth.returncode != 0:
        return CheckResult(
            name="gh",
            ok=False,
            detail=(auth.stderr or auth.stdout or "not authenticated").strip(),
            hint="Run: gh auth login",
        )
    login = _run(["gh", "api", "user", "--jq", ".login"])
    who = (login.stdout or "").strip() or "authenticated"
    return CheckResult(name="gh", ok=True, detail=who)


def check_acli() -> CheckResult:
    if not shutil.which("acli"):
        return CheckResult(
            name="acli",
            ok=False,
            detail="not found on PATH",
            hint=(
                "Install Atlassian CLI: "
                "https://developer.atlassian.com/cloud/acli/guides/install-acli/"
            ),
        )
    # Prefer a cheap authenticated call
    probe = _run(
        [
            "acli",
            "jira",
            "workitem",
            "search",
            "--jql",
            "assignee = currentUser() AND resolution = EMPTY",
            "--limit",
            "1",
            "--fields",
            "key",
            "--json",
        ]
    )
    if probe.returncode != 0:
        err = (probe.stderr or probe.stdout or "acli jira call failed").strip()
        hint = "Run: acli jira auth login --site <yoursite.atlassian.net> --email <you@example.com> --token"
        if "auth" in err.lower() or "unauthorized" in err.lower() or "401" in err:
            hint = (
                "Authenticate Jira, e.g.\n"
                "  acli jira auth login --site redhat.atlassian.net --email YOU@redhat.com --token"
            )
        return CheckResult(name="acli", ok=False, detail=err, hint=hint)
    return CheckResult(name="acli", ok=True, detail="jira search ok")


def run_doctor(*, require_gh: bool = True, require_acli: bool = True) -> list[CheckResult]:
    results = [check_gh(), check_acli()]
    return results


def doctor_ok(results: list[CheckResult], *, require_gh: bool, require_acli: bool) -> bool:
    by = {r.name: r for r in results}
    if require_gh and not by["gh"].ok:
        return False
    if require_acli and not by["acli"].ok:
        return False
    return True


def print_doctor(results: list[CheckResult]) -> None:
    for r in results:
        status = "ok" if r.ok else "FAIL"
        print(f"{r.name}: {status} — {r.detail}")
        if not r.ok and r.hint:
            print(f"  → {r.hint}")
