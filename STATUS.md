# Current maintenance state

Updated: 2026-09-10. Primary maintenance agent: Codex.
Branch: main. Reliability release is deployed; automatic ingestion is enabled.

## Delivered
1. Serialized Durable Object storage with validated one-time KV import.
2. Persisted pending client diffs, serialized POSTs and automatic retries.
3. Pre-publication feed/scraper health checks.
4. Strict favorite response validation; invalid responses skip pruning.
5. CSP-compatible article retry click handler.
6. No stale bot overwrite; deterministic OPML rebuild and main-only publication.

## Verification and production evidence
- Local: Python 31 passed; JavaScript 11 passed; Ruff and Worker dry-run passed.
  Local Wrangler imported dummy KV and retained all 20 simultaneous writes.
- CI: [34425525080](https://github.com/other9/kk-reader/actions/runs/34425525080)
  passed for the final code revision (8be51d8).
- Production state was privately backed up. During a server-side write pause,
  all 2,493 read-state entries and 3 favorite-state entries matched the import
  by canonical SHA-256. [Import check](https://github.com/other9/kk-reader/actions/runs/34425649515)
  passed before reopening writes. Entry counts include stored removal records.
- Final Worker version: 4ee961c6-bd6d-419d-943c-655aaffdba31.
  SYNC_MAINTENANCE=0. SYNC_STATE owns sync data; STATE KV holds article cache
  and the old snapshot. See worker/MIGRATION.md for recovery restrictions.
- [Live API check](https://github.com/other9/kk-reader/actions/runs/34425687382)
  passed: authenticated ping/state, empty-diff write, CORS, shared /fetch format.
  Kenbiya returned upstream 403; actual upstream content retrieval is not proven
  by that contract check. The initial smoke request needed an explicit User-Agent.
- [Ingestion](https://github.com/other9/kk-reader/actions/runs/34425690096)
  succeeded: 72 feeds successful, 1 failed, 2 expired favorites preserved.
  Generated commit 4b06f23 was delivered by Pages successfully.
- Operations portal storage/ownership inventory and automatic measurements were
  updated and deployed successfully on 2026-09-10.

## Remaining verification and separate backlog
Real PC/phone browser add/remove and cross-device UI behavior have not been
manually verified. Automated tests and authenticated API checks are complete.
Dependency pinning, disabled-feed review, repository visibility and independent
backup automation remain separate backlog items.
