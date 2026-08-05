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
# Harness operational contract

## Scope

This document owns operation of current Assignment-bound Harness Runs and the explicit independent P0 Store surface. Current Run execution covers status, run, resume, cancellation, active Tool-step reconciliation, lost-process recovery and semantic Doctor through Host-backed state. P0 Store operation covers initialization, inspection, full Doctor, backup verification and restore. It does not own Host backup/restore or Runtime service repair.

## Normal operation

Operate through `HarnessRunner` or the thin CLI against an existing Host state root and a current committed Assignment. `run` does not synthesize Task authority. A durable Snapshot forces `resume`; a recorded Run cannot be executed again and requires a replacement Assignment admitted through current Host revision fencing.

```bash
ordivon-harness --state-root /path/to/host-state status TASK_ID
ordivon-harness --state-root /path/to/host-state inspect TASK_ID
ordivon-harness --state-root /path/to/host-state handoff TASK_ID
ordivon-harness --state-root /path/to/host-state run TASK_ID
ordivon-harness --state-root /path/to/host-state resume TASK_ID --message 'operator input'
ordivon-harness --state-root /path/to/host-state cancel TASK_ID
ordivon-harness --state-root /path/to/host-state recover TASK_ID
ordivon-harness --state-root /path/to/host-state doctor
```

The current production Runner creates no daemon, scheduler or process registry. Its durable Harness objects remain in Host CAS and are admitted through the Host Journal. P0 separately provides an independent Harness SQLite Journal/CAS, but the current Runner does not write to it and no Run is dual-written. `inspect` and `handoff` are read-only and require neither Runtime nor Provider access.

Initialize and operate the independent Store explicitly:

```bash
ordivon-harness --harness-state-root /path/to/harness-state store-init
ordivon-harness --harness-state-root /path/to/harness-state store-doctor
ordivon-harness --harness-state-root /path/to/harness-state store-inspect HARNESS_RUN_ID
ordivon-harness --harness-state-root /path/to/harness-state store-events HARNESS_RUN_ID
ordivon-harness --harness-state-root /path/to/harness-state store-backup /path/to/backup
ordivon-harness store-verify-backup /path/to/backup
ordivon-harness store-restore /path/to/backup /absent/destination
```

Only `store-init` creates a state root. Backup and restore refuse existing destinations. Restore performs full validation before publishing the destination. [`P0-INDEPENDENT-PERSISTENCE.md`](P0-INDEPENDENT-PERSISTENCE.md) owns the current migration and cutover boundary.

Before operation or upgrade, verify the exact dependency graph:

```bash
uv lock --check
python scripts/check_dependencies.py
python scripts/check_docs.py
python scripts/check_evidence.py
```

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
| Host SQLite, CAS, lease, Task projection, backup, or restore problem | `ordivon-host` Doctor or operations |
| independent Harness Journal, CAS, Run lease, Store backup, or Store restore problem | `ordivon-harness store-doctor` or `store-verify-backup` |
| current Assignment, Run, Trace, Tool-step, recovery, abandonment, or Harness completion problem | Host-backed `ordivon-harness doctor`, `status`, `resume`, or `recover` |
| Workspace, Job, Attempt, process tree, Artifact, cancellation, or Runtime Registry problem | `ordivon-runtime` inspection and recovery |
| domain acceptance or world-state uncertainty | the integrating domain application or participant |

Harness recovery may read Host-backed objects and Runtime evidence, but it does not replace either owner's repair procedure.

## Doctor

Run Host Doctor first when current production state integrity is uncertain. `ordivon-harness doctor` then decodes and validates Harness-specific Assignment, Run, Recovery, Completion, Tool catalog, Intent, Fence, Receipt, Snapshot, delta, Trace, and provenance relationships preserved through the generic Host extension boundary.

For independent P0 state, run `store-doctor`. It verifies SQLite integrity, every admitted CAS object, contiguous Run revisions, projection reconstruction, terminal closure, Event payload binding and caller-neutral Contract identity.

Both Doctor surfaces are read-only with respect to Run semantics. They do not invoke a Provider, redispatch a Tool, repair Host storage, cancel Runtime work, or adjudicate domain truth. Full Store Doctor may update only the trusted-local object-validation cache.

## Acceptance

`scripts/local-acceptance check` validates that all portable and live gates are present. `scripts/local-acceptance run` executes the full deterministic suite, the network-free Agent-loop demonstration, and the real H2 Host→Harness→Runtime correlation journey. The live journey retains exact Runtime Job and Artifact evidence, verifies idempotent replay and conflict behavior, and closes its disposable Workspace.

## Verification

Use deterministic repository tests, semantic history validation, Runtime catalog discovery, Host/Runtime integration fixtures, frozen fault evidence, and final canonical Traces. [`../ARCHITECTURE.md`](../ARCHITECTURE.md) defines semantic ownership; this document defines operational handling. Historical closeouts may explain why a mechanism exists, but they do not change the current recovery order or supported CLI surface.
