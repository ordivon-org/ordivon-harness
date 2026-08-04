---
schema_version: 1
id: harness.verification
title: Harness Verification
type: reference
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - operator
  - researcher
  - agent
updated: 2026-08-04
summary: Claim classes, evidence strength, historical receipt interpretation and current release gates.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.status
  - harness.compatibility
  - harness.releases
---
# Harness Verification

## Evidence classes

| Evidence | Proves | Does not prove |
| --- | --- | --- |
| deterministic unit/integration test | current source invariant under controlled inputs | live Provider or Runtime behavior |
| frozen fixture | a named failure trajectory and expected repair | arbitrary repositories or Providers |
| live receipt | one real journey on an exact dependency graph | current `main` after later changes |
| historical closeout/report | design evolution and prior decisions | current implementation correctness |

No receipt should be cited without its Harness/implementation revision and dependency context.

## Current portable gate

The current release gate includes:

- compile and Ruff;
- complete deterministic suite with `ResourceWarning` as error;
- exact dependency and lockfile checks;
- Host import-boundary tests;
- stable API contract tests;
- semantic-history validation tests;
- documentation and evidence-index validation;
- wheel build and dependency audit.

## Historical live receipts

`evidence/index.json` classifies repository receipts. Existing Codex, Hermes, DeepSeek, Runtime and replacement/recovery receipts are historical because they bind commits before current `main`. They remain valuable evidence for those trajectories but must not be described as certification of current code.

## Current live acceptance

A current release-changing Provider, Runtime, recovery or completion path should produce a new receipt containing:

- Harness Git commit and package version;
- Host and Protocol revisions;
- Runtime identity and Tool catalog digest;
- Provider adapter/model identity;
- Task, Assignment and Run identities;
- relevant Tool Step and Provider Call identities;
- final status and explicit unknowns;
- receipt integrity digest;
- limitations.

The canonical command is `scripts/local-acceptance run` on an owner-trusted acceptance environment.

## Claim discipline

Use these terms consistently:

- **operational**: repeatedly exercised in the supported graph;
- **experimental**: implemented and tested, but public behavior may still change;
- **verified in pinned graph**: deterministic/live evidence exists for named revisions;
- **historical**: evidence exists only for an earlier graph;
- **unsupported**: no contract or safe path exists.

Tests and receipts verify bounded behavior. They do not turn Runtime success into semantic Task completion or remove Provider/domain uncertainty.
