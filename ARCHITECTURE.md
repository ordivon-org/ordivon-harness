# Ordivon Harness architecture

## Boundary

Ordivon Harness is an extension over the thin Ordivon Host kernel, not a second Host and not a Provider Session store.

```text
ordivon-computing / ordivon-protocol
  HarnessToolStepIntent / HarnessToolStepReceipt
  HarnessRunSnapshot / HarnessDispatchFence
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

`OrdivonAgentLoop.resume()` currently resumes:

- `needs-input` after additional messages are supplied;
- `effect-dispatch-pending` after the active Tool Step is reconciled against Runtime.

The resumed Run restores cumulative budget use, messages, observations, seen Model/Tool Call identities, effective-model provenance and Provider usage. It does not restore Provider hidden state.

Runtime owns physical Job and process truth. Harness requests `task.cancel`, observes the result and keeps `cancel-requested` nonterminal until a later Receipt proves `cancelled`, completion, failure, timeout or UNKNOWN. Runtime execution is dispatched with `waitMs=0`, then polled in short bounded intervals so cancellation and deadlines remain responsive.

Provider execution follows the same shape through `AgentTurnCallHandle.poll()` and `cancel()`. The default DeepSeek transport owns one HTTP connection per call and closes the active response/socket on cancellation. Codex and Hermes retain their provider-faithful process/session mechanics.

## Dispatch fencing

Each durable `workspace.exec` preparation writes a `HarnessDispatchFence` bound to:

- Task revision;
- Harness Run and Assignment generation/digest;
- Tool Step Intent digest;
- Runtime operation and `clientRequestId`;
- issue and expiry times.

Harness verifies the fence before dispatch and again when the Runtime response returns. A stale Assignment therefore cannot be silently admitted as current Harness work, and an exposed Runtime Job is cancelled if post-dispatch validation fails.

The fence is also included in Runtime `foreignReferences` as immutable correlation evidence. Runtime does not yet validate a Host MAC or call back into Host at admission, so this is not claimed as cryptographic end-to-end authorization.

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

## Extension surfaces

Harness owns:

- its event-kind constants;
- `harness_operator_handoff()`;
- full Harness semantic history validation;
- the `ordivon-harness doctor` command.

Host owns the generic extension persistence port, handoff capsule and core history validation. Runtime owns Workspace, Job, Attempt, Artifact and cancellation mechanics.

## Freeze rule

Do not generalize the accepted `workspace.exec` durable Tool-step slice into arbitrary mutation, a daemon, workflow DSL, plugin platform, parallel Tools, subagents or Provider routing without a real workload and a reconciliable physical dispatch identity.
