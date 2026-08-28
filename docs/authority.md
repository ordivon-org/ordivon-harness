---
schema_version: 1
id: harness.authority
title: Harness Content Authority
type: decision
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - maintainer
  - builder
  - operator
  - agent
updated: 2026-08-29
summary: Decision identifying the documents and machine sources allowed to define current Harness behavior, compatibility, evidence and operation.
evidence_status: not_applicable
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.quickstart
  - harness.status
  - harness.architecture
  - harness.compatibility
  - harness.verification
  - harness.operations
  - harness.p0-independent-persistence
  - harness.data-privacy
  - harness.releases
---
# Harness Content Authority

## Context

Harness contains current architecture, extraction history, OH/H/P/R closeouts, Provider experiments, fixtures and frozen evidence. These records do not have equal authority, and older evidence cannot silently certify current source.

## Decision

| Responsibility | Canonical source |
| --- | --- |
| public identity, boundaries and navigation | [`../README.md`](../README.md) |
| installation and first deterministic/live journeys | [`QUICKSTART.md`](QUICKSTART.md) |
| maturity, support graph and known limits | [`STATUS.md`](STATUS.md) |
| architecture and semantic ownership | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| dependency-inverted domain Tool Loop boundary | [`DOMAIN-TOOL-BRIDGE-P0.md`](DOMAIN-TOOL-BRIDGE-P0.md) |
| independent Harness Journal/CAS, Run and recovery authority | [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| dependency, Host API, durable object and upgrade compatibility | [`COMPATIBILITY.md`](COMPATIBILITY.md) |
| evidence classes and claim interpretation | [`VERIFICATION.md`](VERIFICATION.md) |
| current research semantics and recovery root | [`../research/README.md`](../research/README.md) and its linked current closeouts |
| machine publication of owner-native research currentness | `../research/authority/CURRENT.json` → immutable digest-bound publication; projection only, never stronger than the research/source/evidence authorities it cites |
| operation, cancellation, recovery, Doctor and escalation | [`OPERATIONS.md`](OPERATIONS.md) |
| sensitive data, Provider disclosure, retention and deletion | [`DATA_AND_PRIVACY.md`](DATA_AND_PRIVACY.md) |
| versions, release gates and deprecation | [`RELEASES.md`](RELEASES.md) |

Source code, owner-local codecs, deterministic tests, exact dependency pins, `uv.lock`, Runtime catalog discovery, current Host Journal/CAS inspection, independent Harness Journal/CAS Doctor checks, canonical Traces and digest-bound evidence remain stronger owners for exact fields, transitions and observed results.

### Repository source-integration currentness

For a present-tense claim about the **source-integrated Harness repository**, the owner source is the canonical repository named by `.ordivon/project.yaml`, on its default `main` branch, after remote freshness has been explicitly observed. In the current Git topology that is the fetched canonical repository `main` corresponding to `origin/main`; a local `refs/heads/main`, worktree `HEAD`, detached Runtime Workspace, or Workspace name may be an exact source fence but does not by itself prove source-integration currentness.

Exact historical or experiment work may intentionally bind any exact Git commit. Such work should say `current-to-this-source` (or equivalent bounded scope) unless it has separately resolved the owner-operation current source. A local/remote ref mismatch is therefore an attention signal, not automatic semantic staleness: if the load-bearing owner carrier is unchanged, a source-bound result can remain valid without being relabelled as current repository source.

This source-integration relation is independent of other Harness currentness relations. `research/authority/CURRENT.json` selects the current owner-research publication and may intentionally source-fence an older Git revision when later implementation-only changes do not alter research standing. A Git tag/release receipt owns release provenance. Runtime/Host/store receipts own their respective deployed or operational state. None of those identities silently substitutes for another.

`evidence/index.json` classifies repository evidence and binds it to implementation/currentness provenance; it does not own the domain/research semantics asserted by that evidence. Historical stage reports and closeouts preserve provenance but do not override current contracts. `CHANGELOG.md` records change and does not redefine current behavior.

## Consequences

- canonical documents are listed in `.ordivon/project.yaml` and validated by `scripts/check_docs.py`;
- exact dependency truth is validated separately by `scripts/check_dependencies.py`;
- evidence/file correspondence and revision/currentness binding are validated by `scripts/check_evidence.py`;
- new current claims must identify current tests or evidence bound to the current graph;
- immutable research evidence may use the explicit index/Git-lineage binding defined by [`VERIFICATION.md`](VERIFICATION.md) instead of rewriting frozen payload bytes to mimic a legacy receipt schema;
- the Atlas-compatible research publication is generated only after owner-side semantic adjudication; its digest/current pointer does not make Atlas, Git recency, or repository existence an alternate research authority;
- a new canonical document must declare which responsibility it owns and update this decision.

## Status

Accepted and active. Reopen when semantic ownership changes, a protocol-level Host boundary replaces source compatibility, or two managed documents claim the same fact.
