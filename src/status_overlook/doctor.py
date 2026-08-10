"""CLI presence and auth checks with actionable login hints."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

from status_overlook.config import AppConfig, load_config
from status_overlook.jira_ids import qa_field_to_jql, safe_jql_status


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
            detail=(auth.stderr or auth.stdout or "not authenticated").strip()[:200],
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
        err = (probe.stderr or probe.stdout or "acli jira call failed").strip()[:200]
        hint = (
            "Authenticate Jira, e.g.\n"
            "  acli jira auth login --site YOUR.atlassian.net --email YOU@example.com --token"
        )
        return CheckResult(name="acli", ok=False, detail=err, hint=hint)
    return CheckResult(name="acli", ok=True, detail="jira search ok")


def check_jira_config(cfg: AppConfig) -> CheckResult:
    if not cfg.jira_site:
        return CheckResult(
            name="jira.site",
            ok=True,
            detail="not set — run init for browse URLs",
            hint="status-overlook init",
        )
    detail = cfg.jira_site
    if cfg.jira_account_id:
        detail += " + account_id"
    else:
        detail += " (account_id empty — QA match limited)"
    return CheckResult(name="jira.site", ok=True, detail=detail)


def check_qa_field(cfg: AppConfig) -> CheckResult | None:
    if not cfg.jira_qa_contact_field:
        return None
    jql_cf = qa_field_to_jql(cfg.jira_qa_contact_field)
    if jql_cf is None:
        return CheckResult(
            name="jira.qa_contact_field",
            ok=False,
            detail=f"invalid id {cfg.jira_qa_contact_field!r}",
            hint="Use customfield_<digits> (e.g. customfield_10470)",
        )
    statuses = []
    for s in cfg.status_testing:
        cleaned = safe_jql_status(s)
        if cleaned:
            statuses.append(cleaned)
    if not statuses:
        return CheckResult(
            name="jira.qa_contact_field",
            ok=False,
            detail="no safe status_testing values",
            hint="Fix jira.status_testing in config.yaml",
        )
    status_list = ", ".join(f'"{s}"' for s in statuses)
    jql = f"{jql_cf} = currentUser() AND status in ({status_list}) AND resolution = EMPTY"
    probe = _run(
        [
            "acli",
            "jira",
            "workitem",
            "search",
            "--jql",
            jql,
            "--limit",
            "1",
            "--fields",
            "key",
            "--json",
        ]
    )
    if probe.returncode != 0:
        err = (probe.stderr or probe.stdout or "QA JQL failed").strip()[:200]
        return CheckResult(
            name="jira.qa_contact_field",
            ok=False,
            detail=err,
            hint="Check field id on your site or clear qa_contact_field",
        )
    try:
        rows = json.loads(probe.stdout or "[]")
        n = len(rows) if isinstance(rows, list) else 0
    except json.JSONDecodeError:
        n = 0
    return CheckResult(
        name="jira.qa_contact_field",
        ok=True,
        detail=f"{cfg.jira_qa_contact_field} ok ({n} sample hit(s))",
    )


def run_doctor(
    *,
    require_gh: bool = True,
    require_acli: bool = True,
    cfg: AppConfig | None = None,
) -> list[CheckResult]:
    if cfg is None:
        cfg, _ = load_config()
    results: list[CheckResult] = []
    if require_gh:
        results.append(check_gh())
    if require_acli:
        results.append(check_acli())
        results.append(check_jira_config(cfg))
        qa = check_qa_field(cfg)
        if qa is not None:
            results.append(qa)
    return results


def doctor_ok(results: list[CheckResult], *, require_gh: bool, require_acli: bool) -> bool:
    by = {r.name: r for r in results}
    if require_gh and by.get("gh") and not by["gh"].ok:
        return False
    if require_acli and by.get("acli") and not by["acli"].ok:
        return False
    if require_acli and by.get("jira.qa_contact_field") and not by["jira.qa_contact_field"].ok:
        return False
    return True


def print_doctor(results: list[CheckResult]) -> None:
    for r in results:
        status = "ok" if r.ok else "FAIL"
        print(f"{r.name}: {status} — {r.detail}")
        if not r.ok and r.hint:
            print(f"  → {r.hint}")
