---
schema_version: 1
id: harness.architecture
title: Ordivon Harness architecture
type: architecture
profile: engineering
lifecycle: active
source_role: canonical
visibility: public
owners:
  - ordivon-harness
audience:
  - builder
  - operator
  - agent
updated: 2026-08-19
summary: Canonical world model for Harness as the durable cognitive execution substrate of an Agent, including cognition, control, effects, continuity and caller/Runtime/Host boundaries.
evidence_status: verified
readiness: READY
applies_to:
  - ordivon-harness
related:
  - harness.start
  - harness.authority
---
# Ordivon Harness Architecture

## Purpose

Ordivon Harness is the **durable cognitive execution substrate of an Agent** and the independent authority for one bounded Agent Run. A caller supplies immutable semantic/execution authority in a `HarnessRunContract`; the Agent owns semantic reasoning, cognition selection and action choice; Harness turns those choices into exact, provenance-bound, recoverable state transitions and effect intents.

Harness does not build the Agent's world model for it. It preserves the structural truth required for an Agent to build, revise, inspect and act from its own world model without conflating history, cognition, observation, control or physical effects.

## Harness world model

The current architecture is not a `messages[]` transcript machine. It has six distinct state domains:

| Domain | Question it answers | Current owner/mechanism |
| --- | --- | --- |
| **Canonical History** | What actually happened? | append-only Harness Journal/CAS, Provider/Tool/WorkingSet events and receipts |
| **Durable Cognition** | What has the Agent explicitly selected as current long-lived cognition? | committed `HarnessWorkingSetSpec` over exact `HarnessWorkingViewSource` pins |
| **Interaction Cognition** | What is the caller currently saying to the Agent? | exact plain caller ingress after the latest `needs_input` boundary |
| **Attempt Cognition** | What has the Agent just observed during this cognition attempt? | Provider-authored Tool-call/result exchange reconstructed from durable evidence |
| **Execution Control** | What may the Agent lawfully do now, and which authority objects may it address? | admitted Tools/cognition controls, budgets, caller provenance and current WorkingSet addressability |
| **Effects** | What action was admitted and what physically happened? | durable Tool/Provider intent/fence/receipt chains plus Runtime/external authority |

These domains compose into one effective Agent turn without collapsing into one authority:

```text
                         Canonical History
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
   Durable Cognition   Interaction Cognition   Attempt Cognition
      WorkingSet            caller ingress        Tool exchange
            └──────────────────┬──────────────────┘
                               ▼
                      Effective Model View
                               │
                     + Execution Control
                               │
                               ▼
                             Agent
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
           cognition       external       conclusion
           transition       action
                 │             │
                 ▼             ▼
            WorkingSet      Runtime / World
                 └──────┬──────┘
                        ▼
                   new History
```

The core inequalities are architectural laws, not documentation slogans:

```text
History ≠ Cognition
Storage ≠ Selection
Observation ≠ Retention
Caller Input ≠ Durable Cognition
Attempt Change ≠ Cognition Change
Cognition Change ≠ Progress
Progress ≠ External Effect
Tool Intent ≠ Physical Effect
Physical Effect ≠ Semantic Success
Source Identity ≠ Source Truth
Provenance ≠ Semantic Validity
Exact Replay ≠ Redispatch
```

Harness therefore owns **structural cognition and execution truth** while the Agent owns **semantic cognition and choice**. Harness may validate, materialize, persist, recover, fence and make authority addressable; it must not rank relevance, choose memories, infer semantic correction, silently summarize sources or conclude world truth on the Agent's behalf.

### Cognition sovereignty laws

1. **History is not cognition.** Past Run events remain durable without being replayed automatically into the model view.
2. **Observation is not retention.** Tool results, caller messages and discovered/materialized sources do not become durable cognition merely because they exist or were observed.
3. **Durable cognition selection belongs to the Agent.** A source becomes current durable cognition only through an Agent-owned WorkingSet selection/promotion path.
4. **Semantic meaning belongs to the Agent; structural truth belongs to Harness.** Harness proves exact identity/provenance/transitions, not relevance, truth or semantic supersession.
5. **Authority required for lawful Agent choice must be visible and addressable.** Hidden current authority that an action must reference is an Agent-usability defect; execution control therefore exposes currently promotable caller indexes, admitted capabilities and exact current WorkingSet identities when those actions are granted.
6. **Cognition, interaction, control and effects remain distinct state domains.** They may be composed for one turn but cannot be treated as interchangeable facts.
7. **Recovery restores proven state, never invented continuity.** Lost Provider/Runtime responses are replayed/reconciled from durable authority; uncertain effects are not blindly redispatched.
8. **New Harness mechanisms require an otherwise inexpressible Agent state transition.** Generic Memory, RAG, ranking, summarization or supersession subsystems are not architectural defaults.

## Ownership

```text
caller / domain / optional Host
        │
        │ HarnessRunContract
        ▼
┌────────────────────────────┐
│ Ordivon Harness            │
│                            │
│ independent Journal / CAS  │
│ Provider Call continuity   │
│ model ↔ Tool loop          │
│ Run budgets                │
│ pause / resume / recovery  │
│ Trace / Run Receipt        │
│ CompletionProposal         │
└─────────────┬──────────────┘
              │ Tool-bearing Runs only
              ▼
       HarnessRuntimeClient
              │
              ▼
           Runtime
```

Harness does not own caller Task state, domain commitments, final acceptance, or Runtime Workspace/Job truth. Runtime does not know the Harness state machine. Host is an optional caller rather than a persistence prerequisite.

> **Run terminality is not epistemic closure.** `candidate_completed` means the bounded Run formed a candidate result; it may retain explicit unresolved unknowns for caller/domain judgment.

## Execution Mandate and strategy

The caller does not have to prescribe every execution step. `HarnessExecutionMandate` is a higher-level delegation envelope over one or more possible Run attempts:

```text
caller / domain / optional Host
        │
        │ HarnessExecutionMandate
        │ + currently available Profiles
        │ + exact prior CompiledAttempt / terminal Receipt / optional CompletionProposal
        │ + exact caller/domain StrategyEvidence
        ▼
HarnessStrategySelectionContext
        │ mechanically derives attempt index + remaining envelope
        │ no ranking / no Strategy choice
        ▼
      Agent
        │ HarnessAgentStrategySelection
        │ exact context digest + chosen Profile/budget/options/evidence
        ▼
compile_harness_selected_attempt()
        │ mechanically admits the choice
        ▼
   HarnessRunContract
   immutable attempt authority
        │
        ▼
    Run → Receipt
        │
        └── exact attempt evidence may enter the next selection context
```

The distinction is deliberate: **Mandate says what has been delegated; Strategy says how the Agent currently chooses to act; Run Contract freezes one admitted attempt; Receipt says what physically happened; CompletionProposal says what the prior Agent proposed; independent StrategyEvidence says what another caller/domain authority supplied for the next Strategy decision.** `maxModelCalls` and `maxToolCalls` remain valid per-attempt runaway/fencing parameters, while aggregate economic authority remains the Mandate's `maxTotalTokens` / `maxWallTimeMs`. For a later attempt, Harness requires exact `HarnessPriorAttemptEvidence`: the prior immutable `CompiledHarnessAttempt` proves its Mandate/System-Manifest/Contract authority and the paired terminal Receipt proves resource consumption. When the prior Run completed and privacy authority allowed model content retention, that evidence may also carry the exact `IndependentCompletionProposal`, bound back to the same Run/Contract/Receipt/Trace. Caller/domain verification is a separate authority: `HarnessStrategyEvidence` freezes an exact digest-bound JSON object and makes it addressable to the Agent without making Harness its semantic verifier. `derive_harness_mandate_consumption()` reconstructs completed-attempt count and aggregate resource use mechanically; a same-named but changed Mandate cannot inherit old receipts because the prior compiled attempt must bind the exact current Mandate digest.

Current Mandate support remains intentionally pure and stateless: Harness does not ship a built-in StrategyPolicy, Mandate scheduler, semantic verifier, or second durable Mandate database. `build_harness_strategy_selection_context()` accepts the exact Mandate, currently available Profiles, a contiguous lineage of exact prior-attempt evidence, and optional exact `HarnessStrategyEvidence`; it derives consumption and remaining authority mechanically and exposes that complete selection surface to the Agent. The Agent authors one `HarnessAgentStrategySelection` bound to the exact context digest; Harness only admits the selected Profile/budget/adopted evidence and freezes the next attempt. The Mandate may explicitly carry `HarnessPrivacyPolicy` when cross-attempt model-content retention is required; absence preserves the metadata-only legacy/default authority and serialized identity. Triggering another attempt, discovering candidate Profiles, producing independent verification, and deciding semantic Strategy remain outside Harness policy.

## Self-change evidence and promotion authority

RSI P2 validated one bounded source-improvement loop without moving source-generation, evaluation, or promotion policy into Harness:

```text
exact baseline failure evidence
        ↓
source-change Agent
        │ semantic candidate edits
        ▼
Runtime materialization
        │ exact source bytes only
        ▼
independent evaluator
        │ baseline ↔ candidate evidence
        ▼
independent promotion decision
        │ promote / revise / reject
        ▼
guarded canonical Git promotion
```

The authorities remain deliberately separate. The source-change Agent may choose what to alter and author the replacement bytes; it does not certify that its own candidate is better. Runtime proves only whether the requested exact source edit can be materialized and executed. The evaluator owns the comparison evidence, not the candidate. Promotion is a separate semantic decision over exact proposal, diff and evaluation evidence, and canonical Git movement remains guarded by repository ancestry/concurrency checks.

The experiment also exposed an action-encoding boundary. Two independent Agent attempts selected the same correct source-level law but emitted malformed unified diffs. Those diffs were rejected unchanged; no human repaired their hunk arithmetic. A later attempt consumed those failures and expressed the same semantic change as exact `oldText → newText` replacements. Runtime admitted each replacement only when the old bytes occurred exactly once. This preserves Agent authorship while moving line-number/hunk-count mechanics out of the model's semantic burden. It does **not** establish a generic source-edit service or require Harness to own self-modification orchestration.

The accepted source candidate also strengthens one existing authority law: caller-authored JSON object keys at Mandate and structured-completion projection boundaries must already be strings. Harness now fails closed instead of silently converting a non-string key into different valid bytes via `str(key)`. Valid legacy all-string-key objects preserve their existing canonical representation.

RSI P3 extends this with a bounded improvement-of-improvement result. The promoted P2 system was not handed a source defect and patch: a target-discovery Agent received the durable P2 receipt plus current source evidence, rejected weak or unreachable candidates, selected the delegated sha256-digest validation gap itself, and authored the falsifier used for baseline admission. A malformed first falsifier did not count as a red baseline merely because it exited non-zero; the experiment distinguished action failure from invariant falsification and introduced static falsifier admission before evaluation.

That failure also reproduced the same stale-world-model pressure seen in ordinary Agent cognition: replaying exact malformed action or diagnostic bytes into the next model request repeatedly anchored the old invalid action even when the failure evidence said it was wrong. P3 therefore applied the existing cognition law to self-change evidence: **canonical failed-action history is not the next Working View**. Exact historical evidence remains digest-bound and recoverable, while the current model view may carry only the selected target, failure class, action digest and current repair constraint. Removing obsolete failed-action/diagnostic bytes from the active view allowed the next Agent attempt to produce an admissible falsifier without deleting the underlying history.

P3 also removed experiment-local mechanical glue. The source Agent still authored exact `oldText → newText`, but materialization used Runtime's native exact replacement authority rather than a custom patch/materializer program. Thus the improvement loop itself became smaller: P2 used separate source-generation and promotion scripts plus custom materialization; P3 used one experiment runner for target selection, source edit and promotion decision, while existing Runtime primitives handled exact mutation. None of this changes Harness ownership: target discovery policy, evaluator construction and canonical promotion triggering remain external, and no Scheduler, generic Evaluator Service, Memory/RAG system or RSI Controller is implied.

The P3 source candidate closes the delegated-digest authority gap selected by the Agent: Mandate-layer digest values must now be exactly `sha256:` followed by 64 lowercase hexadecimal characters, matching the strict digest form already used by core Contracts. The shared Mandate `_digest` boundary therefore rejects non-hex payloads consistently for Mandate consumption, execution Profiles, Strategies and compiled-attempt evidence while preserving all valid lowercase sha256 identities.

RSI P4 tests whether the Agent can compose the *discovery side* of the next improvement cycle rather than receiving a caller-prepared source view. It receives a bounded capability catalog and exact prior evidence, then chooses concrete repository observations itself. In the accepted run it selected 203 observations across path listing, text search, exact file reads, named/unit checks, exact prior-observation recall and bounded probes; 50 of 51 tracked Harness source files were read exactly. The caller did not preselect source slices or evaluator gates.

The run also establishes an asymmetric authority law for recursive improvement. Two Agent-finalized target hypotheses were mechanically rejected because their declared falsifiers exited zero: a plausible target, broad search coverage or model confidence does not earn mutation authority. But requiring the Agent to either keep observing or invent a source target is also incorrect. The initial P4 experiment contract had only `observe | finalize`, so after 203 rounds it entered a low-information search tail and finally hit a no-progress admission. A deterministic meta-falsifier captured this protocol defect. The experiment-only contract was then extended with a bounded `abstain` result that means only **no causal baseline-red target was demonstrated under the observed evidence**. It does not mean Harness is defect-free.

With that outcome available, the Agent immediately abstained on round 204. Because no target survived admission, source generation, materialization, candidate evaluation, source-promotion decision and canonical Git source promotion were intentionally not invoked. This is a stronger authority separation than fabricating a candidate merely to exercise the pipeline. P4 therefore treats no-change as a first-class improvement-cycle outcome: **mutation requires causal red evidence; no-change requires exact provenance plus an explicit epistemic boundary.** The one-off discovery/abstention runner was deleted after its evidence digests were frozen; no RSI controller, Evaluator Service, Scheduler or public self-modification API was added. Discovery efficiency remains an open problem—the accepted semantics required near-complete source coverage—so P4 proves bounded composition/abstention authority, not efficient autonomous repository research.

RSI P5 attacks that discovery-efficiency boundary. Its first negative control intentionally optimised only observation count; the Agent immediately abstained after seeing one mechanical repository index, demonstrating that `fewest observations` is not a valid objective because it rewards ignorance. The corrected experiment instead adds one exact independent external failure observation as world evidence while leaving source targeting, observation choice and evaluator design unselected. The Agent then chooses the next repository observation according to decision value rather than coverage.

The accepted trajectory required 8 admitted observations over 12 Agent decisions: one full mechanical repository index, one exact Host/World failure record, four exact symbol reads, one literal search and one reference search. This is 25.375× fewer observations than P4's 203. The Agent localized the reported no-Tool failure to a deliberate `SQLiteHarnessAgentBridge` guard, but it did not prove that a real no-Tool control path reaches the guard with non-empty observations or Tool Call identities. It therefore abstained rather than converting adjacency into a causal source claim. A later historical P6 did prove and repair that path, a subsequent contraction reopened the current failure while removing its dedicated falsifiers, and current repair 145 now re-establishes the conclusion/control-vs-Tool-authority separation with seven permanent post-contraction regression tests without restoring generic Provider continuation machinery.

P5 also reduces the information repeatedly projected into the model. A 53,618-byte full AST repository index remains exact durable experiment history, while the model-visible map keeps only source/test addressability and symbol names. Exact rejected actions remain in the checkpoint but their malformed arguments are omitted from later Working Views; only capability, decision digest and failure class are projected. Reducing recent exact observations from three to one plus compacting the index lowered one previously rejected request upper bound from 92,595 to 75,592 and restored Provider dispatch without expanding the 90,000-token experiment envelope. A large nested discovery-result schema also proved mechanically fragile, so the Provider-facing structured result was reduced to one `decisionJson` string and strict semantic JSON admission moved caller-side. This mirrors the P2 exact-edit lesson: models own semantic content; infrastructure should not make them perform unnecessary mechanical encoding.

P5 is therefore a bounded R12 result about **evidence-driven high-information discovery**, not general efficiency. The accepted semantic discovery path still used 12 fresh Provider calls and 239,953 total tokens, so observation traversal became dramatically smaller while model-call/token cost remains high. That Agent discovery branch authorized no source change; generator, materializer, candidate evaluator, source promotion decision and canonical source promotion remained intentionally unused. A later independent release-acceptance path did find a separate causal Provider concurrency defect; its source repair has distinct provenance and is not attributed to the discovery Agent.

## Run Contract

`HarnessRunContract` binds one **attempt** to caller identity/reference, Objective and Context refs, Provider/Adapter/model identity, Tool catalog and grant digests, execution budget, completion contract, system manifest, privacy policy, deadline and correlation links. The Contract digest is execution authority for that attempt: a Run may not silently execute against different values. When compiled from a Mandate, its system manifest binds the Mandate, selected profile, Strategy, attempt index, and adopted prior Context evidence.

Harness does not synthesize a higher-level Task from CLI flags. The caller authors the Contract; the CLI only supplies Run-local input messages.

## Persistence and continuity

The independent Store is the only current Harness writer. It owns:

- Run creation, caller binding and terminal projection;
- immutable CAS objects and contiguous Run events;
- leases and revision fencing;
- Provider Call claim, dispatch, completion, failure and UNKNOWN state, with exact request/result content only when authorized;
- Tool-step intent, dispatch fence and receipt chains, plus exact Tool observations only when authorized;
- privacy-projected pause/resume snapshots;
- recovery assessments;
- privacy-projected Trace and terminal Run evidence, with exact conclusion/CompletionProposal content only when authorized.

There is no Host-backed Store, Assignment writer, dual write or cutover selector.

### Privacy authority inside continuity

The Run Contract privacy policy is execution authority, not a diagnostic preference. Default `metadata-only` continuity retains identities, digests, causal/effect receipts and budgets while omitting exact model/Tool content from Harness-managed durable objects. `bounded-private-content` may separately authorize model and Tool content; mixed objects use the stricter applicable authority so Tool calls, Tool-role messages and Tool observations cannot become a model-content persistence bypass.

Privacy does not weaken effect fencing. A digest-only completed Provider Call still prevents physical redispatch after response loss. If exact result/transcript/Tool content was not authorized for retention, recovery fails closed and requires caller-authorized rehydration rather than reconstructing content from another hidden Harness copy.

These are structural content laws, not semantic taint tracking: ordinary model text can semantically repeat Tool-derived information, and Harness does not currently prove otherwise.

Ordinary Store open validates global physical authority: schema, SQLite `quick_check`, and retained CAS object identity/content. It does **not** replay every unrelated Run. Opening a Run continuity boundary validates that Run's complete semantic history before execution; explicit full Doctor remains the authority-wide history replay. This keeps fail-closed semantics local to the Run being executed instead of making every worker pay an all-Runs startup cost.

Durable event and request identities remain deterministic for idempotent replay. Execution ownership does not: Continuity Stores, Agent Bridges, and terminal recorders use process-instance owner identities for leases and Provider claims so two workers cannot consume one durable dispatch admission as two physical executions.

## Model-visible Working View

The mature `OrdivonAgentLoop` no longer requires the Provider request to be identical to the complete canonical Run-local message history. An optional internal `WorkingViewProjector` seam may supply the exact model-visible messages for each Provider turn while the Loop continues to retain canonical execution history for progress accounting, recovery and Tool correlation.

The current `WorkingSetViewProjector` is deliberately narrow: it loads the current **committed** `HarnessWorkingSetSpec` and deterministically compiles its pinned exact sources into one `HarnessWorkingView`. It performs no Context discovery, ranking, RAG, Memory, summarization or automatic source selection.

Discovery and selection are separate authorities. A domain, World integration or Runtime Tool may discover raw paths, URLs, records or already-materialized source identities. Harness does not interpret those results as relevant Context. Raw content must first cross the Run's privacy-aware source-materialization boundary before it can become an exact `HarnessWorkingSetPin`; the resulting CAS object identity, not a caller-guessed semantic digest, is the pin authority.

The model-visible suffix now has two explicit non-WorkingSet authorities. **Caller interaction ingress** consists only of exact plain `user` messages appended on resume after the latest `needs_input` Snapshot; it is caller-owned model cognition, not Agent-selected durable Context. It remains visible across Agent WorkingSet transitions during that interaction and is consumed when the next `needs_input` Snapshot becomes the new interaction boundary. **Transient Tool evidence** remains attempt-local cognition: the exact Provider-authored assistant message containing `toolCalls` followed by the exact bound Tool Observation messages. Journal sequence orders Tool exchanges before and after the caller boundary, so recovery can reconstruct `pre-caller Tool exchange → caller ingress → post-caller Tool exchange` without inventing chronology. The committed Working View remains the exact prefix. Unbound user text, `system`/`assistant`/Tool-shaped caller injection, isolated Tool observations and replacement projections are rejected before physical Provider dispatch. Continuity Doctor independently recomputes the permitted suffix from Snapshot/RunState, WorkingSet, Provider and Tool evidence.

A projected Run may also grant an **Agent-owned caller-ingress promotion** cognition action. The Agent does not restate hidden WorkingSet pins and cannot provide or rewrite source bytes. It names only a new successor slot, a new attempt identity, and exact indexes into the caller ingress that the Provider request explicitly marked as promotable. Harness then mechanically derives those exact caller bytes from durable Snapshot/RunState and Provider evidence, materializes one deterministic `HarnessWorkingViewSource`, and atomically extends the current selected WorkingSet with the new pin. Existing selected pins are preserved mechanically; choosing which caller indexes deserve persistence remains an Agent decision. Promotion is cognition state, not a Runtime Tool effect, and consumes no external Tool-call budget.

Promotion provenance is visible rather than hidden. `AgentTurnRequest` may carry exact caller-ingress references mapping the interaction-local caller index to the corresponding Provider-request message position. Provider adapters can project those references as Harness execution-control metadata. DeepSeek exposes `promote_caller_ingress` only while at least one exact caller index is currently promotable, and constrains its schema to those indexes; once none remain, the cognition capability is withdrawn from the Provider surface. This is capability truth, not a Harness judgment about whether the caller fact is semantically worth keeping.

Caller and durable authority remain separate even after promotion. While the promoted source remains in the current WorkingSet, the exact promoted caller indexes are suppressed only from the caller-overlay projection so the model does not receive duplicate bytes. This is provenance-aware suppression, not text deduplication: if the Agent later drops that promoted pin during the same interaction, the still-valid caller ingress reappears. The next `needs_input` Snapshot ends the caller authority either way; a promoted source survives because its WorkingSet pin, not the old interaction overlay, now owns its durable cognition. Re-promoting an index that is already durable in the current WorkingSet is rejected.

An execution may explicitly grant an Agent-owned cognition transition surface. In that mode, one Provider turn can return an `AgentWorkingSetTransitionProposal` containing exact successor pins plus a bounded basis. This is a third Agent action category beside external Tool calls and a Run conclusion; it is not charged to the Tool budget and it cannot be mixed with either action in the same normalized turn. DeepSeek may encode the proposal as a function call on the wire, but the Adapter normalizes it as cognition state rather than an `AgentToolCall`.

A transition-capable projected turn may also carry **current WorkingSet addressability**. The projector mechanically aligns every current exact pin with the half-open message range `[start,end)` produced by that source in the effective request prefix. `AgentTurnRequest.workingSetRefs` retains this internal provenance, and DeepSeek exposes it as `workingSetSelection` execution-control metadata only when the WorkingSet-transition surface is granted. This is not new task evidence and does not rank or interpret sources: it makes the durable cognition the Agent is already seeing exactly addressable, so retain/drop decisions can use existing `propose_working_set_transition` without guessing hidden logical references, generations, slots or digests. Continuity recomputes the pin/range mapping from the current committed WorkingSet and exact source objects before Provider dispatch; forged identities or message ranges fail closed.

Durable correction therefore requires no separate supersession or memory-update primitive. If caller interaction supplies a correction, the Agent may first use caller-ingress promotion to materialize the exact corrected bytes, then use the ordinary WorkingSet transition to omit the stale pin while retaining the task and corrected pins. The stale source leaves **current cognition** but remains an earlier committed WorkingSet fact and may still be inspected or recalled through the existing historical-cognition boundary. Harness does not infer that a newer-looking statement supersedes an older one; semantic correction ownership remains with the Agent.

Continuity applies one accepted proposal as an atomic `replan → select exact pins → commit` Journal transaction under one Run lease. Provider-authored transitions bind two different facts: `sourceWorkingSetDigest` identifies the durable selected Context that remained current, while `sourceModelViewDigest` identifies the exact effective view the Agent actually saw, including admitted caller interaction ingress and transient Tool exchanges. The exact retained Provider request/result prove that the proposal came from that model view. Competing proposals have one winner, exact replay is idempotent, and Continuity Doctor verifies the proposal/source/Provider evidence rather than trusting a mechanically valid WorkingSet chain alone. Base-only direct transition receipts remain readable under the earlier single-view evidence form.

Transient Tool exchanges are **attempt-local cognition**, not durable selected knowledge. When exact model and Tool content are authorized, any fresh-process resume reconstructs the current attempt's complete Provider-authored Tool exchanges from Journal/CAS authority: the current committed WorkingSet event defines the attempt boundary, later completed Provider Tool turns identify the assistant `toolCalls` messages, terminal Tool intent/receipt/Observation evidence proves physical observations, and an active effect is reconciled without redispatch before any still-pending calls execute. This applies to both hard recovery and an ordinary clean pause/resume. When a successor WorkingSet commits, all predecessor-attempt transient exchanges disappear automatically.

Durable cognition still needs no generic Memory subsystem. For an already-materialized source, promotion remains ordinary Agent WorkingSet selection: the source becomes durable current cognition only when the Agent explicitly includes its exact pin in a successor committed WorkingSet. Caller ingress is a narrower special case because no exact source pin exists yet. Its promotion action therefore combines two mechanical steps—materialize the exact Agent-selected caller bytes, then add the resulting pin to the current selection—under one provenance-bound transaction. In both cases Harness does not decide which facts deserve persistence, synthesize memories, summarize caller text, rank retained sources or inject materialized-but-unselected objects into future model views. `source bytes exist`, `source is current cognition`, `source remains selected later`, and `caller bytes were interaction cognition` remain different facts.

Historical recall is the inverse mechanical boundary, not a semantic Memory search. An execution may explicitly grant `inspect_working_set_history`, which returns a bounded reverse-chronological catalog of **earlier committed WorkingSet identities and exact pins only**. Materialized-but-never-selected CAS objects are absent; historical source content, semantic similarity, relevance scores and automatic source injection are absent. The Agent decides when to inspect the catalog and may use the existing WorkingSet transition control to re-select an exact historical pin. History inspection performs no Runtime dispatch and consumes no external Tool-call budget, but its Provider-faithful function result is bounded by observation bytes and participates in observation/no-progress accounting. Continuity recomputes the result from Journal history relative to the exact WorkingSet that authored the Provider turn, so a forged local history reader cannot authorize invented recall evidence. Exact clean-pause replay of the function-call/result transcript still requires both model- and Tool-content authority because the Provider wire uses a structural Tool channel.

Execution control is distinct from task Context. The exact **per-turn action authority** is now request-bound: `AgentTurnRequest.tools` contains the Runtime/World Tool actions currently admitted for that turn, while provider-neutral `AgentTurnRequest.capabilities` contains the Harness-native actions currently admitted (`submit_run_conclusion`, WorkingSet transition, caller-ingress promotion and bounded WorkingSet-history inspection). Installed mechanisms are not themselves current capability. The Loop derives this action surface from the mechanisms actually wired for the Run plus dynamic turn facts such as current caller-ingress addressability and external-observation gates; the resulting request participates in `dispatchDigest`, Provider claim identity and optional retained request evidence. A Provider adapter may render this exact action authority, but it cannot independently add or remove Harness actions through adapter-local feature flags.

For DeepSeek, the Harness-authored system control envelope names the exact `harnessActions`, Runtime Tools and remaining bounded budget admitted by that `AgentTurnRequest`, plus the exact caller message indexes/Provider positions still eligible for promotion and exact selected durable pins/ranges when the corresponding request-bound capability is present. Caller promotion is true only while at least one exact promotable caller reference exists; after promotion suppresses that ingress from the interaction overlay, the next turn carries promotion=false even though the Run still has a promotion mechanism installed. Capabilities that are no longer executable are therefore absent from both the exact request truth and the Provider surface. The transition control still states that reselecting identical pins is an intentional cognition-attempt reset rather than progress or a substitute for a `needs_input` conclusion.

No-progress and observation-only limits are effect gates, not epistemic verdicts. Their durable authority is the retained progress counters; the process-local gate reason is only a projection and is recomputed after fresh-process resume. Reaching one closes new external observation capability and gives the Agent a subsequent cognition/closure turn over the evidence it has already seen. A successor WorkingSet attempt may still be legal with exactly the same pins because attempt identity owns transient cognition lifetime: such an attempt reset discards predecessor Tool exchanges but is **not** structural progress, does not reset the counters, and does not reopen a closed soft effect gate. A transition whose exact selected pins change is a structural cognition mutation and may reset the soft progress counters/gate. A newly admitted caller interaction ingress is also genuine progress because those exact caller bytes now enter the effective model view; it may reset the soft counters without changing Agent-owned WorkingSet selection. Hard Tool-call budget remains global and cannot be revived by either cognition
transition or caller ingress. A Provider that still refers to a now-unavailable
historical Runtime Tool receives a bounded local, model-correctable rejection with
`physicalDispatch=false`; this consumes the Tool-correction budget but cannot
exceed the external Tool budget. Caller/domain rejection of a Run conclusion is a
separate mechanic: it consumes `maxConclusionCorrections`, not
`maxToolCorrections`, and Harness forwards the owner rejection reason without
assuming that evidence is missing. Harness therefore bounds effects while the Agent
still owns whether to conclude `candidate_completed`, report concrete
`needs_input`, or perform an admitted cognition transition. A Harness-owned
`no_progress` execution stop is not an Agent semantic conclusion: its reason
remains in Run stop detail/Trace and Harness does not synthesize an
`AgentRunConclusion` for that disposition.

The cognition mechanisms now have one **experimental product composition proof** in `StandaloneHarnessRunner`. A `StandaloneCognitionProfile` selects which already-proven cognition mechanisms are wired for the Run, and the Runner constructs the `WorkingSetViewProjector` plus exact Continuity handlers mechanically rather than requiring an application to hand-wire four seams. `StandaloneCognitionSeed` is an explicit caller-authored bootstrap only: it contains exact slot/source pairs and a basis, which the Runner materializes and commits through the existing WorkingSet authority. It performs no discovery, ranking, summarization or memory extraction. Re-entry after a response loss between the initial and committed WorkingSet records is idempotent against the exact seed.

`StandaloneCognitionProfile` now means only **installed cognition mechanisms**. It is deliberately not Provider capability truth. Each concrete turn derives one `AgentTurnCapabilities` value from the mechanisms actually wired plus current addressable authority, and DeepSeek no longer has independent cognition feature booleans. History composition still requires the privacy/Tool-channel authority already established by P-C1.8; capability truth describes what is admitted now, not permission to violate the Run Contract's content authority.

R2 begins physical recomposition only where R0/R1 exposed a proven seam. `AgentTurnProjector` now owns read-side construction of the exact Agent-visible turn: current WorkingView projection, caller-ingress addressability, attempt-local pre/caller/post overlay ordering, stale predecessor-attempt Tool-exchange withdrawal, Runtime Tool surface inclusion and request-bound Harness capabilities. `CognitionAdmissionKernel` owns only the common structural admission law for Agent-authored durable cognition mutations: reload the current WorkingSet, require the exact source digest to remain current, then invoke the action-specific promotion or transition handler. Promotion and ordinary transition remain distinct actions; their progress/evidence semantics stay in the Run coordinator.

This extraction deliberately preserves **construction ≠ verification**. `AgentTurnProjector` constructs a request from the read-side authorities available to the Loop, while `SQLiteHarnessRunContinuityStore` continues to reconstruct the permitted WorkingView prefix, caller provenance, Tool exchange chronology and exact current pin ranges independently from Journal/CAS before Provider admission. R2 therefore does not DRY those two algorithms into one shared authority.

A third seam is now proven by Provider response-loss/retry/UNKNOWN friction. `ProviderCallLifecycle` freezes the optional durable Provider-continuity surface at Loop composition time, validates exact `provider_request_digest` identity for durable calls, and normalizes bridge `begin/admit/fail/retry/complete` addressing. It deliberately does **not** own retry/backoff policy, Run stop codes, token accounting, model-result semantics or physical Provider transport; those remain in the Loop/Adapter, while durable Provider truth remains in Continuity. Current source and tests contain no supported dynamic replacement of these hooks after Loop construction, so repeated per-turn `getattr` discovery is not an authority requirement.

Across the complete current R2 lineage, `_run()` falls from 2,083 lines before kernel extraction to 1,876 after the three proven seams; the Provider-lifecycle extraction alone reduces the current no-progress/two-kernel coordinator from 1,974 to 1,876. The remaining Tool-effect coordination and progress/control code stays in the sequential Run coordinator until an equivalent real friction case demonstrates a stronger boundary. Large function size alone remains insufficient evidence for extraction. No SQLite schema, generic Memory/Capability service or public API is added.

R3 promotes a supported caller-facing Agent Run surface without promoting the R2 kernels themselves. `HarnessAgentRun` owns only mechanical product composition: state-root Store opening, exact Continuity reconstruction, Contract-budget reconstruction, selection of the built-in no-Tool versus independently bound Runtime-search bridge from exact Contract digests, and Snapshot-bound Provider-source rebinding on resume. It receives a caller-supplied Adapter factory and invokes that factory only after structural composition is admissible; therefore Harness can bind the exact persisted Contract without choosing a Provider or constructing one for an invalid surface. Runtime Tool execution still requires caller-supplied `HarnessExecutionBinding` and `HarnessRuntimeClient`; workspace identity, runtime-binding digest and foreign references are not inferred.

R3.2 strengthens `HarnessAgentRun.create()` into the supported surface's **static composition admission boundary**. Every impossibility provable from the exact Contract plus caller-supplied composition inputs is rejected before durable Run creation. Cognition privacy/history authority and exact independent Runtime-binding identity are checked before the Adapter factory is called; Adapter/model and structured-completion binding are checked immediately after the caller-owned factory returns and still before state creation. This is intentionally not Provider or Runtime liveness probing: availability, physical effects and semantic correctness remain outside static admission. Lower layers keep their own validation as defense-in-depth rather than becoming the caller-facing product boundary.

Caller-facing `HarnessCognitionProfile`, `HarnessCognitionSeed`, `HarnessCognitionSeedSource` and the `HarnessCognitionSource` alias are now part of the supported surface because exact initial cognition selection is caller authority. R3.1 is intentionally additive: R0-R2 `StandaloneCognition*` direct-module aliases and the already-supported low-level persistence/Runner exports remain available for compatibility and advanced composition while normal Python execution moves to `HarnessAgentRun`; pruning that older facade is deferred until adoption evidence justifies a breaking R3 slice. `AgentTurnProjector`, `CognitionAdmissionKernel` and `ProviderCallLifecycle` remain internal kernels and are not promoted. Harness still has no generic Capability Service, CandidateSet, Context Service, Memory service or semantic search/relevance policy.

## Provider lifecycle

A Provider Call is durable before uncertain physical delivery. Live claims exclude competing holders; response loss is reconciled from retained Provider state rather than treated as permission to redispatch. Dispatching with no safe proof of outcome becomes UNKNOWN. Retry is admitted only when the retained failure semantics prove redispatch safe and budget remains.

P5 release acceptance adds one narrower post-dispatch law. Once an execution has durably advanced the exact Provider Call to `DISPATCHING` and owns the physical Provider outcome, a competing replay that can already see that same `DISPATCHING` record must not take the generic Run lease merely to discover that redispatch is forbidden. If short mechanical Run-lease contention still exists when the physical result returns, the exact outcome owner may wait for at most one second in bounded local-monotonic intervals, but only while the durable Provider Call record remains byte-identical/current. A changed record fails as superseded; exhausted waiting becomes explicit Provider recovery. This is bounded known-outcome commit authority, not a generic lock-retry policy.

Provider identity belongs to Harness execution. A higher-level caller does not need to model Provider sessions or retry state.

DeepSeek physical egress may be supplied by an external workstation transport without turning Harness into a network router. The cancellable `http.client` transport preserves its historical direct path when no HTTPS proxy is projected. If `HTTPS_PROXY`/`https_proxy` is present, Harness accepts only one unauthenticated `http://127.0.0.1:<port>` CONNECT endpoint, connects to that loopback sidecar, tunnels the fixed official DeepSeek HTTPS origin, and performs TLS end-to-end to DeepSeek. Remote proxies, proxy credentials, non-loopback hosts, conflicting proxy variables and proxy URL paths fail before Provider dispatch. The physical transport is deliberately not part of Provider request identity: changing a safe pre-dispatch route is analogous to changing an IP path, while an ambiguous Provider delivery remains fenced by the existing Provider Call lifecycle and is never permission for automatic mid-call migration.

A Provider turn that simultaneously requests ordinary Tools and submits a Run conclusion is treated as a **model-correctable action conflict**, not as permission to choose on the model's behalf and not as a Harness failure. Harness dispatches none of those ordinary Tools and admits no conclusion from that mixed turn; the next model turn must choose whether to continue acting or conclude.

## Tool lifecycle

Tool-bearing Runs bind a complete Tool catalog digest and Tool grant digest. Before physical delivery, Harness records a Tool intent and dispatch fence. Runtime requests carry Harness authority references. Observation-only failures can be corrected by the Agent; ambiguous external effects require reconciliation and may terminate recovery as UNKNOWN.

The primary CLI intentionally supports only the canonical no-Tool DeepSeek profile. Tool-bearing applications use `ordivon_harness.api`/`core` with an application-supplied `HarnessRuntimeClient`.

## Pause, resume and recovery

Pause snapshots retain Provider source identity plus the Run state content or content digests authorized by the Contract. Exact-content resume starts from an authorized snapshot and may append caller messages. In the non-projected path those messages remain part of the canonical Provider-visible transcript. In a projected WorkingView Run, plain caller `user` messages following a `needs_input` Snapshot are now a separate caller-owned cognition ingress: they are projected after any current-attempt Tool exchanges that happened before that pause, survive WorkingSet transitions, precede Tool exchanges produced after the caller reply, and expire when the next `needs_input` Snapshot starts a new interaction. Their exact bytes are recovered from the authorized Snapshot/RunState continuation and revalidated before Provider dispatch; a forged bridge cannot invent them. Because this is model content rather than a Tool channel, exact caller ingress requires model-content authority but not Tool-content authority. Digest-only recovery remains conservative and cannot reconstruct omitted caller bytes.

## Completion

Harness can conclude that an Agent Run produced a candidate-completed result and can record a `CompletionProposal`. That is not the same as caller/domain completion. Final verification and commitment remain outside Harness.

## Integration boundary

`host_external_adapter.py` is intentionally duck-typed and Host-free. It maps a foreign execution request to an independent Harness Run and maps durable observations/completion proposal back out. It does not import Host, use Host storage, or transfer Run authority.

## Removed pre-H3 architecture

H3 intentionally removed the former `HarnessHost`, Host Assignment/TaskContract model, `HostHarnessRunStore`, Host CLI namespace, cutover machinery, Host dependency extra, and Host-coupled Codex/Hermes drivers. Historical evidence may describe those experiments, but current source does not decode or advertise them.
