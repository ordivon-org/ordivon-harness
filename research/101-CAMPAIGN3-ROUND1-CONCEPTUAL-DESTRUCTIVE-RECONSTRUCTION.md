# 101 — CAMPAIGN 3 ROUND 1
# Conceptual Destructive Reconstruction

**Prebinding authority:** Campaign 3 Charter v1 at commit `157425f` before this analysis.  
**Round type:** conceptual/destructive. Current receipt/status classes are not ontology authority.

## 1. Round 1 classification

`CRITERION_REVISED`.

P3 survives its central ownership claim: Harness can mediate effect-related operational standing without owning physical causality only by separating evidence, dispatch, realization claims, reconciliation and downstream obligations.

However the Charter's initial `Realization-Claim Standing` vocabulary remains too close to treating an Invocation as if it had one scalar world-effect state. Two revisions are required.

### Revision 1 — realization standing is claim-relative

Harness cannot responsibly evaluate “did the effect happen?” without an explicit bounded **Realization Claim** `Q` whose referent/scope is grounded by Invocation/capability/external-owner semantics.

Examples:

- `Q_dispatch`: Invocation I crossed an external dispatch boundary;
- `Q_exec`: external owner reports operation O executed;
- `Q_partA`: sub-effect A occurred;
- `Q_stateX`: target state X was observed after the operation.

Harness evaluates evidence standing **for Q**. It does not invent the causal proposition Q when that proposition belongs to an external/domain owner.

### Revision 2 — “partial realization” is usually mixed standing over an explicit claim set

`PARTIAL_REALIZATION_EVIDENCED` is not sufficiently technology-neutral as one scalar status. For a scoped multi-part realization claim set `{Q1...Qn}`, “partial” means some claims are supported while others are contradicted/unresolved/not established.

This preserves explicit scope and avoids pretending that arbitrary world effects have one universal completion fraction.

Therefore P3 is revised to P3'.

## 2. Revised relation stack

### Layer 0 — Evidence Projection Validity

Evidence artifacts/claims must be provenance-, authority-, lineage- and currentness-valid before they can affect a Realization Claim.

### Layer 1 — Dispatch Standing

Harness may carry bounded dispatch standing:

- `NOT_DISPATCHED_ESTABLISHED`
- `DISPATCHED_ESTABLISHED`
- `DISPATCH_STANDING_UNRESOLVED`

Dispatch remains separate from all external realization claims.

### Layer 2 — Realization Claim Contract

A claim `Q` identifies the bounded external-realization proposition being evaluated and, where necessary, its scope/subject/Invocation relation and the external authority capable of grounding it.

If Harness lacks authority to define/evaluate `Q`, the result is `EXTERNAL_REALIZATION_CLAIM_REQUIRED` rather than a guessed effect state.

### Layer 3 — Realization Evidence Standing for Q

Given admissible evidence `E`, Harness carries only evidence-relative standing:

- `Q_SUPPORTED_BY_ADMISSIBLE_EVIDENCE`
- `Q_CONTRADICTED_BY_ADMISSIBLE_EVIDENCE`
- `Q_EVIDENCE_CONFLICTED`
- `Q_UNDERDETERMINED`

`Q_UNDERDETERMINED` includes no/insufficient evidence. It is not a claim that Q is false.

A multi-part realization is represented by multiple Q standings rather than a universal scalar partial status.

### Layer 4 — Reconciliation / Settlement Standing

For a bounded operational use `U_effect`, Harness asks whether the currently relevant Q set is sufficiently settled for the next decision:

- `SETTLED_FOR_BOUND_USE`
- `RECONCILIATION_REQUIRED`
- `RECONCILIATION_IN_PROGRESS`
- `EVIDENCE_INSUFFICIENT_FOR_SETTLEMENT`
- `EXTERNAL_EFFECT_DECISION_REQUIRED`

Settlement is use-relative. It does not imply metaphysical/world finality.

### Layer 5 — Continuation / Redispatch Obligation

Effect evidence can impose obligations on later operation, but does not by itself establish retry safety. Missing evidence after dispatch can therefore block redispatch; externally owned idempotency/admission semantics may later permit a repeat.

## 3. Proposition P3'

### P3'-A — Realization Claim Standing is claim-scope and evidence relative

Harness evaluates bounded Q from admissible evidence; it does not assign one owner-independent world Effect status to an Invocation.

### P3'-B — Evidence validity != claim support

Valid evidence may support, contradict or leave Q unresolved. Invalid evidence supports nothing.

### P3'-C — Dispatch Standing != Realization Claim Standing

Dispatch is a Harness/external-boundary fact; realization claims concern externally grounded propositions and require separate evidence.

### P3'-D — No receipt/evidence != Q false != retry permission

After dispatch, absence of terminal realization evidence leaves relevant Q underdetermined unless stronger external evidence exists.

### P3'-E — Terminal local/execution standing != external causal finality != semantic success

A receipt may authoritatively settle a bounded issuer-owned claim while leaving broader world consequence and domain success unresolved.

### P3'-F — Cancellation standing != effect absence

Cancellation evidence must be interpreted according to its explicitly owned claim. `cancel requested` cannot imply Q false; even terminal `cancelled` establishes no-realization only if the external owner's semantics actually guarantee that proposition.

### P3'-G — Partial realization is mixed standing over explicit claims

Partiality is represented through claim scope/claim set, not a universal completion scalar.

### P3'-H — Reconciliation updates current standing by lineage

Later evidence may change the current Q standing or settle a bounded use, but prior unresolved/conflicted evidence remains historical provenance.

### P3'-I — Local lifetime != external realization lifetime

Timeout, process loss, Run pause/completion and caller abandonment do not determine the temporal boundary of external Q.

### P3'-J — Invocation cardinality != external realization cardinality

One logical Invocation may map to zero, one or multiple external realization events depending on external semantics/evidence; conversely one external state change may aggregate multiple Invocations. Harness fencing constrains its own dispatch lineage, not universal physical cardinality.

### P3'-K — Compensation creates a new claim/edge; it does not erase prior standing

A compensating operation may support new state/consequence claims while original realization provenance remains.

### P3'-L — Observation/Result/Semantic Success remain separate claim families

An observation can support a realization Q; Result attribution is a bounded Harness object; semantic success remains owner/domain relative.

### P3'-M — Interacting effects require explicit composition claims

Harness may preserve dependency/conflict between Invocations, but if combined causal meaning is not specified by an external/domain owner it must return `EXTERNAL_EFFECT_DECISION_REQUIRED`.

## 4. Fixture evaluation

### T1 — admitted but authoritative non-dispatch

Dispatch standing: `NOT_DISPATCHED_ESTABLISHED`.

No universal world no-effect theorem follows, but the Harness-mediated Invocation path did not cross dispatch. For a Q explicitly claiming realization **through this Invocation dispatch**, evidence can contradict Q; unrelated external causes remain outside scope.

R1 Dispatch Equals Effect is irrelevant here; the key result is claim scoping.

### T2 — dispatch established, response lost, no terminal receipt

Dispatch: established. Relevant realization Q: `UNDERDETERMINED` absent stronger evidence.

Redispatch cannot be inferred safe. This falsifies R3.

### T3 — terminal execution/observation receipt, domain goal unknown/failed

A receipt may strongly support the issuer-owned claim it actually attests, e.g. “operation executed” or “observation returned”. It does not automatically support “domain goal succeeded”.

R2 Receipt Equals Physical Truth and R8 Observation Equals Semantic Success are falsified as universal models.

Important refinement: receipts are not epistemically weak by default; their authority is **claim-scoped**.

### T4 — cancel-requested later reconciled cancelled before known effect

The earlier cancel-request standing remains historical. The reconciled terminal claim may settle bounded continuation.

Whether it supports a `no realization` Q depends on external cancellation semantics. Generic Harness cannot infer this from the word `cancelled` alone.

This revises the Charter's initial expected tendency to be more owner-preserving.

### T5 — cancel requested, later evidence establishes effect occurred first

Cancellation request does not erase the supported realization Q. R4 is falsified.

### T6 — only part of multi-part operation evidenced

There is no justified universal `PARTIAL=true` without a claim scope.

Represent `{Q1 supported, Q2 supported, Q3 underdetermined}` or an owner-defined aggregate Q if one exists.

This falsifies R5 scalar-state thinking and revises the Charter's partial status.

### T7 — delayed realization after timeout/pause

Local timeout/lifetime does not make Q false. R10 is falsified.

### T8 — blind retry under unknown realization

If Q for prior realization is underdetermined and external repeat/idempotency semantics are absent, Harness cannot infer retry safety. R3 is falsified and R7 is pressured.

### T9 — Harness dedupe/fence blocks duplicate dispatch

This establishes a claim about Harness dispatch lineage, not universal uniqueness of physical consequences. R7 Invocation Identity Prevents Duplicate Realization is falsified as universal.

### T10 — explicit external idempotency/repeat admission

Repeat may become operationally admissible because an external owner/capability contract establishes the relevant semantics. This is not inferred from missing receipt or Harness identity alone.

This shows owner-preserving external semantics can legitimately strengthen continuation standing.

### T11 — compensation after prior change

Compensation supports a new claim `Q_compensation` and perhaps a current-state claim. It does not convert the prior supported `Q_original` into “never happened”. R6 is falsified.

### T12 — conflicting evidence sources

If both are admissible and claim-compatible in scope but disagree, Q becomes `Q_EVIDENCE_CONFLICTED` for the bounded evidence set until currentness/authority/reconciliation resolves the conflict.

No scalar truth collapse is permitted.

### T13 — stale terminal evidence superseded by later reconciliation

Prior evidence remains provenance. Current Q standing may change according to explicit authority/currentness/reconciliation lineage.

R9 Reconciliation Rewrites History is falsified.

### T14 — interacting Invocations invalidate assumptions

Harness can represent dependency/conflict and preserve per-Q evidence. It cannot derive arbitrary combined world causality without an owner-defined composition claim.

Result: `EXTERNAL_EFFECT_DECISION_REQUIRED` where composition authority is absent.

### T15 — physical/execution effect succeeds, domain semantic outcome fails

The claims can simultaneously be:

- Q_execution supported;
- Q_domain_success contradicted or unresolved by the domain owner.

No inconsistency. R8 is falsified.

### T16 — local Provider/Run completion before delayed external realization knowable

Local completion is not external causal finality. R10 is falsified again and Campaign-1 continuation separation remains necessary.

### T17 — terminal receipt metadata survives, exact result content unavailable

A bounded terminal/execution Q may remain supported while cognitive availability/result content is insufficient for continuation. This composes Campaign 1 and Campaign 2:

`Realization evidence standing != Result-content availability != Resumability`.

### T18 — nonterminal receipt later reconciled terminal

Reconciliation changes current standing by an explicit lineage edge and preserves the predecessor receipt. Directly supports P3'-H.

## 5. Rival standing after Round 1

| Rival | Standing |
|---|---|
| R1 Dispatch Equals Effect | FALSIFIED_IN_SCOPE |
| R2 Receipt Equals Physical Truth | FALSIFIED_AS_UNIVERSAL; receipt can be authoritative for its owned bounded claim |
| R3 No Receipt Means No Effect / Retry Safe | FALSIFIED_IN_SCOPE |
| R4 Cancellation Means No Effect | FALSIFIED_IN_SCOPE |
| R5 Scalar Success/Failure Effect State | FALSIFIED_IN_SCOPE |
| R6 Compensation Erases Prior Effect | FALSIFIED_IN_SCOPE |
| R7 Invocation Identity Prevents Duplicate Realization | FALSIFIED_AS_UNIVERSAL |
| R8 Observation Equals Semantic Success | FALSIFIED_IN_SCOPE |
| R9 Reconciliation Rewrites History | FALSIFIED_IN_SCOPE |
| R10 Local Lifetime Bounds External Effect Lifetime | FALSIFIED_IN_SCOPE |

## 6. Derived-law candidates

### L-C3-1 — Realization Standing is Claim-Scope and Evidence Relative

Harness does not own one global Effect truth variable; it evaluates bounded externally grounded Q claims from admissible evidence.

### L-C3-2 — Dispatch Standing != Realization Claim Standing

Crossing the dispatch boundary and supporting an external realization proposition are distinct.

### L-C3-3 — No Receipt != No Effect != Retry Permission

Absence of terminal evidence after dispatch cannot establish effect absence or retry safety.

### L-C3-4 — Local Terminality != External Causal Finality != Semantic Success

Local/issuer-owned terminal standing can coexist with unresolved broader external consequences or failed domain success.

### L-C3-5 — Partial Realization is Scoped Mixed Claim Standing

Without an owner-defined aggregate, partiality is represented by mixed support/contradiction/unknown over explicit claims rather than a universal scalar completion state.

### L-C3-6 — Invocation Cardinality != External Realization Cardinality

Harness logical Invocation identity/fencing does not universally determine how many external realization events occurred.

### L-C3-7 — Compensation != Prior Effect Erasure

Compensation is a later operation/claim edge and does not erase prior supported realization provenance.

### L-C3-8 — Reconciliation Settlement is Use-Relative and History-Preserving

Reconciliation may settle bounded downstream operation while preserving prior uncertainty/conflict evidence.

These remain provisional until closeout.

## 7. Campaign-1 compatibility

P3' sharpens Campaign 1 without reopening it.

Campaign 1's `possibly effected / unresolved` state becomes a bounded realization Q with underdetermined evidence standing. Its conservative redispatch rule remains valid.

`Recovery Validity != Run Identity != Resumability` remains intact, with effect-related Q settlement as one possible prerequisite for `SAFE_CONTINUE`.

## 8. Campaign-2 compatibility

Effect evidence/claims may enter Effective Decision Context only according to their actual standing. A Context that silently turns `Q_UNDERDETERMINED` into “Q false” or “Q true” can become insufficient/invalid for a use contract requiring the uncertainty.

Therefore:

`Realization Claim Standing` is an input to Context obligations, not replaced by Context equivalence.

## 9. Foundation pressure

`NO_FOUNDATION_PRESSURE` after Round 1.

The claim-relative revision composes existing Harness distinctions around evidence/provenance, Invocation lineage, Result attribution, action/effect separation and lifecycle/reconciliation. No deletion-essential new owner-native responsibility has been found.

## 10. Round 2 information-positive engineering targets

Use existing fixtures only where they exercise the revised theory:

1. terminal receipt idempotency + old-dispatch fencing;
2. nonterminal -> reconciled terminal lineage;
3. metadata-only terminal receipt with result content absent;
4. Provider response-loss completion fences redispatch without result content;
5. fresh-process recovery reuses completed Tool evidence and executes only pending Tool;
6. missing Tool-content authority blocks continuation without new Runtime effect;
7. Provider lifecycle unknown/failure distinctions if they materially test local terminality/unknown standing.

Do not invent partial/delayed/compensation/interference engineering cases in this campaign.

## 11. Round 1 close

`P3 -> P3'` is a substantive revision.

The strongest result is:

> **Harness should not model “the Effect” as one state. It should preserve evidence-relative standing over explicit realization claims, then derive bounded reconciliation and continuation obligations.**

Proceed to a prebound existing-fixture dogfood contract.
