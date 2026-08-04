---
schema_version: 1
id: harness.compatibility
title: Harness Compatibility
type: policy
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - operator
  - maintainer
  - agent
updated: 2026-08-04
summary: Dependency graph, source-level Host boundary, persistent object compatibility and upgrade rules.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.status
  - harness.releases
  - harness.verification
---
# Harness Compatibility

## Dependency graph

The supported public graph is exact, not a floating version range:

| Component | Required identity |
| --- | --- |
| Harness package | `0.5.0` plus exact Git commit |
| Host | `a992d91661df7040dc666ad5dd2511e57d932d6d` |
| Protocol | `420dc356cb664d75db0f34f356156baebe5843db` |
| Python | `>=3.12,<3.13` |
| Runtime | required Tool catalog and request schemas discovered at execution time |

`pyproject.toml`, `uv.lock`, `requirements-audit.txt`, `_host_compat` and boundary tests must agree.

## Host-native source boundary

Harness is not a generic Host plugin. Only `src/ordivon_harness/_host_compat/` may import Host directly. Its submodules separate Context, domain, effects, persistence, extension and Runtime dependencies so model-loop modules do not accidentally load Host kernel/storage internals.

A Host pin change requires:

1. complete Harness deterministic tests against the candidate Host;
2. lockfile regeneration;
3. compatibility and Changelog update;
4. inspection of raw import/API drift;
5. live evidence when Runtime transport or recovery behavior changes.

## Public API levels

### Recommended facade

`ordivon_harness.api` contains application-facing orchestration types.

### Integration modules

`ordivon_harness.host`, `contracts`, `handoff`, Provider drivers and Runtime bridge modules support advanced Ordivon integration but may evolve during pre-1.0.

### Owner-local protocols

`protocol`, `run_state`, history internals and persistence helpers define durable Harness semantics. Their existing decoders are compatibility obligations, but their Python import layout is not a promise that every class remains at package root.

Historical root exports remain temporarily available. New code should not add dependencies on low-level root aliases.

## Durable objects

Current state includes versioned forms of:

- TaskContract and ToolGrant;
- NativeHarnessRunContract;
- HarnessRunReceipt and HarnessRunState;
- ProviderCallRecord and failure receipt;
- ToolStep intent, dispatch fence and receipt;
- Run Snapshot;
- completion proposal, verification and decision;
- recovery assessment and abandonment.

New writers may use newer schemas only when readers preserve supported older versions or migration/cutover is explicit. History is never rewritten merely to normalize format.

## Upgrade rules for active work

Before upgrading an instance:

1. run Host Doctor and Harness semantic history validation;
2. inspect active Provider Calls and Tool Steps;
3. do not upgrade through an unresolved effect boundary without preserving the exact original identities;
4. back up Host state;
5. verify candidate code can read retained objects;
6. run live acceptance on the candidate graph.

A Provider process or hidden session cannot be migrated mid-call. Provider replacement is allowed only at a safe Assignment/recovery boundary. Completed or UNKNOWN calls must be replayed or reconciled from durable records, not resent.

## Deletion of compatibility code

A decoder, root alias, Host adapter or schema path may be deleted only when all retained state and supported consumers are named, an observation window has completed, tests and receipts prove the replacement and rollback no longer depends on the old path.
