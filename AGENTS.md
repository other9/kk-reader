# kk-reader — agent working agreement

This is the canonical working agreement for any coding agent. Read README.md,
STATUS.md and OPERATIONS.md before editing. CLAUDE.md is only an entry point.
Keep project knowledge in these files rather than relying on agent memory.

## Scope and sources
- Feedly-style RSS reader: Python ingestion, static frontend in docs/, and the
  shared kk-sync Worker in worker/. OPML is the subscription source.
- Cloudflare Pages serves main:/docs; GitHub Pages has been retired.
- docs/data is generated and committed by Actions. Avoid incidental data edits.
- knowledge/ and SETUP.md are historical material, not current instructions.
- Record current work and remaining verification in STATUS.md; durable operating
  procedures belong in OPERATIONS.md. Date historical observations.

## Work and verification
- Check git status and fetch before integrating remote changes. Preserve local
  work; use fast-forward where possible. Never copy the CI bot's reset --hard
  recovery into a developer working tree. Stage only named task files.
- Before code commits: `ruff check .` and `python -m pytest tests/ --tb=short`.
  UI and Worker behavior require targeted checks beyond the Python suite.
- Do not run the live ingestion script just to test a documentation change.
- Do not include [skip ci] in delivery commits: Pages also interprets it.
- Distinguish local verification, CI success, delivery and authenticated browser
  verification. Record anything not tested without claiming success.
- One agent owns a task at a time; concurrent work needs separate branches or
  worktrees and an explicit handoff. Do not discard another agent's edits.

## Behavioral constraints
- Retention is 30 days; favorites are exempt. If favorite state cannot be read,
  skip pruning. Never weaken that failure behavior incidentally.
- Rakumachi feeds remain disabled pending an explicit change in acquisition.
- Preserve scraper request caps/delays and Ruff exclusions.
- Do not register HTMLRewriter onEndTag on void elements; avoid double encoding
  existing entities; do not change article:v3 cache keys without a reason.
- Never broaden CORS to *. Never put tokens in source, logs or documentation.
- kk-sync /fetch is also used by joto-property-report. Interface/authentication
  changes require checking that consumer and the portal's /ping observation.

## Publication and handoff
- This repository is public; write shared docs accordingly. Private handoff,
  local credential locations and infrastructure inventories stay outside Git.
- Before push/deploy, inspect the exact diff and target; follow the current
  user's authorization for external actions. Documentation preparation alone
  does not imply a Worker deployment or a repository visibility change.
- On handoff, record changed files, tests, remaining work, and whether changes
  are committed/pushed/deployed. Keep one canonical rule rather than duplicating
  it in agent-specific files.
