---
schema_version: 1
id: harness.status
title: Harness Status
type: status
profile: organization
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - user
  - builder
  - operator
  - agent
updated: 2026-08-10
summary: Current maturity claim for Harness as a durable cognitive execution substrate, including proven cognition, continuity, execution and support boundaries.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.architecture
  - harness.compatibility
  - harness.verification
---
# Status

## Current state

Ordivon Harness is an independent caller-neutral **durable cognitive execution substrate** for bounded Agent Runs. The current writer is the Harness SQLite Journal/CAS; the default and only CLI authority is `independent-harness-run`.

## Operational

- Agent-owned multi-attempt Strategy admission over caller-delegated `HarnessExecutionMandate`: exact prior `CompiledHarnessAttempt` + terminal Receipt + optional retained `IndependentCompletionProposal` is validated as one contiguous lineage; independent caller/domain verification may enter as digest-bound immutable `HarnessStrategyEvidence`; `HarnessMandateConsumption` and remaining economic authority are derived mechanically; `HarnessAgentStrategySelection` binds the Agent's Profile/budget/adopted-evidence choice to the exact selection-context digest; and `compile_harness_selected_attempt()` resolves that choice into one immutable `HarnessRunContract` without a planner, semantic verifier or second Mandate store. Cross-attempt model-content retention requires explicit Mandate privacy authority while legacy/default Mandates remain metadata-only and preserve their canonical serialized identity;
- `HarnessRunContract` with exact execution-bound authority;
- SQLite Store creation, reopen, Doctor, lease/revision fencing, backup and restore;
- durable Provider Call continuity and response-loss recovery;
- durable Tool-step intents/fences/receipts and Runtime reconciliation;
- Agent loop budgets, pause/resume and no-progress handling, with separate Tool-call
  and caller/domain conclusion-correction counters/budgets;
- model-visible WorkingView projection separated from canonical Run history;
- Agent-owned durable WorkingSet transitions with exact replay/concurrency fencing;
- explicit discovery/materialization versus Agent selection boundary;
- attempt-local Provider/Tool cognition that survives clean/fault recovery but expires on successor cognition attempts;
- caller-owned interaction cognition after `needs_input`, with role/provenance admission and exact recovery;
- Agent-owned exact caller-ingress promotion into durable cognition without generic Memory extraction;
- bounded historical committed-cognition recall and exact-pin re-selection;
- current WorkingSet source addressability for lawful retain/drop/correction decisions;
- experimental `StandaloneHarnessRunner` cognition composition with exact caller-authored initial seed, automatic WorkingView/transition/promotion/history wiring and partial-bootstrap replay recovery;
- provider-neutral per-turn `AgentTurnCapabilities` bound into each exact `AgentTurnRequest`: the Loop derives current Harness-native action authority, DeepSeek renders/parses only that request-bound surface, capability changes alter dispatch/Provider request identity, and caller promotion disappears when no exact promotable caller ref remains;
- R2 internal recomposition now extracts `AgentTurnProjector` for exact read-side turn construction, `CognitionAdmissionKernel` for source-current durable cognition admission, and `ProviderCallLifecycle` for optional durable Provider identity/begin/admit/fail/retry/complete bridge addressing; retry/budget/stop/semantic policy remains in the sequential Loop and Continuity's independent Journal/CAS verifier remains unchanged;
- the complete R2 lineage reduces `_run()` from 2,083 to 1,876 lines on the no-progress-ownership lineage (the Provider port removes 98 lines from the current no-progress/two-kernel coordinator, 1,974 → 1,876) without adding a persistence schema or public service; Tool-effect/progress extraction remains deferred until real friction proves another boundary stronger than file-size pressure;
- DeepSeek mixed Tool+conclusion turns are model-correctable before physical Tool dispatch: neither the ordinary Tool actions nor the simultaneous conclusion are admitted from the ambiguous turn;
- Harness-owned `no_progress` stops carry execution reason in stop detail/Trace and do not synthesize an Agent conclusion, preserving structured-completion shape;
- no-Tool DeepSeek CLI profile;
- caller-supplied Runtime client Python API for Tool-bearing Runs;
- independent Run Receipt, CompletionProposal and recovery evidence;
- caller-defined `structured-result-v1` completion schemas for DeepSeek, with exact completion-Contract binding and generic result decoding;
- repository-repair read/edit bridge test surfaces;
- Host-free external-executor adapter.

## Removed in H3

The old Host-backed Runner, TaskContract/Assignment persistence, Host compatibility package, Host dependency/extra, `host` CLI namespace, cutover/rollback machinery, and Host-coupled Codex/Hermes execution drivers are not supported current paths and have no compatibility aliases.

## Known limits

- primary CLI does not construct Tool-bearing Runtime clients;
- Mandate support can now construct exact multi-attempt selection authority and admit an Agent-authored next Strategy, but Harness still does not schedule the next attempt, discover/rank Profiles, persist Mandate state, or ship a built-in StrategyPolicy/cross-attempt controller;
- there is intentionally no Host-specific cognition bridge: the tested Host cognition slices use generic `structured-result-v1` completion and Host-owned semantic admission;
- CompletionProposal is not caller/domain completion authority;
- `candidate_completed` is bounded-Run terminality, not a claim that all world uncertainty is resolved; CompletionProposal v2 carries `unresolvedUnknowns`, while v1 remains readable with an empty unknown set;
- structured completion constrains Provider output shape but does not make Harness a JSON-Schema or domain verifier; callers must still decode and semantically admit the result under their own authority;
- Provider/Tool UNKNOWN may require external reconciliation;
- public API and owner-local schemas remain pre-1.0;
- historical receipts prove the implementations they bind, not the current source unless indexed as verified;
- R3 introduces `HarnessAgentRun` as the supported state-root based Python execution handle. It hides SQLite Store/Continuity/Bridge/Runner wiring, rebuilds exact Snapshot-bound Provider source on resume, reconstructs budget from the Contract, and calls the caller-selected Adapter factory only after structural composition is admitted; the primary no-Tool CLI now uses this surface for `run`/`resume`;
- R3.2 makes supported composition fail before durable state: cognition privacy/history mismatch and exact Runtime-binding mismatch reject before Adapter construction, while Adapter/model/structured-completion mismatch reject after the caller-owned factory but before `harness.run-created`; Provider/Runtime liveness is deliberately not guessed by this preflight;
- caller-facing `HarnessCognitionProfile`, `HarnessCognitionSeed`, `HarnessCognitionSeedSource` and `HarnessCognitionSource` are now recommended API values for exact Agent-owned cognition bootstrap; the old `Standalone*` names remain compatibility aliases, while `AgentTurnRequest.tools + capabilities` remain the exact per-turn action authority and no global Capability Service is introduced;
- R3.1 is additive rather than a breaking facade cleanup: existing low-level recommended exports remain available while CLI/Python adoption moves to `HarnessAgentRun`; removing `StandaloneHarnessRunner`, concrete SQLite composition objects or other advanced exports is a later evidence-gated decision, not part of this slice;
- there is no generic Memory/RAG/ranking/summarization layer, cross-Run cognition orchestrator, semantic supersession graph or automatic relevance policy;
- large-WorkingSet discovery/inspection strategy, initial cognition bootstrap and cross-Run cognition reuse remain open Agent-side/system-boundary questions rather than solved Harness policy.
- H0 independently reproduced Tool-first/later-correct-reasoning ordering pressure and H1 validated an advanced/internal generic `DeliberationThenToolRunner`. H2 closes the validated internal composition lifecycle with one aggregate RunBudget, one cancellation authority and one absolute composition deadline across deliberation and the later caller-owned Tool loop; phase-A `AgentTurnAdapterError` preserves known failure taxonomy and `PRE_DISPATCH_SAFE` no longer becomes false Provider uncertainty. P1 additionally proves that `DomainToolLoopPlan.assignment_deadline_ms` is authority for the whole lifecycle-bound composition: an already-expired Assignment now blocks phase-A Provider dispatch, and remaining wall-clock Assignment authority is projected into the shared monotonic composition deadline without mixing clock domains. The lifecycle-bound path remains advanced/internal rather than recommended `ordivon_harness.api` because no fresh independent domain consumer has yet forced promotion.

## Operator check

```bash
ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness doctor
```
