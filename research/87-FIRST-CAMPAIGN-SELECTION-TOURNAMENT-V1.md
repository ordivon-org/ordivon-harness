# 87 — HARNESS FIRST CAMPAIGN SELECTION TOURNAMENT v1

**Control task:** `task:harness-first-campaign-selection-tournament-20260818`  
**Foundation effect:** none — HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Decision question

Which bounded research campaign should be the first post-Constitution Harness investigation?

Candidates from Frontier Audit v1:

1. Run Identity Equivalence;
2. Recovery Equivalence;
3. Context Equivalence / Sufficiency;
4. Rich Effect Semantics;
5. Multi-Agent / Federated Operational Mediation;
6. Operational Accountability Graph.

The tournament does not use one weighted universal score. Criteria remain typed because information gain, destructive-testability, cross-owner risk and engineering leverage are not naturally commensurable.

## 2. Typed criteria

- **Information gain** — likelihood of sharpening or revising the project-level theory rather than merely adding examples.
- **Destructive-testability** — availability of rival constructions and concrete cases capable of falsifying the current architecture.
- **Architecture-falsification power** — whether failure would force revision of Operational Spine / Families / derived laws rather than a local patch.
- **Cross-owner significance** — relevance to owner-preserving interfaces.
- **Engineering leverage** — availability of current Ordivon Harness surfaces for dogfood and likely downstream value if the theory survives.
- **Evidence availability** — whether exact current artefacts/behaviours can support a bounded investigation now.
- **Boundary-contamination risk** — danger that the campaign would accidentally annex Runtime, Host, Network, Normative, Human, World/domain or Computing truth.

## 3. Candidate comparison

### C1 — Run Identity Equivalence

Strengths:

- very high information gain: directly sharpens HaF60 plus the HaF51–61 Operational Spine;
- high destructive-testability through process restart, provider/model change, Context reconstruction, migration, branch/divergence and replay variants;
- very high architecture-falsification power: a failed identity criterion can expose insufficient distinctions among Reference, ContextFrame, Invocation lineage, RunEpisode and ControlFlowState;
- high current evidence availability from immutable attempts/contracts, snapshots, WorkingSet continuity, Provider/Tool continuation and Run receipts;
- moderate/low contamination risk when framed as Harness identity rather than execution/domain truth.

Weakness:

- identity studied only in static examples risks becoming classificatory rather than operationally destructive.

Dependency finding:

- failure/recovery scenarios are the strongest available adversarial environment for testing Run identity.

### C2 — Recovery Equivalence

Strengths:

- very high destructive-testability: kill/restart/reconstruct boundaries can be placed before dispatch, after dispatch, after possible effect, after receipt, and after Context update;
- very high engineering leverage because current Harness already contains continuity, reconciliation, WorkingSet reconstruction, Tool intent/fence/receipt and UNKNOWN-effect handling;
- high architecture-falsification power across ContextFrame, Invocation lineage, Result attribution and ControlFlowState;
- high cross-owner significance at the Harness↔Runtime and Harness↔Host boundaries.

Weaknesses:

- cannot define “valid continuation” without a criterion for what operation/Run is supposed to remain identical;
- can drift into full external-effect ontology unless uncertain effect is treated as an external adversarial fact rather than Harness-owned physical truth.

Dependency finding:

- Recovery Equivalence semantically depends on Run Identity Equivalence, while simultaneously providing its best destructive fixtures.

### C3 — Context Equivalence / Sufficiency

Strengths:

- high information gain for Operational Epistemics;
- high engineering leverage from WorkingSet/WorkingView and canonical-history separation;
- relatively low boundary contamination;
- strong destructive cases via removal, substitution, stale provenance, authority/version change and different model-visible projections.

Weaknesses:

- it sharpens one major slice of Harness but exercises less of the entire Operational Spine than identity-under-failure;
- some equivalence questions require a fixed operation identity and success criterion first.

Decision:

- retain as a strong second-wave candidate; use Context changes as fixtures in Campaign 1 without attempting a complete Context Equivalence theory.

### C4 — Rich Effect Semantics

Strengths:

- very high practical importance and destructive-testability;
- strong Runtime bridge and immediate leverage for duplicate/partial/delayed/irreversible-effect safety.

Weaknesses:

- highest boundary-contamination risk among the near-term candidates: physical effects belong to Runtime/external owners, causal/domain consequences may belong to World/domain owners, and permissibility/remedy may belong to Normative;
- a whole rich-effect theory is broader than required to test the current Harness architecture.

Decision:

- do not select as first standalone campaign. Campaign 1 may use only the narrow adversarial fact `effect may have occurred while Harness evidence is incomplete` without claiming a general effect ontology.

### C5 — Multi-Agent / Federated Operational Mediation

Strengths:

- potentially very high information gain and strong pressure on identity, authority, Network and coordination assumptions.

Weaknesses:

- broadest cross-owner dependency surface;
- lower mature engineering evidence availability than single-Run continuity;
- likely inherits unresolved single-Run identity/recovery questions and would multiply ambiguity rather than isolate it.

Decision:

- defer until a single-Run identity/recovery criterion survives destructive testing.

### C6 — Operational Accountability Graph

Strengths:

- strong engineering value; current Run Receipt, CompletionProposal, Invocation/Tool evidence and provenance surfaces provide substantial substrate;
- meaningful cross-owner value for bounded claims and auditability.

Weaknesses:

- depends on stable identity and attribution nodes; an accountability graph built before Run/Invocation recovery identity is sharpened risks encoding unstable referents;
- less direct Foundation/Operational-Spine falsification power than identity-under-failure.

Decision:

- defer until Campaign 1 supplies sharper identity/recovery semantics; then revisit as a likely consumer.

## 4. Structural dependency result

The tournament rejects treating Run Identity Equivalence and Recovery Equivalence as independent competitors.

They form a **minimal paired problem**:

`Run Identity criterion -> defines what continuity is supposed to preserve`

while

`Failure / recovery -> supplies the strongest destructive test of that identity criterion`.

Neither requires a complete Rich Effect Semantics theory. Campaign fixtures need only distinguish externally supplied possibilities such as:

- definitely not dispatched;
- dispatched but effect status unknown;
- effect externally evidenced;
- receipt/result persisted or lost;
- Context/WorkingSet update persisted or lost.

Physical-effect truth remains Runtime/external-owner truth.

## 5. Tournament decision

**SELECTED FIRST CAMPAIGN:**

# Operational Identity Under Failure
## Run Identity & Recovery Equivalence

Programme home: **D — Operational Identity & Recovery**.

This is a paired campaign, not a new Foundation and not HaF62.

### Bounded campaign purpose

Derive and destructively test a technology-neutral criterion for when a recovered operational state is a valid continuation of the same Harness RunEpisode, versus when continuity must split, terminate, remain UNKNOWN, or require a new Run identity.

### Explicit non-goals

The campaign will not:

- create HaF62;
- build a universal workflow ontology;
- define Runtime Job/Attempt identity;
- define physical-effect truth;
- solve full Context Equivalence;
- solve full Multi-Agent mediation;
- build the final Accountability Graph;
- change current engineering behaviour merely to make the theory pass.

## 6. Why this candidate wins without scalarization

The selected pair is the only candidate that simultaneously:

- targets the current Operational Spine's central unresolved identity claim;
- has immediate destructive fixtures with exact current engineering evidence;
- can falsify several existing distinctions rather than merely enrich one family;
- is narrow enough to remain Harness-owned;
- serves as a prerequisite for Multi-Agent identity and Accountability work;
- can consume uncertain-effect cases without annexing external effect ontology.

Context Equivalence remains close behind, but it is not a prerequisite for starting the selected campaign because Context changes can first be treated as controlled fixture dimensions. A complete Context Equivalence criterion can be researched separately after identity-under-failure reveals which Context differences are actually continuity-critical.

## 7. Required next-campaign prebinding

Before any execution-backed dogfood, Campaign 1 must prebind at least:

- Proposition P1 — a candidate same-Run continuation criterion;
- Rival R1 — identity is reducible to a simpler key such as process/session/contract lineage or caller label;
- Rival R2 — recovery identity cannot be technology-neutral and is implementation-defined;
- Falsifiers covering false continuity and false split;
- evaluator rules for SAME_RUN / NEW_RUN_REQUIRED / TERMINAL_OR_UNKNOWN / INSUFFICIENT_EVIDENCE;
- stop conditions preventing expansion into full Effect, Context or Multi-Agent theory.

## 8. Standing after tournament

- `NextHarnessResearchCampaign = Operational Identity Under Failure — Run Identity & Recovery Equivalence`.
- `NextHarnessFoundationRoute = UNKNOWN`.
- `HaF62 = UNKNOWN / NOT SELECTED / NOT ADMITTED`.
- FoundationExpansionPause remains true.
