# 138 — CAMPAIGN-3 REAL RICH-EFFECT OWNER DOGFOOD v1

**Branch role:** post-closeout direct empirical evidence for Campaign 3.  
**Starting authority:** Typed Frontier Tournament v2 at `cac41f9f4f02521ad309c8736eebf059e631e36b`.  
**Historical Campaign-3 authority:** closeout 104 remains closed and is not rewritten.  
**Foundation effect:** none. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED.

## 1. Question

Can the already-admitted Campaign-3 claim-relative realization model and current public Claim Standing surface survive **real Runtime-owner physical trajectories** for:

1. partial multi-step realization;
2. delayed owner realization evidence across a local observation boundary;
3. interfering competing mutations;
4. later compensation/restoration;

without adding a scalar Effect Status, generic Effect graph, global registry, owner-truth inference or fixture-owned physical semantics?

## 2. Truth boundary

Runtime owns the physical/mechanical facts used by this branch:

- Job/Attempt execution state;
- ordered step completion/failure;
- Workspace file bytes/digests;
- digest/currentness rejection of Workspace mutations;
- durable Patch receipts and their committed state.

Harness owns only mediation/value-layer behavior exercised here:

- exact bounded `OperationalClaimRef` identity;
- local evidence-role admission supplied by this research contract;
- immutable `OperationalClaimStandingView` projection;
- preservation of distinct Q and historical views.

The experiment MUST NOT infer arbitrary domain success, causal sufficiency, normative remedy, retry safety, or external-world finality.

## 3. Evidence capture rule

The dogfood uses `research/experiments/campaign3_rich_effect_owner_v1.py` against one JSON capture containing exact observations returned by Runtime tools.

The capture is a research projection of Runtime responses, not a competing physical truth owner. The experiment must mechanically validate the captured predicates before using them as evidence.

A case is invalid if its required Runtime predicate is merely asserted by a semantic label rather than recoverable from concrete fields such as:

- `status`;
- `completedSteps`;
- `failedStepId`;
- exact content/digest;
- patch `state`;
- exact rejection code/commit state.

## 4. RED1 — partial multi-step realization

### Runtime construction

Run one ordered two-step Runtime `workspace.execPlan`:

- step `effect-1` creates a named file with exact bytes;
- step `effect-2` exits non-zero;
- default stop-on-failure remains active.

### Required owner facts

- overall Job is terminal `failed`;
- `completedSteps == 1`;
- `failedStepId == "effect-2"`;
- the step-1 file is still present after terminal failure with an exact digest.

### Bounded claims

- `Q_partial_prefix`: step `effect-1` realized its exact file mutation;
- `Q_partial_whole`: both planned steps completed successfully.

### Expected standing

- `Q_partial_prefix = SUPPORTED` from the exact Runtime owner-fact capture;
- `Q_partial_whole = CONTRADICTED` from the exact same owner-fact capture under a different claim/use role.

### Destructive point

The same composite Job may support one scoped realization claim while contradicting a broader whole-plan-success claim.

No `PARTIAL` scalar is permitted.

## 5. RED2 — delayed realization evidence

### Runtime construction

Admit one Runtime Job whose command intentionally waits before creating a named file.

Observe the Job before terminality and attempt to read the target path during that nonterminal interval. Then observe the same Job to terminality and read the path again.

### Required owner facts

Pre-boundary:

- Job projects `working` / `in_progress`;
- target path is not yet present.

Post-boundary:

- the same Job becomes terminal `succeeded`;
- target path exists with exact bytes/digest.

### Bounded claim

`Q_delayed_output`: the delayed output file has been realized.

### Expected standing

- generation 1 = `UNDERDETERMINED`, carrying a `required_unknown` bound to the nonterminal/pre-output owner facts;
- generation 2 = `SUPPORTED`, carrying later exact terminal/output owner evidence;
- generation-1 view remains byte-for-byte/digest stable after generation 2 exists.

### Destructive point

An earlier local observation boundary with no realization evidence must not become Q-false. Later owner evidence may support Q without rewriting the earlier underdetermined view.

This branch does **not** claim delayed realization after a terminal Harness Run unless such a relation is directly present; it tests delayed owner evidence across the actual nonterminal observation boundary provided by Runtime.

## 6. RED3 — interfering competing effects

### Runtime construction

Start from one exact file state `A` and digest `D_A`.

- mutation M1 binds `D_A` and commits `A -> B`;
- mutation M2 independently binds the stale `D_A` and attempts `A -> C` after M1;
- Runtime must reject M2 on exact currentness/CAS grounds before commit.

### Required owner facts

- M1 has a committed Patch receipt;
- current file digest after M1 equals M1 `afterDigest`;
- M2 is rejected with Runtime currentness/revision mismatch semantics and `commitState = not_committed` (or an exact equivalent owner rejection proving no mutation commit);
- current bytes remain B after M2 rejection.

### Bounded claims

- `Q_interfere_m1`: M1 committed its A->B mutation;
- `Q_interfere_m2`: M2 committed its A->C mutation.

### Expected standing

- `Q_interfere_m1 = SUPPORTED`;
- `Q_interfere_m2 = CONTRADICTED`.

### Destructive point

The branch tests a real competing-effect/currentness conflict. It does not infer general causal interaction beyond the exact owner-defined mutation/CAS semantics.

No generic `INTERFERING` relation is added.

## 7. RED4 — compensation/restoration without erasure

### Runtime construction

Continue from RED3 after M1 committed A->B.

- mutation M3 binds exact current B digest and commits `B -> A`;
- read current bytes/digest;
- re-read M1's durable Patch receipt by its original `clientRequestId`.

### Required owner facts

- M3 is committed;
- final bytes/digest equal original A state/digest;
- M1's original receipt still exists and remains `committed`;
- M1 and M3 retain distinct operation/request identities.

### Bounded claims

- `Q_original_change`: M1 realized A->B;
- `Q_current_restored`: current file state is restored to A after M3.

### Expected standing

Both claims are `SUPPORTED` simultaneously.

The pre-compensation `Q_original_change` StandingView digest must remain unchanged after M3 and the restored-current-state view are created.

### Destructive point

`same final bytes != same operational history`.

A later restoring operation may support a current-state claim without converting the earlier realized operation into “never happened”.

## 8. Cross-case acceptance gates

The branch is accepted as `CAMPAIGN3_RICH_EFFECT_DIRECT_SUPPORT_IN_SCOPE` only if all of the following hold:

1. all four Runtime constructions use actual Runtime owner operations, not mock physical effects;
2. RED1 proves mixed scoped standing without a scalar partial state;
3. RED2 proves underdetermined -> later supported via immutable StandingView generations;
4. RED3 proves exact competing mutation/currentness rejection without a generic causal graph;
5. RED4 proves restoration of current bytes while prior committed operation evidence/history remains;
6. all Q identities remain explicit and distinct;
7. Claim Standing uses only already-admitted evidence roles and requires no production modification;
8. no global Claim/Effect registry or mutable status exists;
9. no result is promoted to domain semantic success, retry safety, normative correctness or universal external causality;
10. the current Harness production test baseline remains healthy after research-only materialization.

## 9. Direct falsifiers

Classify `CAMPAIGN3_RICH_EFFECT_DIRECT_FALSIFIER_FOUND` if any prebound Runtime trajectory directly contradicts a Campaign-3 law, including:

- overall failed multi-step execution forces the realized prefix to disappear or become unrepresentable;
- partiality cannot be represented without adding one scalar Effect state;
- the earlier delayed view must be rewritten/mutated when later evidence arrives;
- a stale competing mutation silently commits over changed state;
- later restoration deletes or invalidates the earlier committed operation receipt/history;
- current-state equality necessarily collapses distinct operational histories;
- Claim Standing cannot represent the bounded Q set without global mutable claim truth.

## 10. Materialization-gap stop rule

Classify `CAMPAIGN3_RICH_EFFECT_MATERIALIZATION_GAP` and STOP before production modification if the owner facts are valid but the current Harness public surfaces cannot express one of the prebound claim-relative cases without adding:

- a generic Effect engine;
- generic dependency/causal graph;
- global claim/effect registry;
- mutable Q/effect status;
- a new owner-truth lookup service.

A gap does not authorize implementation in this branch.

## 11. Evidence-limit classifications

Use narrower classifications when appropriate:

- `RED1_DIRECT_SUPPORT_ONLY`;
- `RED2_DIRECT_SUPPORT_ONLY`;
- `RED3_DIRECT_SUPPORT_ONLY`;
- `RED4_DIRECT_SUPPORT_ONLY`;
- `RUNTIME_OWNER_FACT_CAPTURE_INVALID`;
- `OWNER_BOUNDARY_VIOLATION`;
- `CLAIM_STANDING_PROJECTION_MISMATCH`.

## 12. Explicit non-claims

This branch does not establish:

- arbitrary physical causality;
- delayed effects beyond every local/remote terminality boundary;
- universal distributed interference semantics;
- universal compensation/remedy semantics;
- idempotency/retry safety;
- cross-owner causal composition;
- cross-implementation invariance;
- Campaign 7;
- HaF62.

## 13. Execution order

1. Commit this contract and the mechanical validator before creating the direct owner evidence.
2. Run RED1–RED4 in a disposable isolated Runtime Workspace.
3. Materialize the exact owner-fact capture.
4. Run the prebound validator against that capture using the public Harness Claim Standing API.
5. Run focused/full Harness tests as appropriate.
6. Write result/closeout without rewriting Campaign-3 historical closeout.
7. Update Host continuity and rerun a typed frontier tournament before selecting any subsequent branch.
