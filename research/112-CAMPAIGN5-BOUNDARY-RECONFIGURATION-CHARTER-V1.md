# 112 — CAMPAIGN 5 CHARTER v1
# Boundary Reconfiguration Equivalence
## Operational Preservation Under Cut, Placement, Exposure & Morphology Change

**Control task:** `task:harness-campaign5-boundary-reconfiguration-equivalence-20260819`  
**Programme:** A — Agent–External Boundary Semantics  
**Standing effect:** programme-level investigation only. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Research question

Given a pre-change operational configuration `B0`, a reconfiguration transition `T`, a post-change configuration `B1`, and a bounded Reconfiguration Use Contract `U`, what must be preserved so that Harness may responsibly treat `B1` as a valid substitute/continuation target for the use declared by `U` despite changes in cut, implementation, process, provider, loop morphology, capability placement/exposure or locus?

Campaign 5 does not ask whether two systems are globally behaviorally equivalent.

## 2. Primitive-relation hypothesis

The Charter does **not** pre-assume symmetric equivalence as primitive.

Primary candidate:

`Preserves_U(B0 --T--> B1)`

means the transition preserves every obligation explicitly required by `U`.

Derived candidates:

- `Substitutable_U(B0,B1)` — B1 may replace B0 for the declared use;
- `Equivalent_U(B0,B1)` — only when the relevant preservation/substitution obligations hold in both required directions.

Round 1 may revise this vocabulary.

## 3. Reconfiguration is not one thing

A boundary reconfiguration may alter one or more of:

- Agent/external analytical cut;
- capability FunctionalPlacement;
- BoundaryExposure;
- authority/grant projection;
- Context projection;
- loop/morphology/provider implementation;
- process or Runtime realization path;
- cross-locus placement/Network path;
- Run continuation identity or successor relation;
- evidence/accountability projection.

The changed implementation surface is not itself the semantic criterion.

## 4. Prebound preservation dimensions

For use contract `U`, only dimensions required by U must be preserved, but required dimensions cannot be silently omitted.

### P0 — Reference / Subject Preservation

Relevant referents/claim subjects must remain correctly bound across T. Same names/paths are insufficient if referent identity/currentness changes.

### P1 — Identity / Continuation Preservation

T must preserve whichever identity relation U requires:

- same Run continuation;
- explicit successor/branch relation;
- or no Run-identity preservation requirement.

Equivalent substitution does not universally require same RunEpisode.

### P2 — Context Obligation Preservation

The post-change Effective Decision Context must satisfy the same U-required validity/currentness/sufficiency obligations, or an explicitly revised contract must be admitted.

Same Context bytes are insufficient under changed authority/currentness.

### P3 — Authority / Exposure Preservation

Required capability authority, grants, exposure scope and revocations must be preserved or explicitly re-admitted. Same capability/tool name does not establish same authority.

### P4 — Functional Placement / Mediation Preservation

If U depends on whether a capability is external, mediated, internalized, observation-only, effecting, verification-only, etc., that role must remain explicit. Moving the cut cannot silently change the semantic role.

### P5 — Realization Standing Preservation

Prior dispatch/Realization Claim/reconciliation uncertainty required by U must survive T. Reconfiguration cannot reset `Q_UNDERDETERMINED` into no-effect or retry-safe standing.

### P6 — Accountability / OCSS Preservation

U-required evidence bindings, unknowns, counterevidence, attribution and reproduction obligations must remain inspectable/admissibly rebound. Evidence may be adopted into B1, but not laundered through reconfiguration.

### P7 — External Owner Claim Preservation

Runtime/Network/Normative/World/domain truths needed by U must remain externally grounded. Moving the Harness cut does not transfer semantic truth ownership.

## 5. Proposition P5 — Use-Relative Preservation Under Reconfiguration

A technology-neutral Harness criterion can classify structural reconfiguration without requiring implementation identity if it evaluates directional preservation of explicit operational obligations under U.

### P5-A — Structural difference != semantic non-preservation

Different morphology/provider/process/placement may preserve U.

### P5-B — Structural sameness != semantic preservation

Same implementation can fail U if authority, Context, currentness, exposure or unresolved effect standing changes.

### P5-C — Behavioral sample agreement != preservation proof

Same output on one run cannot prove identity/authority/Context/effect/accountability preservation.

### P5-D — Preservation is use-contract relative

A transition may preserve U1 and fail U2.

### P5-E — Preservation is directional by default

Safe transition B0→B1 does not imply B1→B0 preserves the same obligations.

### P5-F — Same Run identity is optional, typed, and contract-dependent

A successor Run may be substitutable for a use without being the same Run continuation.

### P5-G — Context bytes != Context obligation preservation

Authority/currentness/sufficiency changes can invalidate preservation while bytes remain equal.

### P5-H — Exposure/capability name != authority preservation

Same tool/profile/capability label under changed grant/exposure is not equivalent.

### P5-I — Cut movement != truth-ownership transfer

Internalization/externalization/mediation changes do not automatically move Runtime/Network/domain/Normative truth authority into Harness.

### P5-J — Reconfiguration cannot erase unresolved realization standing

Unknown/partial/conflicted realization required by U must carry until reconciled by admissible evidence.

### P5-K — Reconfiguration cannot launder accountability

Evidence from B0 must be explicitly adopted/rebound under U; lost unknowns, changed roles or broken lineage invalidate preservation.

### P5-L — Outcome identity is not generally required

When U specifies operational obligations rather than deterministic output, differing model/world outcomes do not by themselves falsify preservation.

### P5-M — Reconfiguration evidence is itself accountable

The claim that T preserved U must have an inspectable support basis; “migration succeeded” is not self-authenticating.

## 6. Rival models

### R1 — Same Implementation Equals Equivalent
### R2 — Same Output Equals Equivalent
### R3 — Same Run ID Equals Equivalent
### R4 — Same Context Bytes Equals Equivalent
### R5 — Same Tool/Capability Names Equals Equivalent
### R6 — Successful Restart Equals Same Run
### R7 — Reconfiguration Resets Unknown Effect
### R8 — Cut Movement Transfers Truth Ownership
### R9 — Newer Configuration Automatically Supersedes Old
### R10 — Equivalence Is Global and Symmetric
### R11 — Live Hot-Reload Is Required for Reconfiguration
### R12 — Evidence Copy Equals Accountability Preservation

## 7. Falsifier classes

P5 must be revised/rejected if:

### F1 — Hidden implementation identity
Criterion requires same code/profile/process rather than obligations.

### F2 — Hidden behavioral equivalence
One matching output suffices despite authority/Context/effect/accountability drift.

### F3 — Identity collapse
Criterion cannot distinguish same-Run continuation from successor substitution.

### F4 — Authority blindness
Expanded/revoked authority leaves preservation unchanged when U requires the original authority envelope.

### F5 — Context blindness
Stale/insufficient Context survives solely because bytes/digest names look stable.

### F6 — Effect reset
Unknown realization is silently converted to safe redispatch after reconfiguration.

### F7 — Accountability laundering
Evidence/unknowns/attribution can disappear or change roles while preservation still passes.

### F8 — Owner annexation
Cut movement makes Harness the owner of Runtime/Network/domain/Normative truth.

### F9 — Directionality collapse
A one-way safe transition is forced into symmetric equivalence.

### F10 — Outcome overconstraint
Different nondeterministic outputs falsify preservation even when U does not require output identity.

### F11 — Transition invisibility
Criterion checks B0/B1 only and cannot represent T/adoption/rebinding obligations.

### F12 — Hidden implementation dependence
Criterion requires current AM7/AM8/profile/loop-driver classes.

## 8. Destructive fixture matrix

| Fixture | Scenario | Primary pressure |
|---|---|---|
| T1 | same implementation, authority expanded | sameness != preservation |
| T2 | same implementation, authority revoked | authority obligation |
| T3 | different morphology, same exact Tool grant and relevant stop semantics | structural difference |
| T4 | successor attempt changes loop identity and adopts exact prior receipt | successor vs same Run |
| T5 | same output from two configurations, one used stale Context | output rival |
| T6 | same Context bytes, external authority/currentness changed | bytes rival |
| T7 | available profile/exposure set changes; stale selection reused | re-admission/currentness |
| T8 | process restart reconstructs same admitted Run | same-Run recovery |
| T9 | process restart creates successor Run with explicit prior evidence | substitutability vs identity |
| T10 | provider implementation changes but U-required capability/evidence behavior preserved | provider substitution |
| T11 | provider change weakens dispatch/effect evidence semantics | realization preservation |
| T12 | unresolved prior realization exists at T | uncertainty carryover |
| T13 | capability moves from external Tool mediation to internalized computation | cut/placement semantics |
| T14 | capability label same, external truth owner changes | owner claim preservation |
| T15 | locus moves; Network path changes but required service claim remains available | Network bridge |
| T16 | locus moves and required reachability disappears | owner-grounded failure |
| T17 | OCSS evidence copied but unresolved unknown omitted | accountability laundering |
| T18 | OCSS evidence explicitly adopted/rebound with roles/unknowns preserved | accountability preservation |
| T19 | B0→B1 safe, reverse transition loses required evidence | directionality |
| T20 | different outputs under U that only requires authority/effect/accountability preservation | outcome non-identity |
| T21 | live loop mutation attempted without bounded successor/admission semantics | hot-reload rival |
| T22 | cut moves across a domain object and Harness claims ownership merely due internalization | truth-owner firewall |

## 9. Expected tendencies

- T1/T2 fail preservation when U binds the original authority envelope.
- T3 may preserve U despite morphology difference.
- T4 may be substitutable while not same-Run continuation.
- T5/T6 fail if U requires current Context/authority.
- T7 fails because stale selection is not re-admitted.
- T8 may preserve same-Run identity if Campaign-1 continuation criterion passes.
- T9 may preserve substitution but not same-Run identity.
- T10 may preserve U; T11 fails if U requires prior evidence semantics.
- T12 must preserve unresolved standing.
- T13 requires explicit changed placement/mediation semantics; not automatically fail/pass.
- T14 cannot infer ownership from labels/cut.
- T15/T16 depend on external Network claims, not Harness guesses.
- T17 fails; T18 may preserve U.
- T19 demonstrates preservation is directional.
- T20 may pass if U excludes deterministic outcome identity.
- T21 shows live mutation is not required and may be unsafe without admission.
- T22 fails owner firewall.

## 10. Evaluation method

### Round 1 — conceptual destructive reconstruction
Apply P5/R1–R12 to T1–T22. Test whether `Boundary Reconfiguration Equivalence` should be revised toward **Operational Preservation Under Reconfiguration** with directional primitive preservation.

### Round 2 — existing engineering dogfood only
Use AM7/AM8/E3-E4 plus existing fresh-process/Context-binding fixtures. Do not implement hot reload, locus migration or provider replacement solely to prove P5.

### Round 3 — owner-boundary + Campaign 1–4 compatibility audit
Verify Runtime, Network, Normative, Human, World/domain firewalls and composition with Identity, Context, Realization and OCSS.

### Round 4 — closeout
Classify P5/P5' and Foundation pressure separately.

## 11. Stop conditions

Stop rather than expand when the primary unresolved problem becomes:

- Runtime process/resource equivalence;
- Network path/topology equivalence;
- domain semantic equivalence;
- Normative legitimacy of authority transfer;
- Multi-Agent federation;
- general program equivalence or model behavioral equivalence.

## 12. Immediate next step

Commit/pin this Charter before conceptual analysis or dogfood.
