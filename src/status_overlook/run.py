"""Full pipeline: reconcile → enrich/classify → digests."""

from __future__ import annotations

from status_overlook.config import load_config
from status_overlook.digest import write_digests
from status_overlook.enrich import enrich_and_classify_store
from status_overlook.reconcile import run_reconcile
from status_overlook.store import load_store, save_store


def run_pipeline(
    *,
    skip_github: bool = False,
    skip_jira: bool = False,
    skip_reconcile: bool = False,
) -> int:
    if not skip_reconcile:
        _, _, code = run_reconcile(skip_github=skip_github, skip_jira=skip_jira)
        if code != 0:
            return code

    cfg, _ = load_config()
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
