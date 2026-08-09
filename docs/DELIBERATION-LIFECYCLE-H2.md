---
schema_version: 1
id: harness.research.deliberation-lifecycle-h2
title: Deliberation Lifecycle H2
type: experiment
profile: research
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
updated: 2026-08-09
summary: H2 binds H1 no-Tool deliberation and the later caller-owned Tool loop to one aggregate budget, cancellation authority, and absolute deadline without moving domain strategy or admission into Harness.
evidence_status: verified
readiness: ADVANCED_RESEARCH
related:
  - harness.research.deliberation-composition-h1
  - harness.research.deliberation-before-tools-h0
  - harness.status
  - harness.architecture
---
# Deliberation Lifecycle H2

## Question

H1 validated a generic composition:

```text
no-Tool cognition
→ exact non-authoritative cognition record
→ caller-owned Tool loop
```

but intentionally left two lifecycle gaps:

1. phase A and phase B could receive independent budgets;
2. cancellation only covered the Tool loop while phase A used a direct Adapter call.

H2 asks:

> Can one Harness lifecycle authority span both phases without double-spending budget, minting a fresh phase-B deadline, or falsely claiming cancellation for an uncontrollable Provider call?

## Result

Accepted internal composition:

```text
one RunBudget
one CancellationToken
one absolute RunDeadline
        ↓
no-Tool deliberation
        ↓
exact remaining authority
        ↓
caller-owned DomainToolLoop
```

Harness still owns only sequencing and lifecycle mechanics. It does **not** own domain scoring, strategy, admission, external effects, or world truth.

H2 remains an advanced/internal capability. It is **not** exported through `ordivon_harness.api`, and no hidden deliberation pass is enabled by default.

## Aggregate budget

The caller supplies one authoritative `RunBudget` for the composition.

Phase A consumes:

- one model call;
- accountable Provider tokens;
- elapsed wall time.

Phase B receives only the exact remainder. A conservative `request_token_upper_bound` is honored before phase-A Provider dispatch when the Adapter exposes it.

If phase A leaves no valid model/token/wall authority for phase B, Harness stops before Tool exposure.

## Cancellation

Lifecycle-bound mode reuses existing Adapter control capabilities:

```text
start_invoke + AgentTurnCallHandle
or
invoke_with_control
```

The minimal `AgentTurnAdapter` protocol is not widened.

An Adapter that only provides blocking `invoke()` fails closed in lifecycle-bound mode rather than pretending it supports in-flight cancellation.

Two cancellation races are kept distinct:

```text
cancel while Provider still pending
→ active handle.cancel()
→ cancel_unknown
→ no Tool exposure
```

versus:

```text
cancel arrives while Provider result becomes known
→ known phase-A result
→ cancelled at phase boundary
→ no false UNKNOWN
→ no Tool exposure
```

## Absolute deadline

`OrdivonAgentLoop.run` / `DomainToolLoopRunner.run` gain an optional external `RunDeadline` upper bound.

The effective loop deadline is the earliest applicable authority:

```text
min(
  local RunBudget wall deadline,
  assignment deadline,
  external absolute deadline
)
```

The external deadline can tighten authority but cannot extend it.

H2 creates one absolute deadline before phase A and passes that same deadline into phase B, so phase B does not receive a fresh later wall-time window.

## Mechanical acceptance

Implementation + apparatus revision:

```text
8100879e8ea7823b9ae231a681598dada2ea5c3c
```

Core lifecycle source SHA-256:

```text
e4f54bbe849abc700ed427ec7327f93efc3aa6039c0edd4570f401132815811f
```

Acceptance apparatus SHA-256:

```text
e9b8e9a18641955cc40e0b5b5fc581e2d302431bf54931f2f020d9e0ccf54a97
```

Raw receipt:

```text
evidence/harness-h2-deliberation-lifecycle-8100879.json
bytes  = 2221
sha256 = sha256:8a08890b40f36e92fafe67815c6c886acdff5f49137e3e1e2f803eda02e21bd9
```

Runtime binding:

```text
jobId                 = job-019fe6fb-1594-7d30-92b4-81a459409c13
attemptId             = attempt-019fe6fb-1594-7d30-92b4-81bdc9d1ef87
executionPlanDigest   = sha256:5b55ebb13ef49349e09fe6ca5678c742045f8823aeba7506dc6886270feaed7d
workspaceSourceDigest = sha256:56a78256575df27a7c66c63898d1753019f24b67cf6a986c2dd052eb861c85f5
terminalEvidence      = sha256:94937b201f0bd96b92eaa67f00577f7046eeb98696747dd5364bdc9d82c6b3a5
executionProfile      = trusted_local
```

The Runtime `sourceRevision` remains the Workspace opening revision; exact executed source state is bound by `workspaceSourceDigest` and Workspace current HEAD `8100879...`.

All **12/12 H2 gates** pass:

- normal caller-owned choice remains functional;
- phase-A model-call budget is consumed before phase B;
- phase-A token budget is consumed before phase B;
- aggregate observed usage does not double-spend;
- one cancellation authority spans both phases;
- one absolute deadline spans both phases;
- phase-A exhaustion blocks Tool exposure;
- token preflight can block Provider dispatch;
- pending in-flight cancellation becomes `cancel_unknown` and actively cancels;
- known-result/cancel race remains known and blocks Tool exposure without false UNKNOWN;
- phase-A elapsed time reduces phase-B wall authority;
- uncontrolled Adapters fail closed.

## Regression

On the exact committed H2 revision:

```text
30 focused compatibility tests passed
315 discovered tests passed
3 skipped
compileall passed
```

Regression Runtime Job:

```text
job-019fe6fd-9acf-79a1-88b0-0ab6a5ef52f2
terminal evidence = sha256:4b6319bea48c5e99b33334e1cd8d39b1933c8e67275a4281d6362ee37b2f2f0c
```

## What H2 establishes

H0 → H1 → H2 now supports this Harness world model:

```text
Context
  ↓
optional non-authoritative deliberation
  ↓
considered candidate
  ↓
caller-owned Tool intent
```

with a single bounded lifecycle across the transition.

The key distinction remains:

```text
cognition authority != effect authority
```

Harness may control **when** Tool surfaces become visible and how lifecycle authority spans that transition. Harness must not decide **which** domain action is correct.

## What H2 does not establish

H2 does not establish:

- a mandatory deliberation phase for every Tool-bearing turn;
- a recommended public API;
- domain strategy correctness;
- durable persistence/recovery of deliberation records;
- durable phase-A Provider retry/replay;
- population-level model behavior.

Public promotion remains evidence-gated by a real independent consumer.

## Post-merge closeout: stale prepare lease race

The first post-merge full-suite run exposed one unrelated but real concurrency race in the existing `SQLiteHarnessRuntimeBridge` path. H2 did not modify the bridge/store/test files involved; their Git blobs were identical to the pre-H2 base. The H2 scheduling changes nevertheless made the latent race easier to observe, so closeout did not classify it as harmless noise.

The failing interleaving was:

```text
worker A
  prepare Tool Step at Run revision R
  release prepare lease
  dispatch one physical Runtime call

worker B/C
  observed the earlier Run state
  reacquire tool-prepare after A advanced the Run to R+1
  attempt stale duplicate prepare
  temporarily occupy the Run lease

worker A
  Runtime returns
  receipt admission can collide with the stale prepare lease
```

The physical effect invariant remained intact (`workspace.exec` was dispatched exactly once), but no worker was guaranteed to finish durable receipt recording. A diagnostic failure showed one `harness.tool-step-prepared` Event, one physical Runtime call, and no terminal Tool receipt.

The repair adds an optional expected-Run-revision fence to lease admission. `prepare_tool_step` now binds its observed Run revision before acquiring the prepare lease. If another execution advances the Run first, the stale prepare cannot acquire new authority on the newer revision.

Repair commit:

```text
d4d21cdc404f3af30b7641ea8e8132eff58918e6
```

This adds the more general invariant:

```text
observed Run revision R
!=
authority to acquire a lease on later Run revision R+1
```

Validation on the committed repair revision:

```text
original concurrent RuntimeBridge test: 100 / 100 consecutive passes
Harness full suite:                316 tests passed
skipped:                           3
compileall:                        passed
```

Final main validation Runtime Job:

```text
job-019fe719-98b8-7a43-b06b-ae0b7d855dd3
terminal evidence = sha256:b90bdfafc04209da5d2614884eb91dd5fd50c2c2d79ea2aea437c4dc3e206fd8
```

The repair does not change H2's product boundary. Deliberation lifecycle composition remains advanced/internal, and no recommended public API is forced without an independent domain consumer.
