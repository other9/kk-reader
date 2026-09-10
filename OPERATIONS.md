# kk-reader operations

## Sources and delivery
- Subscriptions: opml/subscriptions.opml. Actions rebuilds feeds on every ingestion run
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
node --test tests/js/*.test.cjs
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
- Preserve device state before attempting sync-state recovery. Initial page sync can
  upload local read/favorite state, but requires working authentication and
  successful server retrieval and upload. Corrupt newer timestamps may override
  local records; verify restored content. Browser storage is not a tested backup.
- Confirm Wrangler version, remote target and backup file before any remote storage change.
- For stale delivery inspect the deployment error and commit message; do not
  assume retries bypass a service quota. Never casually add [skip ci].

## Historical references
SETUP.md and knowledge/ preserve earlier setup and design history. Their old
GitHub Pages URLs, retention settings and update numbering are not current rules.

## Reliability changes (deployed 2026-09-10)
- Sync state is owned by SYNC_STATE Durable Object; STATE KV is
  an import source and article cache. Follow worker/MIGRATION.md for cutover and
  rollback. Do not restore stale KV over current Durable Object state.
- Client diffs stay persisted until acknowledged, sends are serialized, and
  failures retry with a delay capped at 30 seconds.
- Ingestion fails before publication with no successful active feeds, success
  rate below 50%, a drop of at least 25 percentage points from the previous run
  (at least five prior attempts), or scraper count collapse. Scrapers reject
  zero items or fewer than 25% of a prior count of at least ten. These thresholds
  are initial conservative defaults; investigate false alarms before changing.
- Favorite schema errors skip pruning; an explicitly valid empty map is allowed.
- OPML rebuild is deterministic on every run, preserving non-OPML metadata.
- A stale bot push fails instead of replacing concurrent manual edits. The next
  scheduled run regenerates from current main. Production publication is main-only.

## Authenticated operational check
Dispatch worker-smoke.yml on main with expect_maintenance=false. The job uses
WORKER_TOKEN within GitHub Secrets; it does not print credentials or state.
It checks state reads, an empty diff write, ping, CORS and shared /fetch format.
An upstream refusal is reported separately; this does not replace device tests.
SYNC_MAINTENANCE is normally 0; 1 pauses state writes only. Follow
worker/MIGRATION.md before using maintenance mode for a storage migration.
