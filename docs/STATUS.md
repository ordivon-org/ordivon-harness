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
updated: 2026-08-05
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

Operational means the repository has Host-backed production Assignment and Run persistence, durable Provider Call and Tool Step state, explicit UNKNOWN handling, cancellation, bounded budgets, Run Snapshot resume, semantic-history validation, recovery controllers, Provider adapters and real receipts. It also has an independently operational P0 Journal/CAS foundation, but that foundation is not yet the production Runner write path.

Pre-1.0 means public imports, owner-local object schemas, Provider adapter APIs and operational packaging may change. Supported retained state still requires decoders, migration or an explicit cutover; pre-1.0 does not permit silent reinterpretation.

## Supported graph

The canonical public graph currently requires:

- Python 3.12;
- base package: `ordivon-protocol` at `420dc356cb664d75db0f34f356156baebe5843db`;
- optional `host` extra and repository development group: `ordivon-host` at `1a4027bb26d77a2e051ca933bf664578f071a5a9`;
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
| independent Harness Journal/CAS kernel | P0 foundation operational; production Runner not cut over |
| independent observation-only Runtime Tool path | operational P0 vertical slice; not production-selected |
| independent terminal Trace, Receipt, Recovery and CompletionProposal | operational through explicit Standalone Runner |
| Harness daemon or scheduler | not provided |

## Public interface

`ordivon_harness.core` is the Host-free facade for caller-neutral contracts, independent Journal/CAS persistence, Runtime bridging and Standalone execution. `ordivon_harness.api` remains the Host-backed application facade and requires the `host` extra. Historical package-root exports resolve lazily during the pre-1.0 compatibility window; low-level persistence and Provider-driver objects are not newly promised as stable.

## Host relationship

Harness is repository-independent and semantically owns its Agent Run objects, but the current production Runner remains implementation-bound to a pinned Host source API. Host currently owns persistence, revision fencing, leases and event admission for that legacy path; Harness owns schema and lifecycle semantics.

P0 adds a separate Harness Run Journal/CAS, caller binding, revision and lease fencing, operational backup/restore, an event-sourced Provider/Tool/Snapshot continuity implementation, a real no-Tool Agent Loop path, caller-neutral Runtime execution bindings, and an observation-only Runtime Tool path with Harness-owned dispatch fencing and exact-request reconciliation. The independent path now retains segmented Trace evidence across pause/resume, records a caller-neutral Run Receipt and CompletionProposal, and admits Recovery Assessments without Host state. Package installation is now separated: the independent Core has no Host dependency, while the legacy production integration is available through the exact `host` extra. Until production selection and the Host foreign-Run adapter are complete, this remains a staged authority path rather than a production cutover. The semantic dependency remains intentionally non-symmetric for the legacy path:

```text
Harness Core ↛ Host
Harness Host integration → Host
Host ↛ Harness
```

## Known limits

- no production Agent Run selection through the independent store yet;
- the legacy production Runner still requires the optional exact Host integration and remains the default Host-backed entry point;
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

Current production state:

```bash
ordivon-harness --state-root /var/lib/ordivon/host status TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host inspect TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host handoff TASK_ID
ordivon-harness --state-root /var/lib/ordivon/host doctor
```

Independent P0 state:

```bash
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-doctor
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-inspect HARNESS_RUN_ID
ordivon-harness --harness-state-root /var/lib/ordivon/harness store-events HARNESS_RUN_ID
```

## Reopen conditions

Revisit this status when Python support changes, Host compatibility becomes protocol-level rather than source-level, a second Host implementation exists, parallel execution enters the public contract, Provider migration semantics change or the package reaches a declared 1.0 interface.
