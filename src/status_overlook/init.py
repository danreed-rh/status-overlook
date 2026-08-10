"""Interactive init wizard — probe CLIs, write config.yaml."""

from __future__ import annotations

import json
import re
import subprocess

from status_overlook.config import AppConfig, load_config, save_config
from status_overlook.doctor import check_acli, check_gh, print_doctor
from status_overlook.fsutil import ensure_private_dir
from status_overlook.jira_ids import qa_field_to_jql
from status_overlook.paths import cache_dir, config_path, data_dir, log_dir


def _prompt(msg: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{msg}{suffix}: ").strip()
    return raw or default


def _prompt_yes(msg: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = input(f"{msg} ({hint}): ").strip().casefold()
    if not raw:
        return default
    return raw in {"y", "yes"}


def probe_github_login() -> str:
    proc = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip().strip('"')


def probe_jira_account_id() -> str:
    """Best-effort accountId from an assigned issue (may be empty)."""
    proc = subprocess.run(
        [
            "acli",
            "jira",
            "workitem",
            "search",
            "--jql",
            "assignee = currentUser() AND resolution = EMPTY",
            "--fields",
            "assignee",
            "--limit",
            "1",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return ""
    if not isinstance(rows, list) or not rows:
        return ""
    assignee = (rows[0].get("fields") or {}).get("assignee") or {}
    return str(assignee.get("accountId") or "")


def _guess_jira_site_from_acli() -> str:
    """Parse site from acli auth status text if present."""
    proc = subprocess.run(
        ["acli", "jira", "auth", "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    m = re.search(r"([a-z0-9-]+\.atlassian\.net)", text, re.I)
    return m.group(1).casefold() if m else ""


def run_init(*, non_interactive: bool = False, force: bool = False) -> int:
    path = config_path()
    if path.is_file() and not force:
        if non_interactive:
            print(f"Config already exists: {path} (use --force to overwrite)")
            return 1
        if not _prompt_yes(f"Config exists at {path}. Overwrite?", default=False):
            print("Aborted.")
            return 0

    print("Probing CLIs…")
    results = [check_gh(), check_acli()]
    print_doctor(results)
    if not all(r.ok for r in results):
        print("Fix auth/install above, then re-run: status-overlook init")
        return 1

    existing, _ = load_config(path if path.is_file() else None)
    login = probe_github_login() or existing.github_login
    account_id = probe_jira_account_id() or existing.jira_account_id
    guessed_site = _guess_jira_site_from_acli() or existing.jira_site or "redhat.atlassian.net"

    if non_interactive:
        site = guessed_site
        qa = existing.jira_qa_contact_field
        pr = existing.jira_pr_link_field
    else:
        print("")
        login = _prompt("GitHub login", login)
        site = _prompt("Jira site (host only)", guessed_site)
        account_id = _prompt("Jira accountId (leave blank to keep probed)", account_id)
        print("Optional custom fields (blank to skip):")
        qa = _prompt("QA contact field (customfield_NNNNN)", existing.jira_qa_contact_field)
        pr = _prompt("PR link field (customfield_NNNNN)", existing.jira_pr_link_field)

    if qa and qa_field_to_jql(qa) is None:
        print(f"Warning: QA field {qa!r} is not customfield_<digits>; discovery will skip it.")

    cfg = AppConfig(
        github_login=login,
        jira_site=site.strip().removeprefix("https://").removesuffix("/"),
        jira_account_id=account_id.strip(),
        jira_qa_contact_field=qa.strip(),
        jira_pr_link_field=pr.strip(),
        actionable_labels=existing.actionable_labels,
        status_blocked=existing.status_blocked,
        blocked_labels=existing.blocked_labels,
        status_testing=existing.status_testing,
        status_active=existing.status_active,
        status_review=existing.status_review,
        status_done=existing.status_done,
        pins_jira=existing.pins_jira,
        pins_github=existing.pins_github,
        done_retention_days=existing.done_retention_days,
        search_limit=existing.search_limit,
    )

    ensure_private_dir(data_dir())
    ensure_private_dir(cache_dir())
    ensure_private_dir(log_dir())
    out = save_config(cfg, path)
    print(f"Wrote {out}")
    if not cfg.jira_account_id:
        print(
            "Note: Jira accountId empty — QA matching may be incomplete until "
            "you have an assigned issue or set jira.account_id manually."
        )
    print("Next: status-overlook run")
    return 0
