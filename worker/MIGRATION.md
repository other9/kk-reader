# Sync state cutover: KV to Durable Object

This release preserves endpoint contracts and Bearer authentication.
SYNC_STATE (SyncState) owns read/favorite state after cutover. STATE KV remains
the article cache and legacy import source; it is NOT a live state mirror.

## Preparation
1. Confirm authorization, inspect both consumers and preserve a private backup.
2. Run Python/JS tests and wrangler deploy --dry-run. Confirm the SYNC_STATE
   binding and sync-state-v1 SQLite migration. Use a complete deployment, never
   a gradual mixed-version rollout for this storage cutover.
3. Pause fetch-feeds.yml and wait for running ingestion to finish.
4. Deploy a temporary copy of the previous KV Worker that rejects authenticated
   POST /state/diff with 503, while preserving other endpoints. This server-side
   write pause replaces relying on every device closing its reader tabs.
5. Allow existing requests to drain and KV propagation to settle (at least 60
   seconds; longer if snapshots differ). Export legacy state through the admin
   API into private storage. Repeat the snapshot and compare canonical hashes.
   Do not publish state contents. Browser pending changes remain local until
   writes resume; keep the pause short and avoid edits in outdated open clients.

## Import and verification
Deploy the new Worker/config with SYNC_MAINTENANCE=1. GET /state imports the
validated legacy state under a concurrency gate. Missing/invalid state returns
503 without initializing an empty authoritative snapshot.

Dispatch worker-smoke.yml on main with expect_maintenance=true and
expected_state_sha256 equal to the private backup's canonical SHA-256:
JSON sorted keys, compact separators, UTF-8, ensure_ascii=False. The job uses
WORKER_TOKEN within GitHub Secrets and prints only counts/hash, not state.
A mismatch blocks reopening writes; investigate the original backup and import.

After verification, deploy with SYNC_MAINTENANCE=0 and run the smoke job with
expect_maintenance=false and no expected hash (live clients can now edit).
The empty diff checks the write path without changing any favorite/read entry.
It also checks authenticated ping, reader-origin CORS and the shared /fetch
contract. An upstream refusal is reported separately from Worker failure.

Resume fetch-feeds.yml and confirm one successful ingestion and publication.
Update the portal's storage inventory. Separately verify real-device add/remove
and cross-device behavior; automated API tests do not establish browser behavior.
The portal's unauthenticated /ping observation only establishes reachability.

## Rollback and recovery
Before new writes, a failed deployment can be recovered by restoring the previous
Worker only while the legacy snapshot is still authoritative. After new writes,
do not simply deploy the old KV writer: its copy is stale. Prefer a forward fix
keeping Durable Object storage authoritative. A storage rollback requires pausing
writers, exporting current authenticated state into private storage, verifying
the backup and importing it into the chosen target before switching clients.
Never delete the object or apply a delete migration as a routine rollback.

Local validation covered dummy KV import, retained favorites, 20 simultaneous
writes, concurrency, restart and maintenance-mode regression tests. Production
and device verification are tracked separately in STATUS.md.
