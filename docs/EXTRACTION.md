# Ordivon Harness repository extraction

> **Historical implementation evidence:** This document records a bounded pre-extraction or stage-specific design, closeout, experiment, or migration result. It is not a current Harness architecture or operations source. Use [`../README.md`](../README.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`OPERATIONS.md`](OPERATIONS.md), and [`authority.md`](authority.md) for the active boundary. Historical paths and revisions are preserved for provenance.

Status: standalone repository boundary implemented

Source Host revision: `3f50c676802f1c3653767b200db445d15f2f7930`

Host extraction implementation commit: `8275a81b3a56834561d2555f276c10e6c62e2735`

Host merge commit: `98852d0a39b6d4c489396bda2fd0c99cc3870e34`

Extracted source-history head: `fbfeff54163e78ca86060b053cb854a94703968c`

## Why the repository exists

Harness had become a large, independently evolving subsystem inside `ordivon-host`: Provider-faithful Codex and Hermes drivers, a first-party bare-model loop, Tool lowering, Assignment and Run contracts, completion adjudication, recovery, semantic history validation, tests, fixtures and live evidence.

Keeping those concerns in Host created the wrong dependency direction and made every Host audit include Provider and Agent-loop implementation details.

The accepted boundary is now:

```text
ordivon-harness → ordivon-host → ordivon-protocol
```

`ordivon-host` must never import this package.

## Extraction method

The implementation history under `src/ordivon_host/harness` was preserved with `git subtree split`. Ten implementation commits remain visible in this repository, covering:

- H1 Assignment and completion fencing;
- H2 Runtime correlation;
- H3 Codex App Server;
- H4 Hermes ACP;
- H5 cross-Provider replacement and faults;
- OH0–OH2 native Harness skeleton;
- OH3 DeepSeek loop;
- OH4 Host-integrated native Run;
- OH5 process-loss recovery;
- E1–E2 Tool semantics and Run disposition.

A later extraction commit moves the package to `src/ordivon_harness` and imports the thin Host core explicitly.

## What moved

- all Harness production modules;
- Codex, Hermes and first-party bare-model execution;
- Task Contract, Attempt, Assignment, Tool Grant, Run, Recovery and Completion models;
- Harness-aware handoff and semantic history Doctor;
- deterministic tests and frozen evaluation assets;
- live scripts and DeepSeek secret configuration utility;
- design records and immutable evidence.

## What remains in Host

- generic Goal and Task continuity;
- SQLite Journal, immutable CAS and revision admission;
- `HostKernel` and short Task leases;
- generic Context, Effect and Runtime-client infrastructure;
- extension-safe event persistence;
- generic history validation and operator handoff.

Harness objects continue to be stored in Host CAS and admitted to Host Task streams. That is storage ownership, not Python package ownership.

## Compatibility

There is intentionally no `ordivon_host.harness` compatibility package. Consumers import `ordivon_harness` explicitly.

Historical Host state remains readable because Host accepts bounded extension event strings and preserves their exact payloads and CAS references. Full Harness semantic checks run through:

```bash
ordivon-harness --state-root /path/to/host-state doctor
```

The split adds no second database, RPC service, daemon or duplicated Task projection.
