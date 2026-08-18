# 92 — CAMPAIGN 1 ROUND 3 + CLOSEOUT
# Operational Identity Under Failure — Owner Boundary Audit and Final Result

**Campaign task:** `task:harness-campaign1-operational-identity-under-failure-20260818`  
**Prebinding:** Campaign 1 Charter v1 (`88-...`)  
**Conceptual result:** Round 1 (`89-...`)  
**Engineering dogfood:** Round 2 contract/result (`90-...`, `91-...`)

## 1. Final campaign classification

- Original proposition P1: **REVISED**.
- Revised proposition P1': **SUPPORTED_IN_SCOPE**.
- Campaign-level closeout class: `CRITERION_REVISED` with the revised criterion supported by conceptual destructive analysis and bounded engineering dogfood.
- Engineering standing: `ENGINEERING_SUPPORT_IN_SCOPE`.
- Owner-boundary standing: `OWNER_BOUNDARIES_PRESERVED`.
- Foundation pressure: `NO_FOUNDATION_PRESSURE`.

No HaF is reopened. HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 2. Final technology-neutral criterion

A recovery attempt is evaluated in three stages rather than by one boolean `same run / not same run` test.

### Stage 0 — Recovery Projection Standing

Determine whether the reconstructed state is an admissible projection of authoritative prior operational facts:

- `VALID_RECONSTRUCTION`
- `INVALID_RECONSTRUCTION`
- `RECONSTRUCTION_UNDERDETERMINED`

A projection is invalid if it silently widens authority, rewrites settled operational history, erases a required Invocation/result obligation, invents provenance, or exposes unsupported continuations.

### Stage 1 — Run Identity Standing

For a valid reconstruction, determine whether the state continues the same RunEpisode:

- `SAME_RUN`
- `NEW_RUN_REQUIRED`
- `IDENTITY_UNKNOWN`

Same-Run identity requires an admitted continuation relation from the prior authoritative Run state. Shared lineage ancestry alone is insufficient. Explicit branch/replay edges may preserve provenance while creating a new RunEpisode continuation identity.

### Stage 2 — Continuation Standing

For a valid reconstructed Run state, determine what may safely happen next:

- `SAFE_CONTINUE`
- `RECONCILE_FIRST`
- `TERMINAL_UNKNOWN`
- `INSUFFICIENT_EVIDENCE`

Continuation must account for every Invocation crossing the recovery frontier strongly enough to prevent unsafe redispatch, false result attribution or unsupported authority gain. A Run may remain `SAME_RUN` while continuation is blocked.

## 3. Final continuity invariants

The surviving criterion requires the following technology-neutral invariants.

### C1 — Admitted continuation relation

Run identity follows an admitted continuation edge/topology, not process lifetime, session labels, shared ancestor state or equal serialization.

### C2 — No established-history rewrite

Settled operational facts relevant to future action/attribution remain preserved or mechanically reconstructible. Recovery cannot obtain validity by forgetting contradictory history.

### C3 — Authority/context provenance

Authority/exposure and Context may legitimately change during a Run, but changes must be provenance-preserving/admitted. Recovery uncertainty never creates new authority.

### C4 — Invocation frontier accounting

Settled, pending, unresolved and reconciled operations remain distinguishable at the recovery boundary. Harness need not determine physical effect truth; it must preserve the obligation to obtain/consume the appropriate external evidence before acting where that truth matters.

### C5 — Conservative continuation

Recovered state may expose fewer actions than the pre-failure state. Missing evidence cannot justify a new continuation that the available authority/evidence does not support.

### C6 — Explicit continuation topology

One linear continuation point cannot silently admit multiple divergent current successors. Implementations may use revision fences, CAS, leases, logs or other mechanisms; the semantic requirement is unambiguous successor/branch standing, not one specific mechanism.

## 4. Runtime boundary audit

**PASS.**

Campaign 1 never requires Harness to determine whether a physical external effect actually occurred. The criterion consumes typed external evidence/standing such as non-dispatch evidence, receipt status, reconciled outcome or unresolved effect status.

Round 2 dogfood reinforces this boundary:

- Tool receipts carry Runtime job references/evidence;
- reconciled receipt lineage advances Harness operational standing without making Harness the physical executor;
- completed Tool operations are not redispatched merely because the Harness process restarted.

Therefore:

`Harness recovery obligation != Runtime physical-effect truth`.

## 5. Host boundary audit

**PASS.**

Campaign 1 concerns bounded Harness RunEpisode continuation only. It makes no claim that same-Run recovery determines durable Host Task completion or identity.

The existing firewall remains:

`Harness RunEpisode != Host Task`  
`CompletionProposal != Host Task completion`.

A Host Task may survive many Harness Runs, and a Harness Run may become terminal/unknown without deciding Host Task standing.

## 6. Normative boundary audit

**PASS.**

P1' requires recovery to preserve the lineage of authority/exposure and reject silent authority gain. It does not decide whether a permission, obligation or revocation is normatively legitimate.

Thus:

`authority-state continuity != normative correctness`.

Ordivon Normative remains the owner of constitutive/normative admission and consequence semantics.

## 7. Network boundary audit

**PASS / NOT EXERCISED DEEPLY.**

Cross-locus Run migration was intentionally not executed in Campaign 1. P1' requires only that future migration preserve an admitted continuation topology and consume Network-owned realization/reachability evidence where needed.

No Network substrate truth is annexed.

This remains a future extension rather than a missing prerequisite for the single-Run criterion.

## 8. Human / World / domain boundary audit

**PASS.**

Campaign 1 makes no claim to own human cognition, world causality or domain success criteria. Result/effect standing remains evidence-mediated and owner-relative.

`Result attribution != domain semantic success` remains intact.

## 9. Computing boundary audit

**PASS.**

The final criterion is stated in terms of operational roles/relations rather than current classes, database rows or Provider wire formats. It does not claim ownership over the semantics of computational descriptions or computational possibility.

## 10. Context-theory stop-condition audit

**PASS.**

Campaign 1 did not need a full Context Equivalence theory.

Round 1 T5 only established the weaker result that byte-identical Context is neither necessary nor sufficient for Run identity. The criterion requires provenance-preserving operational commitments relevant to continuation, while the general question of when two decision-sufficient Contexts are semantically equivalent remains open Programme B research.

Context Equivalence therefore remains a genuine independent frontier.

## 11. Effect-theory stop-condition audit

**PASS.**

Campaign 1 did not need a general physical/causal Effect ontology.

It consumed only typed external status relevant to Harness continuation:

- not dispatched;
- possibly effected / unresolved;
- reconciled/externally evidenced;
- persisted receipt/result standing.

Rich Effect Semantics remains a separate Programme C frontier.

## 12. Rival closeout

| Rival | Final Campaign 1 standing |
|---|---|
| R1 Label/Key Identity | FALSIFIED_IN_SCOPE |
| R2 Process/Executor Identity | FALSIFIED_IN_SCOPE |
| R3 Snapshot Equality | FALSIFIED_IN_SCOPE |
| R4 Immutable Contract Sufficiency | FALSIFIED_IN_SCOPE |
| R5 Receipt-Complete Recovery | FALSIFIED_IN_SCOPE |
| R6 Implementation-Defined Identity | WEAKENED / NOT FULLY FALSIFIED |

R6 remains a bounded residual: Ordivon Harness dogfood shows the same higher-level distinctions across Provider, Tool, WorkingSet and fresh-process mechanisms, but one implementation family cannot establish universal cross-implementation invariance.

This residual does not block local Campaign 1 closeout.

## 13. Derived laws admitted from Campaign 1

Campaign 1 promotes two project-level derived laws, not Foundations.

### Recovery Validity != Run Identity != Resumability

Whether a reconstructed projection is valid, whether it belongs to the same RunEpisode, and whether external continuation is currently safe are independent semantic questions. None may be inferred automatically from another.

### Lineage Ancestry != Continuation Identity

Shared provenance or ancestor state does not establish same RunEpisode continuation identity. Continuation requires an admitted continuation relation; branching can preserve ancestry while splitting continuation identity.

These laws are materialized into `30-DERIVED-LAWS.md` by this closeout.

## 14. Foundation-pressure audit

Final classification: `NO_FOUNDATION_PRESSURE`.

Reasons:

- the three-stage recovery model composes already-established Reference, Context, Authority, Invocation, Result, Run and Control distinctions;
- P1-G continuation topology is expressible through existing lineage/Run/control foundations;
- no new owner-native responsibility outside HaF0–HaF61 is deletion-essential;
- no frozen HaF claim requires reopening.

`HaF62 = UNKNOWN / NOT SELECTED / NOT ADMITTED` remains canonical.

## 15. Frontier delta after Campaign 1

Closed/deepened:

- P-D1 Run Identity Equivalence: materially deepened; bounded criterion established in scope.
- P-D2 Recovery Equivalence: materially deepened; three-stage recovery criterion established in scope.

Still open:

- P-B1 Context Equivalence / Sufficiency;
- P-C1 Rich Effect Semantics;
- P-E1 Operational Accountability Graph;
- P-A1 Boundary Reconfiguration Equivalence;
- Multi-Agent / federated operational identity;
- R6 cross-implementation invariance of the criterion.

No next research campaign is selected by this closeout.

`NextHarnessResearchCampaign = UNKNOWN` pending a new typed selection decision.  
`NextHarnessFoundationRoute = UNKNOWN`.

## 16. Campaign 1 final closeout

**CAMPAIGN 1 COMPLETE.**

Final capsule:

- Project: Harness — Agent Operational Mediation.
- Campaign: Operational Identity Under Failure — Run Identity & Recovery Equivalence.
- Result: original P1 revised; P1' supported in the tested scope.
- Key semantic advance: three independent recovery axes + admitted continuation topology.
- Engineering dogfood: 6/6 prebound fixtures passed under canonical repository environment.
- Owner firewalls: preserved.
- Foundation pressure: none.
- HaF62: remains unknown/not admitted.
- Next campaign: intentionally unknown.
