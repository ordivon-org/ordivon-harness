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
updated: 2026-08-09
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

- caller-delegated `HarnessExecutionMandate`, receipt-derived `HarnessMandateConsumption`, selectable `HarnessExecutionProfile` / `HarnessExecutionStrategy`, and pure `compile_harness_attempt()` into exact `HarnessRunContract` attempt authority;
- `HarnessRunContract` with exact execution-bound authority;
- SQLite Store creation, reopen, Doctor, lease/revision fencing, backup and restore;
- durable Provider Call continuity and response-loss recovery;
- durable Tool-step intents/fences/receipts and Runtime reconciliation;
- Agent loop budgets, pause/resume and no-progress handling;
- model-visible WorkingView projection separated from canonical Run history;
- Agent-owned durable WorkingSet transitions with exact replay/concurrency fencing;
- explicit discovery/materialization versus Agent selection boundary;
- attempt-local Provider/Tool cognition that survives clean/fault recovery but expires on successor cognition attempts;
- caller-owned interaction cognition after `needs_input`, with role/provenance admission and exact recovery;
- Agent-owned exact caller-ingress promotion into durable cognition without generic Memory extraction;
- bounded historical committed-cognition recall and exact-pin re-selection;
- current WorkingSet source addressability for lawful retain/drop/correction decisions;
- DeepSeek mixed Tool+conclusion turns are model-correctable before physical Tool dispatch: neither the ordinary Tool actions nor the simultaneous conclusion are admitted from the ambiguous turn;
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
- Mandate support currently compiles caller delegation + a supplied Strategy into Run attempts; Harness does not yet persist Mandate state or ship a built-in StrategyPolicy/cross-attempt controller;
- there is intentionally no Host-specific cognition bridge: the tested Host cognition slices use generic `structured-result-v1` completion and Host-owned semantic admission;
- CompletionProposal is not caller/domain completion authority;
- `candidate_completed` is bounded-Run terminality, not a claim that all world uncertainty is resolved; CompletionProposal v2 carries `unresolvedUnknowns`, while v1 remains readable with an empty unknown set;
- structured completion constrains Provider output shape but does not make Harness a JSON-Schema or domain verifier; callers must still decode and semantically admit the result under their own authority;
- Provider/Tool UNKNOWN may require external reconciliation;
- public API and owner-local schemas remain pre-1.0;
- historical receipts prove the implementations they bind, not the current source unless indexed as verified;
- WorkingSet cognition controls remain experimental/internal rather than part of the recommended `ordivon_harness.api` facade;
- there is no generic Memory/RAG/ranking/summarization layer, cross-Run cognition orchestrator, semantic supersession graph or automatic relevance policy;
- large-WorkingSet discovery/inspection strategy, initial cognition bootstrap and cross-Run cognition reuse remain open Agent-side/system-boundary questions rather than solved Harness policy.

## Operator check

```bash
ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness doctor
```
