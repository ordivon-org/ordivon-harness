# 89 — CAMPAIGN 1 ROUND 1
# Conceptual Destructive Reconstruction

**Prebinding authority:** `88-CAMPAIGN1-OPERATIONAL-IDENTITY-UNDER-FAILURE-CHARTER-V1.md` committed before this analysis.  
**Round type:** conceptual / destructive; no current implementation behaviour is used as ontology authority.

## 1. Round 1 result

**Provisional result:** `CRITERION_REVISED`.

P1 survives the central destructive pressure — same-Run recovery is lineage/provenance/control based rather than process/session/snapshot/contract equality — but the prebound evaluator and P1-A are too coarse in two important places:

1. **Recovery projection validity is distinct from Run identity.** A reconstructed state may claim the correct Run lineage yet be an invalid reconstruction because it silently widens authority, rewrites settled history, loses an Invocation obligation or invents a continuation.
2. **Shared ancestry is not same operational identity.** Branch descendants may share an ancestor and provenance while requiring distinct RunEpisode identities. Identity preservation follows an admitted **continuation edge**, not arbitrary reachability in a lineage graph.

No HaF reopen or new-Foundation pressure is produced by these revisions. The existing distinctions among HaF51 Reference, HaF53 Context, HaF57 Selection, HaF58 Result attribution, HaF59 Invocation lineage, HaF60 Run identity and HaF61 ControlFlowState are sufficient to state the stronger criterion.

## 2. Evaluator revision

The prebound two-axis evaluator remains necessary but is not sufficient. Round 1 introduces a third, logically prior axis.

### Axis 0 — Recovery Projection Standing

- `VALID_RECONSTRUCTION`
- `INVALID_RECONSTRUCTION`
- `RECONSTRUCTION_UNDERDETERMINED`

### Axis A — Identity Standing

- `SAME_RUN`
- `NEW_RUN_REQUIRED`
- `IDENTITY_UNKNOWN`

### Axis B — Continuation Standing

- `SAFE_CONTINUE`
- `RECONCILE_FIRST`
- `TERMINAL_UNKNOWN`
- `INSUFFICIENT_EVIDENCE`

These axes are intentionally non-collapsible.

Examples:

- same Run lineage + silent authority gain -> `INVALID_RECONSTRUCTION`; do not force the semantic fiction that the invalid projection became a legitimate new Run;
- same Run + unresolved possibly-effected Invocation -> `VALID_RECONSTRUCTION / SAME_RUN / RECONCILE_FIRST`;
- declared branch from an earlier Run state -> valid branch reconstruction but `NEW_RUN_REQUIRED` for the branch continuation identity;
- missing evidence may yield `RECONSTRUCTION_UNDERDETERMINED / IDENTITY_UNKNOWN / INSUFFICIENT_EVIDENCE`.

## 3. Proposition P1'

Round 1 revises P1 into a three-stage criterion.

### Stage 0 — Reconstruction admissibility

First test whether `S'` is an admissible reconstruction/projection of authoritative prior operational facts. It must not silently widen authority, rewrite settled history, erase required Invocation/result obligations, invent provenance, or expose unsupported continuations.

An invalid reconstruction is rejected before deciding whether a new Run should exist.

### Stage 1 — Run continuation identity

If reconstruction is valid, `S'` is `SAME_RUN` only when it is connected to prior authoritative state by an admitted **Run-continuation edge** preserving the identity-bearing operational commitments required by the continuation relation.

Important refinement:

> `Lineage ancestry != Run identity`.

A branch/replay may preserve exact ancestry and provenance while intentionally creating a new RunEpisode continuation identity.

### Stage 2 — Continuation admissibility

For a valid same-Run reconstruction, determine whether external action may safely continue. Every Invocation crossing the recovery frontier must have sufficient typed standing to avoid unsafe redispatch or false attribution. Unresolved effect status may require reconciliation or terminal uncertainty without changing Run identity.

## 4. Additional continuity invariant — branch/exclusivity discipline

P1' adds an explicit condition absent from P1:

### P1-G — Continuation topology is explicit

A linear Run continuation cannot admit two divergent successor states as the same continuation merely because both descend from one checkpoint. Recovery must provide one of:

- a unique/fenced admitted successor;
- an explicit branch relation producing distinct continuation identities;
- or an `IDENTITY_UNKNOWN` / non-continuable standing until the conflict is resolved.

This is technology-neutral: it does not require a particular lease, CAS or database mechanism, only that the semantic continuation topology not be ambiguous.

## 5. Fixture-by-fixture evaluation

### T1 — process restart, exact durable lineage recovered

Result: `VALID_RECONSTRUCTION / SAME_RUN / SAFE_CONTINUE`, assuming the Invocation frontier contains no unresolved effect obligation.

Pressure: R2 Process/Executor Identity is falsified in scope. Process lifetime is not Run identity.

P1': survives.

### T2 — Provider/model implementation changes

Result: conditionally `SAME_RUN`, not automatically.

If Provider/model identity is merely implementation placement and the operational commitments are preserved through an admitted transition, the Run may continue. If a particular Provider/model identity is itself an immutable admitted commitment of the current attempt, silently changing it makes the reconstruction invalid until an admitted successor attempt/transition exists.

Pressure: RunEpisode identity is coarser than one implementation attempt, but migration cannot rewrite bound commitments.

P1': survives with explicit commitment-relative interpretation.

### T3 — same Run label, authority/exposure silently widened

Result: `INVALID_RECONSTRUCTION`.

The prebound evaluator's `NEW_RUN_REQUIRED`/`IDENTITY_UNKNOWN` options were insufficient. The correct response is first to reject the reconstructed projection. If authoritative prior state can be recovered, the original Run may still be recovered as the same Run under the prior/narrowed authority.

Pressure: R1 Label/Key Identity falsified. Recovery-validity axis required.

### T4 — same Context bytes, different Invocation history

Result: equal Context representation is insufficient. If one reconstruction omits settled Invocation/result facts required for future attribution or dispatch safety, that projection is invalid even though the Context bytes match.

Pressure: R3 Snapshot Equality falsified.

P1': survives.

### T5 — Context reconstructed into different serialization

Result: potentially `VALID_RECONSTRUCTION / SAME_RUN` when exact provenance establishes that the changed representation preserves the required operational commitments and does not change admissible continuation/attribution.

Round boundary: this does not solve general semantic Context Equivalence. It only shows byte/snapshot equality is not necessary.

Pressure: R3 falsified from the opposite direction — equality is neither sufficient nor necessary.

### T6 — Invocation definitely not dispatched

Result: `VALID_RECONSTRUCTION / SAME_RUN / SAFE_CONTINUE` with respect to duplicate-effect risk, provided the pending Invocation/continuation remains otherwise authorized.

A terminal receipt is not logically necessary when authoritative evidence proves non-dispatch.

Pressure: R5 Receipt-Complete Recovery falsified in scope.

### T7 — dispatch recorded, effect may have occurred, receipt lost

Result: `VALID_RECONSTRUCTION / SAME_RUN / RECONCILE_FIRST` when the Run/Invocation lineage is reconstructible.

If exact reconciliation is impossible and redispatch could duplicate an unsafe effect, continuation may become `SAME_RUN / TERMINAL_UNKNOWN`.

Pressure: strongly confirms `Identity != Resumability`. F7 is not triggered after the three-axis revision.

No physical-effect truth is inferred by Harness.

### T8 — external effect/result exactly reconciled after restart

Result: `VALID_RECONSTRUCTION / SAME_RUN / SAFE_CONTINUE` after the reconciled evidence is bound to the original Invocation/result attribution.

Pressure: recovery may cross process failure without replay/redispatch.

R5 is further weakened: terminal evidence may be recovered after the crash rather than pre-existing locally.

### T9 — receipt/result persisted; Context update lost

Result: `SAME_RUN` if the missing Context/WorkingSet transition can be reconstructed from authoritative committed lineage without inventing semantic facts. If reconstruction is not derivable, identity may remain known while continuation is `INSUFFICIENT_EVIDENCE`.

Pressure: current Context persistence and Run identity are separable.

### T10 — two recoveries advance from one checkpoint without branch/fence lineage

Result: P1 requires revision. Shared predecessor is not enough to make both divergent successors the same linear Run continuation.

Round 1 introduces P1-G. Without unique successor/fencing or explicit branch semantics, continuation identity is ambiguous and must not be silently duplicated.

Pressure: major falsifier of the original loose “same lineage anchor” wording; not a falsifier of the revised continuation-edge criterion.

### T11 — explicit authority revocation/reduction in lineage

Result: `VALID_RECONSTRUCTION / SAME_RUN`, with continuation restricted to the reduced authority set.

Authority equality is not an identity invariant; **authority lineage/admission** is the invariant. Recovery may be less permissive than the pre-failure state.

Pressure: supports P1-C/P1-E.

### T12 — silent authority substitution/gain after restart

Result: `INVALID_RECONSTRUCTION`.

This again proves the need for Axis 0. The correct response is not to bless the corrupt state as a “new Run” merely because it differs.

Pressure: R1 and any snapshot/key-only model fail.

### T13 — same immutable contract, different settled result attribution

Result: same contract is insufficient. A reconstruction that assigns a settled result to the wrong Invocation or erases the actual attribution is invalid.

Pressure: R4 Immutable Contract Sufficiency falsified.

The contract may be an identity-bearing commitment of an attempt without being the whole Run identity.

### T14 — declared replay/branch from earlier state

Result: shared ancestry/provenance is preserved, but the branch continuation requires a distinct Run identity unless an explicit higher-level semantics says it is merely an internal substructure of one Run.

For the current RunEpisode referent, default classification is valid branch reconstruction + `NEW_RUN_REQUIRED` for the branch continuation.

Pressure: confirms `Lineage ancestry != Run identity` and P1-G.

## 6. Rival standing after Round 1

| Rival | Round 1 standing | Reason |
|---|---|---|
| R1 Label/Key Identity | FALSIFIED_IN_SCOPE | T3/T12/T10 |
| R2 Process/Executor Identity | FALSIFIED_IN_SCOPE | T1; T2 under admitted migration |
| R3 Snapshot Equality | FALSIFIED_IN_SCOPE | T4 and T5 show neither sufficiency nor necessity |
| R4 Immutable Contract Sufficiency | FALSIFIED_IN_SCOPE | T13; also authority/history divergence |
| R5 Receipt-Complete Recovery | FALSIFIED_IN_SCOPE | T6/T8 |
| R6 Implementation-Defined Identity | STILL LIVE / requires Round 2 | conceptual reconstruction shows a technology-neutral candidate, but cross-implementation/engineering evidence is still useful to test whether the distinctions survive actual mechanisms |

## 7. Derived-law candidates

Round 1 yields two strong derived-law candidates, not new Foundations:

### L-C1 — Recovery Validity != Run Identity != Resumability

A reconstructed state can be invalid while referring to the same historical Run lineage; a valid same-Run state can be temporarily/permanently non-resumable; a new Run can share ancestry/provenance with the old one.

### L-C2 — Lineage Ancestry != Continuation Identity

Shared provenance/ancestor state does not establish same RunEpisode identity. Same-Run continuation requires an admitted continuation relation/topology; explicit branching preserves ancestry while splitting continuation identity.

These laws should remain campaign results until later consolidation decides whether to promote them into `30-DERIVED-LAWS.md`.

## 8. Foundation pressure audit

Current classification: `NO_FOUNDATION_PRESSURE`.

Reason:

- the new third evaluator axis is a composition/analysis distinction over existing Reference/Context/Authority/Invocation/Result/Run/Control structures;
- explicit continuation topology is already expressible through HaF59 Invocation lineage, HaF60 Run identity and HaF61 control/continuation state;
- no coherent deletion-essential Harness-native responsibility outside HaF0–HaF61 has appeared;
- no frozen HaF claim has been concretely falsified in a way requiring reopen.

HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 9. Information-positive Round 2 targets

Execution/engineering dogfood is justified only where it can attack the revised criterion rather than merely demonstrate current implementation.

Highest-value targets:

1. **T6/T7/T8** — non-dispatch, ambiguous effect, and post-crash reconciliation: test identity/resumability separation and no-redispatch obligation.
2. **T9** — persisted result with lost projected cognition update: test reconstruction from authoritative lineage rather than current snapshot equality.
3. **T10** — divergent recovery / fencing: test whether one continuation can be protected from duplicate successor advancement.
4. **R6** — inspect whether the same research distinctions remain visible above current implementation-specific IDs/contracts/schemas.

T3/T12/T13 are already conceptually decisive enough that implementation demonstrations are optional unless they expose a counterexample.

## 10. Round 1 close

`P1 -> P1'` is a substantive revision, not a rejection.

Next step: use the already-prebound fixture set and this revised criterion to design a minimal execution-backed dogfood set. Do not edit current engineering merely to conform to P1'.
