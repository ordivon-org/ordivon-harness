# Ordivon Harness architecture

## Boundary

Ordivon Harness is an extension over the thin Ordivon Host kernel, not a second Host and not a Provider Session store.

```text
ordivon-computing / ordivon-protocol
  native cross-implementation Harness continuity objects
          ↓
ordivon-host
  Task / Journal / CAS / Kernel / Runtime client
          ↑ thin extension adapter
ordivon-harness
  Attempt / Assignment / Run / Tool Step / Recovery / Completion
  Provider adapters and bare-model execution
          ↓ thin Runtime port
ordivon-runtime
  Workspace / Job / Attempt / Artifact / cancellation
```

The dependency must remain one-way. Host accepts extension event kinds as bounded dotted strings and preserves their bytes and Task projections without importing Harness semantics.

## Durable ownership

Harness code constructs and validates:

- `TaskContract` and `TaskAttemptDescriptor`;
- `HarnessAssignment`, `ToolGrant` and native Run Contract;
- retained Tool catalog semantics;
- durable Tool Step Intent, Receipt, Observation and bounded Run Snapshot;
- Run Recovery and Abandonment evidence;
- Trace, Tool Observations and `HarnessRunReceipt`;
- CompletionProposal, independent CompletionVerification and CompletionDecision.

The bytes remain in Host CAS and their event admission remains in the Host Journal. This does not make the Host package depend on Harness code.

## Execution ownership

Provider Sessions, subprocesses, transcripts and model-local message history are disposable execution state. They never own Task continuity. A bounded Run Snapshot may preserve enough public Run state to resume an input/approval boundary or reconcile a prepared Runtime dispatch, but it does not preserve Provider hidden state.

Runtime owns physical process and Job cancellation. Harness may request `task.cancel` and classify the returned evidence, but cannot claim cancellation merely because a local token was set. Host remains the only owner of durable Task truth and completion admission.

Provider-specific adapters remain separate because Codex App Server and Hermes ACP have materially different lifecycle and event semantics. The first-party bare-model loop is a narrow reference path, not a replacement for mature Provider Harnesses.

## Extension surfaces

Harness owns:

- its event-kind constants;
- `harness_operator_handoff()`;
- full Harness semantic history validation;
- the `ordivon-harness doctor` command.

Host owns only the generic handoff capsule and generic history validation.

## Freeze rule

Do not generalize the accepted `workspace.exec` durable Tool-step slice into arbitrary mutation, a daemon, workflow DSL, plugin platform, parallel Tools, subagents or Provider routing without a real workload and a reconciliable physical dispatch identity.
