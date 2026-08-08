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
summary: Privacy authority for model and Tool content, durable metadata, recovery, retention, export and deletion boundaries.
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

A `HarnessRunContract` decides what content Harness is authorized to retain. Recovery convenience does not expand that authority.

The default policy is `metadata-only`. Harness-managed Run/Continuity paths may retain identities, digests, budgets, causal links, effect receipts and other bounded execution metadata, but they do not retain exact model or Tool content merely because doing so would make replay easier.

`bounded-private-content` can separately authorize model and Tool content:

- `allow_model_content=True` permits exact model-facing/model-produced content when that object does not also expose an unauthorized Tool channel;
- `allow_tool_content=True` permits exact structured Tool arguments and Tool observations;
- mixed objects take the stricter applicable authority. For example, an Agent request containing Tool observations, a model result containing Tool calls, or a Trace event containing Tool-call arguments requires Tool-content authority even when model-content retention is allowed.

Harness does not automatically classify PII, secrets, proprietary data, or semantic provenance.

## Durable metadata versus content

Under `metadata-only`, current Harness-managed persistence preserves the facts needed to prove what happened without retaining the corresponding content bytes:

| Durable fact | Exact content under metadata-only |
| --- | --- |
| Run State message digest | model transcript omitted |
| Tool Observation digest and Tool receipt | Tool Observation object omitted |
| Provider request/result digests and completion status | exact AgentTurnRequest/AgentTurnResult omitted |
| Provider failure code and dispatch safety | dynamic Provider error detail reduced to a digest-bearing redacted string |
| Trace causal events and execution digests | normalized model result / Tool-call payload removed when unauthorized; free-form detail reduced to a digest |
| terminal Run receipt and conclusion/proposal digests | exact conclusion and CompletionProposal omitted |

The exact content remains available to the current in-memory execution when it was just produced. Durable omission is therefore not the same as deleting the current Agent's working memory mid-turn.

## Recovery consequence

Privacy and effect safety are independent laws.

If a Provider physically completed and the response was lost, metadata-only continuity still retains enough evidence to prove that the Provider Call completed. Harness therefore does **not** redispatch the call. If the exact result bytes were not authorized for retention, continuation fails closed and requires caller-authorized rehydration instead of inventing a result or repeating the physical effect.

The same principle applies to pause/resume and Tool recovery. Exact cross-process reconstruction of a transcript, Provider result, caller interaction ingress, or Tool Observation requires the corresponding content authority. Caller ingress is ordinary model content, so `allow_model_content=True` is sufficient when the projected interaction contains no Tool channel; Tool exchanges still additionally require Tool-content authority. Digest-only state remains useful for identity, fencing, audit and conservative recovery, but it is not treated as if the omitted content were recoverable.

## Working View sources

Working View source material is model-visible content. Product-level materialization therefore goes through the Continuity privacy boundary (`store_working_view_source`) before the source is admitted to WorkingSet history. Model authority is required; a source containing structured Tool projection also requires Tool authority. A raw discovery result is not itself a WorkingSet pin: materialization returns the actual Harness CAS object identity, and that stored-object digest must be used as `resolvedDigest`. A source's semantic digest is not interchangeable with its CAS envelope identity.

`SQLiteHarnessStore` remains a low-level mechanical CAS/Journal primitive. A privileged caller that deliberately bypasses Continuity and writes arbitrary bytes directly to the Store is exercising its own storage authority; the Run privacy policy cannot stop a process that already has filesystem/Store write authority from doing that. Continuity still rejects an unauthorized mechanically present Working View source from becoming valid cognition history.

The mature Loop may also receive an ephemeral Working View projector. The selected WorkingView remains the exact prefix, but two separately authorized transient layers may follow it. After a `needs_input` Snapshot, exact plain caller `user` messages supplied on resume become **caller interaction cognition**: they require model-content authority, do not require Tool-content authority, do not become WorkingSet pins, remain visible across Agent WorkingSet transitions during that interaction, and are consumed when the next `needs_input` Snapshot becomes the new caller boundary. Provider-authored Tool exchanges remain attempt-local and require their existing model/Tool authority. Continuity orders both layers from Journal/Snapshot evidence, so a pre-pause Tool exchange precedes caller ingress and a post-reply Tool exchange follows it. An unbound user message, caller-supplied `system`/`assistant`/Tool structure, isolated Tool Observation, or replacement projection is not valid model-visible cognition. Fresh-process recovery reconstructs only bytes authorized by the Contract; digest-only evidence can fence effects but cannot recreate omitted caller or Tool cognition.

A domain integration may interpret a raw Tool Observation and materialize discovered content through `store_working_view_source` before returning/enriching the exact Tool Observation that the Agent will see. Materialization is a storage fact, not a cognition grant: an exact source may remain physically present in CAS while never appearing in any future model view. Only an Agent-authored successor WorkingSet that explicitly selects the source pin makes it durable current cognition; later omission of that pin removes its current cognition authority even though the source object still exists. Harness verifies structural materialization/privacy and exact identity boundaries; it does not decide which raw records deserve promotion or whether the domain's interpretation is semantically correct.

An explicitly granted WorkingSet-history cognition control discloses only identities that were previously part of committed Agent cognition: attempt identity, committed WorkingSet digest/event sequence, and exact source pins. It does not disclose historical source bytes, materialized-but-never-selected sources, semantic search results or relevance rankings. The result is deterministically recomputed from Journal history when later Provider admission or recovery validates the transcript, so an integration cannot make a forged pin recall-authoritative by returning it locally. Although the catalog payload is identity metadata, the OpenAI-style Provider transcript returns it through a `tool` role after a Provider-authored function call. Current structural privacy therefore requires both model-content and Tool-content authority for this exact recall surface and its clean-pause replay; Harness does not relabel a Tool channel as metadata to bypass the Contract.

Provider execution-control metadata is a separate disclosure channel from task Context. The DeepSeek adapter currently projects exact per-turn remaining budget and the names of currently admitted Runtime Tools from `AgentTurnRequest` as a Harness-authored system control message. This metadata is not inserted into the WorkingSet or WorkingView and is not evidence about the task world; it tells the Agent which execution laws are currently in force.

Transient Tool exchanges used by a `metadata-only` Run are not made durably reconstructable merely because they became Provider input; only the content authorized by the Contract is retained. An Agent-owned WorkingSet transition is different: it is durable cognition history and requires model-content authority. If the transition was chosen after transient Tool evidence, exact cross-process proof additionally requires Tool-content authority so the bound Provider request/state can retain and revalidate the complete exchange. `metadata-only` therefore cannot silently convert transient discovery bytes into a durable successor WorkingSet.

## Structural versus semantic Tool provenance

The model/tool flags enforce structural content boundaries, not information-flow taint tracking.

Harness can recognize direct Tool channels such as Tool calls, Tool arguments, Tool-role messages and Tool Observation objects. It does **not** currently prove that ordinary model text is semantically independent of prior Tool data. If `allow_model_content=True`, ordinary model-visible text may be retained even when a model or domain integration copied or paraphrased information previously learned from a Tool; selecting that source into a WorkingSet does not create semantic-taint proof after the fact. Callers that require semantic non-interference must not authorize model-content retention or must provide an external provenance/redaction mechanism. A promotion-specific provenance tag would not close this general boundary because generic source materialization would remain structurally indistinguishable from unrelated caller/domain text.

## Data ownership

| Data | Physical owner | Semantic owner |
| --- | --- | --- |
| Run Contract, Run events, Provider/Tool execution metadata, Snapshot metadata, Trace metadata and Run receipt | independent Harness Journal/CAS | Harness execution authority |
| exact model content when explicitly authorized | independent Harness Journal/CAS | caller-authorized Harness Run |
| exact Tool content when explicitly authorized | independent Harness Journal/CAS | caller-authorized Harness Run; Runtime remains physical-effect authority |
| caller Task/Actor state and final outcome | caller/domain/optional Host | caller/domain verifier |
| Workspace, Job, process output and Artifact | Runtime | Runtime physical truth |
| Provider traffic not retained by Harness | Provider/local adapter boundary | Provider/operator policy |
| DeepSeek API key | private local secret file | operator |
| Codex/Hermes child-process state | local Provider adapter/process | disposable Provider state |
| historical engineering receipts | repository `evidence/` | bounded engineering evidence |

## Provider disclosure

A Provider may receive:

- system instructions;
- bounded Task Context / Working View selected for the turn;
- prior model-visible messages supplied by the current execution;
- granted Tool definitions;
- Tool observations selected into the current model view;
- additional operator/caller messages on resume.

Provider disclosure and Harness retention are separate decisions. `metadata-only` prevents Harness-managed durable content retention; it does not prevent content from being sent to the configured Provider when that content is required for the requested turn.

Do not place secrets in Context unless disclosure to the configured Provider is intended. Prompt injection cannot expand ToolGrant, but malicious content can still influence model output.

## Retention

Harness retains its private SQLite Journal and immutable CAS for the exact objects authorized by the Contract plus metadata/digests required for audit, recovery and idempotency. Runtime separately controls Artifact and Workspace retention. Provider-side retention follows the Provider's service or local-process policy; caller/domain state follows its owning system.

Do not delete individual Harness CAS objects or Journal events manually. Selective erasure requires a versioned Harness archival/redaction contract that preserves causal and digest relationships.

## Export and migration

Use Harness `store-backup` / `store-verify-backup` / `store-restore` for independent Run state. A complete operational migration may also require:

- caller-authorized content that was intentionally not retained by metadata-only Harness state;
- Runtime Artifacts and Workspace state;
- exact Harness and Protocol revisions, plus a Host revision only when Host is the caller;
- Provider adapter identity and configuration;
- Runtime catalog digest;
- external domain references.

A file copy alone does not prove a resumable Run. A metadata-only backup can prove durable execution history while still being insufficient to reconstruct omitted cognition content.

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

Harness does not currently provide encryption at rest, per-user tenancy, hosted-service privacy terms, automatic PII detection, semantic taint tracking, selective Journal deletion, secret brokering or protection from a privileged local operator.
