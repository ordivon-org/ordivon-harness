---
schema_version: 1
id: harness.releases
title: Harness Releases and Versioning
type: policy
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
updated: 2026-08-04
summary: Version identities, release gates, compatibility obligations and deprecation rules for Harness.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.status
  - harness.compatibility
  - harness.verification
---
# Harness Releases and Versioning

## Independent identities

| Identity | Meaning |
| --- | --- |
| package version | public Python distribution change set |
| Git commit | exact Harness implementation |
| Harness protocol revision | owner-local Run semantic family |
| object `kind` and `schemaVersion` | retained CAS interpretation |
| Host commit | source-level authority/storage API |
| Protocol commit | promoted cross-repository value contracts |
| Runtime catalog digest | physical Tool schema used by a Run |
| Provider adapter/model identity | inference source semantics |
| receipt digest | exact tested journey |

Package SemVer does not replace these stronger identities.

## Current stage

Harness `0.6.0` is pre-1.0. Public behavior may evolve, but retained state, effect identities and uncertainty cannot be silently reinterpreted.

## Change classes

### Patch

Fix implementation, diagnostics, documentation or tests without intentionally changing supported public API, durable object meaning or Provider/Tool semantics.

### Minor

Add facade APIs, adapters, object versions or capabilities while preserving existing supported readers and safe recovery.

### Major

Remove or reinterpret supported public APIs, object schemas, Host boundaries, Provider semantics or Tool recovery. Requires an explicit cutover, migration/export plan and rollback boundary.

## Release gates

A releasable commit requires:

1. `uv sync --locked`, `uv lock --check` and dependency-contract success;
2. complete deterministic tests and semantic history tests;
3. public API and Host import-boundary tests;
4. documentation/evidence validation;
5. wheel build, metadata validation, isolated installation and CLI entry-point smoke testing;
6. exact Git dependency validation and third-party PyPI vulnerability audit when such dependencies exist;
7. secret scanning and CodeQL;
8. Changelog entry;
9. live receipt when Provider, Runtime, Tool recovery, cancellation or completion semantics change;
10. named limitations and compatibility impact.

## Version source

Runtime client identity must use `ordivon_harness.version.package_version()` rather than a duplicated literal. The fallback version is tested against `pyproject.toml` for source-checkout execution.

## Dependency updates

A Host or Protocol pin update is an architecture compatibility change, not routine Dependabot churn. It requires the full Harness suite against the candidate revision and lockfile regeneration.

## Deprecation

Historical package-root aliases are retained during the transition to `ordivon_harness.api`. Removal requires Changelog notice, an observation window and a planned pre-1.0 breaking release. Durable decoders remain until retained state no longer requires them.

## Publication

Tags matching `v*` trigger the portable release-acceptance workflow and retain the verified wheel as a GitHub Actions Artifact. This is repository provenance, not artifact signing or package-index publication.

Current distribution is source and repository-built wheel. Public package-index publication, signed artifacts, hosted images or automatic deployment require a separate provenance and release-signing contract.
