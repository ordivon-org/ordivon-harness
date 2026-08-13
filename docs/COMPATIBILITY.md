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

The current Harness runtime dependency graph is intentionally small: the package depends only on the exact Ordivon Protocol revision pinned by `pyproject.toml` and `uv.lock`. There is no Host dependency, optional Host extra, or Host development group.

Python support is `>=3.12,<3.13`. Runtime integration is structural through the caller-supplied `HarnessRuntimeClient`; a Runtime server/version is not a Python package dependency.

## Public API

`ordivon_harness.api` is the recommended application facade. The package root mirrors that API plus `package_version`. `ordivon_harness.core` is the wider Host-free integration surface. P0 adds `HarnessAgentRun.explain()` on the existing recommended Run handle. Generated capability projectors live in the advanced `ordivon_harness.capability_catalog` module and the explicit application-local `HarnessAgentRunToolSurface` lives in `ordivon_harness.run_tool_surface`; neither is added to the stable package-root facade yet. These projections are not durable authority and the Tool-surface seam is exact-digest-bound rather than a global registry/plugin lifecycle contract.

H3 intentionally removed historical package-root aliases, `host_api`, `HarnessRunner`, `HarnessHost`, Assignment/TaskContract objects, cutover APIs and Host source compatibility modules. New code must not depend on them.

## Durable state

Current writers own only independent Harness state: `HarnessRunContract`, Run projection/events, Provider Call records, Tool-step intents/fences/receipts, Run snapshots, Trace, recovery assessment, Run Receipt and CompletionProposal.

Pre-H3 Host-backed state is not a current compatibility obligation. Historical receipts remain evidence of the implementation that produced them; they are not a decoder requirement for H3.

Schema-v1 caller-neutral `HarnessRunContract` keeps one narrow compatibility rule
because it is part of the independent line: budget fields present in the Contract
are exact authority; omitted known fields use the historical defaults; unknown
fields fail closed. `maxConclusionCorrections` is a later known budget field with
historical default 3 when absent. An older Contract that explicitly binds
`maxToolCorrections` does not thereby bind conclusion correction: Tool-call
correction and caller/domain conclusion correction are separate execution
mechanics.

## Upgrade rule

Before upgrading active independent work, inspect nonterminal Runs and unresolved Provider/Tool delivery, back up the Harness root, and prove the candidate can reopen current independent state. Do not reinterpret UNKNOWN or resend an ambiguous effect merely because code changed.

Pre-1.0 breaking changes may deliberately drop unused schemas or APIs. Such deletion must be explicit in the Changelog and current tests/docs must describe only the retained authority.
