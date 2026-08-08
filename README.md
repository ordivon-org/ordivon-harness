---
schema_version: 1
id: harness.start
title: Ordivon Harness
type: start
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
summary: Public entry to caller-neutral Agent Run execution, durable Harness-owned continuity, Runtime bridging, and explicit Host compatibility.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.quickstart
  - harness.status
  - harness.architecture
  - harness.compatibility
  - harness.verification
  - harness.operations
  - harness.data-privacy
  - harness.releases
  - harness.authority
---
# Ordivon Harness

Ordivon Harness is an independent Agent Run authority. It turns a caller-authored `HarnessRunContract` into a bounded, durable model/Tool execution with explicit Provider-call continuity, Tool-step fencing, pause/resume, conservative recovery, Trace evidence, a Run Receipt, and a CompletionProposal.

## Responsibility boundary

Harness owns **how one Agent Run executes**: Provider calls, model/Tool turns, Run-local state, budgets, retries, pause/resume and recovery. It does not own the caller's Task truth, domain commitments, final verification, or physical Runtime Workspace/Job truth.

A Host may call Harness, but Host is not a Harness dependency and does not store Harness Run state. The optional `ordivon_harness.host_external_adapter` module is duck-typed and Host-free; it connects two independent authorities without sharing persistence.

## Status

Pre-1.0 and operational for caller-neutral independent Runs. H3 intentionally removed the former Host-backed Assignment/Runner/cutover product line and its compatibility imports. New code uses the independent API and Store only.

## What works

- immutable `HarnessRunContract` authority, including Context refs, Provider/Adapter identity, Tool catalog/grant digests, budget and completion contract;
- independent SQLite Journal/CAS with caller binding, revision fencing, leases, backup/restore and full Doctor;
- durable Provider Call claim/dispatch/completion/failure state with response-loss reconciliation;
- durable Tool intents, dispatch fences, observations and recovery-sensitive receipts;
- bounded Agent loop with DeepSeek and scripted adapters;
- pause/resume snapshots, UNKNOWN handling and conservative recovery;
- Host-free Runtime bridges supplied with a caller-owned `HarnessRuntimeClient`;
- Run Receipt and CompletionProposal that remain proposals to the caller rather than domain completion authority; a completed bounded Run may retain explicit unresolved unknowns for caller/domain judgment;
- caller-defined `structured-result-v1` completion schemas for DeepSeek, bound by the Run Contract while caller/domain semantic admission remains external.

## What it does not do

- own Host Tasks, Task Attempts, Assignments, commitments or TaskOutcome;
- import or require `ordivon-host`;
- migrate or decode the removed Host-backed Harness state model;
- infer success from an ambiguous Provider or Tool delivery;
- provide a built-in Tool-bearing Runtime transport in the primary CLI; applications supply a Runtime client through the Python API.

## Requirements

- Python 3.12;
- the exact Ordivon Protocol revision pinned in `pyproject.toml` and `uv.lock`;
- `uv` for repository workflows;
- a DeepSeek secret only when using the built-in DeepSeek CLI execution profile.

Repository checks use isolated Ruff:

```bash
uvx ruff==0.15.17 check src tests scripts
python scripts/check_dependencies.py
python scripts/check_docs.py
```

## Quick start

```bash
uv sync
ordivon-harness --state-root /var/lib/ordivon/harness store-init
ordivon-harness capabilities
ordivon-harness --state-root /var/lib/ordivon/harness run RUN_CONTRACT.json --message 'Start the bounded Run'
ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
```

For a source checkout, run the deterministic regression suite and wheel gate:

```bash
uv run python -m unittest discover -s tests -v
python -m build
python scripts/check_wheel.py dist
```

## Public API

Use `ordivon_harness.api` for the recommended application surface. `ordivon_harness.core` exposes the wider Host-free persistence, Provider, Runtime and recovery primitives. The package root mirrors the recommended API plus `package_version` and deliberately has no historical lazy compatibility exports.

Tool-bearing applications supply `HarnessRuntimeClient` explicitly. Repository-repair bridges and other domain-specific execution surfaces remain explicit modules rather than package-root policy.

## Operator interface

The CLI has one authority and one state-root meaning:

```text
capabilities
doctor
status
inspect
run
resume
recover
store-init
store-doctor
store-inspect
store-events
store-backup
store-verify-backup
store-restore
```

There is no `host` namespace and no `cutover-*` surface.

## Documentation map

- `ARCHITECTURE.md` — semantic ownership and Run lifecycle;
- `docs/QUICKSTART.md` — deterministic setup and first Run;
- `docs/OPERATIONS.md` — state, recovery, backup and escalation;
- `docs/STATUS.md` — implemented capability and known limits;
- `docs/RELEASES.md` — release acceptance rules.

Historical closeouts explain earlier designs but are not current authority.

## Security and data

Secrets are not persisted as Run evidence. Tool and Provider evidence is bounded by Contract/privacy policy. Unknown physical delivery remains UNKNOWN until reconciled. See `SECURITY.md` for reporting and operational constraints.

## License

Apache-2.0. See `LICENSE`.
