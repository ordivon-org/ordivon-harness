---
schema_version: 1
id: harness.operations
title: Harness operational contract
type: operations
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - operator
  - builder
  - agent
updated: 2026-08-05
summary: Canonical operational contract for Harness Run execution, cancellation, resume, recovery, semantic Doctor, and escalation to Host or Runtime.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.architecture
  - harness.authority
---
# Operations

## Authority

One state root means one independent Harness Journal/CAS. There is no Host-backed writer and no cutover mode.

```bash
ordivon-harness --state-root /path/to/harness-state doctor
ordivon-harness --state-root /path/to/harness-state status HARNESS_RUN_ID
ordivon-harness --state-root /path/to/harness-state inspect HARNESS_RUN_ID
```

## Store administration

```bash
ordivon-harness --state-root /path/to/harness-state store-init
ordivon-harness --state-root /path/to/harness-state store-doctor
ordivon-harness --state-root /path/to/harness-state store-events HARNESS_RUN_ID
ordivon-harness --state-root /path/to/harness-state store-backup /path/to/backup
ordivon-harness store-verify-backup /path/to/backup
ordivon-harness store-restore /path/to/backup /new/state/root
```

Only `store-init` creates an authority root. Backup/restore refuse unsafe destination reuse and verification checks both database and retained CAS object truth.

## Run handling

A CREATED Run is executed with `run`. A PAUSED Run requires `resume`. A terminal Run is inspected rather than executed again. Contract digest conflicts fail closed.

## Provider recovery

Retained Provider Call status controls the next action. A safely failed pre-dispatch call may be retried within budget. A lost response after durable completion is replayed from Store. Ambiguous dispatch remains UNKNOWN until reconciled; transport loss is not implicit redispatch permission.

## Tool recovery

Tool intents and dispatch fences bind the exact Runtime operation and request identity. Observation-only failures may return to the model. Potentially effectful ambiguous delivery requires Runtime/domain reconciliation. The caller-supplied Runtime client remains the physical truth source.

## Escalation

| Problem | Authority |
| --- | --- |
| Harness Journal/CAS, Run revision, Provider/Tool continuity | Harness Doctor / Store tools |
| physical Workspace, Job, Attempt, Artifact or cancellation | Runtime |
| Task meaning, commitment, final verification | caller/domain/optional Host |
| unresolved ambiguous external effect | caller plus relevant external authority |

Harness may read externally supplied evidence during reconciliation but does not replace another owner's repair procedure.
