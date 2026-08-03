# Ordivon Harness P0–P1 closeout

> **Historical implementation evidence:** This document records a bounded pre-extraction or stage-specific design, closeout, experiment, or migration result. It is not a current Harness architecture or operations source. Use [`../README.md`](../README.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`OPERATIONS.md`](OPERATIONS.md), and [`authority.md`](authority.md) for the active boundary. Historical paths and revisions are preserved for provenance.

## Accepted boundary

P0–P1 closes the minimum execution-control, durable Tool-step and public Run-resume path without turning Host or Runtime into Harness implementations.

```text
owner-local Harness protocol over released ordivon-protocol 0.3.0
  HarnessToolStepIntent
  HarnessToolStepReceipt + predecessor chain
  HarnessRunSnapshot
  HarnessDispatchFence

Ordivon Host 0.1.2
  Task / Journal / CAS / authority kernel
  generic HostExtensionPort

Ordivon Harness 0.4.0
  Provider and Runtime call control
  Tool-step persistence and reconciliation
  full checkpoints + Run-state deltas
  Run resume and effect-aware recovery

Ordivon Runtime
  unchanged Workspace / Job / Attempt / Artifact / task.cancel mechanics
```

Host and Runtime do not import `ordivon-harness`. Neither receives a Harness-specific scheduler, database, daemon, process registry or alternate Task state machine.

## P0 execution-control closure

### Provider calls

The first-party Loop admits an optional `AgentTurnCallHandle` with:

```text
poll(timeout)
cancel()
```

The Loop concurrently respects Provider completion, cancellation and the monotonic Run deadline. A cancellation or deadline closes the active handle and drains it for a bounded period before emitting the terminal Run result.

The default DeepSeek path now owns one `http.client` connection per call. Cancellation closes the response, shuts down the socket and closes the connection. The former `urllib` transport remains available for compatibility and deterministic fault tests, but is no longer the default.

Codex and Hermes retain provider-faithful lifecycle implementations and bounded subprocess cleanup. Requested and effective Provider model identities remain separately recorded and unadmitted routing fails closed.

### Runtime calls

Durable `workspace.exec` is dispatched with `waitMs=0` to obtain the Runtime Job identity promptly. Harness then performs bounded `task.observe` polling while checking cancellation and deadline state. A model-supplied `waitMs=0` does not turn the durable Tool Step into a background completion: Harness keeps the Intent active until Runtime reaches a terminal state or cancellation is requested. Physical cancellation is requested through Runtime `task.cancel`; a local cancellation token alone never proves that the Job stopped.

### Nonterminal cancellation

`cancel-requested` is explicitly nonterminal. Its Receipt retains the active Tool Step Intent and may be superseded by a later Receipt for the same Intent:

```text
cancel-requested
  → cancelled
  → observed succeeded / failed / timed_out
  → unknown
```

Each superseding Receipt binds the digest of its predecessor. Only a terminal Receipt clears the active Intent. Historical replay validates the predecessor chain and rejects a terminal Receipt that still claims an active Intent.

## DispatchFence

Before physical `workspace.exec`, Harness persists a `HarnessDispatchFence` bound to:

- Task revision;
- Harness Run identity;
- Assignment identity, generation and digest;
- Tool Step Intent digest;
- Runtime operation and stable `clientRequestId`;
- issue and expiry times.

Harness validates the fence against current Host state immediately before dispatch and again after Runtime returns. The fence is also carried in Runtime `foreignReferences`, so the Job retains immutable correlation evidence.

This is a practical stale-dispatch and provenance fence. Runtime does not independently verify a Host-issued MAC and does not call Host during admission; P0–P1 therefore does not claim cryptographic cross-service authorization.

## Active-step-first recovery

Native Run recovery now orders evidence collection as:

1. load the current Tool Step Intent and latest Receipt;
2. reconcile the original Runtime Job by `clientRequestId` or `runtimeJobRef`;
3. persist a missing or superseding Receipt and Observation;
4. inspect the Workspace and structured diff;
5. derive remaining UNKNOWNs;
6. abandon, retain or replace only when the evidence permits it.

A failed reconciliation is retained as explicit Tool Step UNKNOWN evidence. Recovery events preserve the current Tool Step and Snapshot references rather than erasing their projection path.

## P1 durable Tool step

For native `workspace.exec`, the accepted ordering is:

```text
bind bounded Run state
→ write Intent + Snapshot + DispatchFence to Host CAS/Journal
→ verify current Host fence
→ dispatch Runtime with stable clientRequestId
→ poll / cancel / reconcile
→ write terminal or nonterminal Receipt + immutable Observation
```

If the Harness process dies after Intent persistence but before Receipt persistence, a fresh Harness instance queries Runtime by the original `clientRequestId`, observes exactly one matching Job and writes the missing Receipt without redispatching the command. Zero or multiple matches remain explicit UNKNOWN.

`workspace.mutate` remains rejected when the durable Run Store is active. Runtime mutation does not yet expose a separately observable dispatch identity that can prove whether response loss occurred before or after commitment.

## Executable Run resume

`OrdivonAgentLoop.resume()` upgrades the Snapshot from audit evidence to an executable public-state boundary.

For `needs-input`, the caller supplies additional messages and the Loop continues with cumulative budget accounting. For `effect-dispatch-pending`, the Loop first reconciles the active Tool Step, appends its Observation to model history and only then invokes the model again.

Resume restores:

- messages and Tool Observations;
- Model and Tool Call counts;
- observation-byte and wall-time use;
- seen Model/Tool Call identities;
- requested/effective model provenance;
- Provider usage history.

Provider hidden state, transport sessions and subprocess identity are not restored.

## Incremental Run-state persistence

The first durable checkpoint and explicit pause boundaries retain a complete `harness-run-state` object. Consecutive effect preparations may retain a `harness-run-state-delta` containing only appended messages, observations, call identities and usage plus the new remaining budget.

Each Delta binds the previous state object digest and previous reconstructed state digest. Reconstruction is bounded to 64 links and validates prefix monotonicity. A Delta is used only when it is smaller than the complete state; otherwise Harness writes a full checkpoint.

This avoids repeatedly copying a growing transcript at every durable Tool Step while preserving CAS auditability and restart reconstruction.

## Host extension boundary

`HostHarnessRunStore` now uses the public generic `HostExtensionPort` instead of Host private storage helpers. The port provides:

- CAS put/get/inspect;
- revision/state/frontier-fenced preserving appends;
- retention of top-level extension object references.

It does not know Harness schemas, events, transitions or recovery policy.

## Deliberate non-goals

P0–P1 does not add:

- durable `workspace.mutate`;
- parallel Tool execution;
- subagents or a graph scheduler;
- automatic model routing;
- persistent Provider sessions;
- a Harness daemon or separate database;
- Runtime-side cryptographic DispatchFence verification.

These remain evidence-gated future work, not incomplete hidden promises.

## Validation scope

The release gate covers:

- strict protocol round trips and legacy Receipt decoding;
- late deadline and in-flight Provider cancellation;
- active socket closure against a stalled local HTTP response;
- Runtime Job cancellation and nonterminal Receipt evolution across restart;
- Intent-before-dispatch and DispatchFence correlation;
- active-step-first recovery;
- `clientRequestId` reconciliation without redispatch;
- `needs-input` and prepared-effect Run resume;
- cumulative budget and duplicate-call fencing after resume;
- Run-state Delta size reduction and reconstruction;
- full Harness semantic-history replay;
- Python 3.12 unit/pytest, changed-file Ruff, compile and distribution build gates.

The original P0–P1 repository gate was 126 unittest cases, 126 pytest cases plus 29 subtests, 75% branch coverage, and successful wheel/sdist construction. The R0–R1 application gate is recorded below.

## R0–R1 practical application closure

The post-P1 practical audit found that the durable core was stronger than its application surface. R0–R1 correct that imbalance without weakening the evidence model.

### R0 — honest contracts

The first-party manifest now uses protocol revision `p1` and separately declares public Run-state resume, effect checkpoints, Provider-call cancellation and Runtime-Job cancellation. It still declares Provider Session resume, approval events and compaction as unsupported.

Durable Runs no longer expose `mutate_workspace` in model Tool definitions. The low-level Runtime catalog may contain mutation and historical/experimental Assignments may retain such a Grant, but the durable application plan rejects it and the bridge does not advertise it. The unreachable `approval_required` pause entry is likewise removed from the active execution surface.

Recovery consequence derivation is now a public `HarnessHost` operation rather than a private method used across component boundaries.

### R1 — thin Runner and CLI

`HarnessRunner` centralizes the normal object choreography while preserving every existing authority boundary. It supports preparation, execution, durable resume, status projection, cancellation and recovery. Candidate completion may stop after recording, automatically create a proposal, or proceed to adjudication when explicit verifier callbacks are configured.

`RunHandle` gives one Runner an in-process cancellation handle. It does not persist process identity and cannot replace Snapshot-based restart recovery. The handle is registered before its worker starts, avoiding a fast-completion registration race, and the worker uses an independent HostStorage connection.

The CLI now exposes `status`, `run`, `resume`, `cancel`, `recover` and `doctor`. `run` consumes an existing current Assignment; it does not synthesize Task Contracts or Tool authority from command-line strings. A separate process can reconcile/cancel a durable Runtime Tool Step, but cannot close another process's in-memory Provider connection.

Execution guards prevent accidental redispatch:

```text
current Snapshot exists  → use resume
Run receipt exists        → create a replacement Assignment
missing adjudicators      → fail before preparing the Attempt
durable mutation grant    → reject the Run Plan
```

## Updated validation gate

The `0.4.0` gate adds focused Runner tests for:

- Plan → Assignment → model/Tool loop → Run receipt → CompletionProposal;
- `needs-input` pause and public-state resume;
- active Provider-call cancellation through `RunHandle`;
- durable mutation hiding and approval-pause rejection;
- pre-effect adjudication configuration failure;
- Host-only CLI status projection.

Final deterministic gate: 132 pytest cases plus 29 subtests, the matching unittest discovery suite, changed-file Ruff/format, Python 3.12 compile, wheel/sdist build and fresh wheel installation against exact Host `0.1.2` and Protocol `0.3.0` Git pins.
