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

This document owns the primary independent Harness Run CLI, retained Assignment-bound Host compatibility, the independent Store surface, and explicit cutover control. Independent operation covers Contract-in no-Tool DeepSeek run/resume, status, inspection, conservative recovery, Doctor, initialization, backup verification and restore. Tool-bearing independent execution is a Host-free Python API surface that requires a caller-supplied Runtime client. Cutover inventories retained Host and Harness histories and governs migration of existing deployment state. It does not own Host backup/restore or Runtime service repair.

## Normal operation

The primary CLI consumes an existing caller-authored `HarnessRunContract` and writes only Harness-owned state. `run` does not synthesize Task, Objective, Context, Tool Grant, completion, caller, or budget authority. A durable Snapshot forces `resume`; a terminal Run is inspected rather than executed again.

```bash
ordivon-harness capabilities
ordivon-harness --harness-state-root /path/to/harness-state run RUN_CONTRACT.json --message 'caller input'
ordivon-harness --harness-state-root /path/to/harness-state status HARNESS_RUN_ID
ordivon-harness --harness-state-root /path/to/harness-state inspect HARNESS_RUN_ID
ordivon-harness --harness-state-root /path/to/harness-state resume HARNESS_RUN_ID --message 'caller input'
ordivon-harness --harness-state-root /path/to/harness-state recover HARNESS_RUN_ID
ordivon-harness --harness-state-root /path/to/harness-state doctor
```

The executable CLI profile is currently canonical no-Tool DeepSeek. A Tool-bearing Contract fails before Provider construction because the CLI has no authority to invent a Runtime transport. Applications that need Tools construct the corresponding independent Bridge and supply `HarnessRuntimeClient` through `ordivon_harness.api` or `ordivon_harness.core`.

Retained Assignment-bound behavior is explicit:

```bash
ordivon-harness --state-root /path/to/host-state host status TASK_ID
ordivon-harness --state-root /path/to/host-state host inspect TASK_ID
ordivon-harness --state-root /path/to/host-state host handoff TASK_ID
ordivon-harness --state-root /path/to/host-state host run TASK_ID
ordivon-harness --state-root /path/to/host-state host resume TASK_ID --message 'operator input'
ordivon-harness --state-root /path/to/host-state host cancel TASK_ID
ordivon-harness --state-root /path/to/host-state host recover TASK_ID
ordivon-harness --state-root /path/to/host-state host doctor
```

This legacy `HarnessRunner` path continues to persist through Host CAS and Journal until retained deployment state is explicitly migrated. No Run is dual-written. `host inspect` and `host handoff` are read-only and require neither Runtime nor Provider access.

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

Only `store-init` creates a state root. Backup and restore refuse existing destinations. Restore performs full validation before publishing the destination. Before cutover, operate the explicit preflight:

```bash
ordivon-harness --state-root /var/lib/ordivon/host \
  --harness-state-root /var/lib/ordivon/harness cutover-inventory
ordivon-harness --state-root /var/lib/ordivon/host cutover-status
ordivon-harness --state-root /var/lib/ordivon/host \
  --harness-state-root /var/lib/ordivon/harness cutover-activate
```

Activation requires zero nonterminal legacy Runs and zero nonterminal independent Runs. Its inventory and receipt are immutable files under the Host state root's `harness-cutover/` directory. After activation, legacy `host run`, `host resume`, `host cancel`, and `host recover` commands fail before Runtime or Provider access. `host status`, `host inspect`, `host handoff`, `host doctor` and historical decoding remain available. Rollback is accepted only before any independent Run or Ordivon Harness external request created at or after activation. [`P0-INDEPENDENT-PERSISTENCE.md`](P0-INDEPENDENT-PERSISTENCE.md) owns the migration boundary.

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
| cutover receipt, inventory, selected writer, or rollback refusal | `cutover-status`, `cutover-inventory`, and the immutable receipt chain under the Host state root |
| independent Run, Trace, Provider continuity, recovery, or CompletionProposal problem | `ordivon-harness doctor`, `status`, `inspect`, `resume`, or `recover` against the Harness root |
| retained Host Assignment or legacy Harness extension problem | `ordivon-harness host doctor`, `host status`, `host inspect`, `host resume`, or `host recover` |
| Workspace, Job, Attempt, process tree, Artifact, cancellation, or Runtime Registry problem | `ordivon-runtime` inspection and recovery |
| domain acceptance or world-state uncertainty | the integrating domain application or participant |

Harness recovery may read Host-backed objects and Runtime evidence, but it does not replace either owner's repair procedure.

## Doctor

Run `ordivon-harness --harness-state-root ... doctor` when independent Run integrity is uncertain. It performs the full independent Store Doctor over SQLite integrity, admitted CAS objects, contiguous Run revisions, projection reconstruction, terminal closure, Event payload binding and caller-neutral Contract identity. `store-doctor` remains the explicit administrative spelling for the same root.

For retained Host-backed state, run `ordivon-harness --state-root ... host doctor`. It decodes and validates Harness-specific Assignment, Run, Recovery, Completion, Tool catalog, Intent, Fence, Receipt, Snapshot, delta, Trace and provenance relationships preserved through the generic Host extension boundary.

Both Doctor surfaces are read-only with respect to Run semantics. They do not invoke a Provider, redispatch a Tool, repair Host storage, cancel Runtime work, or adjudicate domain truth. Full Store Doctor may update only the trusted-local object-validation cache.

## Acceptance

`scripts/local-acceptance check` validates that all portable and live gates are present. `scripts/local-acceptance run` executes the full deterministic suite, the network-free Agent-loop demonstration, and the real H2 Host→Harness→Runtime correlation journey. The live journey retains exact Runtime Job and Artifact evidence, verifies idempotent replay and conflict behavior, and closes its disposable Workspace.

## Verification

Use deterministic repository tests, semantic history validation, Runtime catalog discovery, Host/Runtime integration fixtures, frozen fault evidence, and final canonical Traces. [`../ARCHITECTURE.md`](../ARCHITECTURE.md) defines semantic ownership; this document defines operational handling. Historical closeouts may explain why a mechanism exists, but they do not change the current recovery order or supported CLI surface.
