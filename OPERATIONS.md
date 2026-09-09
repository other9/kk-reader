# kk-reader operations

## Sources and delivery
- Subscriptions: opml/subscriptions.opml. Actions rebuilds feeds when appropriate
  while retaining existing feed metadata. Active-state changes require care
  because the bot also writes docs/data/feeds.json.
- Ingestion: fetch-feeds.yml, cron `7 */2 * * *` UTC; commits generated data.
- Site: Cloudflare Pages Git integration, main branch, docs output, no build
  command. Cloudflare Access protects the site; it does not protect a public
  GitHub repository's files. GitHub Pages is retired.
- Worker: worker/worker.js and worker/wrangler.toml. Deployment is separate from
  site delivery and affects both this reader and joto-property-report.

## Local validation
Install requirements in the chosen Python environment, then run:

```text
ruff check .
python -m pytest tests/ --tb=short
```

CI uses Python 3.11; transfer was checked locally on 3.12.10. CI excludes
docs/data/** and root Markdown changes on push; PRs run CI. Documentation-only
pushes therefore must not be described as having passed a new CI run.

## Maintenance cycle
1. Check local changes and untracked files; fetch and compare remote changes.
2. Fast-forward if possible, preserving work in progress. Apply focused changes.
3. Run relevant checks and inspect explicit file diffs.
4. Commit/push within the user's authorized scope. A push can trigger delivery.
5. Check Actions and Pages results and, when relevant, authenticated browser
   behavior. Record the distinction in STATUS.md.

## Shared-service checks
Before changing Worker endpoints, auth or CORS, account for the reader frontend,
ingestion, joto's /fetch consumer and the operations portal. Check authenticated
/ping, OPTIONS for the reader origin, and affected /state, /article or /fetch
paths. An upstream 403 does not by itself establish a Worker regression.
Unauthenticated HTTP errors establish reachability only, not functional health.
Use process environment or the owner's local credential launcher; do not copy
credentials into this repository. Secret rotation includes both consuming
repositories and every configured device.

## Recovery
- Restore lost articles with a targeted patch extracted from Git history after
  preserving current work. Do not reset the developer checkout to emulate CI.
- Preserve device state before attempting KV recovery. Initial page sync can
  upload local read/favorite state, but requires working authentication and
  successful server retrieval and upload. Corrupt newer timestamps may override
  local records; verify restored content. Browser storage is not a tested backup.
- Confirm Wrangler version, remote target and backup file before any KV write.
- For stale delivery inspect the deployment error and commit message; do not
  assume retries bypass a service quota. Never casually add [skip ci].

## Historical references
SETUP.md and knowledge/ preserve earlier setup and design history. Their old
GitHub Pages URLs, retention settings and update numbering are not current rules.
