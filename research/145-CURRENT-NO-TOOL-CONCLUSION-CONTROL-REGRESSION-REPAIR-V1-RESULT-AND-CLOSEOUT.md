# 145 — CURRENT NO-TOOL CONCLUSION-CONTROL REGRESSION REOPEN & REPAIR v1
# Result and Closeout

**Task:** `task:harness-no-tool-conclusion-control-current-regression-repair-v1-20260819`  
**Selection authority:** Tournament 143.  
**Prebound contract + current falsifiers:** `603cf0c9b6a1aa0bbe0d4c26ccaa80a99fb83fc6`.  
**Minimal source repair:** `8925fdba026cdef4f9d8969fae244ee3e5e46730`.  
**Starting canonical:** `ee413f7af20e126656fa03c40e2cde56138c7e4c`.  
**Historical falsifier source:** `6b4cc7724c83061a03fdb85df0003e9b4bff8d26`.

## 1. Classification

`CURRENT_NO_TOOL_CONCLUSION_CONTROL_REPAIR_ACCEPTED`.

The current post-contraction Harness again preserves the authority distinction:

`Harness-native conclusion/control correction != Runtime Tool-history authority`.

The repair required no restoration of `ProviderToolContinuation`, no persistence/schema change, no relaxation of the strict no-Tool bridge and no new authority plane.

## 2. Why this was a real current regression

Tournament 143 reconstructed a nontrivial currentness chain:

1. historical P6 had completed and directly repaired the no-Tool control failure;
2. later Git contraction deliberately removed unearned Provider continuation machinery and also removed the dedicated P6 falsifier file;
3. the ordinary current 437-test baseline remained green;
4. the exact historical seven-test falsifier file still ran against current APIs;
5. running those unchanged tests against current source produced six failures.

Current `tests/test_conclusion_correction_separation.py` still required independent conclusion correction with `maxToolCalls = 0`, so this was not an obsolete historical feature expectation. The contraction had reopened a still-supported authority failure while deleting the direct coverage that would have caught it.

## 3. Prebinding and baseline-red

The current repair contract was frozen before source modification as:

`research/144-CURRENT-NO-TOOL-CONCLUSION-CONTROL-REGRESSION-REPAIR-V1-CONTRACT.md`.

The exact historical P6 seven-test bytes were materialized unchanged as:

`tests/test_current_no_tool_conclusion_control_regression.py`.

Their SHA-256 remained exactly:

`4968d9c391bd5f425e8e45326132b45a45647080616d918f207ee101f7df6147`.

Prebind commit:

`603cf0c9b6a1aa0bbe0d4c26ccaa80a99fb83fc6`.

Frozen baseline-red Runtime Job:

`job-01a01678-29f7-7782-b0c1-113ca765b999`.

Result:

- 7 tests;
- 1 pass;
- 4 assertion failures;
- 2 errors.

The two errors directly reproduced the strict boundary failure:

`ToolBridgeError: no-Tool Agent Run cannot bind Tool observations or Tool Call identities`.

Other failures showed malformed conclusion control stopping as `NO_PROGRESS`, multi-unavailable actions stopping too early as `INVALID_TOOL_CALL`, and conclusion-correction exhaustion losing its independent semantics.

Classification before repair:

`CURRENT_NO_TOOL_CONCLUSION_CONTROL_REGRESSION_REPRODUCED`.

## 4. Causal diagnosis

Historical repair ancestry was used only as causal evidence, not replayed/cherry-picked.

Three historical source commits isolated the original causal logic:

- `0dd31de...` — malformed conclusion control separated before generic Tool handling;
- `e30de1e...` — unavailable no-Tool Provider intent corrected before Runtime Tool history;
- `33593b02...` — turn-level multi-unavailable correction generalized without fake Tool identities.

Current Loop inspection showed those exact pre-classification boundaries were absent, while later cognition/projection/recovery machinery remained intact.

The strict `SQLiteHarnessAgentBridge` check itself was correct: the bug was that invalid/unavailable Provider actions had already entered generic Tool bookkeeping before that check.

## 5. Minimal current-compatible repair

Only:

`src/ordivon_harness/ordivon/loop.py`

changed.

Repair commit:

`8925fdba026cdef4f9d8969fae244ee3e5e46730`.

Source diff:

- 108 insertions;
- 0 deletions;
- no other source file changed.

The two inserted control boundaries are:

### A. malformed Harness conclusion pre-classification

A single normalized `submit_run_conclusion` action carrying an argument error is classified before external-observation/Tool processing.

It:

- consumes `conclusionCorrections`;
- emits bounded model-correctable conclusion feedback;
- records `conclusion_rejected`;
- never earns Runtime Tool identity/observation authority;
- stops deterministically when the conclusion-correction budget is exhausted.

### B. unavailable no-Tool Provider action pre-classification

When the installed Tool bridge exposes an empty Tool definition set and all returned action calls are `unavailable_tool`, the turn is classified before generic Tool execution/history.

It:

- consumes one turn-level Tool correction;
- emits bounded feedback naming unavailable actions;
- records rejection evidence with `physicalDispatch = false` and `seenToolCallIdentity = false`;
- creates no Tool observation/message/history;
- remains bounded by `maxToolCorrections`.

This logic is deliberately narrower than generic continuation state.

## 6. F1–F7 direct acceptance

Focused Runtime Job:

`job-01a01679-acc0-7310-b122-72e5461cf62f`.

Result:

- 7 tests;
- 7 passed;
- 0 failed;
- 0 errors.

Directly accepted:

1. invalid structured conclusion → correction → valid candidate;
2. invalid JSON conclusion → conclusion correction;
3. mixed malformed conclusion + another action remains conflict/non-completion;
4. one unavailable Provider action on no-Tool surface → correction, no Runtime Tool history;
5. multiple unavailable actions on one no-Tool turn → one bounded correction;
6. repeated unavailable turns → deterministic Tool-correction exhaustion without bridge corruption;
7. repeated malformed conclusions → deterministic conclusion-correction exhaustion.

## 7. Current architecture compatibility

Runtime Job:

`job-01a01679-f9f7-7363-866d-1dab27e864df`.

The following current modules ran together:

- `tests.test_conclusion_correction_separation`;
- `tests.test_deepseek_mixed_turn`;
- `tests.test_p0_sqlite_agent_loop`;
- `tests.test_p0_standalone_runner`.

Result:

- 23 tests;
- 23 passed.

Therefore the repair did not:

- collapse Tool vs conclusion correction budgets;
- swallow genuine mixed Tool/conclusion conflict semantics;
- weaken no-Tool bridge composition;
- break durable no-Tool Provider recovery;
- break standalone product recovery/completion.

## 8. Strict no-Tool boundary preserved

Final scope audit Runtime Job:

`job-01a0167c-996f-7d80-b77b-96ab5fcd93db`.

Exact findings:

- `src/ordivon_harness/ordivon/sqlite_agent_bridge.py`: **zero diff** from starting canonical;
- `ProviderToolContinuation` in current `src/tests`: **zero matches**;
- source changed paths: exactly `loop.py`;
- no new persistence schema;
- no new authority plane.

Therefore:

`strict bridge remains the invariant; classification is repaired before the invariant is reached`.

## 9. Repository / release gates

Runtime Job:

`job-01a0167a-51fa-7141-ad79-3a5a96467a1c`.

Passed:

- `git diff --check`;
- documentation contract;
- dependency contract;
- 6 public API tests.

Ruff Runtime Job:

`job-01a0167a-7f2c-78d0-a28c-7238664c4428`.

Result:

`All checks passed!`

No public API was added or removed by the source repair.

## 10. Full acceptance

Runtime Job:

`job-01a0167a-c807-7343-8e40-24d6f08bb6d3`.

Result:

- **444 tests**;
- **OK**;
- **3 skipped**;
- 95.208 seconds.

The pre-repair suite contained 437 tests. The increase to 444 is exactly the seven permanent current regression tests restored by this branch.

This matters: the accepted repair is no longer dependent on manually re-running a historical file from another commit. The falsifier coverage is current product coverage again.

## 11. Currentness law exposed by the repair

This branch adds no new Harness Foundation, but it exposes an important engineering/research currentness law:

> **Green baseline != preserved semantic coverage when a later contraction deletes the falsifier that once proved a boundary.**

More precisely:

`Historical Task Completed != Current Product Property`

when later Git/source contraction materially changes the implementation and removes the direct falsifier.

The correct recovery order is:

`historical owner evidence → later semantic contraction → current source falsification → current re-proof`.

This is currentness/research-method evidence, not a new Harness-native primitive.

## 12. Relationship to historical P6

Historical P6 remains valid evidence for its historical revision. It is not rewritten.

The current proof boundary is now this branch because it validates the post-contraction architecture.

The semantic law agrees with P6, but the current repair does **not** restore the later-deleted `ProviderToolContinuation` machinery. The historical repair was causal guidance; current acceptance stands on current tests and current source.

## 13. Explicit non-results

This repair does not establish or reopen:

- generic Provider continuation/session semantics;
- `ProviderToolContinuation`;
- Campaign 7;
- HaF62;
- OCSS dependency/common-cause relations;
- generic `Preserves_U`;
- locus/internalization OPUR;
- `OperationalClaimUseDisposition`;
- Agent→Agent delegation;
- federation branch/reconciliation;
- cross-implementation invariance.

## 14. Closeout

**CURRENT NO-TOOL CONCLUSION-CONTROL REGRESSION REOPEN & REPAIR v1 COMPLETE.**

Current standing:

- malformed Harness conclusion control separation: **CURRENT DIRECTLY TESTED / ACCEPTED**;
- unavailable Provider action on no-Tool surface: **CURRENT DIRECTLY TESTED / ACCEPTED**;
- strict no-Tool bridge: **PRESERVED**;
- Tool vs conclusion correction budgets: **PRESERVED**;
- mixed Tool/conclusion action conflict: **PRESERVED**;
- `ProviderToolContinuation`: **NOT RESTORED / NOT CURRENT PRODUCT**;
- permanent regression tests: **7 added to current suite**;
- production source change: **one file / two bounded pre-classification blocks**;
- new Foundation: **none**;
- next Harness frontier: **UNKNOWN pending fresh typed tournament**.

Evidence summary:

`evidence/harness-current-no-tool-conclusion-control-repair-v1.json`.
