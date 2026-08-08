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
- Provider Call claim, dispatch, completion, failure and UNKNOWN state, with exact request/result content only when authorized;
- Tool-step intent, dispatch fence and receipt chains, plus exact Tool observations only when authorized;
- privacy-projected pause/resume snapshots;
- recovery assessments;
- privacy-projected Trace and terminal Run evidence, with exact conclusion/CompletionProposal content only when authorized.

There is no Host-backed Store, Assignment writer, dual write or cutover selector.

### Privacy authority inside continuity

The Run Contract privacy policy is execution authority, not a diagnostic preference. Default `metadata-only` continuity retains identities, digests, causal/effect receipts and budgets while omitting exact model/Tool content from Harness-managed durable objects. `bounded-private-content` may separately authorize model and Tool content; mixed objects use the stricter applicable authority so Tool calls, Tool-role messages and Tool observations cannot become a model-content persistence bypass.

Privacy does not weaken effect fencing. A digest-only completed Provider Call still prevents physical redispatch after response loss. If exact result/transcript/Tool content was not authorized for retention, recovery fails closed and requires caller-authorized rehydration rather than reconstructing content from another hidden Harness copy.

These are structural content laws, not semantic taint tracking: ordinary model text can semantically repeat Tool-derived information, and Harness does not currently prove otherwise.

Ordinary Store open validates global physical authority: schema, SQLite `quick_check`, and retained CAS object identity/content. It does **not** replay every unrelated Run. Opening a Run continuity boundary validates that Run's complete semantic history before execution; explicit full Doctor remains the authority-wide history replay. This keeps fail-closed semantics local to the Run being executed instead of making every worker pay an all-Runs startup cost.

Durable event and request identities remain deterministic for idempotent replay. Execution ownership does not: Continuity Stores, Agent Bridges, and terminal recorders use process-instance owner identities for leases and Provider claims so two workers cannot consume one durable dispatch admission as two physical executions.

## Model-visible Working View

The mature `OrdivonAgentLoop` no longer requires the Provider request to be identical to the complete canonical Run-local message history. An optional internal `WorkingViewProjector` seam may supply the exact model-visible messages for each Provider turn while the Loop continues to retain canonical execution history for progress accounting, recovery and Tool correlation.

The current `WorkingSetViewProjector` is deliberately narrow: it loads the current **committed** `HarnessWorkingSetSpec` and deterministically compiles its pinned exact sources into one `HarnessWorkingView`. It performs no Context discovery, ranking, RAG, Memory, summarization or automatic source selection.

Discovery and selection are separate authorities. A domain, World integration or Runtime Tool may discover raw paths, URLs, records or already-materialized source identities. Harness does not interpret those results as relevant Context. Raw content must first cross the Run's privacy-aware source-materialization boundary before it can become an exact `HarnessWorkingSetPin`; the resulting CAS object identity, not a caller-guessed semantic digest, is the pin authority.

Transient Tool evidence is short-lived cognition continuity, not durable selected Context. When a projected Run uses Tools, the Loop carries the complete Provider-faithful exchange for the current WorkingSet attempt: the exact Provider-authored assistant message containing `toolCalls`, followed by the exact bound Tool Observation messages for those calls. A Tool Observation without its preceding Provider-authored call is not a valid model-view suffix. The committed Working View remains the exact prefix; arbitrary user/system text and replacement projections are rejected before physical Provider dispatch. Continuity Doctor independently reconstructs earlier completed Provider Tool turns and their bound observations, so later or mechanically forged events cannot invent transient provenance after the fact.

An execution may explicitly grant an Agent-owned cognition transition surface. In that mode, one Provider turn can return an `AgentWorkingSetTransitionProposal` containing exact successor pins plus a bounded basis. This is a third Agent action category beside external Tool calls and a Run conclusion; it is not charged to the Tool budget and it cannot be mixed with either action in the same normalized turn. DeepSeek may encode the proposal as a function call on the wire, but the Adapter normalizes it as cognition state rather than an `AgentToolCall`.

Continuity applies one accepted proposal as an atomic `replan → select exact pins → commit` Journal transaction under one Run lease. Provider-authored transitions bind two different facts: `sourceWorkingSetDigest` identifies the durable selected Context that remained current, while `sourceModelViewDigest` identifies the exact effective view the Agent actually saw, including any admitted transient Tool exchanges. The exact retained Provider request/result prove that the proposal came from that model view. Competing proposals have one winner, exact replay is idempotent, and Continuity Doctor verifies the proposal/source/Provider evidence rather than trusting a mechanically valid WorkingSet chain alone. Base-only direct transition receipts remain readable under the earlier single-view evidence form.

Transient Tool exchanges are **attempt-local cognition**, not durable selected knowledge. When exact model and Tool content are authorized, any fresh-process resume reconstructs the current attempt's complete Provider-authored Tool exchanges from Journal/CAS authority: the current committed WorkingSet event defines the attempt boundary, later completed Provider Tool turns identify the assistant `toolCalls` messages, terminal Tool intent/receipt/Observation evidence proves physical observations, and an active effect is reconciled without redispatch before any still-pending calls execute. This applies to both hard recovery and an ordinary clean pause/resume. When a successor WorkingSet commits, all predecessor-attempt transient exchanges disappear automatically.

Durable cognition promotion needs no separate Memory object or Harness-authored promotion action. A source may be physically materialized in CAS without becoming Agent cognition. It becomes durable current cognition only when the Agent explicitly includes its exact pin in a successor committed WorkingSet; carrying the pin preserves it across later process/attempt boundaries, while omitting the pin explicitly drops it. Thus `source bytes exist`, `source is current cognition`, and `source remains selected later` are three different facts. Harness still does not decide which observed facts deserve promotion, synthesize memories, rank retained sources or inject materialized-but-unselected objects into future model views.

Historical recall is the inverse mechanical boundary, not a semantic Memory search. An execution may explicitly grant `inspect_working_set_history`, which returns a bounded reverse-chronological catalog of **earlier committed WorkingSet identities and exact pins only**. Materialized-but-never-selected CAS objects are absent; historical source content, semantic similarity, relevance scores and automatic source injection are absent. The Agent decides when to inspect the catalog and may use the existing WorkingSet transition control to re-select an exact historical pin. History inspection performs no Runtime dispatch and consumes no external Tool-call budget, but its Provider-faithful function result is bounded by observation bytes and participates in observation/no-progress accounting. Continuity recomputes the result from Journal history relative to the exact WorkingSet that authored the Provider turn, so a forged local history reader cannot authorize invented recall evidence. Exact clean-pause replay of the function-call/result transcript still requires both model- and Tool-content authority because the Provider wire uses a structural Tool channel.

Execution control is distinct from task Context. Provider adapters may project exact per-turn capability and remaining-budget metadata from `AgentTurnRequest` as a Harness-authored system control envelope; that envelope is not part of the WorkingSet or `HarnessWorkingView`. For DeepSeek, the envelope names the Runtime Tools currently admitted for that turn and the remaining bounded budget, so a capability removed after earlier Tool use is visible to the Agent instead of existing only as a hidden Harness rule.

No-progress and observation-only limits are effect gates, not epistemic verdicts. Their durable authority is the retained progress counters; the process-local gate reason is only a projection and is recomputed after fresh-process resume. Reaching one closes new external observation capability and gives the Agent a subsequent cognition/closure turn over the evidence it has already seen. A successor WorkingSet attempt may still be legal with exactly the same pins because attempt identity owns transient cognition lifetime: such an attempt reset discards predecessor Tool exchanges but is **not** structural progress, does not reset the counters, and does not reopen a closed soft effect gate. A transition whose exact selected pins change is a structural cognition mutation and may reset the soft progress counters/gate. Hard Tool-call budget remains global and cannot be revived by either form of cognition transition. A Provider that still refers to a now-unavailable historical Runtime Tool receives a bounded local, model-correctable rejection with `physicalDispatch=false`; this correction consumes correction budget but cannot exceed the external Tool budget. Harness therefore bounds effects while the Agent still owns whether to conclude `candidate_completed`, report concrete `needs_input`, or perform an admitted cognition transition.

The projector, transition handler, bounded WorkingSet-history reader, overlay helper and DeepSeek cognition switches remain experimental execution seams rather than part of the recommended `ordivon_harness.api` facade. The transition proposal value is available from `ordivon_harness.core` for caller-neutral integrations. Harness still has no generic CandidateSet, Context Service, Memory service or semantic search/relevance policy.

## Provider lifecycle

A Provider Call is durable before uncertain physical delivery. Live claims exclude competing holders; response loss is reconciled from retained Provider state rather than treated as permission to redispatch. Dispatching with no safe proof of outcome becomes UNKNOWN. Retry is admitted only when the retained failure semantics prove redispatch safe and budget remains.

Provider identity belongs to Harness execution. A higher-level caller does not need to model Provider sessions or retry state.

A Provider turn that simultaneously requests ordinary Tools and submits a Run conclusion is treated as a **model-correctable action conflict**, not as permission to choose on the model's behalf and not as a Harness failure. Harness dispatches none of those ordinary Tools and admits no conclusion from that mixed turn; the next model turn must choose whether to continue acting or conclude.

## Tool lifecycle

Tool-bearing Runs bind a complete Tool catalog digest and Tool grant digest. Before physical delivery, Harness records a Tool intent and dispatch fence. Runtime requests carry Harness authority references. Observation-only failures can be corrected by the Agent; ambiguous external effects require reconciliation and may terminate recovery as UNKNOWN.

The primary CLI intentionally supports only the canonical no-Tool DeepSeek profile. Tool-bearing applications use `ordivon_harness.api`/`core` with an application-supplied `HarnessRuntimeClient`.

## Pause, resume and recovery

Pause snapshots retain Provider source identity plus the Run state content or content digests authorized by the Contract. Exact-content resume starts from an authorized snapshot and may append caller messages. In the non-projected path those appended messages are part of the next Provider-visible transcript and may reset soft progress. In the current projected WorkingView path they remain canonical Run history but are not yet a proven model-visible WorkingView ingress, so they do **not** reset soft progress merely by existing; a future cognition-ingress boundary must make such input explicitly Provider-visible before it can count as progress. Digest-only recovery is conservative: it never converts omitted content into reconstructed content, lost delivery into success, or completion into permission to redispatch. Terminal execution evidence remains reopenable from a fresh process even when exact conclusion/proposal content was intentionally not retained.

## Completion

Harness can conclude that an Agent Run produced a candidate-completed result and can record a `CompletionProposal`. That is not the same as caller/domain completion. Final verification and commitment remain outside Harness.

## Integration boundary

`host_external_adapter.py` is intentionally duck-typed and Host-free. It maps a foreign execution request to an independent Harness Run and maps durable observations/completion proposal back out. It does not import Host, use Host storage, or transfer Run authority.

## Removed pre-H3 architecture

H3 intentionally removed the former `HarnessHost`, Host Assignment/TaskContract model, `HostHarnessRunStore`, Host CLI namespace, cutover machinery, Host dependency extra, and Host-coupled Codex/Hermes drivers. Historical evidence may describe those experiments, but current source does not decode or advertise them.
