# Ordivon Harness architecture

## Boundary

Ordivon Harness is an extension over the thin Ordivon Host kernel, not a second Host and not a Provider Session store.

```text
ordivon-host
  Task / Journal / CAS / Kernel / Runtime client
          ↑
ordivon-harness
  Attempt / Assignment / Run / Recovery / Completion
  Provider adapters and bare-model execution
```

The dependency must remain one-way. Host accepts extension event kinds as bounded dotted strings and preserves their bytes and Task projections without importing Harness semantics.

## Durable ownership

Harness code constructs and validates:

- `TaskContract` and `TaskAttemptDescriptor`;
- `HarnessAssignment`, `ToolGrant` and native Run Contract;
- retained Tool catalog semantics;
- Run Recovery and Abandonment evidence;
- Trace, Tool Observations and `HarnessRunReceipt`;
- CompletionProposal, independent CompletionVerification and CompletionDecision.

The bytes remain in Host CAS and their event admission remains in the Host Journal. This does not make the Host package depend on Harness code.

## Execution ownership

Provider Sessions, subprocesses, transcripts and model-local message history are disposable execution state. They never own Task continuity.

Provider-specific adapters remain separate because Codex App Server and Hermes ACP have materially different lifecycle and event semantics. The first-party bare-model loop is a narrow reference path, not a replacement for mature Provider Harnesses.

## Extension surfaces

Harness owns:

- its event-kind constants;
- `harness_operator_handoff()`;
- full Harness semantic history validation;
- the `ordivon-harness doctor` command.

Host owns only the generic handoff capsule and generic history validation.

## Freeze rule

Do not introduce effectful native continuation, a daemon, workflow DSL, plugin platform, parallel Tools, subagents or Provider routing without a real workload that fails under the retained boundary and cannot be served by a mature Provider Harness.
