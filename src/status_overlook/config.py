"""Load/save Status Overlook config (YAML) with safe defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from status_overlook.fsutil import write_private_text
from status_overlook.models import ClassifyConfig
from status_overlook.paths import config_path


@dataclass
class AppConfig:
    github_login: str = ""
    actionable_labels: tuple[str, ...] = ("lgtm",)
    jira_site: str = ""
    jira_account_id: str = ""
    jira_qa_contact_field: str = ""
    jira_pr_link_field: str = ""
    status_blocked: tuple[str, ...] = ("Blocked",)
    blocked_labels: tuple[str, ...] = ("blocked",)
    status_testing: tuple[str, ...] = ("Testing",)
    status_active: tuple[str, ...] = ("New", "To Do", "In Progress")
    status_review: tuple[str, ...] = ("Review", "In Review", "Code Review")
    status_done: tuple[str, ...] = ("Resolved", "Closed", "Done")
    pins_jira: tuple[str, ...] = ()
    pins_github: tuple[str, ...] = ()  # org/repo#n
    done_retention_days: int = 7
    search_limit: int = 50
    raw: dict[str, Any] = field(default_factory=dict)

    def classify_config(self) -> ClassifyConfig:
        return ClassifyConfig(
            status_active=self.status_active,
            status_review=self.status_review,
            status_testing=self.status_testing,
            status_done=self.status_done,
            status_blocked=self.status_blocked,
            blocked_labels=self.blocked_labels,
            actionable_labels=self.actionable_labels,
        )


def _as_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    return tuple(str(x) for x in value)


def load_config(path: Path | None = None) -> tuple[AppConfig, Path | None]:
    """Return config and the path loaded (None if defaults only)."""
    path = path or config_path()
    if not path.is_file():
        return AppConfig(), None

    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "PyYAML is required to read config.yaml. Install with: pip install pyyaml"
        ) from exc

    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"Config must be a mapping: {path}")

    github = data.get("github") or {}
    jira = data.get("jira") or {}
    pins = data.get("pins") or {}

    cfg = AppConfig(
        github_login=str(github.get("login") or ""),
        actionable_labels=_as_tuple(github.get("actionable_labels"), ("lgtm",)),
        jira_site=str(jira.get("site") or ""),
        jira_account_id=str(jira.get("account_id") or ""),
        jira_qa_contact_field=str(jira.get("qa_contact_field") or ""),
        jira_pr_link_field=str(jira.get("pr_link_field") or ""),
        status_blocked=_as_tuple(jira.get("status_blocked"), ("Blocked",)),
        blocked_labels=_as_tuple(jira.get("blocked_labels"), ("blocked",)),
        status_testing=_as_tuple(jira.get("status_testing"), ("Testing",)),
        status_active=_as_tuple(
            jira.get("status_active"), ("New", "To Do", "In Progress")
        ),
        status_review=_as_tuple(
            jira.get("status_review"), ("Review", "In Review", "Code Review")
        ),
        status_done=_as_tuple(jira.get("status_done"), ("Resolved", "Closed", "Done")),
        pins_jira=_as_tuple(pins.get("jira"), ()),
        pins_github=_as_tuple(pins.get("github"), ()),
        done_retention_days=int(data.get("done_retention_days") or 7),
        search_limit=int(data.get("search_limit") or 50),
        raw=data,
    )
    return cfg, path


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    """Write config.yaml with private permissions."""
    import yaml

    path = path or config_path()
    data = {
        "schema_version": 1,
        "github": {
            "login": cfg.github_login,
            "actionable_labels": list(cfg.actionable_labels),
        },
        "jira": {
            "site": cfg.jira_site,
            "account_id": cfg.jira_account_id,
            "qa_contact_field": cfg.jira_qa_contact_field,
            "pr_link_field": cfg.jira_pr_link_field,
            "status_blocked": list(cfg.status_blocked),
            "blocked_labels": list(cfg.blocked_labels),
            "status_testing": list(cfg.status_testing),
            "status_active": list(cfg.status_active),
            "status_review": list(cfg.status_review),
            "status_done": list(cfg.status_done),
        },
        "pins": {
            "jira": list(cfg.pins_jira),
            "github": list(cfg.pins_github),
        },
        "done_retention_days": cfg.done_retention_days,
        "search_limit": cfg.search_limit,
        "scheduler": {"every_minutes": 15},
    }
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    write_private_text(path, text)
    return path
