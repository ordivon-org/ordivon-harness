---
schema_version: 1
id: harness.status
title: Harness Status
type: status
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
updated: 2026-08-11
summary: Current maturity claim for Harness as a durable cognitive execution substrate, including proven cognition, continuity, execution and support boundaries.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.architecture
  - harness.compatibility
  - harness.verification
---
# Status

## Current state

Ordivon Harness is an independent caller-neutral **durable cognitive execution substrate** for bounded Agent Runs. The current writer is the Harness SQLite Journal/CAS; the default and only CLI authority is `independent-harness-run`.

## Operational

- Agent-owned multi-attempt Strategy admission over caller-delegated `HarnessExecutionMandate`: exact prior `CompiledHarnessAttempt` + terminal Receipt + optional retained `IndependentCompletionProposal` is validated as one contiguous lineage; independent caller/domain verification may enter as digest-bound immutable `HarnessStrategyEvidence`; `HarnessMandateConsumption` and remaining economic authority are derived mechanically; `HarnessAgentStrategySelection` binds the Agent's Profile/budget/adopted-evidence choice to the exact selection-context digest; and `compile_harness_selected_attempt()` resolves that choice into one immutable `HarnessRunContract` without a planner, semantic verifier or second Mandate store. Cross-attempt model-content retention requires explicit Mandate privacy authority while legacy/default Mandates remain metadata-only and preserve their canonical serialized identity;
- RSI P2 source-improvement acceptance separates source generation, physical materialization, independent candidate evaluation and promotion decision: a real Agent consumed baseline failure evidence plus two rejected prior source proposals, authored exact source replacements, and independently evaluated A/C authority defects changed baseline-red → candidate-green without Human byte repair. Repeated malformed unified-diff attempts established exact unique `oldText → newText` replacement as the lower-friction experimental action encoding; this evidence does not add a Harness self-modification controller or automatic promotion service;
- caller-authored JSON object keys at Mandate and structured-completion projection boundaries now fail closed unless already strings; Harness no longer silently changes invalid authority bytes through `str(key)` coercion, while valid all-string-key legacy objects retain their canonical representation;
- RSI P3 provides a bounded R10 improvement-of-improvement acceptance: the promoted P2 system let an Agent select the next source target and author its own falsifier from durable P2 evidence/current source, rejected a malformed falsifier before treating it as baseline evidence, projected obsolete failed-action/diagnostic bytes out of the next Working View while retaining their exact history by digest, reused Runtime-native exact replacement for materialization, and retained independent evaluator/promotion authorities. The accepted Agent-selected target hardens all Mandate-layer digest authority to canonical lowercase `sha256:<64 hex>` form;
- RSI P4 provides a bounded R11 capability-composition/no-change acceptance: without caller-preselected source slices or evaluator gates, the Agent selected 203 admitted repository observations and read 50/51 tracked source files exactly; two finalized target hypotheses were denied because their falsifiers were not causal baseline-red; after the experiment protocol gained a bounded `abstain` outcome, the Agent immediately chose no source mutation with an explicit uncertainty boundary. No source generator/materializer/candidate evaluator/promotion/Git source authority was invoked because no target earned mutation authority;
- RSI P5 provides a bounded R12 evidence-driven high-information discovery acceptance: a one-observation negative control first proved that minimizing observations alone rewards ignorance; the accepted run then consumed one exact independent Host/World failure observation and let the Agent choose all repository observations, using 8 rather than P4's 203 (25.375× fewer) while performing six source/reference investigations. It localized the no-Tool failure near a deliberate Agent-bridge guard but did not prove a reachable causal source defect, so it abstained without mutation. Full repository/action history remained durable while the model-visible Working View used a compact addressability map, one current exact observation and abstract failed-action evidence;
- RSI P6 provides bounded R13 high-budget causal-utilization evidence: total DeepSeek tokens are deliberately not minimized. A six-trajectory replay/incremental/batch × two-workload matrix measures repeated versus new evidence exposure and independently re-grounds every terminal claim. Full replay accumulated 966,576 repeated evidence bytes across the two workloads; incremental Working Views nearly eliminated repeated evidence but one compact state merged adjacent Provider mechanisms into a false target; batch eliminated repeated evidence yet produced false causal finalizations on both workloads. Current law is therefore two-stage: compact Agent-authored Working Views guide high-budget research, while terminal causal claims remain proposals until an independent exact source/evidence re-ground validates locality before mutation authority;
- P6 also causally closes the prior no-Tool control-routing failure without weakening the strict bridge: malformed `submit_run_conclusion` control and one-or-more Provider actions normalized as `unavailable_tool` on an empty Tool surface are corrected before Runtime Tool identities/observations exist; mixed actions are not silently swallowed, real Tool-bearing surfaces retain existing semantics, and conclusion/Tool correction budgets bound repeated invalid control intent;
- RSI P7 provides bounded R14 reversible-epistemic-state evidence without changing product source: a 2×3 high-budget matrix compared free compact state with an experiment-only claim/evidence/discriminator ledger on resolved Provider concurrency, resolved no-Tool control and a dispatch-fence locality trap. Compactness alone did not guarantee causal fidelity; state/action admission had to be separated; a persistent root Objective had to prevent true subclaims from masquerading as workload completion; and causal finalize had to require exact evidence the Agent actually observed before independent re-grounding. Free state was faster on the simple negative control, so the ledger is not promoted into a product API. Existing Objective, WorkingSet/WorkingView, non-authoritative deliberation, CompletionProposal evidence/unresolved-unknown and StrategyEvidence boundaries already cover the needed product laws;
- independent P5 release acceptance separately hardened Provider outcome concurrency: same-call `DISPATCHING` and live foreign `CLAIMED` contenders are rejected before taking the generic Run lease, while the exact physical dispatch owner may wait through bounded short lease contention to commit its known Provider result only while the same durable Provider Call remains current. This repair was forced by deterministic/stress evidence after the P5 discovery Agent abstained and is not attributed to that Agent;
- `HarnessRunContract` with exact execution-bound authority;
- SQLite Store creation, reopen, Doctor, lease/revision fencing, backup and restore;
- durable Provider Call continuity and response-loss recovery;
- durable Tool-step intents/fences/receipts and Runtime reconciliation;
- Agent loop budgets, pause/resume and no-progress handling, with separate Tool-call
  and caller/domain conclusion-correction counters/budgets;
- model-visible WorkingView projection separated from canonical Run history;
- Agent-owned durable WorkingSet transitions with exact replay/concurrency fencing;
- explicit discovery/materialization versus Agent selection boundary;
- attempt-local Provider/Tool cognition that survives clean/fault recovery but expires on successor cognition attempts;
- caller-owned interaction cognition after `needs_input`, with role/provenance admission and exact recovery;
- Agent-owned exact caller-ingress promotion into durable cognition without generic Memory extraction;
- bounded historical committed-cognition recall and exact-pin re-selection;
- current WorkingSet source addressability for lawful retain/drop/correction decisions;
- experimental `StandaloneHarnessRunner` cognition composition with exact caller-authored initial seed, automatic WorkingView/transition/promotion/history wiring and partial-bootstrap replay recovery;
- provider-neutral per-turn `AgentTurnCapabilities` bound into each exact `AgentTurnRequest`: the Loop derives current Harness-native action authority, DeepSeek renders/parses only that request-bound surface, capability changes alter dispatch/Provider request identity, and caller promotion disappears when no exact promotable caller ref remains;
- R2 internal recomposition now extracts `AgentTurnProjector` for exact read-side turn construction, `CognitionAdmissionKernel` for source-current durable cognition admission, and `ProviderCallLifecycle` for optional durable Provider identity/begin/admit/fail/retry/complete bridge addressing; retry/budget/stop/semantic policy remains in the sequential Loop and Continuity's independent Journal/CAS verifier remains unchanged;
- the complete R2 lineage reduces `_run()` from 2,083 to 1,876 lines on the no-progress-ownership lineage (the Provider port removes 98 lines from the current no-progress/two-kernel coordinator, 1,974 → 1,876) without adding a persistence schema or public service; Tool-effect/progress extraction remains deferred until real friction proves another boundary stronger than file-size pressure;
- DeepSeek mixed Tool+conclusion turns are model-correctable before physical Tool dispatch: neither the ordinary Tool actions nor the simultaneous conclusion are admitted from the ambiguous turn;
- Harness-owned `no_progress` stops carry execution reason in stop detail/Trace and do not synthesize an Agent conclusion, preserving structured-completion shape;
- no-Tool DeepSeek CLI profile;
- caller-supplied Runtime client Python API for Tool-bearing Runs;
- independent Run Receipt, CompletionProposal and recovery evidence;
- caller-defined `structured-result-v1` completion schemas for DeepSeek, with exact completion-Contract binding and generic result decoding;
- repository-repair read/edit bridge test surfaces;
- Host-free external-executor adapter.

## Removed in H3

The old Host-backed Runner, TaskContract/Assignment persistence, Host compatibility package, Host dependency/extra, `host` CLI namespace, cutover/rollback machinery, and Host-coupled Codex/Hermes execution drivers are not supported current paths and have no compatibility aliases.

## Known limits

- primary CLI does not construct Tool-bearing Runtime clients;
- Mandate support can now construct exact multi-attempt selection authority and admit an Agent-authored next Strategy, but Harness still does not schedule the next attempt, discover/rank Profiles, persist Mandate state, or ship a built-in StrategyPolicy/cross-attempt controller;
- P2 proves one bounded self-modification/promotion composition, P3 proves one bounded improvement of that composition, P4 proves Agent-owned discovery-capability/no-change semantics, and P5 proves one bounded evidence-driven high-information discovery composition; none is a permanent autonomous RSI controller. P5 removes blind near-complete source coverage from the accepted branch but no causal source target survived, so source generator/materializer/candidate-evaluator/promotion branches were intentionally not exercised; cycle triggering and canonical documentation/evidence promotion remain external, and all mutation authorities remain separate;
- P3 closes the P2 delegated-digest falsifier by requiring canonical lowercase `sha256:<64 hex>` values at the Mandate `_digest()` boundary. The experiment's one-runner target/edit/decision apparatus and failed-action Working-View projection remain research scaffolding, not supported product APIs or a generic self-modification service;
- P4's discovery/abstention apparatus is also research scaffolding rather than a supported Harness policy. Its main unresolved problem is search efficiency: the Agent consumed 203 observations and near-complete source coverage before lawful abstention became available. The result validates authority semantics and anti-defect-hunting pressure, not efficient autonomous defect discovery or a claim that no further defects exist;
- P5 closes the specific P4 observation-traversal inefficiency in one bounded workload (203 → 8 observations) but not computational efficiency: the accepted path still used 12 fresh Provider calls and 239,953 total tokens. The compact repository-map/`decisionJson`/discovery runner remain experiment scaffolding, and the separate no-Tool conclusion-correction failure remains open because P5 did not establish its reachable causal source path;
- P5's Provider-outcome lease wait is deliberately narrow: at most one second, only after physical dispatch, only while the exact retained Provider Call remains current, and exhaustion becomes explicit recovery. It is not a generic lease retry framework and does not resolve the separate no-Tool conclusion-correction task;
- there is intentionally no Host-specific cognition bridge: the tested Host cognition slices use generic `structured-result-v1` completion and Host-owned semantic admission;
- CompletionProposal is not caller/domain completion authority;
- `candidate_completed` is bounded-Run terminality, not a claim that all world uncertainty is resolved; CompletionProposal v2 carries `unresolvedUnknowns`, while v1 remains readable with an empty unknown set;
- structured completion constrains Provider output shape but does not make Harness a JSON-Schema or domain verifier; callers must still decode and semantically admit the result under their own authority;
- Provider/Tool UNKNOWN may require external reconciliation;
- public API and owner-local schemas remain pre-1.0;
- historical receipts prove the implementations they bind, not the current source unless indexed as verified;
- R3 introduces `HarnessAgentRun` as the supported state-root based Python execution handle. It hides SQLite Store/Continuity/Bridge/Runner wiring, rebuilds exact Snapshot-bound Provider source on resume, reconstructs budget from the Contract, and calls the caller-selected Adapter factory only after structural composition is admitted; the primary no-Tool CLI now uses this surface for `run`/`resume`;
- R3.2 makes supported composition fail before durable state: cognition privacy/history mismatch and exact Runtime-binding mismatch reject before Adapter construction, while Adapter/model/structured-completion mismatch reject after the caller-owned factory but before `harness.run-created`; Provider/Runtime liveness is deliberately not guessed by this preflight;
- caller-facing `HarnessCognitionProfile`, `HarnessCognitionSeed`, `HarnessCognitionSeedSource` and `HarnessCognitionSource` are now recommended API values for exact Agent-owned cognition bootstrap; the old `Standalone*` names remain compatibility aliases, while `AgentTurnRequest.tools + capabilities` remain the exact per-turn action authority and no global Capability Service is introduced;
- R3.1 is additive rather than a breaking facade cleanup: existing low-level recommended exports remain available while CLI/Python adoption moves to `HarnessAgentRun`; removing `StandaloneHarnessRunner`, concrete SQLite composition objects or other advanced exports is a later evidence-gated decision, not part of this slice;
- there is no generic Memory/RAG/ranking/summarization layer, cross-Run cognition orchestrator, semantic supersession graph or automatic relevance policy;
- large-WorkingSet discovery/inspection strategy, initial cognition bootstrap and cross-Run cognition reuse remain open Agent-side/system-boundary questions rather than solved Harness policy.
- H0 independently reproduced Tool-first/later-correct-reasoning ordering pressure and H1 validated an advanced/internal generic `DeliberationThenToolRunner`. H2 closes the validated internal composition lifecycle with one aggregate RunBudget, one cancellation authority and one absolute composition deadline across deliberation and the later caller-owned Tool loop; phase-A `AgentTurnAdapterError` preserves known failure taxonomy and `PRE_DISPATCH_SAFE` no longer becomes false Provider uncertainty. P1 additionally proves that `DomainToolLoopPlan.assignment_deadline_ms` is authority for the whole lifecycle-bound composition: an already-expired Assignment now blocks phase-A Provider dispatch, and remaining wall-clock Assignment authority is projected into the shared monotonic composition deadline without mixing clock domains. The lifecycle-bound path remains advanced/internal rather than recommended `ordivon_harness.api` because no fresh independent domain consumer has yet forced promotion.

## Operator check

```bash
ordivon-harness --state-root /var/lib/ordivon/harness status HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness inspect HARNESS_RUN_ID
ordivon-harness --state-root /var/lib/ordivon/harness doctor
```

## Current DeepSeek request-locality acceptance

- current DeepSeek projection preserves stable protocol/history before one exact trailing Harness turn-control record; Provider Tool schemas no longer encode changing caller-index enums as if schema shape were authority;
- actual Harness live A/B on ~32K-token prompts changed deterministic common request-body prefix from 642 bytes to ~139.5–139.8 KB; the canonical baseline independently reproduced 0/32,089 second-turn cache hits, while the candidate realized 26,240/32,197 to 32,000/32,113 second-turn hits. Cache realization is best-effort and is not a fixed release threshold;
- all exact per-turn authority remains present and caller-side admission is unchanged: static Provider schema is only an affordance, while exact `caller_ingress_refs`, WorkingSet provenance and Run Store checks remain authoritative;
- a separate release-found `CLAIMED → DISPATCHING` race is also closed: deterministic claim-owner tests pass, the durable failure-capture stress changed from failure at iteration 7 to 500/500, official Standalone/R3 repetitions pass 200/200 each, and current source acceptance passes 356 tests with 3 skipped plus H2 13/13, Host-free wheel verification and final 100/100 Provider concurrency repetition.

## External Harness Cross-Validation X0/X1

- X0 request-locality observatory is experimentally accepted but not productized: it mechanically distinguished the historical DeepSeek leading dynamic system/Tool divergence from the current stable-prefix + trailing turn-control projection and correctly isolated synthetic history/Tool/settings divergence, but a second real Provider turn-wire projection is still required before any provider-neutral locality receipt is justified;
- X1 shows no universal Tool-surface winner. All main static/deferred/dynamic-K4/generic selection matrices were semantically correct at 5, 20 and 100 Tools. Static 100 remained 12/12 with 140,800 cache-hit and 14,255 cache-miss prompt tokens; deferred 100 remained 12/12 with a much smaller 21,058-token visible prompt but 24 Provider calls and 12,226 miss tokens; total prompt, recompute and roundtrip are therefore separate measurements;
- caller-side over-pruning is a proven failure class: dynamic K=1 scored 6/8 at 20 Tools and 10/12 at 100 Tools, with every wrong selection occurring exactly when the correct target was hidden. K=4 retained those candidates and passed. A projection that can eliminate the correct candidate without Agent-owned recovery is semantic policy, not mechanical optimization;
- X1b typed, deferred-typed and generic argument surfaces all achieved exact 8/8 Tool+argument correctness. Typed and generic nested-object/array stress each passed 40/40. This is evidence against treating function-specific Provider JSON Schema as a universal correctness invariant, not evidence that generic invocation should replace typed tools;
- product-boundary audit finds no new core primitive: current `AgentToolSurface`/`AgentTurnProjector` already form a deterministic read-side surface over owned authority, and continuity remains the independent exact-request verifier. X0/X1 experimental runners are not part of the product.
## X2 second-Provider continuation acceptance

- source revision `9087278e69e20cd501310f4e8719b2dcd5811f05` adds one provider-neutral `ProviderToolContinuation` primitive and no built-in Gemini Adapter, persistence schema, scheduler, map/ranker, cache optimizer or retry service;
- a native Gemini 3.6 falsifier accepted an exact function-call continuation and rejected the same next request when only the Provider signature was removed (`400 INVALID_ARGUMENT`), proving that semantic Tool-call reconstruction plus raw-response digest alone was insufficient for this Provider protocol;
- live crash/reopen acceptance completed a real Gemini Tool call, durably executed the Runtime Tool, lost the process, reopened a fresh Store/Adapter and received HTTP 200 on the next Gemini request with the exact continuation digest; the opaque signature remained outside `AgentTurnRequest.messages`, Runtime Tool redispatch count after reopen was zero, and final conclusion was `LIVE_CONTINUATION_OK`;
- ingress and lineage attacks fail closed: callers cannot inject reserved continuation metadata through initial/resume messages, wrong Adapter/turn authority stops before Runtime dispatch, and private-content continuation tampering is rejected against completed Provider evidence before Adapter invocation;
- existing privacy remains authoritative: metadata-only Provider completion retains no opaque continuation object, while exact cross-process continuation recovery requires the same bounded private-content authority already needed for Tool/model transcript recovery;
- the four other frontiers intentionally closed without new product mechanisms: current docs routed blind callers through `HarnessAgentRun` 4/4, checkpoint+idempotency can match exact lifecycle when the external world supplies strong idempotency plus result lookup, AST repo maps did not beat Agent-native navigation under the bounded source-localization controls, and blind UNKNOWN diagnosis correctly followed `inspect → recover → reconcile` without Provider redispatch.
- current source acceptance passes Ruff plus 363 deterministic tests with 3 skipped, H2 remains 13/13, the Host-free `0.6.0` wheel verifies 14 CLI commands, and the Standalone/R3 Provider-concurrency pair passes 100/100 iterations (200/200 selected tests).
