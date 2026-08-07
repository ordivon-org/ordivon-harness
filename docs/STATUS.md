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
updated: 2026-08-07
summary: Stable maturity claim, proven capabilities, support boundary and known limits for Ordivon Harness.
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

Ordivon Harness is an independent caller-neutral Run system. The current writer is the Harness SQLite Journal/CAS; the default and only CLI authority is `independent-harness-run`.

## Operational

- `HarnessRunContract` with exact execution-bound authority;
- SQLite Store creation, reopen, Doctor, lease/revision fencing, backup and restore;
- durable Provider Call continuity and response-loss recovery;
- durable Tool-step intents/fences/receipts and Runtime reconciliation;
- Agent loop budgets, pause/resume and no-progress handling;
- no-Tool DeepSeek CLI profile;
- caller-supplied Runtime client Python API for Tool-bearing Runs;
- independent Run Receipt, CompletionProposal and recovery evidence;
- repository-repair read/edit bridge test surfaces;
- Host-free external-executor adapter.

## Removed in H3

The old Host-backed Runner, TaskContract/Assignment persistence, Host compatibility package, Host dependency/extra, `host` CLI namespace, cutover/rollback machinery, and Host-coupled Codex/Hermes execution drivers are not supported current paths and have no compatibility aliases.

## Known limits

- primary CLI does not construct Tool-bearing Runtime clients;
- CompletionProposal is not caller/domain completion authority;
- Provider/Tool UNKNOWN may require external reconciliation;
- public API and owner-local schemas remain pre-1.0;
- historical receipts prove the implementations they bind, not the current H3 source unless indexed as verified.

## Operator check

```bash
ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness doctor
```
