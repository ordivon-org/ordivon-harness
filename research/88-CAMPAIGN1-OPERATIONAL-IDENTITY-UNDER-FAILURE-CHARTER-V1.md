# 88 — CAMPAIGN 1 CHARTER v1
# Operational Identity Under Failure — Run Identity & Recovery Equivalence

**Control task:** `task:harness-campaign1-operational-identity-under-failure-20260818`  
**Programme:** D — Operational Identity & Recovery  
**Standing effect:** programme-level investigation only. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Research question

When an ongoing Harness Run is interrupted and later reconstructed, migrated or resumed, what technology-neutral criterion distinguishes:

- a valid continuation of the **same RunEpisode**;
- a state that requires a **new Run identity**;
- a state whose Run identity may remain continuous but whose external continuation must first **reconcile** unresolved effects;
- a state that must become **terminal/unknown** or remain **insufficiently evidenced**?

The campaign studies Harness operational identity and recovery. It does not define Runtime Job/Attempt identity, physical effect truth, Host Task identity, full Context Equivalence, full Rich Effect Semantics, Multi-Agent identity or the final Accountability Graph.

## 2. Prebound core distinction

Campaign 1 must not collapse these two questions:

1. **Identity Standing:** is reconstructed state `S'` still part of the same RunEpisode lineage as pre-failure state `S`?
2. **Continuation Standing:** given current evidence, what external continuation is safely admissible?

A Run may remain `SAME_RUN` while continuation is blocked pending reconciliation. Conversely, creating a new process or Provider call does not imply `NEW_RUN`.

### Evaluator axis A — Identity Standing

- `SAME_RUN`
- `NEW_RUN_REQUIRED`
- `IDENTITY_UNKNOWN`

### Evaluator axis B — Continuation Standing

- `SAFE_CONTINUE`
- `RECONCILE_FIRST`
- `TERMINAL_UNKNOWN`
- `INSUFFICIENT_EVIDENCE`

The evaluator records both axes. It must not infer one from the other.

## 3. Proposition P1 — Lineage-Preserving Recovery Criterion

A reconstructed state `S'` is a valid same-Run continuation of an authoritative pre-failure state `S` **iff** the available authority/evidence establishes a provenance-preserving operational lineage from `S` to `S'` that satisfies all of the following:

### P1-A — Run-lineage continuity

`S'` remains bound to the same RunEpisode lineage anchor or to an explicitly admitted successor representation of that anchor. Equality of process id, conversation/session label, caller label or implementation object identity is neither necessary nor sufficient.

### P1-B — No established-history rewrite

`S'` does not contradict, erase or silently replace established committed operational facts required for future reasoning: admitted Context/authority transitions, Invocation lineage, persisted results/receipts, and settled control transitions.

Compression or reconstruction is permitted only when the omitted material is not required to distinguish admissible future action or result attribution.

### P1-C — Authority/context lineage is justified, not merely equal

Current authority/exposure and OperationalContextFrame need not be byte-identical to `S`; they may change through admitted, provenance-preserving transitions. A silent gain, substitution or ungrounded replacement breaks valid continuation even when the Run label is unchanged.

### P1-D — Invocation frontier is accounted for

Every Invocation crossing the recovery boundary must have a typed standing sufficient to prevent unsafe redispatch or false attribution. At minimum, recovery must distinguish cases such as:

- definitely not dispatched;
- dispatch/external effect status unresolved;
- externally evidenced effect/result;
- persisted receipt/result already attributable;
- explicitly abandoned/superseded where the governing owner semantics permits it.

Harness need not own physical-effect truth; it must preserve the unresolved obligation to reconcile that truth where continuation depends on it.

### P1-E — Control continuation is provenance-consistent

`S'` exposes only continuations justified by the reconstructed lineage and evidence. Recovery may conservatively reduce the available continuation set. It must not gain a continuation merely because lost state cannot disprove it.

### P1-F — Identity and resumability remain orthogonal

Failure to prove `SAFE_CONTINUE` does not by itself imply `NEW_RUN_REQUIRED`. An unresolved possibly-effected Invocation may leave `IdentityStanding=SAME_RUN` with `ContinuationStanding=RECONCILE_FIRST` or `TERMINAL_UNKNOWN`.

## 4. Rival models

### R1 — Label/Key Identity

Same Run identifier/session/conversation key is sufficient for same-Run recovery.

Predicted failure: false continuity under rewritten authority/context/history or divergent recovery branches.

### R2 — Process/Executor Identity

Run identity is tied to process/executor/provider lifetime; restart or migration creates a new Run.

Predicted failure: false split under exact lineage-preserving reconstruction.

### R3 — Snapshot Equality

A recovered state is valid iff its current serialized Context/control snapshot equals the pre-failure snapshot.

Predicted failure: false split under legitimate provenance-preserving Context changes/reconstruction, and false continuity where equal-looking snapshots hide different Invocation history or authority.

### R4 — Immutable Contract Sufficiency

Binding the same immutable attempt/run contract is sufficient for same-Run continuation.

Predicted failure: same contract can coexist with divergent Invocation/result history, revoked authority or unresolved external effect boundaries.

### R5 — Receipt-Complete Recovery

Same-Run recovery is valid only when every prior external Invocation has a terminal receipt.

Predicted failure: false split or unnecessary terminalization when non-dispatch is proven, when external reconciliation can recover exact standing, or when an Invocation is legitimately pending and continuation is restricted rather than identity-split.

### R6 — Implementation-Defined Identity

No technology-neutral criterion exists; Run identity is whatever the current implementation declares.

Predicted failure: cross-implementation fixtures can preserve the same operational commitments/lineage while changing process/provider/storage representation, demonstrating stable distinctions above implementation.

## 5. Prebound falsifier classes

P1 is weakened, revised or rejected if any fixture establishes one of the following:

### F1 — False continuity

P1 classifies `SAME_RUN` but the reconstructed state can silently authorize an operation, redispatch an effect, misattribute a result or rewrite established history that the pre-failure Run could not validly perform.

### F2 — False split

P1 requires `NEW_RUN_REQUIRED` even though all identity-bearing operational commitments and lineage are preserved and future admissible behaviour/attribution can be reconstructed without semantic discontinuity.

### F3 — Hidden implementation dependence

The criterion requires a specific Python class, SQLite record, process id, Provider protocol or current product schema rather than technology-neutral operational facts.

### F4 — Owner annexation

The criterion can only work by making Harness decide Runtime physical-effect truth, Host Task identity/completion, Normative legitimacy, Network reachability truth or domain causal truth.

### F5 — Context-theory explosion

Same-Run recovery cannot be evaluated without first solving full Context Equivalence rather than using bounded explicit Context differences/lineage facts.

### F6 — Effect-theory explosion

Same-Run recovery cannot be evaluated without first solving general physical/causal Effect Semantics rather than consuming typed external effect-evidence status.

### F7 — Identity/resumability collapse

The criterion cannot represent a same-Run state that is temporarily or permanently unsafe to continue.

## 6. Destructive fixture matrix

The following fixtures are prebound before conceptual or execution-backed evaluation.

| Fixture | Change/failure | Primary pressure |
|---|---|---|
| T1 | process restart, exact durable lineage recovered | reject process-identity model / false split |
| T2 | Provider/model implementation changes, operational commitments preserved | technology-neutral identity |
| T3 | same Run label but authority/exposure silently widened | false continuity |
| T4 | same current Context bytes but Invocation history differs | snapshot-equality failure |
| T5 | Context reconstructed from exact provenance into different serialization | identity vs Context representation |
| T6 | Invocation definitely not dispatched before crash | safe continuation without terminal receipt |
| T7 | dispatch recorded; physical effect may have occurred; receipt lost | identity/resumability separation; reconciliation barrier |
| T8 | external effect/result is exactly reconciled after restart | recovery without redispatch |
| T9 | receipt/result persisted; WorkingSet/Context update lost | history-derived reconstruction |
| T10 | two recoveries from one checkpoint both advance without branch/fence lineage | divergent identity / false continuity |
| T11 | explicit authority revocation/reduction occurs during Run and is durably in lineage | identity-preserving capability reduction |
| T12 | authority substitution/gain appears only after restart with no admitted lineage | invalid continuation |
| T13 | same immutable contract, different settled result attribution | contract-sufficiency failure |
| T14 | replay/branch intentionally forks from earlier state with declared branch lineage | same ancestor does not imply same Run continuation |

## 7. Prebound expected evaluator tendencies

These are **predictions**, not results; conceptual/destructive analysis may falsify them.

- T1 -> likely `SAME_RUN / SAFE_CONTINUE` if no unresolved Invocation frontier exists.
- T2 -> likely `SAME_RUN` if model/provider identity is not itself an immutable semantic commitment of the Run; otherwise explicit admitted migration is required.
- T3 -> not valid same-Run continuation as reconstructed; likely `IDENTITY_UNKNOWN` or `NEW_RUN_REQUIRED` depending whether authoritative prior state can be recovered.
- T4 -> equal Context snapshot is insufficient; classification depends on Invocation/authority lineage.
- T5 -> potentially `SAME_RUN` if semantic/provenance commitments and continuation behaviour are preserved.
- T6 -> potentially `SAME_RUN / SAFE_CONTINUE` with a fresh Invocation because non-dispatch is established.
- T7 -> potentially `SAME_RUN / RECONCILE_FIRST`; if reconciliation is impossible and duplicate effect is unsafe, `SAME_RUN / TERMINAL_UNKNOWN` is admissible.
- T8 -> likely `SAME_RUN / SAFE_CONTINUE` after exact reconciliation and attribution.
- T9 -> likely `SAME_RUN` if Context/WorkingSet state is mechanically reconstructible from committed lineage without inventing facts.
- T10 -> both branches cannot silently claim one linear continuation identity; explicit branch/new Run identity or fencing is required.
- T11 -> likely `SAME_RUN` with reduced continuation authority when revocation is an admitted external/authority transition.
- T12 -> invalid continuation; silent authority gain cannot be justified by recovery uncertainty.
- T13 -> same contract alone is insufficient.
- T14 -> branch lineage preserves ancestry/provenance but does not make both branches the same continuation RunEpisode.

## 8. Evaluation method

### Round 1 — Conceptual destructive reconstruction

Apply P1 and R1–R6 to T1–T14 without current implementation as authority. Record contradictions, missing distinctions and cases whose classification is underdetermined.

### Round 2 — Engineering dogfood only where information-positive

Use current Ordivon Harness / Runtime evidence only for fixtures where implementation can expose a genuine falsifier or ambiguity, especially T6–T10. Execution success is physical evidence only; research evaluation remains separate.

### Round 3 — Cross-owner boundary audit

Verify that surviving criterion does not annex Runtime effect truth, Host Task continuity, Normative legitimacy or other external owner truth.

### Round 4 — Closeout

Classify result as one of:

- `CRITERION_SUPPORTED_IN_SCOPE`
- `CRITERION_REVISED`
- `CRITERION_FALSIFIED`
- `INSUFFICIENT_EVIDENCE`

Separately classify Foundation pressure:

- `NO_FOUNDATION_PRESSURE`
- `FOUNDATION_REOPEN_PRESSURE` with exact HaF claim/falsifier
- `NEW_FOUNDATION_PRESSURE` only if a coherent deletion-essential Harness-native responsibility is found.

No Foundation standing changes automatically.

## 9. Stop conditions

Stop and return a bounded result rather than expanding scope when:

- the next question requires full Context Equivalence;
- the next question requires a general physical/causal Effect ontology;
- Multi-Agent/federated identity becomes necessary rather than a later extension;
- accountability-graph design becomes the main problem;
- current implementation lacks an information-positive fixture;
- the evidence supports a local criterion but not necessity/sufficiency claims.

## 10. Engineering non-authority rule

Current Ordivon Harness concepts such as immutable HarnessRunContract, WorkingSet/WorkingView, snapshots, Tool intent/dispatch fence/receipt, Runtime reconciliation, Run Receipt and CompletionProposal are candidate dogfood surfaces only. The theory must be expressible without those concrete class/schema names.

## 11. Immediate next step

With this Charter committed as prebinding, run Round 1 conceptual destructive reconstruction over T1–T14. Do not modify current engineering to fit P1 during Round 1.
