# Current maintenance state

Updated: 2026-09-10. Primary maintenance agent: Codex.

Claude Code supplied the handoff; Codex independently checked the local code and
tests. Rules are now in AGENTS.md, operations in OPERATIONS.md. Agent-specific
memory is not a source of project policy.

## Verification at transfer
- Fetched origin and fast-forwarded main to b125cb6. The 232 incoming commits
  changed only docs/data/feeds.json and docs/data/articles.json.
- Ruff passed and 15 Python tests passed before documentation changes.
- The five latest observed Fetch RSS feeds runs succeeded; latest observed run:
  34403626493, created 2026-09-09T20:52:15Z. This is an observation, not a guarantee
  of continuing schedule execution.
- Authenticated multi-device UI/sync recovery was not tested by Codex.
- Transfer documentation is prepared for local commit; no transfer push or
  Worker deployment has been performed.

## Separate backlog (not part of ownership transfer)
- Repository visibility and generated article-body distribution policy.
- Dependency update backlog and reproducible dependency pinning.
- Disabled-feed review and alternate acquisition if upstream blocking persists.
- Multi-device sync verification, Android initial-render issue, article size,
  timestamp comparisons in retention, and broader test coverage.
- KV state backup and tested recovery procedure.

The original private handoff and detailed operational inventory are retained by
the owner outside version control. Update this file after the next actual change.

Cloudflare Pages read verification through the shared launcher succeeded: project kk-reader, branch main, deployment success. Portal ownership notice updated locally; its scheduled weekly updater may publish it. Authenticated browser checks remain unperformed.
