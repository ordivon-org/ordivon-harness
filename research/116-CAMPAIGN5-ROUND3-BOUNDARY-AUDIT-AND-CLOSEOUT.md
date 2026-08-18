# 116 — CAMPAIGN 5 ROUND 3 + CLOSEOUT
# Operational Preservation Under Reconfiguration — Boundary Audit and Final Result

**Campaign task:** `task:harness-campaign5-boundary-reconfiguration-equivalence-20260819`  
**Charter:** `112-CAMPAIGN5-BOUNDARY-RECONFIGURATION-CHARTER-V1.md`  
**Conceptual result:** `113-CAMPAIGN5-ROUND1-CONCEPTUAL-DESTRUCTIVE-RECONSTRUCTION.md`  
**Dogfood:** `114-...`, `115-...`

## 1. Final classification

- Original P5: **REVISED**.
- Revised P5'/OPUR: **SUPPORTED_IN_SCOPE**.
- Campaign class: `CRITERION_REVISED` with directional use-relative preservation supported by conceptual destructive analysis and bounded engineering dogfood.
- Engineering standing: `ENGINEERING_SUPPORT_IN_SCOPE`.
- Evidence-limit standing: `PROVIDER_LOCUS_INTERNALIZATION_AUTHORITY_REAUTH_OCSS_TRANSITION_CASES_CONCEPTUAL_ONLY`.
- Owner-boundary standing: `OWNER_BOUNDARIES_PRESERVED`.
- Foundation pressure: `NO_FOUNDATION_PRESSURE`.

HaF0–HaF61 remain frozen. HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 2. Final semantic core — OPUR

`Boundary Reconfiguration Equivalence` is retained as the campaign/family label. The technology-neutral primitive is **Operational Preservation Under Reconfiguration (OPUR)**.

For pre-configuration `B0`, transition `T`, post-configuration `B1`, and bounded Reconfiguration Use Contract `U`:

`Preserves_U(B0 --T--> B1)`

means every U-required preservation obligation is either:

- `PRESERVED`, or
- `EXPLICITLY_REBOUND_OR_READMITTED` in a manner admitted by U.

Required obligations marked `UNRESOLVED` or `VIOLATED` prevent preservation. Unrequired dimensions remain `NOT_REQUIRED_BY_U` rather than being silently converted into invariants.

The obligation families are:

1. reference/subject;
2. identity/continuation;
3. Context validity/currentness/sufficiency;
4. authority/exposure;
5. functional placement/mediation;
6. realization standing/reconciliation;
7. OCSS accountability;
8. externally owned claims needed by U.

`Equivalent_U` is derived only when all required directions/substitutions hold. It is not the primitive.

## 3. Runtime boundary

**PASS.**

OPUR may consume Runtime-owned evidence about process, Workspace/Job/Attempt or physical realization when U depends on it. Harness does not define general Runtime process equivalence.

A process restart can preserve a Harness Run under Campaign-1 criteria, or create a successor Run under a different relation. Runtime process sameness/difference is neither necessary nor sufficient by itself.

`Runtime process identity != Harness preservation standing`.

## 4. Network boundary

**PASS / NOT DEEPLY EXERCISED.**

A locus transition may preserve U only if required externally grounded Network service/reachability claims remain satisfied. Harness does not infer path/topology equivalence.

`Network path changed` does not automatically mean OPUR failed; `required Network capability unavailable` does fail the corresponding U obligation.

## 5. Normative boundary

**PASS.**

Campaign 5 distinguishes:

- `TransitionValid(U0 -> U1)`;
- `Preserves_U0(B0 -> B1)`.

An authority expansion/revocation can be legitimately re-authorized under a new contract while failing preservation of the old authority envelope.

Harness does not decide whether the new authority is normatively legitimate. That remains Normative/domain-owned.

## 6. World / domain boundary

**PASS.**

Cut movement/internalization/externalization does not transfer domain truth ownership.

A representation moved inside the Agent/Harness remains a representation unless an external owner rule says otherwise. Same output or same stored domain object does not establish domain semantic equivalence.

`Cut Movement != Truth-Owner Transfer`.

## 7. Human boundary

**PASS.**

Changing where human approval, instruction or interaction is mediated can change the Harness cut/exposure relation. It does not make Harness the owner of Human cognition, intent or social legitimacy.

Human-in-the-loop placement is therefore a preservation/bridge obligation when U requires it, not a transfer of Human semantics.

## 8. Host boundary

**PASS.**

Host continues to own durable Host Task continuity plus Journal/CAS/fencing/handoff authority.

A Harness successor Run or morphology change may preserve a bounded use while Host Task continuity remains unchanged. Conversely, Host Task continuity does not prove Harness same-Run preservation.

`Host Task continuity != Harness OPUR != same Run`.

## 9. Accountability boundary

**PASS.**

Campaign 4 OCSS becomes a first-class preservation obligation.

Evidence copied across T is insufficient. Required roles, unknowns, currentness, attribution and lineage must be explicitly preserved/adopted/rebound.

Thus:

`Evidence Copy != Accountability Preservation`.

The preservation claim itself requires accountable transition evidence.

## 10. Campaign-1 compatibility — Identity & Recovery

**PASS.**

Campaign 1 distinguishes same-Run continuation from recovery validity/resumability. Campaign 5 preserves that distinction.

A transition can be:

- same-Run OPUR;
- successor-Run substitutable OPUR;
- valid transition but non-preserving under U;
- failed/unknown transition.

Therefore:

`Run Identity != Reconfiguration Substitutability`.

## 11. Campaign-2 compatibility — Context

**PASS.**

Context preservation is obligation-based, not byte-based. Same bytes under changed authority/currentness can fail U. Different Context serialization can preserve U if the required Effective Decision Context obligations remain satisfied.

`Context Bytes != Context Preservation`.

## 12. Campaign-3 compatibility — Realization

**PASS.**

Unknown/partial/conflicted realization standing required by U crosses T until admissibly reconciled.

Round-2 D8 directly supports this across two morphologies; D10 supports settled/pending preservation across process loss.

`Reconfiguration != uncertainty reset`.

## 13. Campaign-4 compatibility — OCSS

**PASS.**

OCSS support roles and required unknowns do not transfer merely because artifacts are copied. Transition T must preserve/adopt the relevant accountability relations.

Preservation edges themselves do not compose through graph reachability alone; their U obligations, scope and currentness must remain compatible.

## 14. Rival closeout

| Rival | Final standing |
|---|---|
| R1 Same Implementation Equals Equivalent | FALSIFIED_IN_SCOPE |
| R2 Same Output Equals Equivalent | FALSIFIED_IN_SCOPE |
| R3 Same Run ID Equals Equivalent | FALSIFIED_IN_SCOPE + engineering support |
| R4 Same Context Bytes Equals Equivalent | FALSIFIED_IN_SCOPE |
| R5 Same Tool/Capability Names Equals Equivalent | FALSIFIED_IN_SCOPE |
| R6 Successful Restart Equals Same Run | FALSIFIED_IN_SCOPE |
| R7 Reconfiguration Resets Unknown Effect | FALSIFIED_IN_SCOPE + engineering support |
| R8 Cut Movement Transfers Truth Ownership | FALSIFIED_IN_SCOPE |
| R9 Newer Configuration Automatically Supersedes Old | FALSIFIED_IN_SCOPE |
| R10 Equivalence Is Global and Symmetric | FALSIFIED_IN_SCOPE |
| R11 Live Hot-Reload Is Required | FALSIFIED_IN_SCOPE + engineering support |
| R12 Evidence Copy Equals Accountability Preservation | FALSIFIED_IN_SCOPE |

## 15. Derived laws admitted from Campaign 5

### Reconfiguration Preservation is Use-Relative and Directional

`Preserves_U(B0→B1)` is the primitive; symmetric equivalence is derived only when all required directions hold.

### Valid Reconfiguration != Old-Contract Preservation

A transition can be legitimately readmitted under a new contract without preserving the old contract's semantics.

### Structural Sameness != Operational Preservation != Behavioral Agreement

Implementation/configuration identity and sampled output agreement are neither necessary nor sufficient for OPUR.

### Run Identity != Reconfiguration Substitutability

Same-Run continuation and bounded successor substitution are independent relations.

### Cut Movement != Truth-Owner Transfer

Functional placement/mediation can move without transferring external semantic authority.

### Reconfiguration Cannot Reset Unresolved Realization Standing

Unknown/partial/conflicted realization obligations cross T until admissibly reconciled.

### Evidence Copy != Accountability Preservation

OCSS preservation requires role/currentness/unknown/lineage-aware adoption or rebinding.

### Transition Lineage is Semantically First-Class

Endpoint similarity cannot replace evidence about adoption, revocation, rebinding, supersession and reconciliation carried by T.

### Preservation Composition Requires Obligation Compatibility

Directional preservation edges do not compose by path reachability alone; U obligation identity/scope/currentness and transition assumptions must remain compatible.

These are project-level derived laws, not Foundations.

## 16. Engineering evidence limitation

Current engineering directly supports:

- attempt-bound morphology change;
- Context/profile-set fencing;
- successor Run/loop identity change with exact prior evidence adoption;
- Tool-authority preservation across scheduling morphologies;
- unresolved-effect carryover across morphology;
- non-authoritative internal deliberation;
- fresh-process recovery preserving settled/pending standing;
- absence of uncontrolled live hot-reload surface.

Current engineering does **not** establish general:

- provider replacement preservation;
- locus/Network migration;
- capability internalization/externalization;
- authority expansion/revocation readmission;
- truth-owner replacement;
- general OCSS rebuttal/counterevidence transition preservation;
- bidirectional/cross-implementation equivalence.

These remain conceptual/future evidence/reopen opportunities.

## 17. Foundation-pressure audit

Final classification: `NO_FOUNDATION_PRESSURE`.

OPUR composes existing Cut Relativity, reference, FunctionalPlacement, BoundaryExposure, Context, identity, realization and accountability relations. Directional preservation is a derived synthesis over the existing substrate, not a deletion-essential new primitive Foundation.

## 18. Frontier delta after Campaign 5

Materially deepened:

- Programme A Boundary semantics now has a directional operational preservation theory;
- identity/context/realization/accountability can be treated as explicit preservation dimensions rather than implicit architecture assumptions;
- structural evolution can now be distinguished from semantic preservation and from contract readmission.

Still open:

- **Multi-Agent / Federated Operational Identity** — now substantially more researchable because multiple/split/moved cuts can consume OPUR rather than inventing boundary semantics from scratch;
- cross-implementation invariance;
- real provider/locus/internalization OPUR dogfood;
- real accountability independence/rebuttal dogfood;
- real rich-effect owner dogfood.

Campaign 5 does **not** select Campaign 6.

`NextHarnessResearchCampaign = UNKNOWN` pending a new typed frontier decision.  
`NextHarnessFoundationRoute = UNKNOWN`.

## 19. Campaign 5 closeout

**CAMPAIGN 5 COMPLETE.**

- Project: Harness — Agent Operational Mediation.
- Campaign: Boundary Reconfiguration Equivalence / OPUR.
- Result: P5 revised to directional use-relative P5'; supported in bounded scope.
- Key advance: equivalence demoted; `Preserves_U(B0 --T--> B1)` becomes primitive.
- Additional advance: valid evolution/readmission is distinguished from preservation; Run identity from substitutability; cut movement from truth ownership.
- Dogfood: 10/10 prebound existing fixtures passed.
- General provider/locus/internalization/authority-reauthorization/OCSS-transition proof: explicitly not claimed.
- Owner boundaries: preserved.
- Foundation pressure: none.
- Next campaign: intentionally unknown.
