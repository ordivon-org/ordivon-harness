# Changelog

All user-visible changes to Ordivon Harness are recorded here. Release and compatibility rules are defined in `docs/RELEASES.md`.

## Unreleased

### Added

- recommended `ordivon_harness.api` facade and runtime package-version accessor;
- private `_host_compat` package that centralizes all source-level Host imports;
- public status, Quick Start, compatibility, verification, data/privacy, release, security and contribution documents;
- dependency, documentation and evidence checks;
- operator `inspect` and `handoff` commands;
- pinned CI, CodeQL, secret scanning, dependency audit, Dependabot and acceptance workflows;
- claim-to-evidence index for historical receipts.

### Changed

- `ordivon-host` dependency and `uv.lock` now agree on remote-reachable revision `a992d91661df7040dc666ad5dd2511e57d932d6d`;
- CLI Runtime identity now derives from installed package metadata instead of a hard-coded version;
- architecture now describes Harness as Host-native rather than a generic Host plugin;
- README recommends a constrained public facade instead of treating every root export as stable;
- pure model-Tool request lowering now lives in `ordivon/runtime_lowering.py`, separate from Runtime I/O and Host writes;
- durable Tool-batch restoration and evidence comparison now live in `ordivon/run_recovery.py`, outside the main Agent loop.

### Compatibility

- historical package-root exports remain available during the pre-1.0 transition;
- durable Harness objects and event semantics are unchanged by the Host import centralization;
- current evidence receipts remain historical records bound to their original revisions.

## 0.5.0 — Current operational prototype

- Host-backed Provider Call and Tool Step durability;
- bounded Agent loop, cancellation, budgets and resume;
- DeepSeek, Codex App Server and Hermes ACP adapters;
- semantic history validation and recovery evidence;
- public `HarnessRunner` orchestration facade.
