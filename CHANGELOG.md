# Changelog

All user-visible changes to Ordivon Harness are recorded here. Release and compatibility rules are defined in `docs/RELEASES.md`.

## Unreleased

No user-visible changes recorded after `0.5.0`.

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
