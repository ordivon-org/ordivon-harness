# Changelog

All user-visible changes to Ordivon Harness are recorded here. Release and compatibility rules are defined in `docs/RELEASES.md`.

## Unreleased

### Added

- first-class Host-free CLI `capabilities`, `run`, `resume`, `status`, `inspect`, `recover` and `doctor` over the independent Harness Journal/CAS, with caller-supplied `HarnessRunContract` authority;
- canonical no-Tool Tool Grant identity, enforced together with the no-Tool catalog before independent Provider execution;
- caller-neutral `HarnessRunContract`, bounded references, W3C correlation context and metadata-first privacy policy;
- independent `SQLiteHarnessStore` with append-only Run Events, caller binding, revision fencing, Run leases, immutable CAS and full-history Doctor;
- owner-neutral `HarnessRunContinuityStore` consumed by `RuntimeToolBridge`, with shared retained Run values and lifecycle errors outside the Host-backed implementation;
- caller-neutral Provider Call Record and Dispatch Fence v2 codecs while retaining exact v1 Host-backed decoding;
- event-sourced `SQLiteHarnessRunContinuityStore` for Provider Call, Tool Step, Snapshot, pause and replay semantics over the independent Journal/CAS;
- `SQLiteHarnessAgentBridge` and canonical no-Tool surface for real Host-free Agent Loop completion, pause/resume and durable Provider replay;
- caller-neutral `HarnessExecutionBinding`, Runtime references and generic Workspace execution request builder;
- Host-free Runtime Tool lowering with the legacy Host bridge adapted through the same binding while preserving request identity;
- `SQLiteHarnessRuntimeBridge` for observation-only independent Runtime search, Harness-owned dispatch fencing, exact-request response-loss reconciliation and durable Tool observations;
- explicit `StandaloneHarnessRunner` and `IndependentRunRecorder` for segmented Trace retention, caller-neutral Run Receipt, Recovery Assessment and CompletionProposal admission;
- Host-free `ordivon_harness.core` facade, lazy compatibility exports and an optional exact `host` integration extra;
- Host-neutral `OrdivonHarnessExternalExecutorAdapter` and a cross-repository response-loss roundtrip with separate Host and Harness histories;
- active legacy/independent Run inventory, append-only cutover and rollback receipts, tamper detection, and a legacy writer gate;
- explicit `store-init`, `store-doctor`, `store-inspect` and `store-events` operator commands;
- online Store backup, exact verification, tamper detection and restore to a fresh destination;
- frozen P0 inventory for 27 durable object classes and 15 Host extension Event kinds;
- bounded atomic Harness Event batches with complete replay idempotency, partial-replay rejection, same-batch causality checks, and one-lease projection commit;
- repository-owned 1,000-Run / 100,000-Event scale acceptance and integrity-bound receipt generation.

### Fixed

- independent `StandaloneHarnessRunner` now enforces every `RunBudget` field explicitly claimed by `HarnessRunContract`; unsupported budget fields fail closed instead of being silently ignored;
- `HarnessRunContract` snapshots and exposes read-only top-level budget/completion authority maps so caller-side mutation cannot change the durable Contract digest after construction.

### Compatibility

- the primary CLI now names independent Harness Run operations directly; historical Host-backed Task/Assignment commands move under the explicit `host` namespace without removing the underlying compatibility APIs or durable decoders;
- fresh package capability discovery advertises the recommended Host-free facade instead of optional Host-backed root aliases; historical lazy attribute access remains available during the pre-1.0 window;
- primary CLI execution is intentionally limited to the canonical no-Tool DeepSeek profile; Tool-bearing independent execution remains available through the Host-free Python API with a caller-supplied Runtime client rather than a duplicated Host transport.
- the optional Host integration and development graph now pin remote-reachable Host `428a6f2f90b4050535507c9be078c450552177e5`;
- the historical `HarnessRunner` compatibility path remains Host-backed; retained Host Provider Call, Tool Step, Snapshot, recovery and completion bytes are not rewritten by the independent CLI transition;
- no new Run is dual-written and no retained Host history is rewritten;
- `ordivon_harness.api` is now the recommended Host-free application facade; the former Host-backed facade is preserved explicitly as `ordivon_harness.host_api`, while historical package-root aliases remain during the pre-1.0 window;
- the base wheel requires only the exact Protocol revision and proves the recommended API loads without Host; Host-backed APIs require the exact `host` extra, while the repository dev group keeps the complete regression graph.

### Verification

- focused P0 Contract, Journal/CAS, lease, idempotency, corruption, permissions, CLI, backup and restore tests;
- independent Provider/Tool continuity tests covering claim races, stale completion privacy, UNKNOWN recovery, safe retry budgets, Harness authority fences, Receipt chains and close/reopen reconstruction;
- real Agent Loop tests for independent candidate completion, lost-completion-response replay and `needs_input` resume without Host or Runtime access;
- independent Runtime Tool tests for direct completion, response loss without redispatch, ambiguous lookup cardinality and pre-admission rejection;
- Standalone Runner tests for terminal restart inspection, pause/resume Trace combination and status-preserving Recovery Assessment;
- isolated base-wheel proof that `ordivon_host` is absent while a persistent Run completes and reopens, followed by optional Host-extra API verification;
- real DeepSeek `deepseek-v4-flash` no-Tool primary-CLI acceptance: one Provider call reached `candidate_completed`, produced an independent Run Receipt and CompletionProposal, then reopened through fresh `status`, `inspect`, `recover` and full Doctor commands;
- Host request-only commit-gap acceptance proving exact retry binds the same completed Harness Run and collects a proposal without Task completion;
- cutover acceptance for active legacy blockers, terminal legacy admission, nonterminal independent blockers, safe rollback, post-activation rollback refusal, CLI selection and receipt tampering;
- Execution Binding tests for deterministic identities, Harness-only foreign references, generic Tool lowering and exact legacy Host request compatibility;
- complete legacy Host-backed Harness suite remains a required regression gate;
- atomic Event-batch rollback/replay tests and deterministic scale-receipt smoke are part of the current gate;
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
