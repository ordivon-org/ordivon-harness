# 98 — CAMPAIGN 2 ROUND 3 + CLOSEOUT
# Operational Context Equivalence — Boundary Audit and Final Result

**Campaign task:** `task:harness-campaign2-operational-context-equivalence-20260818`  
**Charter:** `94-CAMPAIGN2-OPERATIONAL-CONTEXT-EQUIVALENCE-CHARTER-V1.md`  
**Conceptual result:** `95-CAMPAIGN2-ROUND1-CONCEPTUAL-DESTRUCTIVE-RECONSTRUCTION.md`  
**Dogfood contract/result:** `96-...`, `97-...`

## 1. Final classification

- Original P2: **REVISED**.
- Revised P2': **SUPPORTED_IN_SCOPE**.
- Campaign result: `CRITERION_REVISED` with the revised relation stack supported by conceptual destructive analysis and bounded existing-fixture dogfood.
- Engineering standing: `ENGINEERING_SUPPORT_IN_SCOPE`.
- Owner-boundary standing: `OWNER_BOUNDARIES_PRESERVED`.
- Foundation pressure: `NO_FOUNDATION_PRESSURE`.

No HaF is reopened. HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 2. Final technology-neutral relation stack

For a bounded **Context Use Contract** `U` carrying explicit decision obligations/discriminants, relevant provenance/currentness/authority requirements and continuation horizon:

### 2.1 Context Projection Validity

A Context projection must be grounded and admissible. Forged provenance, unauthorized expansion, impossible source/generation claims or invented currentness fail before sufficiency is considered.

A valid Context may still be stale, contradictory or insufficient.

### 2.2 Effective Decision Context

The Context that matters at one decision frontier is the admissibly exposed Context there, not merely the durable selected basis. Effective Context can include admitted transient caller or Tool cognition whose lifetime differs from durable selected Context.

### 2.3 Decision Sufficiency

`Sufficient(C,U)` means the effective Context preserves the explicit `U` obligations strongly enough for the bounded operational decision use, including relevant unknown/conflict standing and required provenance/currentness/authority relations.

Harness does not independently invent arbitrary domain relevance. If `U` cannot specify the externally owned discriminants needed to judge sufficiency, the result is `EXTERNAL_DECISION_CONTRACT_REQUIRED`.

### 2.4 Obligation-Preserving Substitution

`C2 >=_U C1` means `C2` can replace `C1` with respect to the bounded operational obligations in `U` without hiding required unknowns/conflicts or weakening required standing.

This relation is directional. It does **not** assert identical Agent behavior or global/domain safety.

### 2.5 Operational Context Equivalence

`C1 ~=_U C2` means mutual obligation-preserving substitution under the same `U`.

It is an interface/use-contract equivalence, not intrinsic semantic identity, byte equality or model-output equivalence.

## 3. World / domain truth boundary

**PASS.**

Campaign 2 does not authorize Harness to decide arbitrary domain relevance or external truth.

The Context Use Contract binds externally supplied or already-Harness-owned operational discriminants; it does not create them by interpretation.

Therefore:

`Context sufficiency for U != external truth completeness`  
`Context equivalence for U != domain semantic equivalence`.

T18 is the decisive boundary case: when no authoritative bounded relevance/discriminant contract exists, Harness must return `EXTERNAL_DECISION_CONTRACT_REQUIRED` rather than guessing.

## 4. Model / Computing boundary

**PASS.**

Campaign 2 explicitly rejects model-output identity as a Context-equivalence authority.

Two obligation-equivalent Contexts may produce different model outputs because model/provider behavior is not defined by Harness Context equivalence. Conversely, the same output may be produced from insufficient, forged or differently grounded Context.

Thus:

`Operational Context Equivalence != Agent/Model Behavioral Equivalence`.

Campaign 2 does not annex model semantics, computational-description semantics or computational-possibility truth.

## 5. Runtime boundary

**PASS.**

Runtime may physically materialize, persist or execute mechanisms used to obtain Context evidence. Physical storage/execution does not determine current Harness Context authority or sufficiency.

Round 2 directly shows materialized bytes may remain outside current cognition.

Therefore:

`Physical availability/materialization != Context selection/sufficiency`.

## 6. Host boundary

**PASS.**

Context sufficiency and retention horizon do not decide durable Host Task identity/completion. A Host Task may continue after one Harness Context becomes insufficient; Harness may require a new Context without changing Host Task standing.

`Context sufficiency != Host Task continuity/completion`.

## 7. Normative / authority boundary

**PASS.**

Campaign 2 preserves authority/currentness/provenance standing when they are relevant to `U`; it does not decide whether an authority relation is normatively legitimate.

An unauthorized/forged projection can be invalid from Harness's bound operational contract without Harness becoming the owner of general normative legitimacy.

`Authority standing carried by Context != normative correctness`.

## 8. Network boundary

**PASS / NOT DEEPLY EXERCISED.**

Campaign 2 does not equate cross-locus availability with Context equivalence. Future remote/federated Context transfer must preserve `U` obligations while Network retains reachability/transport/substrate truth.

This supplies a consumer interface for later Boundary Reconfiguration / Multi-Agent work without solving it here.

## 9. Accountability boundary

**PASS.**

Campaign 2 may include explicit provenance/dependency obligations in `U`, as demonstrated conceptually by T8/T9, but does not define the complete Accountability Graph or universal evidence-sufficiency theory.

Its contribution is narrower:

> if an accountability/assurance decision declares provenance/dependency standing as required, Context substitution must preserve it.

Operational Accountability remains a separate downstream frontier.

## 10. Rich Effect boundary

**PASS.**

Campaign 2 does not define delayed/partial/irreversible effect ontology. Tool observations may enter effective Context as grounded operational evidence, but effect truth remains Runtime/external-owner truth and effect semantics remains Programme C research.

## 11. Campaign-1 compatibility audit

**PASS.**

Campaign 1 established a three-stage recovery criterion and permitted provenance-preserving Context change without defining Context Equivalence.

Campaign 2 sharpens the missing relation:

- recovery reconstruction can require a valid Context projection;
- a recovery decision frontier can require `Sufficient(C,U_recovery)`;
- transient Context may be sufficient for an immediate frontier yet insufficient for a future recovery horizon;
- same Run identity does not imply equivalent or sufficient Context;
- equivalent Context under one `U` does not imply same Run identity.

Therefore:

`Run Identity` and `Context Equivalence/Sufficiency` are orthogonal but composable relations.

No Campaign-1 result is reopened.

## 12. Rival closeout

| Rival | Final standing |
|---|---|
| R1 Byte Identity | FALSIFIED_IN_SCOPE |
| R2 Model-Output Equivalence | FALSIFIED_IN_SCOPE |
| R3 Superset Monotonicity | FALSIFIED_IN_SCOPE |
| R4 Provenance Blindness | FALSIFIED_IN_SCOPE |
| R5 Newest Wins | FALSIFIED_IN_SCOPE |
| R6 Lifetime Blindness | FALSIFIED_IN_SCOPE + engineering support |
| R7 WorkingSet Identity | FALSIFIED_IN_ENGINEERING_SCOPE as universal criterion |
| R8 Global Semantic Equivalence | FALSIFIED_IN_SCOPE |

Cross-implementation universality remains unproven: current evidence is one implementation family with multiple distinct Context mechanisms.

## 13. Derived laws admitted from Campaign 2

### Context Validity != Currentness != Sufficiency

Grounded representation, current standing and bounded decision sufficiency are independent roles.

### Durable Context Basis != Effective Decision Context

The durable selected basis is not identical to the Context admissibly exposed at a decision frontier. Transient admitted cognition can affect effective Context without becoming durable selected Context.

### Context Sufficiency is Use-Contract and Horizon Relative

No intrinsic global sufficiency relation exists. A Context pair can be equivalent for one bounded decision/horizon and non-equivalent for another.

### Context Superset != Context Dominance

Adding Context does not automatically increase validity, sufficiency or equivalence; added material can be irrelevant, contradiction-revealing, obligation-changing or invalid.

### Operational Context Equivalence != Agent Behavioral Equivalence

Mutual obligation-preserving substitution under a bounded use contract does not assert identical model/Agent decisions or world outcomes.

These are derived project laws, not Foundations.

## 14. Foundation-pressure audit

Final classification: `NO_FOUNDATION_PRESSURE`.

The final relation stack composes existing Harness responsibilities for representation/provenance, retention/history/cognition, ContextFrame, authority and control. The distinction between durable basis and effective exposure is a cross-family/project law over existing roles, not a deletion-essential new Foundation responsibility.

HaF0–HaF61 remain frozen. HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 15. Frontier delta after Campaign 2

Materially deepened:

- P-B1 Context Equivalence / Sufficiency: bounded technology-neutral relation stack established in scope;
- decision-sufficient operational views: sharpened as use-contract/horizon-relative;
- provenance/currentness/lifetime conditions for Context substitution: materially sharpened.

Still open:

- Rich Effect Semantics;
- Operational Accountability Graph;
- Boundary Reconfiguration Equivalence;
- Multi-Agent / Federated Operational Identity;
- cross-implementation invariance of Campaign 1/2 criteria;
- task/domain-specific construction of Decision/Context Use Contracts where owner semantics are not already explicit.

Campaign 2 does **not** select Campaign 3.

`NextHarnessResearchCampaign = UNKNOWN` pending a new typed frontier decision.  
`NextHarnessFoundationRoute = UNKNOWN`.

## 16. Campaign 2 closeout

**CAMPAIGN 2 COMPLETE.**

Final capsule:

- Project: Harness — Agent Operational Mediation.
- Campaign: Operational Context Equivalence — Decision-Sufficient Views, Provenance & Safe Omission.
- Result: P2 revised to P2'; P2' supported in tested scope.
- Key advance: Context equivalence demoted from intrinsic identity to derived mutual obligation-preserving substitution under bounded use/horizon.
- Additional advance: durable Context basis separated from effective decision Context.
- Dogfood: 7/7 prebound existing fixtures passed.
- Owner boundaries: preserved.
- Foundation pressure: none.
- Next campaign: intentionally unknown.
