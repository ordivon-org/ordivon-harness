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
updated: 2026-08-08
summary: Canonical architecture for caller-neutral independent Harness Runs, execution-instance fencing, and targeted durable-state validation.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.authority
---
# Ordivon Harness Architecture

## Purpose

Ordivon Harness is an **independent Agent Run authority**. A caller supplies immutable semantic/execution authority in a `HarnessRunContract`; Harness owns the bounded execution lifecycle required to produce durable Run evidence.

## Ownership

```text
caller / domain / optional Host
        │
        │ HarnessRunContract
        ▼
┌────────────────────────────┐
│ Ordivon Harness            │
│                            │
│ independent Journal / CAS  │
│ Provider Call continuity   │
│ model ↔ Tool loop          │
│ Run budgets                │
│ pause / resume / recovery  │
│ Trace / Run Receipt        │
│ CompletionProposal         │
└─────────────┬──────────────┘
              │ Tool-bearing Runs only
              ▼
       HarnessRuntimeClient
              │
              ▼
           Runtime
```

Harness does not own caller Task state, domain commitments, final acceptance, or Runtime Workspace/Job truth. Runtime does not know the Harness state machine. Host is an optional caller rather than a persistence prerequisite.

> **Run terminality is not epistemic closure.** `candidate_completed` means the bounded Run formed a candidate result; it may retain explicit unresolved unknowns for caller/domain judgment.

## Execution Mandate and strategy

The caller does not have to prescribe every execution step. `HarnessExecutionMandate` is a higher-level delegation envelope over one or more possible Run attempts:

```text
caller / domain / optional Host
        │
        │ HarnessExecutionMandate
        │ objective + Context + completion semantics
        │ allowed execution profiles
        │ aggregate token / wall-time envelope
        ▼
  StrategyPolicy (not built in)
        │
        │ HarnessExecutionStrategy
        │ chosen profile + exact attempt budget/options
        │ optional adopted prior evidence refs
        ▼
  compile_harness_attempt()
        │
        ▼
   HarnessRunContract
   immutable attempt authority
        │
        ▼
    Run → Receipt
        │
        └── caller/Agent may choose another strategy/attempt
```

The distinction is deliberate: **Mandate says what has been delegated; Strategy says how the Agent currently chooses to act; Run Contract freezes one admitted attempt; Receipt says what actually happened.** `maxModelCalls` and `maxToolCalls` remain valid per-attempt runaway/fencing parameters, but the Mandate compiler does not treat them as caller-owned aggregate policy. It enforces the allowed execution-profile set and aggregate economic bounds (`maxTotalTokens`, `maxWallTimeMs`). Later attempts require an explicit `HarnessMandateConsumption` reconstructed from prior receipts; the compiler only admits a new RunBudget that fits inside the remaining envelope.

Current Mandate support is intentionally pure and stateless: Harness does not ship a built-in StrategyPolicy, Mandate scheduler, or second durable Mandate database. The caller supplies the exact Mandate plus consumption snapshot on re-entry; immutable Run receipts remain the source evidence from which that snapshot is reconstructed. Prior Run evidence can be adopted into a later Strategy as bound Context refs; automatic cross-attempt orchestration remains outside the current product until more real use pays for it.

## Run Contract

`HarnessRunContract` binds one **attempt** to caller identity/reference, Objective and Context refs, Provider/Adapter/model identity, Tool catalog and grant digests, execution budget, completion contract, system manifest, privacy policy, deadline and correlation links. The Contract digest is execution authority for that attempt: a Run may not silently execute against different values. When compiled from a Mandate, its system manifest binds the Mandate, selected profile, Strategy, attempt index, and adopted prior Context evidence.

Harness does not synthesize a higher-level Task from CLI flags. The caller authors the Contract; the CLI only supplies Run-local input messages.

## Persistence and continuity

The independent Store is the only current Harness writer. It owns:

- Run creation, caller binding and terminal projection;
- immutable CAS objects and contiguous Run events;
- leases and revision fencing;
- Provider Call claim, dispatch, completion, failure and UNKNOWN state;
- Tool-step intent, dispatch fence, receipt and observation chains;
- pause/resume snapshots;
- recovery assessments;
- Trace, Run Receipt and CompletionProposal objects.

There is no Host-backed Store, Assignment writer, dual write or cutover selector.

Ordinary Store open validates global physical authority: schema, SQLite `quick_check`, and retained CAS object identity/content. It does **not** replay every unrelated Run. Opening a Run continuity boundary validates that Run's complete semantic history before execution; explicit full Doctor remains the authority-wide history replay. This keeps fail-closed semantics local to the Run being executed instead of making every worker pay an all-Runs startup cost.

Durable event and request identities remain deterministic for idempotent replay. Execution ownership does not: Continuity Stores, Agent Bridges, and terminal recorders use process-instance owner identities for leases and Provider claims so two workers cannot consume one durable dispatch admission as two physical executions.

## Provider lifecycle

A Provider Call is durable before uncertain physical delivery. Live claims exclude competing holders; response loss is reconciled from retained Provider state rather than treated as permission to redispatch. Dispatching with no safe proof of outcome becomes UNKNOWN. Retry is admitted only when the retained failure semantics prove redispatch safe and budget remains.

Provider identity belongs to Harness execution. A higher-level caller does not need to model Provider sessions or retry state.

A Provider turn that simultaneously requests ordinary Tools and submits a Run conclusion is treated as a **model-correctable action conflict**, not as permission to choose on the model's behalf and not as a Harness failure. Harness dispatches none of those ordinary Tools and admits no conclusion from that mixed turn; the next model turn must choose whether to continue acting or conclude.

## Tool lifecycle

Tool-bearing Runs bind a complete Tool catalog digest and Tool grant digest. Before physical delivery, Harness records a Tool intent and dispatch fence. Runtime requests carry Harness authority references. Observation-only failures can be corrected by the Agent; ambiguous external effects require reconciliation and may terminate recovery as UNKNOWN.

The primary CLI intentionally supports only the canonical no-Tool DeepSeek profile. Tool-bearing applications use `ordivon_harness.api`/`core` with an application-supplied `HarnessRuntimeClient`.

## Pause, resume and recovery

Pause snapshots retain exact Run state and Provider source identity. Resume starts from that snapshot and may append caller messages. Recovery is conservative: it never converts lost delivery into success or automatic redispatch. Terminal evidence is reopenable from a fresh process.

## Completion

Harness can conclude that an Agent Run produced a candidate-completed result and can record a `CompletionProposal`. That is not the same as caller/domain completion. Final verification and commitment remain outside Harness.

## Integration boundary

`host_external_adapter.py` is intentionally duck-typed and Host-free. It maps a foreign execution request to an independent Harness Run and maps durable observations/completion proposal back out. It does not import Host, use Host storage, or transfer Run authority.

## Removed pre-H3 architecture

H3 intentionally removed the former `HarnessHost`, Host Assignment/TaskContract model, `HostHarnessRunStore`, Host CLI namespace, cutover machinery, Host dependency extra, and Host-coupled Codex/Hermes drivers. Historical evidence may describe those experiments, but current source does not decode or advertise them.
