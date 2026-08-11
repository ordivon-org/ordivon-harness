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

RSI P2 also validated a source-improvement composition without adding a Harness self-modification controller: one Agent authored a candidate source change from exact baseline failures, Runtime materialized only exact source replacements, an independent evaluator compared baseline and candidate, and a separate Agent decided promotion from the resulting evidence. Two earlier Agent-authored unified diffs were rejected unchanged as mechanically corrupt; the successful attempt represented semantic edits as exact `oldText → newText` replacements that fail closed unless the old bytes occur exactly once. This is experimental evidence about agent-first action encoding and authority separation, not a new recommended Harness API or an automatic source-promotion service.

RSI P3 then exercised the promoted P2 system against the improvement loop itself. Target selection and the falsifier became Agent-owned rather than caller-preselected; malformed falsifiers are statically admitted before baseline evaluation; exact failed-action history remains durable while stale failed action/diagnostic bytes can be omitted from the next model Working View; and source materialization reuses Runtime's native exact replacement authority instead of a custom experiment-local materializer. The accepted P3 Agent independently selected the remaining delegated-digest authority gap, authored a baseline-red falsifier and one exact source edit, while an independent evaluator and separate promotion-decision Agent retained the P2 authority split. This is a bounded R10 result: it shows that evidence from one improvement cycle can simplify and strengthen the next cycle, but target discovery, evaluator configuration and canonical promotion triggering are still external rather than an autonomous RSI controller.

RSI P4 moves the next boundary from target choice to improvement-cycle capability composition. The Agent was not given preselected source slices or evaluator gates: it selected 203 admitted repository observations, including exact source reads, searches, tests and bounded probes. Two apparently plausible target finalizations were denied because their own falsifiers exited zero, so no source authority was earned. The experiment then exposed a protocol defect in the improvement mechanism itself: an `observe | finalize` contract could not represent a justified no-change result and therefore created pressure to keep hunting for a defect. After adding an experiment-only bounded `abstain` outcome, the Agent immediately terminated at round 204 with no target and an explicit uncertainty boundary. P4 therefore records a bounded R11 capability-composition/no-change result: **source mutation requires causal baseline-red; abstention requires exact provenance and bounded uncertainty, not proof that the codebase is globally correct.** No source generator, materializer, candidate evaluator, promotion decision or Git source promotion was invoked because no target survived admission, and the abstention runner remains research scaffolding rather than product API.

RSI P5 tests the efficiency failure left by P4. A one-observation negative control showed that simply rewarding fewer observations degenerates into ignorance: the Agent can look only at a repository map and abstain. The accepted P5 run instead began from an exact independent Host/World failure observation and a mechanical repository map, then let the Agent choose every source/reference observation. It used 8 admitted observations rather than P4's 203 (25.375× fewer), including six real source/reference investigations, and narrowed the external no-Tool failure to a deliberate `SQLiteHarnessAgentBridge` guard without pretending that the guard itself proved a defect. Because no reachable invocation path, failing unittest or causal baseline-red was established, it lawfully abstained. P5 therefore records a bounded R12 **evidence-driven high-information discovery** result. It also reuses the existing history/Working-View law: the full AST index and exact rejected actions remain durable while the model sees a compact addressability map, one current exact observation and abstract failed-action evidence. This is not yet computationally efficient—the accepted 12 decision calls consumed 239,953 total tokens—and the one-off discovery runner/`decisionJson` action envelope remain research scaffolding rather than supported Harness APIs.

RSI P6 changes the optimization target from token minimization to **high-budget causal utilization**. DeepSeek budgets remain deliberately large; the experiment measures whether prompt bytes carry new/discriminating evidence or merely replay settled material. Across two workloads and three discovery protocols, incremental Working Views reduced repeated evidence almost to zero while full replay exposed 966,576 repeated evidence bytes across the pair. But compression alone is not authority: incremental and batch trajectories also produced false causal finalizations by merging adjacent mechanisms or selecting the wrong source locality. P6 therefore records bounded R13 evidence for a two-stage law: keep exact history durable while the Agent uses a compact, revisable Working View for high-budget research; then independently re-ground every terminal causal claim against exact source/evidence before it can authorize mutation. No generic Memory/RAG or planner is added. The experiments also causally closed the previously separate no-Tool control failure: malformed Harness conclusion control and Provider actions that never received Runtime Tool authority are corrected before they can create Runtime Tool identities/observations, while the no-Tool bridge itself remains fail-closed.

RSI P7 attacks the next problem: **causal fidelity of the compact world model itself**. A high-budget 2×3 experiment compared free compact state with an experiment-only reversible claim/evidence/discriminator ledger on resolved Provider concurrency, resolved no-Tool control and an attractive dispatch-fence locality trap. P7 did not find a universal winning representation: free state solved the simple negative control faster, while ledger state was more conservative on adjacent-mechanism workloads. The stable result is instead an authority composition. Exact evidence stays outside the Working View and must be rehydratable by bound address/digest; cognition-state admission is distinct from action admission; the root Objective cannot be silently replaced by an easy supported subclaim; and a causal terminal claim needs evidence the Agent actually observed before independent re-grounding can admit it. Correct prose, a hidden oracle and an evaluator verdict cannot manufacture missing epistemic authority. P7 records bounded R14 evidence for these laws and deliberately does **not** add a Causal Ledger API, Memory/RAG subsystem or evaluator service: current Objective, WorkingSet/WorkingView, non-authoritative deliberation, CompletionProposal evidence and unresolved-unknown primitives already cover the required product boundary.

P5 closeout then found a **separate** pre-existing Provider concurrency defect during independent release acceptance; this was not retroactively attributed to the discovery Agent. Under contention, one execution could own the only physical Provider dispatch while a non-dispatching contender briefly took the generic Run lease; the physical winner could then raise `HarnessLeaseHeld` before recording its already-known result, leaving the durable Provider Call at `DISPATCHING`. Current Provider continuity now rejects same-call `DISPATCHING`/live-foreign-`CLAIMED` replays before they take the Run lease, and the exact physical outcome owner uses a bounded one-second mechanical wait for short lease contention while requiring the same durable Provider Call record to remain current. Supersession still fails closed and wait exhaustion becomes explicit recovery. Deterministic regressions, 100/100 official Standalone/R3 concurrency repetitions, 29 focused tests and the 344-test full source gate validate this narrow authority repair.

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

## Provider request locality

DeepSeek request projection now treats cache locality as a physical Adapter concern rather than a semantic reason to shrink Agent reasoning. Stable Provider protocol, retained model-visible history and stable Tool shapes precede one exact Harness-authored trailing `ordivon_harness_turn_control` record containing per-turn budget, caller-ingress and WorkingSet identities. Exact caller-side Run Store admission still decides whether a proposed cognition action is legal; Provider schemas are model affordances, not capability authority.

Acceptance deliberately separates deterministic Harness locality from best-effort Provider caching. On independent ~32K-token live requests, the prior projection diverged after 642 request-body bytes and repeatedly received zero second-turn cache-hit tokens. The current projection preserves about 140 KB of common request bytes; DeepSeek then realized 81.5%–99.65% second-turn prompt-cache hits across independent runs. No fixed cache-hit percentage is a Harness guarantee, and no reduction of high-value model token budgets is claimed.

## External Harness cross-validation

The X0/X1 cross-validation series treats external systems as falsifiers rather than feature checklists. Across OpenAI, OpenHands, Anthropic, Aider, mini-SWE-agent, DeepSeek and cache-aware serving systems, the stable convergence is at the boundary level: durable authority is separate from model-visible projection; request/cache observability is separate from optimization policy; and a Tool surface is an affordance over already-owned authority rather than the authority itself.

X0 therefore remains a mechanical experiment rather than a core optimizer. It can report exact Provider-request digests, changed strata, message-prefix divergence and Tool-surface changes without saying which layout is better. It correctly distinguishes the historical DeepSeek projection that rewrote the leading system/Tool prefix from the current trailing-control projection, but Harness currently has only one real Agent-turn Provider wire Adapter, so no provider-neutral request-locality API is claimed yet.

X1 similarly rejects one universal Tool-surface policy. In controlled 5/20/100-Tool experiments, static full surfaces, Agent-owned deferred discovery, caller-preselected dynamic top-k and a simple generic catalog could all be correct. A 100-Tool stable static surface remained 12/12 correct and most repeated prompt tokens were Provider cache hits; deferred discovery reduced visible context but doubled Provider roundtrips. The hard failure appeared when caller-side dynamic pruning became too narrow: K=1 hid the correct Swift/Rust operations and forced wrong selections, while K=4 preserved Agent choice and remained correct. Surface pruning that can remove the correct candidate without an Agent-owned recovery path is therefore semantic policy, not a mechanical efficiency optimization.

A second argument-affordance experiment also failed to justify a mandatory representation. Typed function-specific schemas, deferred typed discovery and a text catalog plus one generic `arguments_json` invoke all produced exact Tool+argument results on the controlled cases; typed and generic forms each survived 40/40 repeated nested-object/array stress. This does not make generic invocation a production law. It means only that typed Provider schemas have not earned status as a universal correctness invariant from these experiments. Exact caller admission remains the authority in every surface.
## Provider protocol continuation

A Provider may require exact opaque protocol bytes from an earlier Tool turn in a later request even when those bytes are not Agent cognition. `ProviderToolContinuation` is the provider-neutral carrier for that case: an Adapter may attach one exact continuation to a Tool-bearing `AgentTurnResult`, Harness binds it to the Adapter/source turn/model call, persists it only under the Run's existing content-retention authority, removes it from model-visible messages, and reprojects it separately on the next `AgentTurnRequest`. Continuity independently verifies retained continuation lineage before Provider dispatch. Caller-supplied initial/resume messages cannot create this authority.

X2 used a temporary native Gemini 3.6 Adapter only as acceptance scaffolding. A real function-call signature survived Provider call → Runtime Tool effect → process loss → fresh Store/Adapter reopen → second Provider call, while the second request contained the exact continuation outside Agent messages and the already-completed Runtime effect was not redispatched. The Gemini Adapter itself was not added to the product.
