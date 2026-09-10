# Current maintenance state

Updated: 2026-09-10. Primary maintenance agent: Codex.
Branch: fix/reliability-review. Production cutover is pending.

## Reliability implementation
1. Serialized Durable Object storage with validated one-time KV import.
2. Durable pending client diffs, serialized POSTs and automatic retries.
3. Pre-publication feed/scraper health checks.
4. Strict favorite response validation; invalid responses skip pruning.
5. CSP-compatible article retry click handler.
6. No stale bot overwrite; deterministic OPML rebuild and main-only publication.

## Verification
Python: 31 passed. JavaScript: 10 passed. Ruff and Worker dry-run build passed.
Real local Wrangler runtime: imported dummy KV state, preserved original records
and retained all 20 simultaneous favorite writes. Production state untouched.
See worker/MIGRATION.md for the separate cutover procedure and rollback limits.

## Remaining work
Authorize and perform production cutover, verify authenticated devices and joto
compatibility, then reflect the new storage inventory in the operations portal.
Dependency pinning, disabled-feed review, repository visibility and independent
backup automation remain separate backlog items.
