# Sync state cutover: KV to Durable Object

This release leaves /state, /state/diff, /ping, /article and /fetch contracts and
Bearer authentication unchanged. SYNC_STATE (SyncState) owns read/favorite state
after cutover. STATE KV remains the article cache and legacy import source.

## Before production deployment
1. Confirm the owner has authorized the cutover and check both consumers.
2. Close reader tabs on all devices after flushing pending changes. Pause the
   feed workflow and wait for any running ingestion or old Worker writes to end.
3. Export the authenticated /state response to the owner's private backup store;
   record read/favorite counts and last timestamps without publishing content.
   Compare it with the legacy KV state; account for KV propagation delay. Keep
   clients quiet until the import is verified.
4. Run Python/JS tests and wrangler deploy --dry-run. Confirm SYNC_STATE binding
   and sync-state-v1 SQLite migration. Never use a gradual mixed-version rollout
   for this storage cutover.

## Cutover and verification
Deploy the complete Worker/config together. The first state request imports the
legacy state under a concurrency gate, only if its schema is valid. Missing or
invalid state returns 503 and does not create an empty authoritative snapshot.
Later restarts read Durable Object storage, not KV. The original KV value is
retained and is NOT a live mirror.

Compare authenticated /state with the pre-deployment snapshot before reopening
clients. Verify add/remove and cross-device sync, then /ping, reader-origin CORS
and joto's /fetch compatibility. Resume the feed workflow and confirm an actual
successful fetch run and pruning behavior. Update the local operations portal's
storage inventory from KV state to Durable Object state. The portal /ping probe
does not validate storage.

## Rollback and recovery
Do not simply redeploy the old KV-writing Worker after new writes: its copy is
stale. Prefer a forward fix keeping the Durable Object authoritative. If a
rollback is necessary, quiesce clients again, export the current authenticated
state, verify a private backup, and plan/import it into the chosen target before
switching readers/writers. Do not delete the object or apply a delete migration
as a routine rollback. KV article-cache loss is separate from sync-state recovery.

Local validation used only dummy state: KV import, preserved legacy favorites,
20 simultaneous writes under Wrangler's local runtime, and concurrency/restart
regression tests. Production deployment and authenticated device checks are
separate steps, not implied by passing local tests.
