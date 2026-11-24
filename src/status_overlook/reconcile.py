"""Orchestrate discover → merge track store."""

from __future__ import annotations

from status_overlook.config import AppConfig, load_config
from status_overlook.doctor import doctor_ok, print_doctor, run_doctor
from status_overlook.providers import github as github_provider
from status_overlook.providers import jira as jira_provider
from status_overlook.providers.github import ProviderError as GhError
from status_overlook.providers.jira import ProviderError as JiraError
from status_overlook.store import (
    Candidate,
    ReconcileStats,
    TrackStore,
    load_store,
    normalize_item_id,
    reconcile,
    save_store,
)


def _pin_ids(cfg: AppConfig) -> set[str]:
    pins: set[str] = set()
    for key in cfg.pins_jira:
        pins.add(f"jira:{key}")
    for key in cfg.pins_github:
        # accept org/repo#n or already github-pr:… / legacy github:…
        if key.startswith("github-pr:") or key.startswith("github-issue:"):
            pins.add(key)
        elif key.startswith("github:"):
            pins.add(normalize_item_id(key))
        else:
            pins.add(f"github-pr:{key}")
    for key in cfg.pins_github_issues:
        pins.add(
            key
            if key.startswith("github-issue:")
            else f"github-issue:{key}"
        )
    return pins


def run_reconcile(
    *,
    skip_github: bool = False,
    skip_jira: bool = False,
    dry_run: bool = False,
    persist: bool = True,
    defer_lifecycle: bool = False,
) -> tuple[TrackStore, ReconcileStats, int]:
    """Return staged or persisted store, stats, and exit code.

    ``persist=False`` lets the full pipeline commit only after enrichment.
    ``defer_lifecycle=True`` keeps discovery from changing lifecycle before
    enrichment confirms the current visible state.
    """
    cfg, cfg_path = load_config()
    if cfg_path is None:
        print("No config file found; using defaults.")
        print(f"  (expected {__import__('status_overlook.paths', fromlist=['config_path']).config_path()})")

    results = run_doctor(require_gh=not skip_github, require_acli=not skip_jira, cfg=cfg)
    print_doctor(results)
    if not doctor_ok(results, require_gh=not skip_github, require_acli=not skip_jira):
        return load_store(), ReconcileStats(), 1

    candidates: list[Candidate] = []
    try:
        if not skip_github:
            candidates.extend(github_provider.fetch_open_prs(limit=cfg.search_limit))
            candidates.extend(
                github_provider.fetch_assigned_issues(limit=cfg.search_limit)
            )
        if not skip_jira:
            candidates.extend(
                jira_provider.fetch_assigned_and_qa_issues(
                    site=cfg.jira_site,
                    qa_contact_field=cfg.jira_qa_contact_field,
                    testing_statuses=cfg.status_testing,
                    limit=cfg.search_limit,
                )
            )
    except (GhError, JiraError) as exc:
        print(f"Provider error: {exc}")
        if getattr(exc, "hint", ""):
            print(f"  → {exc.hint}")
        return load_store(), ReconcileStats(), 1

    store = load_store()
    store, stats = reconcile(
        store,
        candidates,
        pin_ids=_pin_ids(cfg),
        retention_days=cfg.done_retention_days,
        defer_lifecycle=defer_lifecycle,
    )
    if not dry_run:
        if persist:
            path = save_store(store)
            print(f"Wrote {path}")
        else:
            print("Store write deferred until enrichment")
    else:
        print("Dry run — store not written")

    active = sum(1 for i in store.items.values() if i.lifecycle == "active")
    done = sum(1 for i in store.items.values() if i.lifecycle == "done")
    print(
        f"Reconcile: +{len(stats.added)} added, "
        f"{len(stats.refreshed)} refreshed, "
        f"{len(stats.finished)} finished, "
        f"{len(stats.pruned)} pruned, "
        f"{len(stats.pinned_kept)} pinned-kept"
    )
    print(f"Store: {active} active, {done} done, {len(store.items)} total")
    if stats.added:
        print("Added:")
        for i in stats.added[:20]:
            print(f"  {i}")
        if len(stats.added) > 20:
            print(f"  … +{len(stats.added) - 20} more")
    if stats.finished:
        print("Finished:")
        for i in stats.finished[:20]:
            print(f"  {i}")
    return store, stats, 0
