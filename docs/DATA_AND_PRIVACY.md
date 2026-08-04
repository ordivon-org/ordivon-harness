---
schema_version: 1
id: harness.data-privacy
title: Harness Data and Privacy
type: policy
profile: organization
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - user
  - operator
  - builder
  - agent
updated: 2026-08-04
summary: Sensitive data, Provider disclosure, Host/Runtime storage, retention, export and deletion boundaries.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.operations
  - harness.compatibility
---
# Harness Data and Privacy

## Principle

Harness preserves public Agent Run state so work can survive a Provider or process failure. That state may include sensitive prompts, source-derived content, Tool arguments, model output and execution references. Treat Host state, Runtime Artifacts, Provider traffic and evidence receipts as sensitive.

Harness does not automatically classify or redact personal data, credentials or proprietary source.

## Data ownership

| Data | Physical owner | Semantic owner |
| --- | --- | --- |
| Assignment, Provider Call, Tool Step, Snapshot, Run receipt | Host Journal/CAS | Harness |
| Task and outcome | Host | Host/domain verifier |
| Workspace, Job, process output and Artifact | Runtime | Runtime physical truth |
| Provider request and response | Provider boundary plus Host-retained digest/content where recorded | Harness interprets normalized result |
| DeepSeek API key | private local secret file | operator |
| Codex/Hermes child-process state | local Provider adapter/process | disposable Provider state |
| historical receipts | repository `evidence/` | bounded engineering evidence |

## Provider disclosure

A Provider may receive:

- system instructions;
- bounded Task Context;
- prior public conversation messages;
- granted Tool definitions;
- retained Tool observations;
- additional operator messages on resume.

Do not place secrets in Context unless disclosure to the configured Provider is intended. Prompt injection cannot expand ToolGrant, but malicious content can still influence model output.

## Retention

Harness has no separate database or retention engine. Host retains Journal/CAS records required for replay, audit, recovery and idempotency. Runtime controls Artifact and Workspace retention. Provider-side retention follows the Provider's own service or local process policy.

Do not delete individual Harness CAS objects or Journal events manually. Selective erasure requires a versioned Host archival/redaction contract that preserves causal and digest relationships.

## Export and migration

Use Host backup/restore to export Harness-backed state. A complete operational migration may also require:

- Runtime Artifacts and Workspace state;
- exact Harness, Host and Protocol revisions;
- Provider adapter identity and configuration;
- Runtime catalog digest;
- external domain references.

A file copy alone does not prove a resumable Run.

## Deletion and retirement

To retire an instance:

1. stop new Assignment and Run admission;
2. inspect or reconcile active Provider Calls and Tool Steps;
3. export required Host and Runtime state;
4. stop Harness/Provider processes;
5. remove Host state through the Host retirement procedure;
6. remove Runtime state through Runtime policy;
7. delete local Provider secrets and rotate credentials;
8. review Provider and domain systems for retained data or committed effects.

Harness cannot retract effects already committed outside it.

## Sharing diagnostics

Before publishing status, handoff, Trace, receipt or evidence output, remove Task text, source content, paths, participant identities, Provider request/response content, external IDs and Artifact content unless required. Never publish API keys, Runtime bearer tokens, raw Host databases, CAS roots or private Provider configuration.

## Non-goals

Harness does not currently provide encryption at rest, per-user tenancy, hosted-service privacy terms, automatic PII detection, selective Journal deletion, secret brokering or protection from a privileged local operator.
