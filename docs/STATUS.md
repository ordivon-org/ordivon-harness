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
updated: 2026-08-04
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

Operational means the repository has Host-backed Assignment and Run persistence, durable Provider Call and Tool Step state, explicit UNKNOWN handling, cancellation, bounded budgets, Run Snapshot resume, semantic-history validation, recovery controllers, Provider adapters and real receipts.

Pre-1.0 means public imports, owner-local object schemas, Provider adapter APIs and operational packaging may change. Supported retained state still requires decoders, migration or an explicit cutover; pre-1.0 does not permit silent reinterpretation.

## Supported graph

The canonical public graph currently requires:

- Python 3.12;
- `ordivon-host` at `1a4027bb26d77a2e051ca933bf664578f071a5a9`;
- `ordivon-protocol` at `420dc356cb664d75db0f34f356156baebe5843db`;
- `uv.lock` generated from those exact pins;
- Linux for trusted-local live operation;
- Ordivon Runtime for physical Tool execution.

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
| Harness daemon or independent database | not provided |

## Public interface

`ordivon_harness.api` is the recommended application facade. Historical package-root exports remain during the pre-1.0 compatibility window, but low-level persistence and Provider-driver objects are not newly promised as stable.

## Host relationship

Harness is repository-independent and semantically owns its Agent Run objects, but it remains implementation-bound to a pinned Host source API. Host owns persistence, revision fencing, leases and event admission; Harness owns schema and lifecycle semantics.

This is intentional non-symmetric coupling:

```text
Harness → Host
Host ↛ Harness
```

## Known limits

- no independent persistence or operation without a Host authority;
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

```bash
ordivon-harness --state-root /var/lib/ordivon/host status TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host inspect TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host handoff TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host doctor
```

## Reopen conditions

Revisit this status when Python support changes, Host compatibility becomes protocol-level rather than source-level, a second Host implementation exists, parallel execution enters the public contract, Provider migration semantics change or the package reaches a declared 1.0 interface.
