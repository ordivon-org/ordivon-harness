# 139 — CAMPAIGN-3 REAL RICH-EFFECT OWNER DOGFOOD v1
# Result and Closeout

**Task:** `task:harness-campaign3-rich-effect-owner-dogfood-v1-20260819`  
**Prebound contract:** `138-CAMPAIGN3-REAL-RICH-EFFECT-OWNER-DOGFOOD-V1-CONTRACT.md` committed before direct owner evidence at `786d64a7cfb21d52e9e541331c3db67a9edd4f29`.  
**Historical Campaign-3 closeout:** 104 remains authoritative for its original closeout revision.  
**Production source modification:** none.

## 1. Classification

`CAMPAIGN3_RICH_EFFECT_DIRECT_SUPPORT_IN_SCOPE`.

All four prebound owner-native cases passed the mechanical validator against current public Harness Claim Standing without production modification, a scalar Effect state, a generic Effect graph, a global registry, or mutable claim truth.

This branch upgrades the current evidence standing for Campaign 3's previously conceptual-only rich-effect cases. It does not rewrite the historical Campaign-3 closeout and does not create Campaign 7.

## 2. Exact evidence

Research capture:

- `evidence/harness-campaign3-rich-effect-owner-v1-capture.json`;
- capture canonical digest reported by the prebound validator: `sha256:5b0a0d01ab17734c05bc87752e462c36e8b5a646d88166e433736a54eacd1a94`.

Validator result:

- `evidence/harness-campaign3-rich-effect-owner-v1-result.json`;
- classification: `CAMPAIGN3_RICH_EFFECT_DIRECT_SUPPORT_IN_SCOPE`;
- validation Job: `job-01a01653-ab03-7843-a2e2-5a08624077c1`.

Full current Harness baseline after research-only materialization:

- Runtime Job `job-01a01654-11db-78f1-8438-b60c8ffad737`;
- `437` tests;
- `OK`;
- `3` skipped.

## 3. RED1 — partial multi-step realization

Runtime owner Job:

`job-01a01652-050f-7f03-8f89-29f3024122ab`.

Observed owner facts:

- overall Job terminal status = `failed`;
- `completedSteps = 1`;
- `failedStepId = effect-2`;
- exit code = `7`;
- terminal evidence digest = `sha256:b33deb0c49b5dc49f9670ea564514b421fe60855f4ef20eac9bff0225fb8db23`;
- step-1 file still exists with exact bytes `step1\n`;
- step-1 digest = `sha256:674727562efe74444161457767ce2a69571d5f7fa4ddf1e7a7fa273304c56d1c`.

The validator projected two explicit Q rather than one scalar Effect status:

- `Q_partial_prefix` → `SUPPORTED`;
- `Q_partial_whole` → `CONTRADICTED`.

This is direct support for **Partial Realization is Scoped Mixed Claim Standing**. One real Runtime composite operation can be terminally failed while a realized prefix remains physically observable. No `PARTIAL` enum or completion fraction is needed.

## 4. RED2 — delayed realization evidence

Runtime owner Job:

`job-01a01652-37d4-7132-a922-a78bb9a43838`.

Pre-boundary observation:

- Job = `working`;
- delivery = `in_progress`;
- target path read failed with `WORKSPACE_PATH_NOT_FOUND`;
- path-read commit state = `not_committed`.

Later observation of the same Job:

- Job = `succeeded`;
- terminal evidence digest = `sha256:84d40112646414196a177969f084a346cc6985e6a95cdb1bf3231a4c9665195b`;
- exact output = `arrived-v1\n`;
- output digest = `sha256:c7b7e98da9da475f7ad2d974a2763214bc73a3d1009cf4022028c4a889bd3a29`.

The same Q was projected as generation 1 `UNDERDETERMINED` and generation 2 `SUPPORTED`; the generation-1 StandingView digest remained unchanged.

This directly supports the bounded form of **No earlier realization evidence != Q false; later evidence updates current standing without rewriting prior uncertainty.** Evidence limit: this crosses a real nonterminal observation boundary, not a proven terminal Harness-Run boundary.

## 5. RED3 — interfering competing mutations

Runtime Workspace: `harness-c3-rich-effect-owner-effects-20260819`.

Initial state was `A\n` at digest `sha256:06f961b802bc46ee168555f066d28f4f0e9afdf3f88174c1ee6f9de004fc30a0`.

M1:

- client request `harness-c3-red3-m1-a-to-b-20260819-v1`;
- operation `patch-01a01652-b0bf-7192-9143-60efa28940b2`;
- request digest `sha256:7876a1b05c55f76c970088efe4b019ac5d3805248a55d8943b935bed0e587f25`;
- committed `A -> B`;
- after digest `sha256:c0cde77fa8fef97d476c10aad3d2d54fcc2f336140d073651c2dcccf1e379fd6`.

M2:

- client request `harness-c3-red3-m2-stale-a-to-c-20260819-v1`;
- still bound the old A digest;
- Runtime rejected it with `REVISION_MISMATCH`;
- `commitState = not_committed`;
- current bytes remained `B\n`.

Claim projections were Q(M1 committed A->B) = `SUPPORTED` and Q(M2 committed stale A->C) = `CONTRADICTED`.

This supplies direct owner-native interference/currentness pressure without pretending that Harness owns a universal causal-interaction graph.

## 6. RED4 — compensation/restoration without erasure

M3:

- client request `harness-c3-red4-m3-b-to-a-20260819-v1`;
- operation `patch-01a01652-fdcd-74b0-8068-3beb87cf485e`;
- request digest `sha256:d743c98bef1c680a54cc0215364d89e9033f44ef873c382aaca6d753eb829cd2`;
- committed `B -> A`.

Final content returned to `A\n` and the exact original digest `sha256:06f961b802bc46ee168555f066d28f4f0e9afdf3f88174c1ee6f9de004fc30a0`.

After M3, `workspace.patch.get` for M1 still returned operation `patch-01a01652-b0bf-7192-9143-60efa28940b2` with state `committed`. M1 and M3 retained distinct operation/request identities.

Claim projections simultaneously supported Q(original A->B realized) and Q(current state restored to A after M3); the original Q StandingView digest remained unchanged.

This is direct support for **Compensation != Prior Effect Erasure** and the compact empirical corollary **Same Final Bytes != Same Operational History**.

## 7. Acceptance gates

All ten prebound gates passed:

- partial mixed claim standing = true;
- no scalar partial status = true;
- delayed underdetermined then supported = true;
- prior delayed view immutable = true;
- stale competing mutation contradicted = true;
- compensation restores current bytes = true;
- prior committed operation history preserved = true;
- same final bytes do not collapse history = true;
- Claim Standing production modification required = false;
- global Claim/Effect registry required = false.

No direct falsifier fired. No `CAMPAIGN3_RICH_EFFECT_MATERIALIZATION_GAP` was found.

## 8. Campaign-3 currentness update

Historical closeout 104 remains correct at its own revision: `PARTIAL_DELAYED_COMPENSATING_INTERFERING_CASES_CONCEPTUAL_ONLY`.

Current evidence standing is now more specific:

- partial multi-step realization: **BOUNDED DIRECT SUPPORT**;
- delayed owner realization evidence across nonterminal observation boundary: **BOUNDED DIRECT SUPPORT**;
- exact CAS/currentness interference: **BOUNDED DIRECT SUPPORT**;
- compensation/restoration without prior-history erasure: **BOUNDED DIRECT SUPPORT**.

Still not directly established: arbitrary world-effect partiality; delayed effects after every relevant terminality boundary; general causal interaction/composition across owners; general idempotency/retry semantics; normative remedy sufficiency; cross-implementation invariance.

## 9. Claim Standing evaluation

Current Claim Standing proved sufficient for the bounded representational pressure: separate explicit Q, mixed support/contradiction, required unknown for an earlier unresolved view, immutable later generations, and simultaneous support for original-operation/current-restored-state claims.

No global claim registry or mutable effect state was needed. The generic value layer therefore survived a qualitatively richer physical owner surface than E5-v2/rebuttal dogfood.

## 10. OperationalClaimUseDisposition standing

This branch does **not** create deletion-essential implementation pressure for `OperationalClaimUseDisposition`.

RED1–RED4 directly test evidence-relative Q standing and history preservation. None contains a real downstream consumer that must make a bounded retry/continue/settle decision from a Q set. Implementing generic settlement/use-disposition now would still be anticipatory/symmetry-driven.

The future trigger is sharper: if a real consumer must decide retry/continuation/admission from RED1-style mixed Q, RED2 currentness-changing evidence, RED3 rejected competing operation, or RED4 endpoint-equal/non-equivalent history, use-relative settlement becomes directly testable.

Current standing: `research-approved / unimplemented / NOT deletion-essential`.

## 11. Owner-boundary audit

**PASS.** Runtime remained owner of execution state, step completion/failure, Workspace bytes/digests, Patch commit/currentness and durable Patch receipt state. Harness did not claim arbitrary world causality or domain success. The capture is a digest-bound research projection of Runtime observations, not an alternative physical truth authority.

## 12. Foundation / theory pressure

`NO_FOUNDATION_PRESSURE`.

No Campaign-3 law required revision. No new Foundation responsibility appeared. HaF0–HaF61 remain frozen; HaF62 remains UNKNOWN / NOT SELECTED / NOT ADMITTED. Campaign 7 is not selected by this result.

## 13. Closeout

**CAMPAIGN-3 REAL RICH-EFFECT OWNER DOGFOOD v1 COMPLETE.**

- Campaign 3 theory: historical closeout remains closed;
- rich partial/delayed/interfering/compensating owner evidence: upgraded to bounded direct support in the exact tested scopes;
- Claim Standing: survived all four direct rich-effect cases without production change;
- materialization gap: none;
- `OperationalClaimUseDisposition`: still optional/unimplemented;
- generic Effect engine/graph/registry: not required;
- new Foundation: none;
- next Harness frontier: intentionally UNKNOWN pending a fresh typed tournament.
