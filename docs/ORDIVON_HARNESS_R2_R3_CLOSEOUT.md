# Ordivon Harness R2–R3 closeout

## Accepted boundary

R2–R3 closes four practical gaps without adding a daemon, scheduler, session database or generic workflow engine:

```text
R2
  live semantic event projection
  bounded transient Provider retry
  Provider-reported token hard limit
  bounded known-no-effect Tool correction

R3
  capability-adaptive durable structured Patch
  Host Intent before Runtime effect
  Runtime receipt reconciliation after response loss or process loss
```

The authoritative owners remain unchanged:

- Host owns Task, Assignment, Journal, CAS and completion authority;
- Harness owns the model–Tool loop, Run-local state and semantic evidence;
- Runtime owns Workspace bytes and Patch commitment truth.

## Live events

`TraceRecorder` records every event into the canonical Trace before invoking an optional live sink. `RunHandle.iter_events()` and CLI `--events-jsonl` consume that projection. Sink exceptions are ignored by design: a UI or terminal subscriber cannot invalidate the Run. Restart continuity comes from Host state and the final Trace, not from replaying an in-memory event queue.

## Provider retry and token budget

Only explicit `transport_failed` and `unavailable` failures are retryable. Timeout, Provider rejection, malformed output, ordinary failure and unknown semantics stop the Run. Retries preserve the same logical Turn request and are bounded by both retry count and the monotonic wall deadline.

The token hard limit uses Provider-returned usage only. Harness accepts explicit total tokens or prompt-plus-completion counts and never fabricates a missing estimate. Usage is checked before Tool dispatch, so an over-budget response cannot create a subsequent physical Effect.

## Tool correction

Harness returns a Tool rejection to the model only when it can prove that no Runtime Effect was committed: local argument/schema rejection, Tool Grant denial, or Runtime `not_committed` rejection. UNKNOWN remains terminal. The correction count is bounded and persists through Run snapshots.

This is not automatic Tool retry. The model must issue a new Tool Call identity and corrected arguments.

## Durable structured Patch

Runtime capability discovery treats `workspace.patch` and `workspace.patch.get` as an inseparable optional pair. Older Runtime catalogs remain usable without Patch; a partial pair fails closed.

For an admitted Patch:

```text
bind Assignment / Run / Step / Tool Call digest
→ derive stable clientRequestId
→ persist Host Tool Step Intent and DispatchFence
→ Runtime persists Patch Intent and before/after digest plan
→ apply only from the complete before state
→ commit Runtime Patch receipt
→ persist Host Receipt and Observation
```

If the response is lost, Harness reissues the byte-identical request. If the Harness process dies after Runtime commitment but before Host Receipt persistence, a fresh Harness calls `workspace.patch.get` and records the committed result without redispatching file writes. A mixed physical file state remains UNKNOWN.

Low-level `workspace.mutate` remains unavailable in durable Run plans.

## Validation

The deterministic release gate contains 141 unittest cases, including nine new fault-focused R2–R3 cases:

- transient Provider retry with one Tool Effect;
- timeout without retry;
- local Tool correction without Effect;
- token hard limit before Tool dispatch;
- live event stream equal to the canonical Trace;
- exact Patch response-loss replay with one physical modification;
- process-loss Patch reconciliation through `workspace.patch.get` without redispatch;
- fail-closed partial Runtime capability discovery;
- zero retry/correction budget persistence.

The paired Runtime gate additionally proves exact Patch replay, request-identity conflict, missing-Receipt recovery, mixed-state UNKNOWN, rollback-compatible additive Patch storage and a real 15-Tool MCP journey.
