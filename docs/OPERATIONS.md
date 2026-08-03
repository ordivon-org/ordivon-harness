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
updated: 2026-08-04
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
# Harness operational contract

## Scope

This document owns operation of Assignment-bound Harness Runs: status, run, resume, cancellation, active Tool-step reconciliation, lost-process recovery, semantic Doctor, and escalation to Host or Runtime. It does not own Host backup/restore or Runtime service repair.

## Normal operation

Operate through `HarnessRunner` or the thin CLI against an existing Host state root and a current committed Assignment. `run` does not synthesize Task authority. A durable Snapshot forces `resume`; a recorded Run cannot be executed again and requires a replacement Assignment admitted through current Host revision fencing.

```bash
ordivon-harness --state-root /path/to/host-state status TASK_ID
ordivon-harness --state-root /path/to/host-state run TASK_ID
ordivon-harness --state-root /path/to/host-state resume TASK_ID --message 'operator input'
ordivon-harness --state-root /path/to/host-state cancel TASK_ID
ordivon-harness --state-root /path/to/host-state recover TASK_ID
ordivon-harness --state-root /path/to/host-state doctor
```

The Harness creates no daemon, scheduler, process registry, or separate database. Durable Harness objects remain in Host CAS and are admitted through the Host Journal.

## Failure detection

Treat catalog drift, stale Assignment or DispatchFence identity, missing or inconsistent Intent/Receipt chains, unresolved Runtime delivery, Provider ambiguity, deadline or token exhaustion, unsupported durable mutation, stale late results, and invalid replacement or completion evidence as explicit findings. Do not reinterpret an absent process, response, or Provider message as proof that no effect occurred.

## Recovery

Recover active physical work before considering Workspace cleanup or Run replacement:

```text
load the active Tool Step
→ reconcile the original Runtime request by clientRequestId or runtimeJobRef
→ persist the latest Receipt and Observation
→ inspect Workspace and retained diff/evidence
→ derive remaining UNKNOWN claims
→ resume, retain, abandon, or replace only when current evidence permits
```

Recovery never redispatches an uncertain Tool Step. Durable `workspace.exec` reconciles the original Runtime Job; durable Patch reconciles the stable Runtime Patch receipt through `workspace.patch.get`. `workspace.mutate` remains unsupported in durable Runs because it lacks the required independently observable dispatch identity.

A same-process `RunHandle` may close an active Provider connection. A separate CLI process cannot cancel another process's in-memory Provider socket; it can record or reconcile durable state and request Runtime cancellation for a known physical Job. `cancel-requested` remains nonterminal until a later Receipt proves the effective outcome.

## Cross-component escalation

| Finding | Owner and next operation |
| --- | --- |
| SQLite, CAS, lease, Task projection, backup, or restore problem | `ordivon-host` Doctor or operations |
| Assignment, Run, Trace, Tool-step, recovery, abandonment, or Harness completion problem | `ordivon-harness` Doctor, `status`, `resume`, or `recover` |
| Workspace, Job, Attempt, process tree, Artifact, cancellation, or Runtime Registry problem | `ordivon-runtime` inspection and recovery |
| domain acceptance or world-state uncertainty | the integrating domain application or participant |

Harness recovery may read Host-backed objects and Runtime evidence, but it does not replace either owner's repair procedure.

## Doctor

Run Host Doctor first when core state integrity is uncertain. `ordivon-harness doctor` then decodes and validates Harness-specific Assignment, Run, Recovery, Completion, Tool catalog, Intent, Fence, Receipt, Snapshot, delta, Trace, and provenance relationships preserved through the generic Host extension boundary.

Doctor is read-only. It does not invoke a Provider, redispatch a Tool, repair Host storage, cancel Runtime work, or adjudicate domain truth.

## Verification

Use deterministic repository tests, semantic history validation, Runtime catalog discovery, Host/Runtime integration fixtures, frozen fault evidence, and final canonical Traces. [`../ARCHITECTURE.md`](../ARCHITECTURE.md) defines semantic ownership; this document defines operational handling. Historical closeouts may explain why a mechanism exists, but they do not change the current recovery order or supported CLI surface.
