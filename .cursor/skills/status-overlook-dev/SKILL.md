---
name: status-overlook-dev
description: >-
  Implement or extend the Status Overlook CLI (reconcile, enrich, classify,
  digest, serve). Use when working in the status-overlook repo on providers,
  classification rules, store migration, UI, or tests. Not for reading
  digests from other repos — use skills/status-overlook there.
---

# Status Overlook — implementation

You are in the **implementation** repo. Read [docs/AGENT_CONTEXT.md](../../../docs/AGENT_CONTEXT.md) first for architecture, phased history, and recent fixes.

## Canonical docs

| Doc | Use for |
|-----|---------|
| [docs/AGENT_CONTEXT.md](../../../docs/AGENT_CONTEXT.md) | Handoff, pipeline, pitfalls |
| [docs/DECISIONS.md](../../../docs/DECISIONS.md) | Locked classification + grouping rules |
| [docs/CONFIG.md](../../../docs/CONFIG.md) | Paths, blocked, Review+PR, UI, GitHub Issues |
| [docs/SUCCESS.md](../../../docs/SUCCESS.md) | Phase checklist |

## Start here (modules)

```
src/status_overlook/
  cli.py, run.py, reconcile.py, enrich.py, store.py, digest.py
  classify_jira.py, classify_github.py, classify_github_issue.py, cues.py
  term_show.py, serve.py, providers/jira.py, providers/github.py, web/
```

## Change checklist

1. Pure classification logic stays in `classify_*.py` (no I/O). Cue mapping stays in `cues.py`.
2. New `action` values require [DECISIONS.md](../../../docs/DECISIONS.md) + unit tests. New cue ids likewise.
3. Source IDs must not collide (`jira:`, `github-pr:`, `github-issue:`).
4. Run `.venv/bin/pytest tests/ -q` before finishing.
5. Restart `serve` after `build_ui_digest` or static asset changes.

## Consumer skill (other repos)

[skills/status-overlook/SKILL.md](../../../skills/status-overlook/SKILL.md) — how agents **read** digests elsewhere; do not duplicate implementation rules there.
