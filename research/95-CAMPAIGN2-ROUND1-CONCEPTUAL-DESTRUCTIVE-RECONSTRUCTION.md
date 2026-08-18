# 95 — CAMPAIGN 2 ROUND 1
# Conceptual Destructive Reconstruction

**Prebinding authority:** Campaign 2 Charter v1 at commit `92e8fc7` before this analysis.  
**Round type:** conceptual/destructive. Current implementation vocabulary is not ontology authority.

## 1. Round 1 classification

`CRITERION_REVISED`.

P2 survives its central claim: a useful Harness Context relation is technology-neutral only when it is bounded-use-relative and preserves validity, required discriminants, provenance/currentness/authority standing and continuation lifetime rather than bytes or model output.

However two prebound formulations were too coarse:

1. **“Safe operational substitute” is too strong.** Harness can establish preservation of bounded operational obligations; it cannot infer identical Agent behavior, domain outcome or global safety. The directional relation is renamed **Obligation-Preserving Substitution**.
2. **Durable Context basis is not the complete decision Context.** A decision frontier is evaluated against the effective Context exposed to the Agent at that frontier, which may include transient caller/Tool cognition not present in the durable selected basis. Future-horizon sufficiency additionally depends on what can remain/reconstruct as authoritative Context.

Therefore P2 is revised to P2'.

## 2. Revised relation vocabulary

For a fixed bounded **Context Use Contract** `U`, comprising decision obligations/discriminants, authority/provenance/currentness requirements and a continuation horizon:

### Layer 0 — Context Projection Validity

`Valid(C, U)` means the Context projection has grounded provenance/authority/representation standing. A stale source can be **validly represented as stale**; validity does not mean current or sufficient.

### Layer 1 — Effective Decision Context

`Effective(C, U)` is the Context actually admissibly exposed at the decision frontier, including the relevant durable Context basis plus admitted transient ingress/observations.

This is distinct from the durable basis used to reconstruct later Context.

### Layer 2 — Decision Sufficiency

`Sufficient(C, U)` means `Effective(C,U)` preserves every explicitly required `U` discriminant, relevant unknown/conflict standing and required provenance/currentness/authority relation strongly enough for the bounded operational decision contract.

This remains directional/task-relative and makes no claim that the Agent will choose correctly.

### Layer 3 — Obligation-Preserving Substitution

`C2 >=_U C1` means replacing `C1` with `C2` preserves every obligation standing required by `U` that `C1` validly supplies, without hiding a required contradiction/unknown or weakening required provenance/currentness/authority/lifetime standing.

This is not called globally “safe” because safety/outcome semantics may belong outside Harness.

### Layer 4 — Operational Context Equivalence

`C1 ~=_U C2` means mutual obligation-preserving substitution under the **same** `U`:

`C1 >=_U C2` and `C2 >=_U C1`.

This is an **interface/obligation equivalence**, not behavioral equivalence.

## 3. Proposition P2'

### P2'-A — Validity != Currentness != Sufficiency

A Context can be validly grounded yet stale, superseded, contradictory or insufficient. Currentness/sufficiency cannot be inferred from projection validity.

### P2'-B — Durable Context Basis != Effective Decision Context

Selected/durable Context and effective decision exposure are distinct roles. Transient admitted material can matter now without becoming durable Context; durable material can survive a horizon where transient material expires.

### P2'-C — Sufficiency is Context-Use-Contract relative

No task-independent sufficiency relation is available without annexing external relevance/truth. Missing external discriminants produce `EXTERNAL_DECISION_CONTRACT_REQUIRED` rather than a guessed verdict.

### P2'-D — Obligation preservation is directional

One Context can dominate another for `U` without mutual equivalence. Extra valid information may make `C2 >=_U C1` while `C1 >=_U C2` fails if the extra information changes a required unknown/conflict/claim basis.

### P2'-E — Equivalence is derived mutual substitution

Operational Context Equivalence remains meaningful only as a scoped quotient under one `U`; it is not an intrinsic Context identity relation.

### P2'-F — Content equality and output equality are non-authoritative

Byte/content equality is neither necessary nor sufficient when provenance/currentness/lifetime differs. Model-output equality/difference does not define the relation.

### P2'-G — Context superset is not a dominance theorem

Adding Context may be irrelevant, may add useful obligations, may reveal contradiction/unknowns, or may be invalid/unauthorized. Therefore `C1 subset C2` alone establishes no Context order.

### P2'-H — Horizon changes the relation

A substitution may hold for `U_now` but fail for `U_resume` because retention/reconstructibility is part of the later use contract.

### P2'-I — Safe omission means obligation-preserving omission

Omission is admitted only if validity and all `U` obligation standings survive. It does not require identical Agent output and cannot hide a known required unknown/conflict.

## 4. Fixture evaluation

### T1 — identical bytes, grounded vs forged provenance

Result: forged projection is `INVALID_CONTEXT_PROJECTION`; not equivalent.

This falsifies R1 Byte Identity and R4 Provenance Blindness. Content identity cannot repair missing provenance authority.

### T2 — different serialization/order, same grounded sources and obligations

Result: potentially equivalent under `U` when serialization/order is not itself an obligation and effective exposure preserves all required distinctions.

This falsifies byte equality as a necessary condition.

Limit: if ordering is explicitly operationally significant to `U`, equivalence need not hold.

### T3 — same content, current generation vs explicitly superseded generation

Result: both may be valid representations of historical facts, but they are not interchangeable for a current-state `U` when generation/currentness is required.

Key revision: stale != invalid. `Validity != Currentness` must be explicit.

### T4 — newer-looking source without authority/supersession edge

Result: recency alone does not establish currentness or substitution. A newer timestamp-like presentation can coexist with lower/no authority.

R5 Newest Wins is falsified in scope.

### T5 — add F/U-irrelevant grounded material

Result: the added material may preserve obligation equivalence under `U`, but Campaign 2 cannot claim identical Agent behavior.

This is where “safe operational substitute” was too broad. The correct result is obligation equivalence, not behavioral equivalence.

### T6 — add grounded contradiction relevant to U

Result: if `C1` presented a settled-looking value and `C2` adds a relevant grounded contradiction, `C2` may be **more epistemically informative** yet not equivalent to `C1`. The appropriate obligation standing may change from settled to unresolved/contested.

This falsifies Superset Monotonicity as an equivalence/dominance rule.

Important: added contradiction does not make `C2` invalid.

### T7 — omit U-essential discriminant/evidence

Result: insufficient; substitution fails.

This is the basic false-sufficiency guard.

### T8 — omit duplicate bytes with the same upstream dependency

Result: potentially obligation-preserving when `U` requires content/standing but not artifact multiplicity. Because the copies have the same dependency, dropping one does not reduce independent corroboration.

This is compatible with the existing law `Multiple artifacts != independent corroboration`.

### T9 — replace independent corroboration with copied duplicate

Result: not equivalent when `U` explicitly requires independent corroboration/assurance standing. Same textual content is insufficient.

This uses only an explicit assurance obligation; it does not build the full Accountability Graph.

### T10 — same bytes transiently and durably available; immediate frontier

Result: potentially mutually sufficient for `U_now` if origin/lifetime is not itself required for the immediate decision.

This does **not** imply equivalence for a future horizon.

### T11 — transient vs durable after continuation/recovery horizon

Result: not equivalent for `U_resume` when transient material is no longer admissibly reconstructible.

R6 Lifetime Blindness is falsified. Context equivalence is horizon-relative.

### T12 — caller ingress vs promoted durable source during same interaction

Result: content may be sufficient for an immediate content obligation, but the two contexts carry different authority/lifetime roles. They are equivalent only for a `U` that does not require those distinctions; they are non-equivalent for a continuation/provenance-sensitive `U`.

This is not ambiguity in the theory; it is evidence that `U` is essential.

### T13 — same durable selected Context, different transient Tool exchange

Result: same durable Context basis does not establish equivalent **effective decision Context**. If transient evidence is U-relevant, the contexts differ.

R7 WorkingSet Identity is falsified conceptually as a universal criterion.

This produces the `Durable Context Basis != Effective Decision Context` revision.

### T14 — different selected Contexts resolve same explicit U obligations

Result: potentially equivalent despite different source/representation sets, provided validity and all required standing are preserved.

This is the strongest constructive case for technology-neutral operational equivalence.

### T15 — compression preserves summary content but removes exact provenance/unknown required by U

Result: insufficient substitution.

The failure is not “summary bad”; it is exact obligation loss. Campaign 2 therefore does not need a universal summarization-quality theory.

### T16 — forged Context expansion adds apparently useful unauthorized source

Result: invalid projection. More content cannot dominate because validity precedes sufficiency.

R3 Superset Monotonicity is falsified from the validity side.

### T17 — stale and current conflicting sources both retained with explicit relation

Result: potentially sufficient for a `U` that requires current state plus conflict/history awareness. Silently deleting the stale source may be obligation-preserving for a narrow current-value `U`, but not for a diagnostic/history/contestability `U`.

This confirms scope-relativity rather than forcing one universal omission verdict.

### T18 — no explicit domain discriminants for semantic relevance

Result: `EXTERNAL_DECISION_CONTRACT_REQUIRED`.

Harness may bind and preserve Context relations, but it cannot invent the target-domain relevance criterion. R8 Global Semantic Equivalence is falsified in scope.

## 5. Rival standing after Round 1

| Rival | Standing | Primary destructive cases |
|---|---|---|
| R1 Byte Identity | FALSIFIED_IN_SCOPE | T1, T2, T3 |
| R2 Model-Output Equivalence | FALSIFIED_IN_SCOPE conceptually | same output does not ground provenance/sufficiency; behavior can vary under equivalent obligation standing |
| R3 Superset Monotonicity | FALSIFIED_IN_SCOPE | T6, T16 |
| R4 Provenance Blindness | FALSIFIED_IN_SCOPE | T1, T3, T9 |
| R5 Newest Wins | FALSIFIED_IN_SCOPE | T4 |
| R6 Lifetime Blindness | FALSIFIED_IN_SCOPE | T10/T11/T12 |
| R7 WorkingSet Identity | FALSIFIED_AS_UNIVERSAL / engineering support still useful | T13/T14 |
| R8 Global Semantic Equivalence | FALSIFIED_IN_SCOPE | T18 |

## 6. Derived-law candidates

### L-C2-1 — Context Validity != Currentness != Sufficiency

Grounded representation, current standing and decision sufficiency are distinct.

### L-C2-2 — Durable Context Basis != Effective Decision Context

Durable selected Context is not identical to the Context actually exposed at a particular decision frontier; admitted transient cognition may change effective Context without becoming durable basis.

### L-C2-3 — Context Sufficiency is Use-Contract and Horizon Relative

There is no intrinsic global sufficiency relation. The same Context pair can be equivalent now and non-equivalent for later recovery, or equivalent for one decision and non-equivalent for another.

### L-C2-4 — Context Superset != Context Dominance

More Context is not automatically more valid, more sufficient or equivalent. Added material may be irrelevant, contradictory, obligation-changing or invalid.

These remain campaign results until closeout.

## 7. Campaign-1 compatibility check after Round 1

Campaign 1 required “provenance-preserving Context change” without defining general Context Equivalence.

P2' sharpens that statement without reopening Campaign 1:

- same Run continuation does not require Context byte equality;
- a Context transition needed for recovery must at minimum be a valid projection and preserve the recovery decision's bound obligations;
- if the recovery use contract requires future reconstructibility, transient-only Context cannot be treated as equivalent to durable Context;
- Campaign 1 identity and Campaign 2 Context relation remain distinct: `same Run` does not itself prove Context sufficiency.

No contradiction with Campaign 1 is found.

## 8. Foundation pressure

`NO_FOUNDATION_PRESSURE` after Round 1.

All revisions compose existing ContextFrame, representation/provenance, retention/history/cognition, authority and control distinctions. No deletion-essential new Harness-native responsibility appears; no frozen HaF claim requires reopen.

## 9. Round 2 information-positive targets

Existing engineering is useful only where it can attack P2' rather than demonstrate implementation identity.

High-value targets:

1. same durable WorkingSet + different transient effective exposure (T13);
2. transient caller/Tool cognition versus durable promoted/selected Context across horizon (T10–T12);
3. forged/deterministically inconsistent WorkingView projection rejection (T1/T16-like validity pressure);
4. source generation / stale transition / successor WorkingSet fencing (T3/T4-like currentness pressure);
5. historical recall and explicit reselection rather than automatic injection (safe omission/currentness/horizon pressure);
6. changed vs unchanged selected Context producing distinct progress/control consequences without treating content count as the relation.

Do not create new tests merely to confirm P2'.

## 10. Round 1 close

`P2 -> P2'` is a substantive revision.

The most important result is not “we found a Context equality algorithm.” It is the opposite:

> Harness can responsibly state **validity, obligation-relative sufficiency and scoped mutual substitution**; it cannot promote those relations into intrinsic semantic or behavioral identity.

Proceed to a prebound existing-fixture dogfood contract.
