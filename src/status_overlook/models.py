"""Core domain types for classification (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Source(str, Enum):
    JIRA = "jira"
    GITHUB = "github_pr"  # legacy alias name kept; value is github_pr
    GITHUB_PR = "github_pr"
    GITHUB_ISSUE = "github_issue"


class Lifecycle(str, Enum):
    """Whether the tool still actively tracks the item."""

    ACTIVE = "active"
    DONE = "done"
    UNTRACKED = "untracked"


class ActionState(str, Enum):
    """What the digest should tell the user about the item."""

    ACTIONABLE = "actionable"
    PENDING = "pending"
    BLOCKED = "blocked"
    DONE = "done"
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
    # Jira Software Flagged / impediment (board "blocked" flag)
    flagged: bool = False
    labels: tuple[str, ...] = ()
    pr_link: str | None = None
    # True when Git Pull Request field points at a merged GitHub PR.
    # None = not probed / no usable PR URL / probe failed.
    linked_pr_merged: bool | None = None
    # True when an "is blocked by" issue link points at a non-terminal issue.
    blocked_by_unresolved: bool = False
    # Issue type name (e.g. Epic, Story). Case-insensitive Epic check in classify.
    issue_type: str = ""
    # For Epics only: True when every child is done/resolved/closed.
    # None = not an epic, or children not fetched yet (treat as not-all-done).
    epic_children_all_done: bool | None = None


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
    # Provider-filled: CHANGES_REQUESTED and/or any unresolved inline review threads
    has_unresolved_reviews: bool = False
    ci_failed: bool = False
    # User (assignee/reviewer) posted /lgtm or applied an actionable label
    user_gave_lgtm: bool = False
    # User started at least one inline review thread that is still unresolved.
    # None = probe failed / unknown — classify fail-closed as pending.
    assignee_unresolved_threads: bool | None = False


@dataclass
class GitHubIssueSnapshot:
    """Normalized GitHub Issue fields used for rules."""

    repo: str
    number: int
    state: str  # open | closed
    assignee_is_user: bool = False
    labels: tuple[str, ...] = ()
    linked_pr_open: bool = False
    # True when a linked PR is merged and none remain open.
    # None = not probed / probe failed.
    linked_pr_merged: bool | None = None
    linked_jira_blocked: bool = False
    # Best open (or merged) PR URL for digest pairing via TrackedItem.pr_link
    pr_link: str | None = None


@dataclass(frozen=True)
class ClassifyConfig:
    """Status names and labels — site-specific; defaults are common English names."""

    status_active: tuple[str, ...] = ("New", "To Do", "In Progress")
    status_review: tuple[str, ...] = ("Review", "In Review", "Code Review")
    status_testing: tuple[str, ...] = ("Testing",)
    status_done: tuple[str, ...] = ("Resolved", "Closed", "Done")
    # Blocked if ANY of: status in this set, label in blocked_labels, flagged=True,
    # or unresolved "is blocked by" issue link (see blocked_by_unresolved on snapshot)
    status_blocked: tuple[str, ...] = ("Blocked",)
    blocked_labels: tuple[str, ...] = ("blocked",)
    # Ready-to-merge style labels on open PRs
    actionable_labels: tuple[str, ...] = ("lgtm",)
    label_match_case_insensitive: bool = True

    def status_in(self, status: str, group: tuple[str, ...]) -> bool:
        return status.casefold() in {s.casefold() for s in group}

    def label_in(self, labels: tuple[str, ...], group: tuple[str, ...]) -> bool:
        if self.label_match_case_insensitive:
            have = {x.casefold() for x in labels}
            return any(g.casefold() in have for g in group)
        return any(g in labels for g in group)
