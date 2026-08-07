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
# Harness Status

## Maturity

Ordivon Harness is an **operational engineering prototype for owner-trusted local work** and **pre-1.0 as a public package**.

Operational means the repository has a caller-neutral independent Run write path with durable Provider Call and Tool Step state, explicit UNKNOWN handling, bounded budgets, Run Snapshot resume, semantic-history validation, recovery evidence, Provider adapters and real receipts. The primary CLI now targets this independent Journal/CAS for no-Tool DeepSeek Runs. Retained Host Task/Assignment state remains supported through the explicit `host` compatibility namespace; deployment cutover receipts are still required before existing production roots are migrated.

Pre-1.0 means public imports, owner-local object schemas, Provider adapter APIs and operational packaging may change. Supported retained state still requires decoders, migration or an explicit cutover; pre-1.0 does not permit silent reinterpretation.

## Supported graph

The canonical public graph currently requires:

- Python 3.12;
- base package: `ordivon-protocol` at `420dc356cb664d75db0f34f356156baebe5843db`;
- optional `host` extra and repository development group: `ordivon-host` at `428a6f2f90b4050535507c9be078c450552177e5`;
- `uv.lock` generated from those exact pins;
- Linux for trusted-local live operation;
- Ordivon Runtime only when physical Tool execution is requested.

## Capability status

| Area | Status |
| --- | --- |
| Host-backed Task Attempt and Assignment admission | operational |
| Provider Call claim/dispatch/result/failure/UNKNOWN/replay | operational |
| Tool Step intent/fence/receipt/reconciliation | operational |
| Run Snapshot, pause, resume and budget continuity | operational |
| cancellation of in-flight Provider and Runtime work | operational within declared adapter/runtime support |
| semantic-history Doctor | operational |
| DeepSeek sequential model–Tool loop | experimental, tested |
| Codex App Server adapter | experimental, historical live evidence |
| Hermes ACP adapter | experimental, historical live evidence |
| `workspace.read`, search, Artifact read and durable exec | operational in pinned graph |
| reconciliable patch path | experimental |
| Provider replacement between safe Assignments | experimental |
| hidden-state migration during an active Provider Call | unsupported |
| parallel Tools and subagents | unsupported |
| automatic Provider routing | not provided |
| independent Harness Journal/CAS kernel | operational; atomic batch and 1,000-Run/100,000-Event scale gate passed |
| independent no-Tool CLI run/resume/status/inspect/recover | operational H1 surface with caller-supplied Contract and DeepSeek adapter |
| independent observation-only Runtime Tool path | operational Python-API vertical slice with caller-supplied Runtime client; not exposed as CLI execution |
| independent terminal Trace, Receipt, Recovery and CompletionProposal | operational through Standalone Runner and primary CLI |
| Host foreign-Run adapter over independent Harness authority | operational local P0 acceptance; exact Host release pin aligned, deployment pending |
| active legacy-Run inventory and append-only cutover receipts | operational; activation disables legacy write commands before Runtime access |
| Harness daemon or scheduler | not provided |

## Public interface

`ordivon_harness.api` is the recommended small Host-free application facade for bounded Agent runs and domain-owned Tool loops. `ordivon_harness.core` remains the wider Host-free integration surface for persistence, Provider, Runtime, recovery and advanced composition. Historical Host-backed application behavior is explicit in `ordivon_harness.host_api` and requires the `host` extra; package-root exports remain transitional compatibility aliases.

## Host relationship

Harness is repository-independent and semantically owns its Agent Run objects. The default CLI now writes those Runs directly to Harness-owned persistence. The historical `HarnessRunner` remains implementation-bound to a pinned Host source API for retained Task/Assignment work; Host owns persistence, revision fencing, leases and event admission only for that compatibility path.

P0 adds a separate Harness Run Journal/CAS, caller binding, revision and lease fencing, operational backup/restore, an event-sourced Provider/Tool/Snapshot continuity implementation, a real no-Tool Agent Loop path, caller-neutral Runtime execution bindings, and an observation-only Runtime Tool path with Harness-owned dispatch fencing and exact-request reconciliation. The independent path now retains segmented Trace evidence across pause/resume, records a caller-neutral Run Receipt and CompletionProposal, and admits Recovery Assessments without Host state. Package installation is now separated: the independent Core has no Host dependency, while the legacy production integration is available through the exact `host` extra. A Host-neutral foreign-Run adapter now exposes the independent authority without importing Host or sharing databases. Local cross-repository acceptance proves request-only commit gaps, exact retry, one physical Harness execution, separate reopenable histories and CompletionProposal collection while the Host Task remains ready. An explicit inventory and append-only cutover receipt chain now select the deployment mode. Activation is refused while a legacy or independent Run is nonterminal; after activation, legacy `host run`, `host resume`, `host cancel`, and `host recover` commands fail before Runtime access. Rollback is allowed only before any post-activation independent Run or Host external request exists. Until these receipts are applied to production roots with exact cross-repository release pins, this remains a staged authority path rather than a production cutover. The semantic dependency remains intentionally non-symmetric for the legacy path:

```text
Harness Core ↛ Host
Harness Host integration → Host
Host ↛ Harness
```

## Known limits

- the production Host and Harness roots do not yet exist and have not been activated by a cutover receipt;
- local Harness and Computing integration mains remain ahead of their remote release heads until I0 is published; Host is aligned to its current remote C3 revision;
- the historical Host-backed `HarnessRunner` still requires the optional exact Host integration; it is no longer the default CLI entry point, but retained deployments still require it until explicitly migrated;
- the primary CLI executes only the canonical no-Tool DeepSeek profile; Tool-bearing independent Runs require an application-supplied Runtime client through the Host-free Python API;
- no cross-machine distributed consensus;
- no automatic redaction of prompts, model output or Tool observations;
- no hostile multi-tenant isolation;
- no generic compatibility with arbitrary Host implementations;
- old live receipts certify only their named implementation revisions;
- Runtime success is not semantic completion;
- Provider sessions are replaceable hints, not durable continuity;
- several internal modules remain large and require controlled decomposition rather than cosmetic splitting.

## Machine-owned state

Current Task/Run state must be queried:

Independent Harness Run state:

```bash
ordivon-harness --harness-state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --harness-state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --harness-state-root /var/lib/ordivon/harness doctor
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-events HARNESS_RUN_ID
```

Retained Host-backed Task state:

```bash
ordivon-harness --state-root /var/lib/ordivon/host host status TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host host inspect TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host host handoff TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host host doctor
ordivon-harness --state-root /var/lib/ordivon/host cutover-status
```

## Reopen conditions

Revisit this status when Python support changes, Host compatibility becomes protocol-level rather than source-level, a second Host implementation exists, parallel execution enters the public contract, Provider migration semantics change or the package reaches a declared 1.0 interface.
