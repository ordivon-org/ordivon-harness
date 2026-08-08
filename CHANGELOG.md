# Changelog

All user-visible changes to Ordivon Harness are recorded here. Release and compatibility rules are defined in `docs/RELEASES.md`.

## Unreleased

### Changed

- `candidate_completed` now means bounded Run completion rather than epistemic closure: conclusions may retain honest unresolved unknowns, and new `IndependentCompletionProposal` v2 records them while still reading v1 proposals as having no recorded unknowns;
- the recommended `ordivon_harness.api` facade is now closed over basic Run Contract authoring and the built-in execution paths: DeepSeek settings/adapter, no-Tool and search capability digests, bound/correlation references, execution/runtime references, and Runtime error-contract types are available without dropping to `ordivon_harness.core`;
- no-Tool Runs may bind `maxToolCalls=0`; model, observation, wall-time and token budgets remain positive and Tool capability is still controlled only by the Contract Tool catalog/grant;
- Run privacy is now authoritative over Harness-managed durable content: default `metadata-only` continuity retains execution identities/digests/fences without exact model transcript, Provider result, Tool observation, dynamic Provider-error detail, Trace payload or terminal conclusion/proposal content; exact cross-process content replay requires explicit `bounded-private-content` authority, while completed-effect fencing still prevents redispatch when bytes were intentionally not retained;
- **Breaking pre-1.0 H3:** Ordivon Harness is now a single independent Agent Run product line. The SQLite Harness Journal/CAS is the only current Run writer and `HarnessRunContract` is the only current caller/execution contract.
- the CLI has one `--state-root` meaning and only independent `capabilities`, Run/recovery, and `store-*` commands; the historical `host` namespace and all `cutover-*` commands were removed;
- the package root now mirrors `ordivon_harness.api` plus `package_version` instead of resolving historical lazy compatibility exports;
- the built wheel and repository dependency graph contain only the exact Ordivon Protocol dependency. There is no `host` extra, Host development dependency, or Host pin.

### Removed

- `HarnessHost`, Host-backed `HarnessRunner`, `HostHarnessRunStore`, TaskContract/Assignment/native-Run compatibility objects, `_host_compat`, Host history/handoff/recovery controllers, cutover state, and Host-backed CLI/configuration paths;
- Host-coupled Codex App and Hermes ACP drivers and their old live/stress acceptance scripts; future Provider integrations must bind directly to independent Harness Run authority;
- frozen pre-migration persistence inventory/checks whose object/event set described the deleted Host-backed writer;
- compatibility aliases and decoders whose only purpose was preserving the removed Host-backed product line. Historical evidence receipts remain immutable evidence of the implementation revisions they bind.

### Retained

- independent Provider Call claim/dispatch/completion/failure durability, response-loss replay and UNKNOWN recovery;
- independent Tool-step intent/fence/receipt continuity and caller-supplied Runtime bridges;
- bounded Agent loop, pause/resume snapshots, Trace, Run Receipt, Recovery Assessment and CompletionProposal;
- repository-repair read/edit bridges and the Host-free duck-typed `host_external_adapter` integration module.

### Fixed

- DeepSeek turns that simultaneously request ordinary Tools and `submit_run_conclusion` no longer become Harness failures: the mixed turn is rejected before physical Tool execution and returned through the existing model-correction path so the Agent can choose one action on the next turn;
- the DeepSeek conclusion Tool now describes caller/domain verification rather than the removed Host-backed verification model, and Standalone execution fails closed when a structured completion Contract is not bound by the executing Adapter;
- Quick Start now includes a caller-authored Contract construction path, the DeepSeek 8,192-token completion-ceiling preflight behavior, Runtime error-translation requirements for Tool-bearing callers, and a wheel-verification command that passes the actual wheel path;
- canonical security, data/privacy, verification and domain-Tool guidance now describe the independent Harness Journal/CAS and current Host-free Run API instead of removed Host-backed Assignment/Runner persistence; documentation checks reject those stale current claims;
- concurrent same-digest CAS publication now preserves one immutable published inode and tolerates publication-only `ctime` movement without weakening canonical digest, inode, size, mtime, mode, or no-follow checks;
- SQLite database/WAL/SHM hardening now happens outside active SQLite lock ownership, preventing hardening descriptors from disturbing process-scoped locks under multi-process Store use;
- Continuity, Provider-claim, and terminal-recording execution owners are process-instance unique, so idempotent durable dispatch admission cannot be consumed as duplicate physical Provider or Runtime execution;
- ordinary Store open validates global physical state without replaying every unrelated Run; the target Run is fully history-validated when Continuity opens and full Doctor remains authority-wide.

### Verification

- current deterministic suite runs only the independent product line and preserves Provider/Tool response-loss, fencing, recovery and restart coverage;
- isolated wheel verification requires one Protocol dependency, no Host installation, no Host-backed modules, one independent package-root API, and 14 independent CLI commands;
- `check_dependencies.py`, `check_docs.py` and repository-boundary tests fail if Host imports/dependencies or compatibility product files reappear.

## 0.6.0 — 2026-08-04

### Added

- caller-delegated `HarnessExecutionMandate`, `HarnessExecutionProfile`, `HarnessExecutionStrategy`, and pure `compile_harness_attempt()` separate objective/capability/economic delegation from one exact immutable Run attempt; aggregate Mandate enforcement covers allowed profile IDs plus total-token/wall-time envelopes, with later attempts requiring receipt-derived `HarnessMandateConsumption`; per-attempt model/Tool call limits remain Strategy parameters;
- generic caller-defined `structured-result-v1` completion for DeepSeek: the Run Contract binds a result schema, the Provider conclusion Tool emits a structured result, and callers decode the canonical result without introducing Host/domain policy or a second durable result schema;
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
