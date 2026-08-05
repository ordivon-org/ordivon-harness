---
schema_version: 1
id: harness.p0-independent-persistence
title: P0 independent persistence foundation
type: architecture
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - operator
  - agent
updated: 2026-08-05
summary: Current implementation boundary, contracts, operations, evidence, and remaining cutover work for the independent Harness Journal and CAS.
evidence_status: verified
readiness: EXPERIMENTAL
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.architecture
  - harness.status
  - harness.operations
  - harness.compatibility
---
# P0 independent persistence foundation

## Result before phase detail

Ordivon Harness now has a Host-independent persistence kernel for caller-neutral Run contracts, an append-only Run Journal, immutable CAS objects, revision and lease fencing, full-history Doctor checks, and verified backup and restore. This foundation is operational as an explicit `store-*` surface.

The production Agent Runner has **not** cut over. Existing `run`, `resume`, `recover`, `status`, `inspect`, `handoff`, and legacy `doctor` operations still use Host Assignment state, Host CAS, and Host extension events. No Run is dual-written.

## Implemented boundary

The independent path consists of:

```text
HarnessRunContract
→ SQLiteHarnessStore
   ├── runs projection
   ├── append-only run_events
   ├── run leases and revision fencing
   ├── caller bindings
   ├── provider_calls and tool_steps projection tables
   └── immutable content-addressed objects
→ store Doctor / backup / verification / restore
```

`HarnessRunContract` binds caller, objective, Context, Provider, Adapter, requested model, Tool catalog and grant digests, complete budget, completion contract, System Manifest, source and Artifact references, correlation context, privacy policy, creation time, and optional deadline. It contains no Host projection, Host lease, Host Journal revision, Host CAS metadata, Host extension event, Runtime credential, Provider secret, or domain outcome field.

## State root

The P0 state root is explicit and separate from Host:

```text
/var/lib/ordivon/harness/
├── harness.sqlite3
├── objects/
└── SQLite WAL/SHM while open
```

The root and object directory use mode `0700`. The database, WAL/SHM files, and objects use mode `0600`. State roots, databases, and objects reject symlinks and irregular files.

Normal opening does not create a missing database. Only `store-init` initializes a state root.

## Journal schema v1

| Table | Current role |
| --- | --- |
| `schema_info` | active schema version |
| `schema_migrations` | reserved migration receipts and backup path |
| `runs` | checked current Run projection |
| `run_events` | append-only authoritative Run event stream |
| `object_refs` | admitted CAS metadata |
| `run_object_refs` | causal payload and reference retention |
| `run_leases` | bounded single-writer admission |
| `caller_bindings` | caller request to one Run identity |
| `provider_calls` | reserved checked Provider Call projection |
| `tool_steps` | reserved checked Tool Step projection |
| `object_validation` | full-object validation cache |

The Provider Call and Tool Step tables exist for migration but are not yet the production Runner's write path. Their existence does not transfer current Host-backed Run authority or authorize dual writes.

## Store operations

Initialize and inspect the independent root:

```bash
ordivon-harness \
  --harness-state-root /var/lib/ordivon/harness \
  store-init

ordivon-harness \
  --harness-state-root /var/lib/ordivon/harness \
  store-doctor

ordivon-harness \
  --harness-state-root /var/lib/ordivon/harness \
  store-inspect HARNESS_RUN_ID

ordivon-harness \
  --harness-state-root /var/lib/ordivon/harness \
  store-events HARNESS_RUN_ID
```

Create and verify an online backup:

```bash
ordivon-harness \
  --harness-state-root /var/lib/ordivon/harness \
  store-backup /root/backups/ordivon-harness/backup-001

ordivon-harness \
  store-verify-backup /root/backups/ordivon-harness/backup-001
```

Restore only into an absent destination:

```bash
ordivon-harness \
  store-restore \
  /root/backups/ordivon-harness/backup-001 \
  /var/lib/ordivon/harness-restored
```

A backup contains an online SQLite snapshot, every object referenced by `object_refs`, and a canonical manifest binding the database digest, object file digests, content addresses, kinds, lengths, creation time, and source Doctor summary. Verification compares the manifest, SQLite integrity, object envelopes, content addresses, and exact database object-reference set. Restore opens the copied state and runs a full Doctor before publication.

## Admission semantics

- one caller identity and caller Run reference bind at most one Harness Run;
- exact duplicate Run creation returns the existing Run;
- one Event identity may be replayed only with identical content, references, revision, cause, and time;
- each non-creation Event requires the exact current Run revision and a live exact lease;
- an admitted Event consumes its lease;
- an expired lease may be replaced with a higher lease revision;
- terminal Run status refuses another Event or lease;
- missing, modified, wrong-kind, wrong-mode, or symlinked objects fail closed;
- Doctor reconstructs Run revision, status, terminal identity, update time, and Contract binding from the event history.

These semantics are local single-node fencing. They do not claim distributed consensus.

## Frozen migration inventory

[`../specs/p0-persistence-inventory-v1.json`](../specs/p0-persistence-inventory-v1.json) freezes 27 current durable object classes and 15 Host extension Event kinds at Harness revision `796e9f07899a250ea4d87ae3e96f38c7172ff674`.

Each entry records its current owner, intended P0 owner, schema versions, source literal, privacy class, causal role, and migration disposition. The checker [`../scripts/check_p0_persistence_inventory.py`](../scripts/check_p0_persistence_inventory.py) verifies that the inventory remains bound to current source literals and its canonical digest.

The cutover rules are fixed:

```text
new Run dual write                forbidden
bulk historical byte rewrite      forbidden
active legacy Run at cutover       forbidden by default
legacy Host-backed reader          required
```

## Verified evidence

The focused P0 suite proves:

- caller-neutral Contract round-trip and exact decoding;
- no Host imports in the new core Contract, Store protocol, or SQLite store modules;
- deterministic Contract and Event identities;
- close/reopen reconstruction;
- Event idempotency and conflict detection;
- Run revision and lease fencing;
- terminal closure;
- private modes and symlink rejection;
- missing CAS failure on reopen;
- online backup, tamper detection, verification, and independent restore;
- explicit CLI separation between Host state and Harness state;
- compatibility with the complete existing Host-backed Harness suite.

Repository gates and exact revision receipts remain the stronger evidence for a particular commit.

## Not yet implemented

This foundation does not yet provide:

- production `HarnessRunner` execution through `SQLiteHarnessStore`;
- persisted Provider Call and Tool Step projections in the new store;
- Run Snapshot resume through the new store;
- a standalone Runner that installs without the current Host dependency;
- Host `ExternalExecutorAdapter` and foreign Run binding;
- legacy active-Run inventory and cutover command;
- production `/var/lib/ordivon/harness` deployment;
- automatic observation export.

## Next migration slice

The next slice moves the existing Provider Call and Tool Step admission semantics behind the `HarnessStore` boundary while preserving their current identities, UNKNOWN rules, Runtime reconciliation, and restart behavior. It must pass focused fault tests before the main Runner is allowed to select the independent store.

The Host adapter and final no-dual-write cutover follow only after the standalone Run path can reconstruct Snapshot, Provider Call, Tool Step, Trace, terminal receipt, recovery, and completion proposal from the Harness state root alone.

## Stop conditions

Stop and redesign if the migration requires mutable Host projection fields for Run recovery, makes Host decode Harness internal events, writes a new Run to both stores, weakens Provider or Runtime response-loss reconciliation, or turns the Store protocol into a general workflow or domain state model.
