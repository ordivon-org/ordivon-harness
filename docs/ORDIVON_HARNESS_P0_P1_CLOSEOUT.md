# Ordivon Harness P0–P1 closeout

## Accepted boundary

P0–P1 closes the minimum execution-control and durable Tool-step path without turning Host or Runtime into Harness implementations.

```text
Ordivon Computer / ordivon-protocol
  HarnessToolStepIntent / HarnessToolStepReceipt / HarnessRunSnapshot

Ordivon Harness
  Run deadline and cancellation scope
  Provider provenance and subprocess ownership
  Tool-step preparation, observation, cancellation and reconciliation
  effect-aware recovery and Harness semantic history validation

Ordivon Host
  unchanged Task / Journal / CAS / authority kernel

Ordivon Runtime
  unchanged Workspace / Job / Attempt / Artifact / task.cancel mechanics
```

The Host and Runtime repositories do not import `ordivon-harness` and receive no Harness-specific scheduler, database, daemon, process registry or alternate Task state machine.

## P0 execution-control closure

The first-party Loop now:

- uses a monotonic absolute deadline rather than a wall-clock boundary check;
- clamps supported Provider and Runtime timeouts to remaining Run time;
- rejects a Provider result returned after cancellation or deadline expiry;
- records requested and effective Provider model identities and rejects unadmitted routing;
- maps unexpected execution exceptions to a terminal Harness result rather than losing the Run boundary;
- bounds Tool Observations before they enter subsequent model context;
- calls native Runtime `task.cancel` for active Jobs and distinguishes confirmed cancellation from `cancel-requested` uncertainty;
- cleans up Codex and Hermes subprocesses on initialization failure and performs bounded terminate → kill → stream/thread cleanup.

Effect-aware recovery now force-closes only observation-only Workspaces. A Workspace with possible mutations or process effects is retained and inspected through `workspace.get` and `workspace.diff`; the recovery record remains blocking until evidence resolves the unknown.

## P1 durable Tool step

For native `workspace.exec`, the ordering is:

```text
bind bounded Run state
→ write HarnessToolStepIntent + RunSnapshot to Host CAS/Journal
→ dispatch Runtime workspace.exec with stable clientRequestId
→ observe/reject/retain UNKNOWN
→ write ToolStepReceipt + immutable ToolObservation
```

If the Harness process dies after Intent persistence but before Receipt persistence, a fresh Harness instance:

1. loads the current Intent from Host Journal/CAS;
2. queries Runtime Jobs by the original `clientRequestId`;
3. observes exactly one matching Job;
4. writes the missing Receipt and Observation;
5. never redispatches the command.

Zero or multiple matching Jobs remain explicit UNKNOWN.

`workspace.mutate` is intentionally rejected when the durable Run Store is active. Runtime mutation currently lacks a separately observable dispatch identity that can prove whether response loss occurred before or after commitment. This is a truthful capability reduction, not a permanent architectural prohibition.

## Pause snapshots

A bounded `HarnessRunSnapshot` is retained for:

- `needs-input`;
- approval-required extension points;
- effect dispatch prepared but not yet resolved.

Snapshots bind Assignment generation/digest, Tool Catalog digest, requested/effective model identity, bounded messages, prior Observation digests and remaining budget. They do not own Task truth, Runtime Job state or Provider hidden state.

## Validation

The release gate includes:

- strict Computer protocol round trips and schema validation;
- late deadline and mid-Provider cancellation fault injection;
- effective Provider model mismatch rejection;
- Tool Observation truncation before model history;
- Provider subprocess termination;
- Intent-before-dispatch ordering;
- restart loading of Snapshot, Intent, Receipt and Observation;
- `clientRequestId` reconciliation without a second `workspace.exec`;
- effectful recovery retaining the Workspace;
- full Harness semantic-history replay.
