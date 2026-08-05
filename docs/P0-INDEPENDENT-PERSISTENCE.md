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
→ HarnessRunContinuityStore protocol
   ├── owner-neutral Provider Call, Tool Step and Snapshot values
   ├── stable Run/Assignment binding identity
   ├── scalar caller revision compatibility
   └── no Host store, Journal, CAS or projection types
→ SQLiteHarnessStore
   ├── runs projection
   ├── append-only run_events
   ├── run leases and revision fencing
   ├── caller bindings
   ├── reserved provider_calls and tool_steps projection tables
   └── immutable content-addressed objects
→ SQLiteHarnessRunContinuityStore
   ├── Provider claim, dispatch, terminal outcome and safe retry
   ├── Tool Intent, Harness-owned Dispatch Fence and Receipt chain
   ├── Run Snapshot, pause and replay source reconstruction
   └── event-sourced continuity Doctor
→ SQLiteHarnessAgentBridge
   ├── canonical empty Tool surface
   ├── real OrdivonAgentLoop Provider lifecycle
   ├── needs-input Snapshot and resume
   └── durable Provider result replay after response loss
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

The Provider Call and Tool Step projection tables remain reserved and non-authoritative. The independent continuity implementation reconstructs its current heads from the append-only Run Event chain and immutable CAS objects. This avoids a two-stage failure window between Event admission and projection update. A later projection migration must prove exact reconstruction before those tables may become operational accelerators.

`RuntimeToolBridge` consumes `HarnessRunContinuityStore` rather than the concrete `HostHarnessRunStore`. Common retained Provider Call, Tool Step, Snapshot, object-view and lifecycle-error values live outside the Host implementation. Both the legacy Host Store and `SQLiteHarnessRunContinuityStore` implement the same behavioral boundary.

`SQLiteHarnessAgentBridge` proves the real bounded `OrdivonAgentLoop` can execute and resume a no-Tool Agent Run using only the independent state root. It binds the canonical empty Tool surface, persists the complete Provider lifecycle, records `needs_input` Snapshot state, and replays a completed Provider result after a lost Bridge response without another physical invocation. It deliberately rejects every Tool Call. The production `HarnessRunner` still selects only the legacy Host-backed path.

`HarnessExecutionBinding` now owns the caller-neutral immutable inputs required to lower a Tool Call into a Runtime request: Harness Run identity, Workspace reference, binding identity and digest, Tool catalog and optional Tool Grant digests, deadline, Runtime binding digest, and uniquely sorted foreign references. Generic Runtime request construction and `lower_runtime_tool` no longer import Host types. The legacy `RuntimeToolBridge` adapts its current `CommittedHarnessAssignment` into the same Binding and preserves the exact existing client request identity and foreign-reference bytes.

The retained Host-backed Provider Call Record and Dispatch Fence remain exact version-1 codecs. Caller-neutral version-2 records bind to a `HarnessRunStoreBinding` digest and independent Run revision; they contain no Host Task identity or Task revision. Version-1 fences project `ordivon.host` authority, while version-2 fences project `ordivon.harness` authority into Runtime foreign references. Execution consumes structural Provider Call and Dispatch Fence views, so v1 and v2 remain usable without rewriting history. The independent Store is the only v2 writer.

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
- Provider claim exclusion, expiry takeover, dispatch fencing, terminal idempotency, UNKNOWN recovery and safe retry accounting;
- losing Provider completion cannot retain an unreferenced result object;
- Tool Intent, version-2 Harness authority Fence, non-terminal and terminal Receipt chains, stale Fence rejection and Snapshot replay;
- a real no-Tool Agent Loop candidate completion with no Host or Runtime access;
- Provider result replay after a durable completion response loss with zero physical redispatch;
- `needs_input` Snapshot close/reopen and second-turn completion;
- caller-neutral Execution Binding round-trip, deterministic request and patch identities, and Host-free Tool lowering;
- exact compatibility of legacy Host Runtime request identity and foreign references through the Host adapter;
- explicit CLI separation between Host state and Harness state;
- compatibility with the complete existing Host-backed Harness suite.

Repository gates and exact revision receipts remain the stronger evidence for a particular commit.

## Not yet implemented

This foundation does not yet provide:

- production `HarnessRunner` selection of the independent Agent path;
- an independent Runtime Tool Bridge that combines `HarnessExecutionBinding` with `SQLiteHarnessRunContinuityStore`;
- checked Provider Call and Tool Step accelerator projections; the Event chain remains authoritative;
- terminal Trace, Run receipt, recovery and completion proposal through only the independent state root;
- a standalone Runner package graph without the current Host dependency;
- Host `ExternalExecutorAdapter` and foreign Run binding;
- legacy active-Run inventory and cutover command;
- production `/var/lib/ordivon/harness` deployment;
- automatic observation export.

## Next migration slice

The next slice builds an independent Runtime Tool Bridge from `HarnessExecutionBinding`, a caller-supplied Runtime client, Tool Grant/catalog objects, and `SQLiteHarnessRunContinuityStore`. It must run a Tool-bearing Agent Loop without `CommittedHarnessAssignment` while preserving version-2 Harness dispatch authority, response-loss reconciliation, cancellation and Tool Receipt causality.

Production Runner selection, the Host `ExternalExecutorAdapter`, and final no-dual-write cutover follow only after the standalone Run path reconstructs terminal Trace, Run receipt, recovery and completion proposal from the Harness state root alone.

## Stop conditions

Stop and redesign if the migration requires mutable Host projection fields for Run recovery, makes Host decode Harness internal events, writes a new Run to both stores, weakens Provider or Runtime response-loss reconciliation, or turns the Store protocol into a general workflow or domain state model.
