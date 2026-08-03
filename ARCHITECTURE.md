---
schema_version: 1
id: harness.architecture
title: Ordivon Harness architecture
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
updated: 2026-08-03
summary: Canonical Harness architecture for Assignment-bound Agent execution, durable Run state, Tool semantics, Provider adaptation, dispatch fencing, recovery, and completion.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.authority
---
# Ordivon Harness architecture

## Purpose

Provide replaceable Agent execution lifecycles over durable Host Tasks while preserving explicit Tool authority, Runtime correlation, bounded Provider behavior, recoverable Run state, and independently admitted completion.

## Boundaries

Host owns generic Task continuity, Journal, CAS, revision fencing, and Runtime client mechanics. Harness owns Assignment, Run, Tool-step, Provider, recovery, abandonment, and completion semantics. Runtime owns physical Workspace, Job, Attempt, Artifact, and cancellation truth. Domain applications retain task meaning and final domain verification.

## Components

The architecture consists of the Host Harness extension, Assignment-bound native Tool catalog semantics, Provider-faithful adapters, the first-party bounded Agent loop, durable Run snapshots and deltas, Tool-step Intent and Receipt chains, RuntimeToolBridge, HarnessRunner, live event projection, recovery, operator handoff, and semantic Doctor checks.

## Data flow

An application prepares a Task Contract, Context, Tool Grant, and Assignment; the Agent loop calls a replaceable Provider; admitted Tool calls are fenced and lowered to Runtime; observations and usage become a canonical Trace and Run receipt; Harness recovers or resumes from durable checkpoints; completion is proposed and independently adjudicated through Host-backed state.

## Failure modes

Harness fails closed on catalog drift, stale Assignment or fence identity, unsupported durable mutation, ambiguous Provider output, unbounded retry or token use, unresolved effectful Tool steps, missing receipts, UNKNOWN physical consequence, invalid replacement, and attempts to treat live streams, handles, sessions, or hidden model state as durable continuity.

## Verification

Exact behavior is verified by deterministic tests, semantic history validation, Host and Runtime integration fixtures, frozen provider and fault evidence, production Runtime catalog inspection, recovery matrices, and the canonical final Trace. The repository entry is [`README.md`](README.md), and the authority boundary is recorded in [`docs/authority.md`](docs/authority.md). Stage and closeout documents retain the evidence behind these claims but are not alternate current architectures.

## Boundary

Ordivon Harness is an extension over the thin Ordivon Host kernel, not a second Host and not a Provider Session store.

```text
ordivon-computing / ordivon-protocol
  owner-local HarnessToolStepIntent / HarnessToolStepReceipt
  owner-local HarnessRunSnapshot / HarnessDispatchFence
          ↓
ordivon-host
  Task / Journal / CAS / Kernel / HostExtensionPort / Runtime client
          ↑ thin generic extension port
ordivon-harness
  Attempt / Assignment / Run / Tool Step / Recovery / Completion
  Provider adapters and bare-model execution
          ↓ thin Runtime port
ordivon-runtime
  Workspace / Job / Attempt / Artifact / cancellation
```

The dependency remains one-way. Host preserves extension fields and CAS references under revision, state and ready-frontier fencing without importing Harness semantics. Runtime remains unaware of the Harness state machine.

## Durable ownership

Harness code constructs and validates:

- `TaskContract` and `TaskAttemptDescriptor`;
- `HarnessAssignment`, `ToolGrant` and native Run Contract;
- retained Tool catalog semantics;
- durable Tool Step Intent, DispatchFence, Receipt chain and Observation;
- bounded full Run checkpoints and append-only state deltas;
- Run Recovery and Abandonment evidence;
- Trace, Tool Observations and `HarnessRunReceipt`;
- CompletionProposal, independent CompletionVerification and CompletionDecision.

The bytes remain in Host CAS and their event admission remains in the Host Journal. The public Host extension port supplies storage and concurrency fencing only; it does not supply a Harness scheduler, table, state machine or recovery policy.

## Execution ownership

Provider Sessions, subprocesses, transcripts and hidden model state are disposable execution state. They never own Task continuity. Public Run state can be restored from a `HarnessRunSnapshot` plus its full-or-delta state object chain.

These durable formats are internal to `ordivon_harness.protocol`. They are not exported from the package root and are not part of `ordivon-protocol`; promotion requires another materially different consumer or transport boundary.

`OrdivonAgentLoop.resume()` currently resumes:

- `needs-input` after additional messages are supplied;
- `effect-dispatch-pending` after the active Tool Step is reconciled against Runtime.

The resumed Run restores cumulative budget use, messages, observations, seen Model/Tool Call identities, effective-model provenance and Provider usage. It does not restore Provider hidden state.

Runtime owns physical Job and process truth. Harness requests `task.cancel`, observes the result and keeps `cancel-requested` nonterminal until a later Receipt proves `cancelled`, completion, failure, timeout or UNKNOWN. Runtime execution is dispatched with `waitMs=0`, then polled in short bounded intervals so cancellation and deadlines remain responsive.

Provider execution follows the same shape through `AgentTurnCallHandle.poll()` and `cancel()`. Explicit `transport_failed` and `unavailable` failures may be retried within a bounded retry budget while preserving the same logical Turn request. Timeout, rejection, malformed output and ambiguous failures are not retried. Provider-reported token usage is accumulated as a hard Run budget; Harness does not estimate missing usage. The default DeepSeek transport owns one HTTP connection per call and closes the active response/socket on cancellation. Codex and Hermes retain their provider-faithful process/session mechanics.

## Live event projection

The canonical `HarnessTrace` remains the durable semantic event record. `TraceRecorder` may additionally emit each already-recorded event to a best-effort sink used by `RunHandle.iter_events()` and CLI JSON Lines. Sink failure cannot change Run execution or evidence; consumers reconnect through Host state and the final Trace rather than treating the live stream as a durable broker.

## Dispatch fencing

Each durable `workspace.exec` preparation writes a `HarnessDispatchFence` bound to:

- Task revision;
- Harness Run and Assignment generation/digest;
- Tool Step Intent digest;
- Runtime operation and `clientRequestId`;
- issue and expiry times.

Harness verifies the fence before dispatch and again when the Runtime response returns. A stale Assignment therefore cannot be silently admitted as current Harness work, and an exposed Runtime Job is cancelled if post-dispatch validation fails.

The fence is also included in Runtime `foreignReferences` as immutable correlation evidence. Durable `workspace.patch` uses the same Host Intent/fence ordering but delegates physical effect reconciliation to Runtime's stable Patch receipt. On restart Harness queries `workspace.patch.get`; it never reconstructs or redispatches the edit from a partial local transcript. Runtime does not yet validate a Host MAC or call back into Host at admission, so this is not claimed as cryptographic end-to-end authorization.

## Recovery ordering

Native Run recovery is ordered as:

```text
load active Tool Step
→ reconcile Runtime dispatch / cancellation
→ persist the latest Receipt and Observation
→ inspect Workspace and diff
→ derive remaining UNKNOWNs
→ retain, abandon or replace only when evidence permits
```

This prevents Workspace cleanup or replacement decisions from racing ahead of an unresolved physical Tool Step.

## Application surface

`HarnessRunner` is a facade over the existing authorities:

```text
HarnessRunPlan
  → TaskContract / Context compilation / ToolGrant admission
  → HarnessHost Assignment
  → HostHarnessRunStore + RuntimeToolBridge
  → OrdivonAgentLoop
  → durable Run receipt
  → optional CompletionProposal / adjudication
```

It adds no durable object of its own. Every persisted transition still passes through `HarnessHost`, Host CAS and the Host Journal. Every physical Tool operation still passes through Runtime. `HarnessExecutionResult` only aggregates the already-authoritative Run, proposal and decision results for the caller.

`RunHandle` is an in-process thread boundary for responsive Provider cancellation and live event projection. The Runner registers the handle before starting its worker, uses a fresh HostStorage connection in that worker, and removes the handle after completion. It is not a scheduler, service or recoverable process registry. After process loss, continuity comes from the durable Snapshot and `recover()`/`resume()`, not from the handle.

Execution entry guards are explicit:

- a current durable Snapshot must be resumed rather than restarted;
- an already recorded Run cannot be executed again;
- adjudication configuration is validated before an Attempt or Assignment is created;
- durable `workspace.mutate` is removed from model Tool definitions and rejected by `HarnessRunPlan`;
- durable `patch_workspace` is admitted only when both Runtime Patch operations are present and the Tool Grant binds allowed mutation paths;
- approval events remain unsupported rather than represented by an unreachable pause state.

The CLI is a thin projection of the same facade: `status`, `run`, `resume`, `cancel`, `recover` and `doctor`. It creates no alternate lifecycle. CLI `run` consumes a current Assignment; Assignment construction remains with the integrating Host/application because it requires concrete Task Contract, Context and Tool authority.

## Extension surfaces

Harness owns:

- its event-kind constants;
- `harness_operator_handoff()`;
- full Harness semantic history validation;
- the `ordivon-harness doctor` command.

Host owns the generic extension persistence port, handoff capsule and core history validation. Runtime owns Workspace, Job, Attempt, Artifact and cancellation mechanics.

## Freeze rule

Do not generalize the accepted `workspace.exec` durable Tool-step slice into arbitrary mutation, a daemon, workflow DSL, plugin platform, parallel Tools, subagents or Provider routing without a real workload and a reconcilable physical dispatch identity.
