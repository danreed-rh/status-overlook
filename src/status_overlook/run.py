"""Full pipeline: reconcile → enrich/classify → digests."""

from __future__ import annotations

from status_overlook.config import AppConfig, load_config
from status_overlook.digest import write_digests
from status_overlook.enrich import enrich_and_classify_store
from status_overlook.reconcile import run_reconcile
from status_overlook.store import load_store, save_store
from status_overlook.team import refresh_team_queue
from status_overlook.working_hours import should_skip_working_hours


def run_pipeline(
    *,
    skip_github: bool = False,
    skip_jira: bool = False,
    skip_reconcile: bool = False,
    force: bool = False,
) -> int:
    cfg, _ = load_config()
    if should_skip_working_hours(cfg.working_hours, force=force):
        print(
            "Outside working hours — skipping run "
            "(use status-overlook run --force to override)."
        )
        return 0

    personal_code = _run_personal_pipeline(
        cfg,
        skip_github=skip_github,
        skip_jira=skip_jira,
        skip_reconcile=skip_reconcile,
    )
    if not skip_github:
        _refresh_team(cfg)
    return personal_code


def _run_personal_pipeline(
    cfg: AppConfig, *, skip_github: bool, skip_jira: bool, skip_reconcile: bool
) -> int:
    """Keep personal digests independent of the GitHub-only team queue."""

    store = None
    if not skip_reconcile:
        store, _, code = run_reconcile(
            skip_github=skip_github,
            skip_jira=skip_jira,
            persist=False,
            defer_lifecycle=True,
        )
        if code != 0:
            return code

    if store is None:
        store = load_store()
    if not store.items:
        print("Track store empty — nothing to enrich. Run reconcile first.")
        return 1

    try:
        classified, changes = enrich_and_classify_store(store, cfg)
    except RuntimeError as exc:
        print(f"Enrich error: {exc}")
        return 1

    save_store(store)
    md_path, json_path = write_digests(store)
    print(f"Classified {classified} items ({changes} state changes)")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")

    # Brief console summary
    from collections import Counter

    counts = Counter(i.action or "unset" for i in store.items.values() if i.lifecycle == "active")
    print("Active by action:", dict(counts))
    return 0


def _refresh_team(cfg: AppConfig) -> None:
    try:
        team_queue = refresh_team_queue(
            limit=cfg.search_limit, self_login=cfg.github_login
        )
        if team_queue.last_error:
            print(f"Team queue refresh failed (previous results kept): {team_queue.last_error}")
        else:
            print(f"Team queue: {len(team_queue.items)} PR(s)")
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Team queue refresh failed: {exc}")
