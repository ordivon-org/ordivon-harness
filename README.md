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
updated: 2026-08-10
summary: Public entry to the durable cognitive execution substrate for caller-neutral Agent Runs, with explicit cognition, action, continuity, Runtime and Host boundaries.
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

Ordivon Harness is the **durable cognitive execution substrate of an Agent**. A caller may submit one exact `HarnessRunContract`, or delegate a broader `HarnessExecutionMandate` that is compiled with a chosen `HarnessExecutionStrategy` into one immutable Run attempt. Within that attempt, the Agent owns semantic reasoning, cognition selection and action choice; Harness turns those choices into exact, provenance-bound, recoverable cognition transitions, Provider calls, Tool intents and durable Run evidence.

Harness deliberately separates **history from cognition, observation from retention, caller interaction from durable knowledge, cognition from execution control, and physical effects from semantic success**. It does not build the Agent's world model for it. It provides a trustworthy substrate on which the Agent can build, revise and act from its own world model.

## Responsibility boundary

Harness owns **how admitted Agent execution attempts become durable and executable**: Run semantics, current cognition state, Provider lifecycle, Agent action normalization, Tool intent/admission, pause/resume and recovery. A Mandate constrains aggregate capability/resource delegation without dictating exact cognitive step counts. It does not own the caller's Task truth, domain commitments, final verification, external-world truth, or physical Runtime Workspace/Job truth.

Its current state model is intentionally multi-domain:

```text
Canonical History        what actually happened
Durable Cognition        Agent-selected WorkingSet
Interaction Cognition    current caller ingress
Attempt Cognition        Provider-authored Tool exchange
Execution Control        current capabilities, provenance and budgets
Effects                  exact admitted actions and physical consequences
```

The effective model view is compiled from the cognition domains plus execution control; it is not a replay of the complete canonical history.

A Host may call Harness, but Host is not a Harness dependency and does not store Harness Run state. The optional `ordivon_harness.host_external_adapter` module is duck-typed and Host-free; it connects two independent authorities without sharing persistence.

## Status

Pre-1.0 and operational for caller-neutral independent Runs. H3 intentionally removed the former Host-backed Assignment/Runner/cutover product line and its compatibility imports. New code uses the independent API and Store only.

## What works

- Agent-owned multi-attempt Strategy admission over `HarnessExecutionMandate`: `build_harness_strategy_selection_context()` exposes the exact Mandate, currently available Profiles, and prior `CompiledHarnessAttempt` + terminal Receipt pairs; Harness mechanically derives `HarnessMandateConsumption` and the remaining economic envelope, an Agent returns one context-digest-bound `HarnessAgentStrategySelection`, and `compile_harness_selected_attempt()` resolves that chosen Profile and freezes the next exact `HarnessRunContract` without a built-in planner or second Mandate state machine;
- immutable `HarnessRunContract` attempt authority, including Context refs, Provider/Adapter identity, Tool catalog/grant digests, budget and completion contract;
- independent SQLite Journal/CAS with caller binding, revision fencing, leases, backup/restore and full Doctor;
- durable Provider Call claim/dispatch/completion/failure state with response-loss reconciliation;
- explicit physical DeepSeek egress composition: the cancellable transport remains direct by default and may consume only a validated loopback HTTPS CONNECT sidecar projected by the execution environment, preserving end-to-end Provider TLS without adding automatic Provider routing;
- durable Tool intents, dispatch fences, observations and recovery-sensitive receipts;
- bounded Agent loop with DeepSeek and scripted adapters;
- Agent-owned WorkingSet/WorkingView cognition selection, exact current-source addressability, caller interaction ingress, attempt-local Tool cognition, explicit caller-to-durable promotion and bounded historical cognition recall;
- experimental Standalone cognition composition: one `StandaloneCognitionProfile` lets the Runner mechanically wire WorkingView projection, Agent-owned transitions, caller promotion and bounded history against the existing Continuity authority, while an exact caller-authored `StandaloneCognitionSeed` bootstraps the first committed WorkingSet without ranking or memory extraction;
- request-bound per-turn action authority: Runtime/World actions live in `AgentTurnRequest.tools`, Harness-native conclusion/cognition actions live in provider-neutral `AgentTurnRequest.capabilities`, and Provider adapters render that exact digest-bound surface instead of owning independent cognition feature flags;
- first friction-driven kernel extraction: exact Agent-turn projection and structural cognition-mutation admission now have internal owners separate from the sequential Run coordinator, while Continuity independently reconstructs/verifies durable authority rather than sharing the constructor;
- pause/resume snapshots, UNKNOWN handling and conservative recovery;
- Host-free Runtime bridges supplied with a caller-owned `HarnessRuntimeClient`;
- Run Receipt and CompletionProposal that remain proposals to the caller rather than domain completion authority; a completed bounded Run may retain explicit unresolved unknowns for caller/domain judgment;
- caller-defined `structured-result-v1` completion schemas for DeepSeek, bound by the Run Contract while caller/domain semantic admission remains external.

## What it does not do

- own Host Tasks, Task Attempts, Assignments, commitments or TaskOutcome;
- import or require `ordivon-host`;
- migrate or decode the removed Host-backed Harness state model;
- infer success from an ambiguous Provider or Tool delivery;
- provide a built-in Tool-bearing Runtime transport in the primary CLI; applications supply a Runtime client through the Python API;
- choose execution strategy for a Mandate with a built-in planner, schedule later attempts, or persist a second Mandate state machine. Harness exposes and validates exact Strategy-selection authority, but the Agent owns the semantic choice and an external caller/Host still decides when another attempt should be requested;
- provide a generic Memory/RAG/semantic-ranking service, automatically select or summarize cognition, infer that one source semantically supersedes another, or silently inject historical sources into the Agent's current view.

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
rm -rf dist
uv build --wheel --out-dir dist
python scripts/check_wheel.py "$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit)"
```

## Public API

Use `ordivon_harness.api` for the recommended application surface. `ordivon_harness.core` exposes the wider Host-free persistence, Provider, Runtime and recovery primitives. The package root mirrors the recommended API plus `package_version` and deliberately has no historical lazy compatibility exports.
`HarnessAgentRun` is now the supported Python execution handle for one exact Agent Run. It owns mechanical state-root → Continuity → Bridge → Runner composition, exact pause/resume Provider-source rebinding and Contract-budget reconstruction. The caller still supplies the Contract, a Contract-bound Adapter factory, and any exact Runtime execution authority; custom bridge composition remains an advanced `core` concern.
Static composition is fail-closed before durable Run creation: exact Contract/cognition/Runtime-binding incompatibilities are rejected before the Adapter factory when they do not depend on it, and Adapter/structured-completion mismatches are rejected before `harness.run-created`. This preflight proves composition only; it does not probe Provider or Runtime availability.
R3.1 adds this surface without removing the existing low-level exports; applications should prefer the handle for normal execution, while advanced integrations may continue to compose the lower layers directly.

For delegated multi-attempt execution, applications should prefer `build_harness_strategy_selection_context()` + `HarnessAgentStrategySelection` + `compile_harness_selected_attempt()`. Prior-attempt authority is an exact `HarnessPriorAttemptEvidence` bundle: the immutable compiled attempt proves the Mandate/System-Manifest/Contract lineage, its terminal Receipt proves what that attempt consumed, and an authorized retained `IndependentCompletionProposal` may expose the prior Agent's candidate result and unresolved unknowns. Caller/domain verification remains separate from the generating Agent: exact `HarnessStrategyEvidence` can carry digest-bound external verification into the next selection context, but Harness treats those bytes as addressable evidence rather than judging, ranking, or endorsing their semantics. The Agent decides which exact prior outcome/verifier refs to adopt and which Profile/budget to choose; Harness derives the next attempt index and remaining token/wall-time envelope mechanically and only admits the choice. Cross-attempt model content is retained only when the Mandate explicitly grants a `HarnessPrivacyPolicy`; the legacy/default Mandate remains metadata-only.

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

- `ARCHITECTURE.md` — current Harness world model, semantic ownership and Run lifecycle;
- `docs/ORDIVON_HARNESS_PC1_COGNITION_CLOSEOUT.md` — historical P-C1.1–P-C1.12 experimental path that established the current cognition model;
- `docs/DELIBERATION-BEFORE-TOOLS-H0.md` — current Harness-native research evidence for deliberation/Tool-exposure sequencing;
- `docs/DELIBERATION-COMPOSITION-H1.md` — validated advanced/internal composition of no-Tool cognition into a later caller-owned Tool loop;
- `docs/DELIBERATION-LIFECYCLE-H2.md` — deterministic lifecycle closeout for aggregate budget, cancellation and absolute-deadline authority across that advanced/internal composition;
- `docs/QUICKSTART.md` — deterministic setup and first Run;
- `docs/OPERATIONS.md` — state, recovery, backup and escalation;
- `docs/STATUS.md` — implemented capability and known limits;
- `docs/RELEASES.md` — release acceptance rules.

Historical closeouts explain earlier designs but are not current authority.

## Security and data

Secrets are not persisted as Run evidence. Tool and Provider evidence is bounded by Contract/privacy policy. Unknown physical delivery remains UNKNOWN until reconciled. See `SECURITY.md` for reporting and operational constraints.

## License

Apache-2.0. See `LICENSE`.
