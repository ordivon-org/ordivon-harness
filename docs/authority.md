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
updated: 2026-08-04
summary: Decision identifying the documents and machine sources allowed to define current Harness execution, recovery, and completion behavior.
evidence_status: not_applicable
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.architecture
  - harness.operations
---
# Harness Content Authority

## Context

Harness contains current architecture, extraction history, OH and P/R closeouts, H-series proposals, E-series design audits, boundary experiments, fixtures, and frozen evidence. Many records accurately describe the state at one implementation stage but cannot all define the current system simultaneously.

## Decision

[`../README.md`](../README.md) is the canonical repository entry. [`../ARCHITECTURE.md`](../ARCHITECTURE.md) owns the current Harness architecture and responsibility split. [`OPERATIONS.md`](OPERATIONS.md) owns Run operation, cancellation, resume, recovery ordering, semantic Doctor, and cross-component escalation.

Source code, internal protocol codecs, deterministic tests, exact dependency pins, Runtime catalog discovery, Host Journal and CAS inspection, final canonical Traces, and retained receipts remain stronger owners for exact fields, transitions, compatibility, provider behavior, and observed recovery results. Extraction notes, H/OH/E/P/R documents, boundary stages, and closeouts explain design evolution and evidence; they do not silently redefine the current architecture.

## Consequences

Only the repository entry, architecture, operations contract, and this decision enter strict content management in this adoption step. Stage-oriented texts remain available with explicit historical markers. A later human-centered rewrite may turn the strongest evidence into clearer concepts, examples, and troubleshooting paths, but it must preserve provenance and declare supersession rather than create a second current Harness model.

## Status

Accepted and active. Reopen when Harness ownership changes, a stable external protocol or service boundary is introduced, or two managed documents claim the same execution responsibility.
