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
updated: 2026-08-08
summary: Sensitive data, Provider disclosure, independent Harness/Runtime storage, retention, export and deletion boundaries.
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

Harness preserves public Agent Run state so work can survive a Provider or process failure. That state may include sensitive prompts, source-derived content, Tool arguments, model output and execution references. Treat Harness state, caller/domain state, Runtime Artifacts, Provider traffic and evidence receipts as sensitive.

Harness does not automatically classify or redact personal data, credentials or proprietary source.

## Data ownership

| Data | Physical owner | Semantic owner |
| --- | --- | --- |
| Run Contract, Run events, Provider Call, Tool Step, Snapshot, Trace, Run receipt and CompletionProposal | independent Harness Journal/CAS | Harness |
| caller Task/Actor state and final outcome | caller/domain/optional Host | caller/domain verifier |
| Workspace, Job, process output and Artifact | Runtime | Runtime physical truth |
| Provider request and response | Provider boundary plus Harness-retained normalized/digest content where configured | Harness interprets normalized result |
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

Harness retains its own private SQLite Journal and immutable CAS required for Run replay, audit, recovery and idempotency. Runtime separately controls Artifact and Workspace retention. Provider-side retention follows the Provider's own service or local process policy; caller/domain state follows its owning system.

Do not delete individual Harness CAS objects or Journal events manually. Selective erasure requires a versioned Harness archival/redaction contract that preserves causal and digest relationships.

## Export and migration

Use Harness `store-backup` / `store-verify-backup` / `store-restore` for independent Run state. A complete operational migration may also require:

- Runtime Artifacts and Workspace state;
- exact Harness and Protocol revisions, plus a Host revision only when Host is the caller;
- Provider adapter identity and configuration;
- Runtime catalog digest;
- external domain references.

A file copy alone does not prove a resumable Run.

## Deletion and retirement

To retire an instance:

1. stop new Harness Run admission;
2. inspect or reconcile active Provider Calls and Tool Steps;
3. back up required Harness state and separately export any required caller/domain and Runtime state;
4. stop Harness/Provider processes;
5. remove the independent Harness state root only after required backups are verified;
6. remove Runtime state through Runtime policy when appropriate;
7. delete local Provider secrets and rotate credentials;
8. review callers, Providers and domain systems for retained data or committed effects.

Harness cannot retract effects already committed outside it.

## Sharing diagnostics

Before publishing status, handoff, Trace, receipt or evidence output, remove Task text, source content, paths, participant identities, Provider request/response content, external IDs and Artifact content unless required. Never publish API keys, Runtime bearer tokens, raw Harness databases, Harness CAS roots, caller-owned private state or private Provider configuration.

## Non-goals

Harness does not currently provide encryption at rest, per-user tenancy, hosted-service privacy terms, automatic PII detection, selective Journal deletion, secret brokering or protection from a privileged local operator.
