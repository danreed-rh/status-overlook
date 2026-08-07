"""Core domain types for classification (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Source(str, Enum):
    JIRA = "jira"
    GITHUB = "github"


class Lifecycle(str, Enum):
    """Whether the tool still actively tracks the item."""

    ACTIVE = "active"
    DONE = "done"
    UNTRACKED = "untracked"


class ActionState(str, Enum):
    """What the digest should tell the user to do."""

    ACTIONABLE = "actionable"
    PENDING = "pending"
    DONE = "done"
    # Not shown as needing attention; still may be stored
    IGNORE = "ignore"


@dataclass(frozen=True)
class ClassificationResult:
    lifecycle: Lifecycle
    action: ActionState
    reasons: tuple[str, ...] = ()
    blocked: bool = False

    @property
    def should_track(self) -> bool:
        return self.lifecycle == Lifecycle.ACTIVE


@dataclass
class JiraIssueSnapshot:
    """Normalized Jira fields used for rules (filled by providers later)."""

    key: str
    status: str
    assignee_is_user: bool = False
    qa_contact_is_user: bool = False
    blocked: bool = False
    labels: tuple[str, ...] = ()
    pr_link: str | None = None


@dataclass
class GitHubPrSnapshot:
    """Normalized GitHub PR fields used for rules."""

    repo: str
    number: int
    state: str  # open | closed
    merged: bool = False
    draft: bool = False
    author_is_user: bool = False
    assignee_is_user: bool = False
    labels: tuple[str, ...] = ()
    linked_jira_blocked: bool = False


@dataclass(frozen=True)
class ClassifyConfig:
    """Status names and labels — site-specific; defaults are common English names."""

    status_active: tuple[str, ...] = ("New", "To Do", "In Progress")
    status_review: tuple[str, ...] = ("Review", "In Review", "Code Review")
    status_testing: tuple[str, ...] = ("Testing",)
    status_done: tuple[str, ...] = ("Resolved", "Closed", "Done")
    # Extra status names treated as blocked (in addition to snapshot.blocked)
    status_blocked: tuple[str, ...] = ("Blocked",)
    actionable_labels: tuple[str, ...] = ("lgtm", "/lgtm")
    # Case-insensitive label match
    label_match_case_insensitive: bool = True

    def status_in(self, status: str, group: tuple[str, ...]) -> bool:
        return status.casefold() in {s.casefold() for s in group}
