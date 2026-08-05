# Changelog

All user-visible changes to Ordivon Harness are recorded here. Release and compatibility rules are defined in `docs/RELEASES.md`.

## Unreleased

### Added

- caller-neutral `HarnessRunContract`, bounded references, W3C correlation context and metadata-first privacy policy;
- independent `SQLiteHarnessStore` with append-only Run Events, caller binding, revision fencing, Run leases, immutable CAS and full-history Doctor;
- owner-neutral `HarnessRunContinuityStore` consumed by `RuntimeToolBridge`, with shared retained Run values and lifecycle errors outside the Host-backed implementation;
- explicit `store-init`, `store-doctor`, `store-inspect` and `store-events` operator commands;
- online Store backup, exact verification, tamper detection and restore to a fresh destination;
- frozen P0 inventory for 27 durable object classes and 15 Host extension Event kinds.

### Compatibility

- the production `HarnessRunner`, Provider Call, Tool Step, Snapshot, recovery and completion paths remain Host-backed;
- no new Run is dual-written and no retained Host history is rewritten;
- the stable `ordivon_harness.api` facade is unchanged; P0 types are transitional package-root exports;
- the exact Host and Protocol dependency graph remains required until standalone package extraction is separately completed.

### Verification

- focused P0 Contract, Journal/CAS, lease, idempotency, corruption, permissions, CLI, backup and restore tests;
- complete legacy Host-backed Harness suite remains a required regression gate;
- [`docs/P0-INDEPENDENT-PERSISTENCE.md`](docs/P0-INDEPENDENT-PERSISTENCE.md) records the implemented boundary and remaining cutover work.

## 0.6.0 — 2026-08-04

### Added

- public `DomainToolCatalog`, `DomainToolBridge`, `DomainToolLoopPlan` and `DomainToolLoopRunner`;
- deterministic domain catalog/grant identity and an inspectable execution identity binding Harness, Provider, domain Bridge and complete Loop budget;
- fail-closed tests proving unknown grants are rejected before Provider invocation and non-Runtime domain Tools complete a full model/Tool/conclusion loop.

### Compatibility

- existing `HarnessRunner`, Host Assignment persistence and `RuntimeToolBridge` behavior are unchanged;
- the new boundary is additive and keeps Harness independent of Security, Game, World and other domain packages;
- domains remain responsible for durable domain state, admission, effect truth and verification.

### Verification

- 264 deterministic and semantic-history tests pass;
- the new module passes isolated strict type checking and full-repository Ruff checks;
- public API, documentation, dependency direction and wheel installation remain release gates.

## 0.5.0 — 2026-08-04

### Added

- recommended `ordivon_harness.api` facade and runtime package-version accessor;
- private `_host_compat` package that centralizes all source-level Host imports;
- public status, Quick Start, compatibility, verification, data/privacy, release, security and contribution documents;
- dependency, documentation, evidence and wheel-installation checks;
- operator `inspect` and `handoff` commands;
- pinned CI, CodeQL, secret scanning, third-party PyPI audit, Dependabot and acceptance workflows;
- tag-triggered release acceptance with retained wheel Artifact;
- bug, capability-proposal and pull-request change contracts;
- claim-to-evidence index for historical receipts.

### Changed

- `ordivon-host` dependency and `uv.lock` now agree on remote-reachable governance revision `1a4027bb26d77a2e051ca933bf664578f071a5a9`;
- CLI Runtime identity now derives from installed package metadata instead of a hard-coded version;
- architecture now describes Harness as Host-native rather than a generic Host plugin;
- README recommends a constrained public facade instead of treating every root export as stable;
- canonical setup and verification commands now use the locked `uv` graph and a pinned isolated Ruff invocation;
- pure model-Tool request lowering now lives in `ordivon/runtime_lowering.py`, separate from Runtime I/O and Host writes;
- durable Tool-batch restoration and evidence comparison now live in `ordivon/run_recovery.py`, outside the main Agent loop.

### Compatibility

- historical package-root exports remain available during the pre-1.0 transition;
- durable Harness objects and event semantics are unchanged by the Host import centralization and internal execution-seam extraction;
- current repository receipts remain historical records bound to their original revisions;
- the distribution remains source and repository-built wheel rather than a package-index publication.

### Verification

- 261 deterministic and semantic-history tests pass against the final public pinned graph;
- wheel metadata, exact dependency identities, public API imports and CLI entry points are checked through an isolated installation;
- live Host→Harness→Runtime acceptance remains required for commits that change effect, recovery, cancellation or completion semantics.
