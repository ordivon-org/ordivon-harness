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
updated: 2026-08-12
summary: Public entry to the durable cognitive execution substrate for bounded Agent Runs, with explicit cognition, Provider and Tool continuity, recovery, evidence, and caller/domain boundaries.
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

An Agent Run is more than one model response.

A Provider call may be interrupted. A Tool may have changed the world before its response is lost. The caller may supply new information. The Agent may decide that some evidence should remain in its current cognition while other history should not be replayed. A model may conclude that its bounded Run is finished while the caller's Task is still unresolved.

**Ordivon Harness makes that bounded Agent Run durable without taking the Agent's semantic choices away from it.**

The caller binds one exact `HarnessRunContract`, or delegates a broader `HarnessExecutionMandate` that is compiled with an Agent/application-selected Strategy into one immutable attempt. Harness then preserves the structural truth needed to run, pause, recover, and inspect that attempt: Provider identity, current cognition, admitted actions, Tool effects, budgets, evidence, and completion proposal.

It does **not** build the Agent's world model, decide which evidence is important, or decide whether a domain objective is finally satisfied.

## Why Harness exists

Consider a Tool-bearing Run:

```text
Agent asks for a Tool effect
→ Harness admits one exact Tool intent
→ Runtime begins physical work
→ the effect may occur
→ the response path breaks
→ the Agent process disappears
```

On restart, blindly issuing the Tool again may duplicate the effect. Replaying every old message may also give the model stale or irrelevant cognition. Treating a recovered Provider response as Task completion would be a third error.

Harness therefore keeps three questions separate:

1. **What actually happened in this Run?** — canonical execution history and receipts.
2. **What should the Agent see now?** — Agent-selected cognition plus current caller/Tool context.
3. **What actions are admitted now?** — exact per-turn capabilities, Tools, budgets, and provenance.

Those answers are related, but they are not one message list.

## Responsibility boundary

Harness owns **how one admitted Agent execution attempt becomes durable, executable, and recoverable**.

```text
Canonical History       what happened in the Run
Durable Cognition       Agent-selected WorkingSet
Interaction Cognition   current caller ingress
Attempt Cognition       current Provider/Tool exchange
Execution Control       exact actions, provenance and budgets allowed now
Effects                  admitted Tool intents and bound physical evidence
```

The effective model view is compiled from current cognition and execution control. It is not a replay of complete Run history.

Other owners keep their own meaning:

| Fact or responsibility | Owner |
| --- | --- |
| caller Task, domain objective, final semantic acceptance | caller / Host / domain |
| Agent selection of current evidence and next action | Agent within delegated authority |
| bounded Run structure, Provider/Tool continuity, current cognition mechanics | Harness |
| local Workspace/Job/Attempt execution truth | Runtime |
| external-world/native occurrence truth | the external owner/provider/domain |

A Host may call Harness, but Host is not a Harness dependency and does not store Harness Run state. Harness may return a `CompletionProposal`; that proposal is **not** Host Task completion or domain truth.

## One normal Run

```text
caller authors Contract
→ Harness creates durable Run identity
→ current Working View is projected
→ Provider receives exact request-bound actions
→ Agent reasons and may:
     • conclude the bounded Run
     • call an admitted Runtime/World Tool
     • change selected durable cognition
     • promote exact caller ingress into durable cognition
     • inspect bounded cognition history when admitted
→ Harness records structural/effect evidence
→ pause, recover, or continue as needed
→ Harness emits Run Receipt + optional CompletionProposal
→ caller/domain decides what that result means
```

Provider-specific wire state may exceed reconstructed semantic messages, but the current contracted product does **not** expose a generic `ProviderToolContinuation` primitive. Opaque Provider-local continuation therefore remains Provider/integration-local unless fresh direct pressure earns a bounded Harness surface.

## Status

Harness is **pre-1.0 but operational** as an independent, caller-neutral durable cognitive execution substrate. The only current writer is the Harness SQLite Journal/CAS. The former Host-backed Assignment/Runner/cutover product line was removed and has no supported compatibility path.

Current maturity and known limits live in [`docs/STATUS.md`](docs/STATUS.md). Exact evidence interpretation lives in [`docs/VERIFICATION.md`](docs/VERIFICATION.md).

## What works

The current product includes:

- immutable `HarnessRunContract` attempt authority with caller/objective/context, Provider/Adapter, Tool catalog/grant, budgets, privacy and completion contract;
- independent SQLite Journal/CAS with leases, revision fencing, backup/restore and Doctor;
- durable Provider Call claim/dispatch/completion/failure state and response-loss recovery;
- durable Tool intent, dispatch fence, receipt/observation and Runtime reconciliation boundaries;
- Agent-owned WorkingSet/WorkingView selection separated from canonical history;
- caller interaction ingress that can remain transient or be explicitly promoted by the Agent into durable cognition;
- attempt-local Tool cognition that survives recovery but expires when a successor cognition attempt commits;
- bounded historical committed-cognition inspection and exact pin re-selection;
- advanced exact cross-Run reusable cognition admission: an external owner can resolve a digest-bound knowledge/procedure source into the existing cognition-seed path without automatic injection, ranking, evaluation or Harness-owned storage;
- request-bound `AgentTurnRequest.tools` and Harness-native capabilities, so installed mechanisms do not silently become current action authority;
- advanced opt-in bounded ToolProgram composition: the Agent may author one linear program over only the exact Tools admitted on that turn, while every inner step remains one normal physical Tool Call with existing budget, effect evidence, recovery and UNKNOWN semantics; intermediate Tool content is mechanically consumed and only one compact program result returns to the model;
- a generated `effective_capability_catalog()` that separates **installed**, **Run-admitted**, and **turn-admitted** capability truth instead of making package installation an authority grant;
- bounded task-conditioned capability discovery over already-published descriptors, with progressive `candidate -> exact inspection` disclosure. Discovery is read-only navigation: a candidate does not prove currentness, grant authority, or expand a Tool surface;
- a current-affordance projection that intersects discovered candidates with caller/owner-supplied `AVAILABLE / BLOCKED / UNKNOWN` standing and already-admitted actions. Missing standing remains `UNKNOWN`, and the existing turn Tool projector still permits only subtraction from exact admitted Tools;
- a compact capability-aware model projection that carries only identity/actionability (`capabilityId`, owner, action, standing, admission and `canInvokeNow`) by default, while exact descriptor/evidence/reason bytes remain on-demand inspection material. A preregistered currentness-dependent fresh-Agent ablation earned this split: retrieval-only did not resolve semantic-twin ambiguity, while standing + existing admission materially improved current-carrier selection in the bounded experiment;
- `HarnessAgentRun` as the supported Python handle for normal state-root → Run composition and resume, with `HarnessAgentRun.explain()` for process-local composition inspection without Provider/Runtime liveness claims;
- `HarnessAgentRunToolSurface` as an explicit application-local advanced seam for exact non-default Runtime-backed Tool surfaces; it is not a registry and does not change an admitted Run;
- advanced `build_observation_tool_surface()` composition for observation-only `search_workspace + read_workspace`: callers bind exact readable path/digest authority and may additionally bind owner/authority/version/transport evidence. Exact immutable owner publications can be projected by one bound `subjectRef` only after complete-file digest verification; search projects object routing rather than treating matched lines as semantic authority, and Harness never mints owner truth;
- durable `inspect` plus `explain` workbench projections over existing Journal/CAS state, with unavailable process-local facts left explicit rather than guessed;
- multi-attempt Mandate/Strategy admission where Harness derives remaining resource authority mechanically but does not choose the Strategy;
- caller-defined structured completion shapes, with optional Contract-bound local structural conformance verification while semantic/evidence admission remains outside Harness;
- explicit non-support for a generic opaque Provider-continuation primitive in the contracted current core; Provider-local continuation remains integration-local unless new direct pressure earns a bounded surface;
- conservative UNKNOWN handling: ambiguous Provider or Tool delivery is reconciled from durable evidence rather than blindly repeated.

Detailed API and compatibility contracts are linked below instead of reproduced here.

## What it does not do

Harness does not:

- own Host Tasks, Assignments, commitments, `TaskOutcome`, or domain completion;
- import or require `ordivon-host`;
- own Runtime Workspace/Job/Attempt truth;
- infer external effect success from local or transport success;
- choose which evidence is semantically relevant to the Agent;
- own a global capability registry, semantic capability ranker, or owner-currentness service; task-conditioned discovery only narrows already-published descriptors and never turns retrieval into a grant;
- provide a generic Memory/RAG store, semantic ranking, automatic knowledge extraction, hidden cross-Run injection, or Harness-owned procedure evaluation/promotion service;
- schedule a Mandate's next Strategy or persist a second Mandate workflow engine;
- turn Provider JSON Schema, cache locality, or Tool pruning into semantic policy;
- treat a model-correct Run conclusion as automatically authoritative outside the bounded Run.

If a new shared mechanism cannot survive deletion against Agent-owned choice, caller/domain ownership, or mature Provider/Runtime mechanics, it should remain deleted or local.

## Requirements

- Python 3.12;
- the exact Ordivon Protocol revision pinned by `pyproject.toml` and `uv.lock`;
- `uv` for repository workflows;
- Provider credentials only for the Provider profile actually used.

Repository checks use isolated Ruff rather than assuming it is installed inside the project environment:

```bash
uvx ruff==0.15.17 check src tests scripts
python scripts/check_dependencies.py
python scripts/check_docs.py
```

## Quick start

Set up and verify the checkout:

```bash
scripts/owner-environment bootstrap
scripts/owner-environment doctor
scripts/owner-environment test
rm -rf dist
uv build --wheel --out-dir dist
.venv/bin/python scripts/check_wheel.py "$(find dist -maxdepth 1 -type f -name '*.whl' -print -quit)"
```

The owner environment binds the exact development lint dependency separately from Harness runtime semantics; it does not reintroduce Host as a Harness dependency. `scripts/owner-environment cold-start` proves the default suite from an empty temporary venv.

Initialize an independent state root and inspect available capabilities:

```bash
ordivon-harness --state-root /var/lib/ordivon/harness store-init
ordivon-harness capabilities

# Progressive disclosure: retrieve a bounded candidate set without printing the full catalog.
ordivon-harness capabilities --query 'search workspace observation' \
  --term search --term workspace --limit 4

# Inspect one exact descriptor only after selection. This still grants no Run/Tool authority.
ordivon-harness capabilities --inspect \
  harness.execution.runtime-search.v1.tool.search_workspace
```

A caller then supplies an exact Run Contract:

```bash
ordivon-harness --state-root /var/lib/ordivon/harness \
  run RUN_CONTRACT.json --message 'Start the bounded Run'

ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness telemetry HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness explain HARNESS_RUN_ID
```

`capabilities` with no discovery arguments preserves the generated package projection: it reports installed built-in and specialized surfaces plus their exact source-owned digests and requirements, but it does not grant them to a Run. `--query` returns a bounded candidate projection and omits the full catalog; explicit `--term` values act as candidate-admission constraints while intent tokens contribute additional matching. `--inspect` expands one exact source-derived descriptor. Neither operation proves owner currentness or execution admission. `explain` is a durable read model: it can prove Contract/Journal/CAS facts but deliberately does not invent whether an application-owned Adapter or Runtime client is currently live.

The CLI does not invent the Objective, Context, Tool grant, Provider, budget, or completion authority. See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for Contract construction, Python examples, cognition profiles, Tool-bearing Runtime clients, and structured completion.

## Public API

Use `ordivon_harness.api` for normal applications. The recommended execution handle is `HarnessAgentRun`: the caller supplies the exact Contract, Contract-bound Adapter factory, and any Runtime execution authority; Harness mechanically reconstructs the durable composition on resume. Advanced installed-capability projection lives in `ordivon_harness.capability_catalog`; experimental task-conditioned candidate discovery, exact inspection and current-affordance compilation live in `ordivon_harness.capability_discovery`; exact cross-Run knowledge/procedure references and seed compilation live in `ordivon_harness.knowledge_topology`; bounded programmatic Tool composition/recovery lives in `ordivon_harness.tool_program*`; and the explicit non-default Tool-surface seam lives in `ordivon_harness.run_tool_surface`. None is promoted into the stable package-root facade yet. These projections/admission helpers do not grant authority or own external knowledge repositories/effects.

For broader delegated execution, the current path is:

```text
HarnessExecutionMandate
→ build_harness_strategy_selection_context()
→ Agent/application chooses HarnessAgentStrategySelection
→ compile_harness_selected_attempt()
→ immutable HarnessRunContract
→ HarnessAgentRun
```

Harness derives remaining token/wall-time consumption from prior exact attempt evidence. It does not ship a Strategy planner.

Use `ordivon_harness.core` only when an advanced integration needs the lower-level Store, Continuity, Provider, Runtime, or recovery primitives. Historical `Standalone*` names remain compatibility aliases where documented; normal applications should not hand-wire those layers.

Exact supported exports and upgrade expectations are owned by [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md), not by this summary.

## Operator interface

Operators normally need five questions:

```bash
ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness telemetry HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness recover HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness doctor
```

`telemetry` is a read-only projection over exact Harness state: it normalizes usage, budget remainder, Provider cache hit/miss counters when present, and recovery/UNKNOWN context. Cache metrics are measurement only; they never become cognition or semantic policy. `inspect` remains the exact deeper evidence escape hatch.

Recovery is evidence-driven. A dispatched operation with uncertain physical outcome is not automatically safe to repeat. `doctor` is the authority-wide history replay; normal Run reopen validates the relevant Run before new execution.

See [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for backup/restore, cancellation, concurrent worker fencing, Provider/Tool UNKNOWN, and escalation.

## Documentation map

Choose the document for the job you have:

| Need | Read |
| --- | --- |
| understand why Harness exists and where it stops | this README |
| perform a first Run | [`docs/QUICKSTART.md`](docs/QUICKSTART.md) |
| understand semantic ownership and internal state domains | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| inspect current maturity and known limits | [`docs/STATUS.md`](docs/STATUS.md) |
| look up supported API/dependency compatibility | [`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) |
| decide what a receipt or experiment actually proves | [`docs/VERIFICATION.md`](docs/VERIFICATION.md) |
| operate, recover, back up, cancel or diagnose | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| understand retention and private-content authority | [`docs/DATA_AND_PRIVACY.md`](docs/DATA_AND_PRIVACY.md) |
| understand release/deprecation rules | [`docs/RELEASES.md`](docs/RELEASES.md) |
| inspect which document owns which fact | [`docs/authority.md`](docs/authority.md) |
| inspect research derivation and historical closeouts | linked research/closeout documents and `evidence/index.json` |

Research phases remain valuable evidence, but a reader does not need to learn their numbering before understanding the current product.

## Security and data

The Run Contract privacy policy is execution authority. Default `metadata-only` continuity can preserve identities, digests, causal/effect receipts and budgets without retaining exact model or Tool content. Exact model/Tool recovery across process loss requires the corresponding private-content authority; Harness does not recover forbidden content from a hidden second store.

Tool and Provider effect fencing remains independent of content retention. A digest-only durable Provider Call can still block duplicate physical dispatch after response loss.

See [`docs/DATA_AND_PRIVACY.md`](docs/DATA_AND_PRIVACY.md) and [`SECURITY.md`](SECURITY.md).

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
