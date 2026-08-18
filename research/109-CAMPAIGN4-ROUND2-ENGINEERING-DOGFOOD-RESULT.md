# 109 — CAMPAIGN 4 ROUND 2
# Engineering Dogfood Result

**Prebound contract:** `108-CAMPAIGN4-ROUND2-ENGINEERING-DOGFOOD-CONTRACT.md` at commit `f4b6d3d` before execution.  
**Runtime Job:** `job-01a015b3-b97b-74d2-a502-efddb118cb75`.  
**Mechanical result:** repository-canonical `uv run`; 13 selected existing tests; 13/13 PASS in 0.822s.

## 1. Round-level classification

`ENGINEERING_SUPPORT_IN_SCOPE`.

The selected fixtures directly support P4'/OCSS for exact binding, evidence visibility/admission, proposal-role typing, unresolved-unknown preservation, restart inspectability and conservative telemetry projection. They do not establish general common-cause independence, rebuttal semantics, support-cycle handling or cross-owner support composition.

## 2. D1 — prior-attempt evidence compound binding

Mechanical result: PASS.

Implementation fact: prior-attempt evidence round-trips only with its exact compiled attempt/manifest/contract/receipt structure.

Technology-neutral interpretation:

> evidence identity/support basis is exact-lineage bound, not a loose label or artifact name.

P4' pressure: `SUPPORT` for exact attribution/binding.

## 3. D2 — changed mandate rejects old receipt

Mechanical result: PASS.

Implementation fact: mandate ID can remain the same while digest changes; prior receipt then cannot be reused for derived consumption.

Technology-neutral interpretation:

> same semantic-looking name != same accountability use/claim contract.

P4' pressure: strong `SUPPORT` for P4'-J and against binding blindness.

## 4. D3 — malformed evidence/accounting fails closed

Mechanical result: PASS.

Implementation fact: changed contract digest, manifest digest or incomplete usage evidence is rejected rather than silently accepted.

Technology-neutral interpretation:

> an evidence artifact cannot support the advertised operational claim when its required binding/accounting structure is internally inconsistent.

P4' pressure: `SUPPORT` for Evidence Admission + exact support obligations.

## 5. D4 — invisible receipt cannot be adopted

Mechanical result: PASS.

Implementation fact: a well-formed invented receipt reference that is not exact prior evidence in the current selection Context is rejected.

Technology-neutral interpretation:

> syntactic reference existence != admitted support path.

P4' pressure: strong `SUPPORT` for evidence admission/visibility and Campaign-2 composition.

## 6. D5 — CompletionProposal is exact evidence and preserves unknowns

Mechanical result: PASS.

Implementation fact:

- CompletionProposal is digest-bound to exact prior-attempt evidence;
- unresolved unknowns remain encoded in the proposal and later selection Context.

Technology-neutral interpretation:

> positive proposal evidence and unresolved unknowns coexist; accountable completion proposal cannot erase its known limits.

P4' pressure: strong `SUPPORT` for first-class unknowns and proposal-role typing.

## 7. D6 — CompletionProposal receipt mismatch fails

Mechanical result: PASS.

Implementation fact: proposal with mismatched run-receipt digest is rejected.

Technology-neutral interpretation:

> support role depends on exact receipt lineage, not proposal shape/text.

P4' pressure: `SUPPORT` for exact attribution/binding.

## 8. D7 — noncompleted attempt cannot carry CompletionProposal

Mechanical result: PASS.

Implementation fact: a proposal-shaped artifact cannot be attached to a non-completed attempt even when its digests are mechanically rewritten.

Technology-neutral interpretation:

> evidence roles are lifecycle/claim typed; structure alone cannot manufacture semantic standing.

P4' pressure: strong `SUPPORT` against R5/R8-style role collapse.

## 9. D8 — independent strategy evidence is immutable/digest-bound

Mechanical result: PASS.

Implementation fact: later mutation of source Python data does not change the captured evidence snapshot; wrong digest fails closed.

Technology-neutral interpretation:

> adopted evidence is an exact bounded snapshot, not a live mutable assertion.

P4' pressure: `SUPPORT` for evidence admission/reproduction integrity.

Limit: the implementation class name `independent` is **not** treated as proof of universal causal/statistical independence.

## 10. D9 — evidence-role alias conflict rejected

Mechanical result: PASS.

Implementation fact: strategy evidence cannot reuse a reference already occupied by prior-attempt evidence with different role semantics.

Technology-neutral interpretation:

> evidence identity and evidence role must not be silently aliased across incompatible support semantics.

P4' pressure: `SUPPORT` for typed bearing/role structure.

## 11. D10 — candidate completion preserves unresolved unknowns

Mechanical result: PASS.

Implementation fact: candidate-completed Run preserves unresolved unknowns in both conclusion and CompletionProposal.

Technology-neutral interpretation:

> completion-like operational standing does not justify suppressing known uncertainty.

P4' pressure: very strong `SUPPORT` for P4'-G.

## 12. D11 — terminal candidate completion is restart-inspectable

Mechanical result: PASS.

Implementation fact:

- terminal receipt binds exact contract and trace digest;
- CompletionProposal binds the run receipt;
- after restart the terminal result remains inspectable by exact receipt identity.

Technology-neutral interpretation:

> bounded accountability/reproduction can mean durable re-inspection of exact support objects across process restart, not identical world/model replay.

P4' pressure: `SUPPORT` for exact attribution and bounded reproduction.

## 13. D12 — telemetry preserves unavailable fields/unknowns

Mechanical result: PASS.

Implementation fact: absent provider cache evidence remains explicitly unavailable; unknown provider outcome remains represented as an unresolved continuity condition.

Technology-neutral interpretation:

> derived accountability projection must preserve evidence absence/unknown standing rather than fill missing facts.

P4' pressure: strong `SUPPORT` for unknown preservation.

## 14. D13 — terminal telemetry limits semantic interpretation

Mechanical result: PASS.

Implementation fact: derived telemetry projects exact Run receipt evidence and explicitly states that Harness completion does not imply domain semantic completion.

Technology-neutral interpretation:

> evidence projection can be useful/derived while retaining a hard claim-scope boundary.

P4' pressure: strong `SUPPORT` against Receipt Equals Proof / CompletionProposal Equals Completion.

## 15. Engineering boundary

Current engineering strongly supports OCSS in these dimensions:

- exact evidence/claim binding;
- changed-contract rejection;
- evidence visibility/admission;
- lifecycle-typed proposal role;
- immutable evidence snapshots;
- evidence-role collision rejection;
- unresolved-unknown preservation;
- restart inspectability;
- conservative derived projection.

Current engineering does **not** directly establish:

- causal/common-cause independence criteria;
- general corroboration composition;
- rebuttal/counterevidence revision semantics;
- arbitrary support-cycle rejection in a general graph engine;
- cross-owner claim-support composition;
- cross-implementation bounded reproduction.

Those remain conceptual/future evidence frontiers.

## 16. Cross-implementation standing

The same high-level distinctions recur across strategy selection, prior-attempt evidence, CompletionProposal, standalone Run recording and telemetry projection. This weakens implementation-object-specific rivals but remains one Ordivon Harness implementation family.

Universal invariance is not established.

## 17. Foundation pressure

`NO_FOUNDATION_PRESSURE` remains.

The dogfood supports relational laws over existing evidence/provenance/Result/Invocation/explanation/contestability/assurance substrate. No deletion-essential new Harness-native responsibility appears.

## 18. Next step

Run Round 3 owner-boundary + Campaign-1/2/3 compatibility audit. If P4' survives, close Campaign 4 while explicitly preserving the evidence gap for independence/counterevidence/cycles/cross-owner composition.
