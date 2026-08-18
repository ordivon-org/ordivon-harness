# 113 — CAMPAIGN 5 ROUND 1
# Conceptual Destructive Reconstruction

**Prebinding authority:** Campaign 5 Charter v1 at commit `2ff9b3c` before this analysis.  
**Round type:** conceptual/destructive.

## 1. Round 1 classification

`CRITERION_REVISED`.

P5 survives, but the campaign title's symmetric `Equivalence` is too strong as the semantic primitive. The primary relation is revised to **Operational Preservation Under Reconfiguration (OPUR)**.

For pre-configuration `B0`, transition `T`, post-configuration `B1`, and bounded use contract `U`:

`Preserves_U(B0 --T--> B1)`

is directional and obligation-relative.

`Equivalent_U(B0,B1)` is only a derived relation when the required substitution/preservation obligations hold in every direction relevant to U.

## 2. Revision 1 — Preservation is an obligation vector, not a similarity score

Let `O(U)` be the explicit set of obligations required by U. Each obligation receives a typed transition standing:

- `PRESERVED`;
- `EXPLICITLY_REBOUND_OR_READMITTED`;
- `UNRESOLVED`;
- `VIOLATED`;
- `NOT_REQUIRED_BY_U`.

`Preserves_U` requires every U-required obligation to be preserved or explicitly rebound/readmitted in a way permitted by U. One scalar similarity/equivalence score is rejected.

## 3. Revision 2 — Valid reconfiguration != preservation under the old contract

A transition may be legitimately re-authorized into a new contract `U1` while failing preservation of `U0`.

Example: read-only authority expands to read-write by explicit new authorization.

- `TransitionValid(U0 -> U1)` may be true;
- `Preserves_U0(B0 -> B1)` is false if U0 required the old authority envelope.

This distinction prevents legitimate evolution from being mislabeled as semantic equivalence.

## 4. Revision 3 — Identity preservation and substitution are orthogonal

Three cases must remain distinct:

1. same Run continuation + preserved obligations;
2. new/successor Run + preserved substitution obligations;
3. same Run identifier/lineage but violated Context/authority/effect/accountability obligations.

Therefore Run identity is neither necessary nor sufficient for general OPUR.

## 5. Revision 4 — Cut movement does not move semantic ownership

Moving a capability/referent across the analytical Agent/external cut changes mediation/placement roles. It does not automatically change the semantic truth owner.

An internalized cache of Runtime evidence does not become Runtime truth authority. An internalized domain representation does not become domain truth authority. Owner transfer requires an independent owner-level rule, not a Harness cut change.

## 6. Revision 5 — Transition T is first-class

B0 and B1 snapshots alone are insufficient. T carries adoption, rebinding, revocation, supersession, reconciliation and evidence-lineage semantics.

Two identical B1 snapshots reached by different transitions can have different preservation standing because one transition preserved/rebound evidence and the other laundered or dropped it.

## 7. Revised proposition P5'

### P5'-A — Operational Preservation is U-relative and directional

No global symmetric boundary equivalence is assumed.

### P5'-B — Preservation is typed obligation satisfaction, not similarity

Implementation/configuration/behavioral closeness is non-authoritative unless U names it as an obligation.

### P5'-C — Structural difference can preserve U

Different morphology/provider/process/locus/placement can preserve the required semantics.

### P5'-D — Structural sameness can violate U

Same code/configuration can fail after authority/currentness/exposure/effect/accountability drift.

### P5'-E — Valid transition != old-contract preservation

Explicit readmission into U1 may make a transition legitimate without preserving U0.

### P5'-F — Same Run != preservation; preservation != same Run

Identity/continuation is one typed obligation family.

### P5'-G — Same output != preservation

Behavioral samples cannot substitute for authority/Context/realization/accountability checks.

### P5'-H — Same Context bytes != Context preservation

Effective authority/currentness/sufficiency semantics must remain valid.

### P5'-I — Same capability label != authority/exposure preservation

Grant/exposure/placement semantics are first-class.

### P5'-J — Cut movement != truth-owner transfer

Mediation placement and semantic ownership are independent relations.

### P5'-K — Unresolved realization must cross the transition unless reconciled

Reconfiguration cannot reset effect uncertainty or create retry permission.

### P5'-L — Accountability preservation requires role-aware adoption/rebinding

Evidence copying alone is insufficient; U-required unknowns/roles/currentness/lineage remain visible.

### P5'-M — Transition evidence is part of the preservation claim

A claim that reconfiguration preserved U must itself have accountable support.

### P5'-N — Outcome identity is optional and contract-specific

Different nondeterministic outputs may coexist with preservation if U does not require output identity.

### P5'-O — Preservation composition is not automatic

`Preserves_U(B0→B1)` and `Preserves_U(B1→B2)` support composition only when obligation identity/scope/currentness and transition assumptions remain compatible. Path chaining alone does not prove `Preserves_U(B0→B2)`.

## 8. Fixture evaluation

### T1 — same implementation, authority expanded

If U binds the original authority envelope, `VIOLATED`. Explicit new authorization may make the transition valid under U1 but does not preserve U0.

R1 is falsified.

### T2 — same implementation, authority revoked

Fails U when the removed authority was required. Same code is irrelevant.

### T3 — different morphology, same exact Tool grant and relevant stop semantics

Can preserve U if scheduling morphology is not itself a required invariant and Context/effect/accountability obligations remain satisfied.

Structural identity is unnecessary.

### T4 — successor attempt changes loop identity and adopts prior receipt

Can be substitutable for a bounded use while **not** being same-Run continuation. Explicit prior-evidence adoption is part of T.

R3 is falsified as a general equivalence model.

### T5 — same output, stale Context

Fails any U requiring current/sufficient Context despite matching output. R2 is falsified.

### T6 — same Context bytes, external authority/currentness changed

Fails when U requires the effective authority/currentness relation. R4 is falsified.

### T7 — profile/exposure set changes; stale selection reused

Fails readmission/currentness obligation. Old selection cannot cross T unchanged merely because its requested profile still has the same name.

### T8 — process restart reconstructs same admitted Run

May preserve same-Run continuation only if Campaign-1 continuation/recovery criteria pass. Process identity is not Run identity.

### T9 — restart creates successor Run with explicit prior evidence

Can preserve substitution/accountability obligations while failing same-Run identity. This is not contradictory.

### T10 — provider implementation changes, required semantics preserved

Potentially preserves U. Provider implementation identity is not fundamental.

### T11 — provider change weakens dispatch/effect evidence semantics

Fails U if U requires Campaign-3 standing/reconciliation guarantees, even if final text output appears equivalent.

### T12 — unresolved prior realization at transition

Must remain unresolved or be reconciled through admissible evidence. Reconfiguration cannot reset it. R7 falsified.

### T13 — capability external Tool becomes internalized computation

No automatic pass/fail. FunctionalPlacement and authority/effect/accountability obligations must be reevaluated. If U depends on external receipt/effect fencing, internalization may fail U unless equivalent owner-grounded obligations are re-established.

### T14 — same label, external truth owner changes

Label equality does not preserve owner authority. U requires explicit owner/claim rebinding where relevant.

### T15 — locus moves, Network service claim remains available

Harness may preserve its U obligations using an externally grounded Network claim; it does not prove Network path equivalence itself.

### T16 — locus moves, required reachability disappears

Fails preservation because an external required capability claim is no longer satisfied. Harness reports the owner-grounded failure rather than deriving network theory.

### T17 — OCSS copied but unresolved unknown omitted

Fails accountability preservation. Evidence copying is not semantic preservation. R12 falsified.

### T18 — OCSS explicitly adopted/rebound, roles/unknowns preserved

May preserve U even if storage location/Run changes.

### T19 — B0→B1 safe, reverse loses evidence

Directly establishes directionality. `Preserves_U(B0→B1)` does not imply reverse preservation. R10 global symmetry falsified.

### T20 — different outputs under non-output U

Does not falsify preservation. R2/output-equivalence framing is insufficient in both directions.

### T21 — live loop mutation without bounded admission

Live hot reload is not required and may violate identity/Context/accountability obligations. Successor-attempt substitution can be safer and semantically clearer. R11 falsified.

### T22 — cut moves and Harness claims domain truth ownership

Owner firewall violation. R8 falsified.

## 9. Rival standing

| Rival | Standing |
|---|---|
| R1 Same Implementation Equals Equivalent | FALSIFIED_IN_SCOPE |
| R2 Same Output Equals Equivalent | FALSIFIED_IN_SCOPE |
| R3 Same Run ID Equals Equivalent | FALSIFIED_IN_SCOPE |
| R4 Same Context Bytes Equals Equivalent | FALSIFIED_IN_SCOPE |
| R5 Same Tool/Capability Names Equals Equivalent | FALSIFIED_IN_SCOPE |
| R6 Successful Restart Equals Same Run | FALSIFIED_IN_SCOPE |
| R7 Reconfiguration Resets Unknown Effect | FALSIFIED_IN_SCOPE |
| R8 Cut Movement Transfers Truth Ownership | FALSIFIED_IN_SCOPE |
| R9 Newer Configuration Automatically Supersedes Old | FALSIFIED_IN_SCOPE |
| R10 Equivalence Is Global and Symmetric | FALSIFIED_IN_SCOPE |
| R11 Live Hot-Reload Is Required | FALSIFIED_IN_SCOPE |
| R12 Evidence Copy Equals Accountability Preservation | FALSIFIED_IN_SCOPE |

## 10. Derived-law candidates

### L-C5-1 — Reconfiguration Preservation is Use-Relative and Directional

`Preserves_U(B0→B1)` is primitive; symmetric equivalence is derived only when required directions hold.

### L-C5-2 — Valid Reconfiguration != Old-Contract Preservation

A transition can be legitimately readmitted under a new contract while failing preservation of the old one.

### L-C5-3 — Structural Sameness != Operational Preservation != Behavioral Agreement

Implementation/configuration identity and sampled output equality are neither necessary nor sufficient.

### L-C5-4 — Run Identity != Reconfiguration Substitutability

Same-Run continuation and bounded successor substitution are distinct relations.

### L-C5-5 — Cut Movement != Truth-Owner Transfer

Functional placement/mediation can move without transferring external semantic authority.

### L-C5-6 — Reconfiguration Cannot Reset Unresolved Realization Standing

Unknown/partial/conflicted effect standing crosses T until admissibly reconciled.

### L-C5-7 — Evidence Copy != Accountability Preservation

OCSS preservation requires role/currentness/unknown/lineage-aware adoption or rebinding.

### L-C5-8 — Transition Lineage is Semantically First-Class

B0/B1 endpoint similarity cannot replace the semantics of adoption/revocation/rebinding/reconciliation carried by T.

### L-C5-9 — Preservation Composition Requires Obligation Compatibility

Directional preservation edges do not compose by path reachability alone.

These remain provisional until closeout.

## 11. Campaign 1–4 compatibility

- Campaign 1: same-Run continuation is one preservation dimension, not universal equivalence.
- Campaign 2: Context obligations, not bytes, determine Context preservation.
- Campaign 3: unresolved Q standing must survive T unless reconciled.
- Campaign 4: OCSS adoption/rebinding must preserve required roles/unknowns/lineage.

No completed campaign is reopened.

## 12. Foundation pressure

`NO_FOUNDATION_PRESSURE` after Round 1.

OPUR composes existing Cut Relativity, reference/placement/exposure, Context, Invocation/realization, operational identity and accountability relations. The directional transition criterion is a derived project law, not deletion-essential new Foundation responsibility.

## 13. Round 2 information-positive targets

Existing engineering can directly test:

1. attempt-bound morphology selection;
2. stale available-profile Context rejection;
3. Harness refusal to auto-select/rank morphology;
4. successor attempt changes loop identity with exact prior receipt adoption;
5. no live hot-reload/factory surface;
6. scheduling morphology changes while Tool authority stays exact;
7. distinct morphologies share the same granted Tool surface;
8. unknown external effect stops both morphologies;
9. deliberation record remains non-authoritative;
10. fresh-process recovery preserves settled/pending Tool standing.

Process/locus migration, provider replacement, internalization/externalization, authority expansion and OCSS rebuttal preservation remain conceptual/future evidence unless current fixtures directly exercise them.

## 14. Round 1 close

`P5 -> P5'` is a substantive revision.

> **The semantic question is not whether two Harness configurations are “the same”. It is whether a particular transition preserves every obligation required for a bounded operational use, with identity, authority, uncertainty and accountability kept explicit.**
