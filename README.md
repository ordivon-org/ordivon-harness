---
schema_version: 1
id: harness.start
title: Ordivon Harness
type: start
profile: organization
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - operator
  - agent
updated: 2026-08-04
summary: Canonical entry to replaceable Agent execution, Assignment and Run continuity, Tool semantics, Provider adapters, recovery, and completion.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.architecture
  - harness.authority
---
# Ordivon Harness

## Purpose

Ordivon Harness owns replaceable Agent execution lifecycles above the thin `ordivon-host` continuity kernel.

It contains three deliberately distinct concerns:

```text
Host Harness extension
  TaskAttempt / Assignment / Run / Recovery / Completion

Provider-faithful adapters
  Codex App Server / Hermes ACP

First-party bare-model execution
  bounded sequential model–Tool loop / DeepSeek adapter / Runtime Tool bridge
```

The dependency is one-way:

```text
ordivon-harness → ordivon-host → ordivon-protocol
```

`ordivon-host` does not import this package. Host owns generic Task, Journal, CAS, Kernel, the public `HostExtensionPort`, and Runtime client mechanics; Harness owns its event vocabulary, semantic history validation, handoff projection, durable Run state and Agent execution behavior.

## Current boundary

Harness owns replaceable Agent execution semantics above Host and before Runtime. It does not own durable Task continuity, physical execution truth, domain-world rules, promoted cross-project protocol, Provider hidden state, or another database or scheduler.

## Repository selection

| Change concerns | Use | Do not put here |
| --- | --- | --- |
| Workspace, Job, Attempt, process tree, Artifact, physical cancellation, or execution recovery | `ordivon-runtime` | Task meaning, Agent Run policy, or domain completion |
| durable Task continuity, Journal/CAS, commitment admission, verification records, or Task outcomes | `ordivon-host` | Provider loops, Harness Run semantics, or physical process truth |
| Assignment, Agent Run, Provider adapter, model–Tool loop, Tool-step checkpoint, or Run recovery | `ordivon-harness` | a second Task database, Runtime supervision, or domain-world authority |

## Start here

- [`ARCHITECTURE.md`](ARCHITECTURE.md) defines the current ownership, execution, recovery, fencing, and application boundaries.
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md) defines Run operation, cancellation, restart recovery, Doctor, and cross-component escalation.
- [`docs/authority.md`](docs/authority.md) identifies which records may define current Harness behavior.
- `docs/ORDIVON_HARNESS_*`, extraction, and boundary-stage documents are historical implementation evidence and do not replace the current architecture or operations contract.

## Verified boundary

The retained evidence proves:

- durable Task Attempt and Assignment identity before Provider or Runtime activity;
- Codex and Hermes provider-faithful lifecycle adapters;
- one first-party bare-model sequential loop;
- Assignment-scoped Tool authority and Runtime correlation;
- durable Trace, Tool Observation, Run receipt and completion verification;
- conservative UNKNOWN handling, safe read-only abandonment and retained effectful recovery evidence;
- Assignment-bound native Tool semantics and one pure Run disposition derivation;
- monotonic Run deadlines, cancellable Provider call handles and requested/effective model provenance;
- active socket cancellation for the default DeepSeek HTTP transport;
- durable native `workspace.exec` Intent → DispatchFence → Receipt → Observation with restart reconciliation by `clientRequestId`;
- capability-adaptive durable `workspace.patch` with exact request replay and `workspace.patch.get` receipt reconciliation;
- bounded Provider retry for explicit transient transport/unavailable failures, with stable logical Turn identity and no Tool redispatch;
- Provider-reported token hard limits and bounded known-no-effect Tool correction;
- best-effort live semantic event projection whose authoritative form remains the final canonical Trace;
- nonterminal `cancel-requested` Receipts that can be superseded by one final reconciled Receipt;
- active-Tool-Step-first Run recovery before Workspace assessment;
- executable `needs-input` and prepared-effect Run resume;
- append-only Run-state deltas between bounded full checkpoints.

The current DispatchFence is a Host revision/Assignment/Intent fence retained in CAS and Runtime correlation evidence, with validation immediately before and after dispatch. Runtime does not independently authenticate it with a Host-issued MAC; it is therefore a practical stale-dispatch fence, not a cryptographic cross-service capability token.

Generic effectful continuation remains deliberately narrower than the Runtime catalog: durable `workspace.exec` is accepted; `patch_workspace` is exposed only when Runtime advertises the paired `workspace.patch` and `workspace.patch.get` contract; durable `workspace.mutate` remains hidden and `HarnessRunPlan` rejects that grant. Patch uses complete before digests and a stable Runtime receipt identity rather than weakening the mutation boundary. Approval pause/resume is also not advertised or accepted. Parallel Tools, subagents, automatic routing, persistent Provider sessions, a Harness daemon and a separate Harness database remain outside the accepted boundary.

## Recommended application surface

`HarnessRunner` is the supported orchestration facade. It composes the existing Host lifecycle, Runtime Tool bridge and Agent loop; it does not own another Task state machine or database.

```python
from ordivon_harness import CompletionMode, HarnessRunPlan, HarnessRunner

runner = HarnessRunner(host, runtime=runtime, adapter=adapter)
result = runner.run(
    HarnessRunPlan(
        task_contract=task_contract,
        context_blocks=context_blocks,
        workspace_ref=workspace_id,
        tool_grant=tool_grant,
        completion_mode=CompletionMode.PROPOSE,
    )
)
```

The public lifecycle is deliberately small:

```text
prepare(plan)       compile Context and commit the native Assignment
run(plan)           prepare, execute and record one Run
run_current(task)   execute an already committed Assignment
resume(task)        continue a durable needs-input/effect checkpoint
status(task)        project current Host-backed Harness state
cancel(task)        cancel this Runner's active call or reconcile a Runtime effect
recover(task)       perform active-step-first lost-process recovery
```

`RunHandle` provides in-process start/result/cancel mechanics without introducing a daemon. `iter_events()` projects semantic events while the Run is active; the returned final Trace remains authoritative and event consumers must tolerate a lossy sink. A durable Snapshot forces callers onto `resume`; a recorded Run cannot be executed again and requires a replacement Assignment.

The CLI operates on existing Host state:

```bash
ordivon-harness --state-root /path/to/host-state status task:example
ordivon-harness --state-root /path/to/host-state run task:example
ordivon-harness --state-root /path/to/host-state run task:example --events-jsonl
ordivon-harness --state-root /path/to/host-state resume task:example --message 'operator input'
ordivon-harness --state-root /path/to/host-state cancel task:example
ordivon-harness --state-root /path/to/host-state recover task:example
ordivon-harness --state-root /path/to/host-state doctor
```

CLI `run` executes the current committed Assignment; creation of Task Contracts, Context blocks, Tool Grants and new Assignments remains an explicit Python/Host integration operation. `--max-total-tokens`, `--max-model-retries` and `--max-tool-corrections` set explicit bounded Run policy. `--events-jsonl` writes the live event projection to stderr and preserves the final result JSON on stdout. A separate CLI process cannot interrupt an in-memory Provider socket owned by another process, but it can reconcile or cancel a durable active Runtime Tool Step.

## Development

Python 3.12 is required.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m pytest -q tests
python -m unittest discover -s tests
ruff check <changed files>
python -m compileall -q src tests scripts
```

Harness semantic history can be checked separately from the Host core doctor:

```bash
ordivon-harness --state-root /path/to/host-state doctor
```

See `ARCHITECTURE.md` and `docs/OPERATIONS.md` for the active contract. The OH, P/R, extraction, and boundary documents remain historical evidence for the stages that produced it.

## Project family

- [Public project directory](https://ordivon.com/projects) — reader-facing role, maturity, and next steps.
- [Cross-project map](https://github.com/zycxfyh/ordivon-computing/blob/main/projects/README.md) — stable roles, repository links, and authority entry points for all nine repositories.
- Related owners: [Ordivon Host](https://github.com/zycxfyh/ordivon-host) preserves durable Task continuity; [Ordivon Runtime](https://github.com/zycxfyh/ordivon-runtime) owns physical execution; [Ordivon Computing](https://github.com/zycxfyh/ordivon-computing) owns promoted shared contracts.
